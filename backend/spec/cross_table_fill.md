# 跨表数据填充模块规格（v0.6.0）

> 适配规格：SparkMemo v0.6.0
> 适用范围：单用户本地版，无登录。
> **数据库可移植性约束**：所有日期字段统一使用 10 字符字符串 `YYYY-MM-DD`；不依赖任何数据库内置日期函数（沿用既有项目约定，详见 `task_management.md` §约束）。

> **v0.6.0 首次发布**：
> 1. 新增独立模块「**跨表数据填充**」（`Cross-Table Fill`，简称 CTF）。提供 VLOOKUP/XLOOKUP 风格的图形化匹配能力：用户上传两张 Excel（目标表 / 基础表），选定主键字段，勾选映射列，后端按主键将基础表对应行的字段值回填到目标表的新列（或覆盖原列）。
> 2. 前端入口：路由 `/cross-table-fill`，对应 `views/CrossTableFill.vue`（spec 在 `frontend/spec/cross_table_fill.md`）。
> 3. 后端 API 端点挂在 `/api/cross-table-fill` 下；与「周需求管理」「透视查询」平级。
> 4. 数据模型采用**三张新表**：`cross_table_fill_jobs`（任务元数据）+ `cross_table_fill_rows`（双表数据 + JSON 存储）+ `cross_table_fill_configs`（唯一约束的匹配配置）。详见 §数据模型。
> 5. 默认 join 语义为 **left join**（VLOOKUP 语义）；base 同一主键有多个匹配行时**合并**为 `;` 分隔字符串并**计入多匹配计数**；映射目标列与 target 现有列同名时由用户在 UI 显式选择 `overwrite` / `new_column`；执行结果**双轨交付**（前 1000 行预览 + xlsx 下载）。详见 §匹配算法 与 §API 章节。
> 6. 不涉及登录 / 不涉及多用户；不涉及历史记录归档（每次新任务独立，任务默认 24h 后过期）；不涉及近似匹配 / 模糊匹配 / 正则匹配。
> 7. **覆盖确认**：`mapping.mode='overwrite'` 时强制前端 `ElMessageBox.confirm` 二次确认；后端在执行前校验 `confirm_token` 字段，缺失 → 409。

---

## Summary

实现一个面向「ETL / 数据补全」场景的跨表匹配模块，包含：

1. **上传 + 解析（第一步）**：用户上传两张 `.xlsx` 并指定角色（target / base）；后端读取两张表的第一行表头并返回给前端；**不**把全量数据返回前端，只返回 headers 与行数；
2. **角色定义（第二步）**：在上传时即指明 target / base；后续不允许颠倒（API 层面通过 job 数据隔离保证）；
3. **主键 + 映射（第三步）**：用户在两张表各自选择 1 个或多个字段作为匹配键，并勾选 base 表中需要填充的字段及其落点（target 表哪个列 + `overwrite` 或 `new_column`）；
4. **执行 + 交付（第四步）**：后端按主键匹配，将 base 对应行的字段值写入 target 同一行的指定列中；执行完成后同步返回前 1000 行预览 + 短期 `download_token`；前端可用 token 调下载端点拉取完整填充结果的 `.xlsx`。

---

## Key Changes

### 数据模型

| 表 | 状态 | 字段 |
|----|------|------|
| `cross_table_fill_jobs` | 新增 | id / target_filename / base_filename / target_headers (JSON) / base_headers (JSON) / target_row_count / base_row_count / status / result_row_count / filled_count / unmatched_count / multi_match_count / created_at / updated_at / expires_at |
| `cross_table_fill_rows` | 新增 | id / job_id (FK, CASCADE) / role (`target` / `base`) / row_index / key_value / data (JSON) |
| `cross_table_fill_configs` | 新增 | job_id (FK, UNIQUE) / target_keys (JSON list) / base_keys (JSON list) / mappings (JSON list) / join_mode / match_mode / case_sensitive / trim_strings / confirm_token / created_at / updated_at |

> **三张表的作用分工**：
> - `cross_table_fill_jobs`：存元数据 + 状态机 + 执行摘要；上传即创建。
> - `cross_table_fill_rows`：用 `role` 字段统一存两张表的全量数据；`data` 为 JSON 字典，因 Excel 字段任意。
> - `cross_table_fill_configs`：UNIQUE on `job_id`，存匹配配置；配置 PATCH 时 upsert。
>
> **生命周期**：`expires_at` 在 job 创建时设为当前时间 + 24 小时；查询 / 配置 / 执行链路上的每一跳先校验未过期；过期 job 状态迁移为 `expired`，懒清理时 DELETE 关联 rows 与 configs。

> **日期字段统一为 `YYYY-MM-DD` 字符串**：`created_at` / `updated_at` / `expires_at` 均为 10 字符定长字符串，不使用数据库原生 `DATE` / `DATETIME` 类型。

---

### `cross_table_fill_jobs` 字段

```python
id                  Mapped[int]       # 主键，自增
target_filename     Mapped[str]       # 256，非空；原始 target xlsx 文件名
base_filename       Mapped[str]       # 256，非空；原始 base xlsx 文件名
target_headers      Mapped[str]       # JSON，TEXT；非空；target 表头列表，如 ["工号","姓名","部门"]
base_headers        Mapped[str]       # JSON，TEXT；非空；base 表头列表
target_row_count    Mapped[int]       # 非空；target 数据行数（不含表头）
base_row_count      Mapped[int]       # 非空；base 数据行数（不含表头）
status              Mapped[str]       # 16，非空；pending / configured / executed / failed / expired
result_row_count    Mapped[int|None]  # 执行后写入的 target 行数（=target_row_count）
filled_count        Mapped[int|None]  # 执行后至少 1 个 mapping 成功填充的 target 行数
unmatched_count     Mapped[int|None]  # target 主键在 base 不存在的行数
multi_match_count   Mapped[int|None]  # target 至少 1 个主键在 base 命中 >=2 行的行数
created_at          Mapped[str]       # 10，YYYY-MM-DD
updated_at          Mapped[str]       # 10，YYYY-MM-DD
expires_at          Mapped[str]       # 10，YYYY-MM-DD；created_at + 24h
```

> **`target_headers` / `base_headers` 存为 JSON 字符串**：因 Excel 字段名任意（包括中文 / 含空格的字段名），解析层在第一时间存为 `list[str]`。
>
> **`status` 取值**：
> - `pending` — 仅上传，未配置
> - `configured` — PATCH /config 完成
> - `executed` — POST /execute 完成（终态，success）
> - `failed` — POST /execute 中断（终态，failure）
> - `expired` — `expires_at < today`（终态；查询 / 配置 / 执行链路会拒绝）

---

### `cross_table_fill_rows` 字段

```python
id           Mapped[int]       # 主键，自增
job_id       Mapped[int]       # FK -> cross_table_fill_jobs.id，ON DELETE CASCADE，index
role         Mapped[str]       # 16，非空；target / base
row_index    Mapped[int]       # 非空；该行在原 Excel 中的 0-based 行号（不含表头）
key_value    Mapped[str|None]  # 1024；主键值预拼接归一化字符串；用于快速去重 / 命中诊断
data         Mapped[str]       # JSON，TEXT，非空；整行字段值字典，如 {"工号":"E001","姓名":"张三"}
```

> **`role` 单表存两张表**：两张表同构（皆为 `dict[str, Any]`），分成两张表无收益。
>
> **`key_value` 是归一化后的拼接字符串**：在 **execute 阶段** 由配置确定归一化规则后实时计算（不上传阶段）；存为 `str|None`（配置阶段尚未生成键值时为 NULL）。最长 1024 字符。
>
> **`data` 是 JSON 字符串**：用 SQLAlchemy `JSON` 类型（或 MySQL `JSON` / SQLite `TEXT` 兼容），cell 值统一序列化为原生 JSON（数字 / 字符串 / null / bool）；datetime / date 不在支持范围（用户 Excel 不含此类）。

---

### `cross_table_fill_configs` 字段

```python
job_id          Mapped[int]       # PK & FK -> cross_table_fill_jobs.id，ON DELETE CASCADE
target_keys     Mapped[str]       # JSON，TEXT，非空；list[str]，至少 1 个
base_keys       Mapped[str]       # JSON，TEXT，非空；list[str]，与 target_keys 等长
mappings        Mapped[str]       # JSON，TEXT，非空；list[{base_field, target_field, mode}]
join_mode       Mapped[str]       # 16，非空；left (默认) / inner
match_mode      Mapped[str]       # 16，非空；merge_multi (默认) / first / last
case_sensitive  Mapped[bool]      # 非空；默认 True
trim_strings    Mapped[bool]      # 非空；默认 True
confirm_token   Mapped[str|None]  # 64；仅 mappings 含 overwrite 模式时填入
created_at      Mapped[str]       # 10，YYYY-MM-DD
updated_at      Mapped[str]       # 10，YYYY-MM-DD
```

> **`job_id` 同时是主键和外键**：保证一对一的配置关系。
>
> **`mappings` JSON 结构**：
>
> ```json
> [
>   {"base_field": "部门", "target_field": "部门", "mode": "overwrite"},
>   {"base_field": "薪资", "target_field": "薪资", "mode": "new_column"}
> ]
> ```
>
> **`mode` 取值**：
> - `overwrite` — 直接覆盖 `target_field` 列的同名单元格
> - `new_column` — 在 target 表末尾追加新列；列名 = `target_field`（若该名与现有 target 列冲突，自动加后缀 `_filled`）
>
> **`confirm_token` 用途**：当 mappings 含 `overwrite` 模式时，前端必须先 `ElMessageBox.confirm`；确认后前端生成一个 `confirm_token`（UUIDv4 字符串）随 PATCH 一并提交，后端校验存在即通过；缺该字段 → 409。

---

## 工作流拆解（4 步）

### 第一步：上传 + 解析（POST `/api/cross-table-fill/jobs`）

| 步骤 | 用户行为 | 后端行为 |
|------|----------|----------|
| 1.1 | 选择两个 xlsx 文件 + 指明 target / base | 接收 multipart；分别解析 |
| 1.2 | — | 校验 MIME / size；`openpyxl` load → 读第 1 行表头 → 入库 job + rows |
| 1.3 | 看到 target_headers / base_headers 下拉框 | 前端用 headers 渲染下拉框；行数展示用于预估 |

> **关键约束**：
> - MIME 必须 `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`；
> - 单文件 ≤ 20 MB；
> - 表头第一行 cell 值做 `strip()` 后存入 `target_headers` / `base_headers`；
> - 表头为空字符串 / 重复名 → 422；
> - 不读、不展示数据行内容（防卡顿；execute 阶段才读取）。

### 第二步：角色定义

**该步骤在第一步合并完成**（上传时即指明 target / base）。后续不允许颠倒（spec 边界）。

### 第三步：主键 + 映射（PATCH `/api/cross-table-fill/jobs/{job_id}/config`）

| 步骤 | 用户行为 | 后端行为 |
|------|----------|----------|
| 3.1 | 在 target_headers 下拉里选 target_keys（≥1） | 校验每个字段都在 target_headers 中 |
| 3.2 | 在 base_headers 下拉里选 base_keys（与 3.1 等长、按位置对应） | 校验等长 + 都在 base_headers 中 |
| 3.3 | 勾选 base 表中要填充的字段 | 校验 base_field 都在 base_headers 中 |
| 3.4 | 给每个勾选指定 target 列 + mode（overwrite / new_column） | 校验 target_field 都在 target_headers 中 |
| 3.5 | 若 mapping 含 overwrite，前端弹 `ElMessageBox.confirm` → 用户选「确定」→ 前端生成 UUIDv4 作为 `confirm_token` | 校验 mappings schema + 若有 overwrite 则要求 confirm_token → 写入 cross_table_fill_configs + 把 job.status 设为 configured |

> **`target_keys` 与 `base_keys` 按位置配对**：例如 `target_keys=["工号", "姓名"]` + `base_keys=["EID", "Name"]` → 元组 `("E001", "Zhang San") == ("E001", "Zhang San")` 为相等条件。
>
> **空键值处理**：target 行某主键值为空（empty string / None）→ 该行**直接判为 unmatched**，不抛错；base 行某主键值为空 → 该行**不出现在 base_index**，相当于"自身不可被匹配"（与 Excel VLOOKUP 一致：空键查不到）。

### 第四步：执行 + 交付（POST `/api/cross-table-fill/jobs/{job_id}/execute`）

| 步骤 | 用户行为 | 后端行为 |
|------|----------|----------|
| 4.1 | 点「执行填充」 | 校验 status=configured、configs 存在、未过期 |
| 4.2 | — | 加载 base_rows + target_rows，按 §匹配算法 计算 |
| 4.3 | — | 写 result_row_count / filled_count / unmatched_count / multi_match_count；status=executed |
| 4.4 | 看到前 1000 行预览 + 「下载完整 xlsx」按钮 | execute 响应同步返回前 1000 行 + `download_token`（5 min TTL） |
| 4.5 | 点下载 | 调 GET `/api/cross-table-fill/jobs/{job_id}/download?token=...` → StreamingResponse |

> **预览行裁剪**：response 的 `preview` 字段为 list，最长 1000 条；超过 1000 条的剩余部分仅在 xlsx 中可见。
>
> **`download_token`**：32 字符 URL-safe 随机串（`secrets.token_urlsafe(24)`）；存内存字典 `dict[job_id, token]`，TTL 5 分钟；过期返回 401。token 与 job_id 必须匹配。

---

## 文件名解析规则

本模块**不**解析文件名（不像 `dsp_uploads` 需要从文件名提取 vendor / item / sub_item）。仅原样保存 `target_filename` / `base_filename` 用于审计与下载时的 default 名（下载时自动命名为 `cross_table_fill_{job_id}_filled_{YYYYMMDDHHMMSS}.xlsx`，原文件名仅展示）。

---

## Excel 解析规则

### 工作表

| 项 | 规则 |
|----|------|
| sheet 选择 | 取第一个 sheet（不限定 sheet 名）；若工作簿无 sheet → 422 |
| 表头读取 | 仅读 row 1；所有 cell 值 `str(cell.value).strip()`；空字符串保留为空字符串（不入 headers 列表） |
| 数据行读取 | 仅在 execute 阶段读取；row 2 起每行视为数据行 |
| cell 值归一化 | 数字 → 数字（int 直接 int，float 不截断，保留原值；如 `1.0` 保留 `1.0`）；字符串 → str 后 strip；bool → bool；None → None |
| datetime 单元格 | 视为非法 → 该行整行 422（spec 边界：本模块不支持日期类型字段） |

> **headers 去重校验**：若 target_headers 含重复字段名 → 422（`detail="target_headers contains duplicate: '<name>'"`）；base_headers 同理。
>
> **headers 空校验**：若去重后 target_headers 或 base_headers 为空 → 422（`detail="<role>_headers is empty"`）。
>
> **「表头允许空列吗」**：允许空 cell（视为空字符串 cell，不进 headers）；但**不允许重复名**。

### 数据行的字段值读取

读取阶段（execute 时）：

```python
for c in headers:
    raw = ws.cell(row=row_index + 2, column=c + 1).value  # row_index 是 0-based
    # cell 归一化：
    if raw is None:
        value = None
    elif isinstance(raw, (int, float, bool)):
        value = raw  # 原样保留；写入 xlsx 时再格式化为字符串 / 数字
    elif isinstance(raw, str):
        value = raw.strip()  # 仅 strip；不做大小写转换
    else:
        raise BadCellTypeError(f"cell at row {row_index} col {c}: unsupported type {type(raw).__name__}")
```

> **写回 xlsx 的语义**：None → 空白 cell；int / float → 数字 cell；str → 字符串 cell；bool → `'TRUE'` / `'FALSE'` 字符串（避免 Excel 自动转 1/0）。

---

## 匹配算法

### 0. 预校验

```python
assert job.status in ("configured", "executed")  # executed 也允许重跑（覆盖式）
assert job.expires_at >= today
configs = get_configs(job_id)
assert configs is not None
```

### 1. 计算 base 主键索引

```python
base_index: dict[tuple, list[dict]] = defaultdict(list)

for base_row in base_rows:                # base_row.data 是 dict
    raw_key = tuple(base_row.data[k] for k in configs.base_keys)

    # 归一化（与 §主键归一化 一致）
    norm_key = tuple(_normalize(v, configs) for v in raw_key)

    # 任一主键值为 None 或空字符串 → 该行不入索引
    if any(v is None or v == "" for v in norm_key):
        continue

    base_index[norm_key].append(base_row.data)
```

### 2. 主键归一化

```python
def _normalize(value, configs):
    if value is None:
        return None
    s = str(value)
    if configs.trim_strings:
        s = s.strip()
    if not configs.case_sensitive:
        s = s.lower()
    # 数字 / bool 走 str 序列化；JSON 序列化无副作用
    return s
```

> **关键**：归一化后的键类型**统一为字符串**。原因：base 表 "1"（字符串）与 target 表 `1`（int）会被统一处理为 `"1"`，避免类型不一致引发的 false miss。
>
> **数字精度**：`1` 与 `1.0` 归一化后分别是 `"1"` 与 `"1.0"`——**视为不同键**。这是显式选择：用户的 Excel 模板可能刻意区分两者。
>
> **执行后** 立即把每个 target 行的 target_keys 归一化结果**回写到 `cross_table_fill_rows.key_value`** 字段（替换 NULL），便于审计 / 诊断。

### 3. 遍历 target

```python
result_target_rows = []  # list[list[cell]]  按 target 原始顺序
filled_count = 0
unmatched_count = 0
multi_match_count = 0

for target_row in target_rows:
    raw_key = tuple(target_row.data[k] for k in configs.target_keys)
    norm_key = tuple(_normalize(v, configs) for v in raw_key)

    # 任一主键值为 None 或空 → unmatched
    if any(v is None or v == "" for v in norm_key):
        result_target_rows.append(_copy_with_no_fill(target_row, configs))
        unmatched_count += 1
        continue

    candidates = base_index.get(norm_key, [])
    if not candidates:
        result_target_rows.append(_copy_with_no_fill(target_row, configs))
        unmatched_count += 1
        continue

    # 按 match_mode 选 base
    if configs.match_mode == "first":
        chosen = [candidates[0]]
    elif configs.match_mode == "last":
        chosen = [candidates[-1]]
    else:  # merge_multi（默认）
        chosen = candidates
    if len(candidates) > 1:
        multi_match_count += 1

    # 应用 mappings
    out_row = list(target_row.data.values())  # 按 target 原始 headers 顺序拷贝
    n_filled_here = 0
    for m in configs.mappings:
        # 收集来自 chosen 各行的 base_field 值，去除 None 与空字符串
        vals = [c[m.base_field] for c in chosen if c.get(m.base_field) not in (None, "")]
        if not vals:
            continue  # 没有有效填充值，不动 target
        fill_value = vals[0] if configs.match_mode != "merge_multi" else ";".join(map(str, vals))

        # 写 target 列
        if m.mode == "overwrite":
            out_row[target_header_index[m.target_field]] = fill_value
            n_filled_here += 1
        else:  # new_column
            new_col_index = len(result_headers) + new_col_counter
            out_row.append(fill_value)  # 实际写法见 §4
            n_filled_here += 1

    if n_filled_here > 0:
        filled_count += 1
    result_target_rows.append(out_row)
```

> **`merge_multi` 拼接语义**：用 `str(v)` 转换每个值；空字符串 / None 已在前置过滤；数字保留原字面（如 `1` 与 `1.0` 会以 `"1"` / `"1.0"` 拼接）。

### 4. 列名冲突与 `_filled` 后缀（`new_column` 模式）

```python
existing_target_headers = list(job.target_headers)  # 原始 headers
new_columns_to_add: list[str] = []

for m in configs.mappings:
    if m.mode == "new_column":
        desired = m.target_field
        # 避免与已存在的 target headers 冲突
        if desired not in existing_target_headers and desired not in new_columns_to_add:
            new_columns_to_add.append(desired)
        else:
            # 加 _filled 后缀；若仍冲突循环 _filled_2 / _filled_3 ...
            base = desired + "_filled"
            candidate = base
            n = 2
            while candidate in existing_target_headers or candidate in new_columns_to_add:
                candidate = f"{base}_{n}"
                n += 1
            new_columns_to_add.append(candidate)

# 最终 headers = original_headers + new_columns_to_add
final_headers = existing_target_headers + new_columns_to_add
```

> **`overwrite` 模式不需后缀**：因为按 `target_field` 列直接覆盖。
>
> **`mode` 强制字段**：API 接收的 mapping schema 中 `mode` 字段**必填**，不允许缺省。

### 5. 写回结果

```python
output_xlsx = build_xlsx(
    headers=final_headers,
    rows=result_target_rows,
)
job.status = "executed"
job.result_row_count = len(result_target_rows)
job.filled_count = filled_count
job.unmatched_count = unmatched_count
job.multi_match_count = multi_match_count
job.updated_at = today_str()
```

### 6. 持久化预览（可选）

execute 同步响应中把前 1000 行（前缀裁剪）作为 `preview` 字段回给前端；不持久化预览。

---

## 输出生成（`build_xlsx`）

```python
def build_xlsx(headers: list[str], rows: list[list]) -> bytes:
    """生成 xlsx 二进制流；依赖 openpyxl。"""
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(_normalize_cell(r))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

> **cell 规范化**（与 §Excel 解析规则 的读端对应）：
> - None → 空白
> - int / float → 数字
> - bool → `'TRUE'` / `'FALSE'` 字符串
> - str → 字符串
> - 其它（list / dict 等）→ `str(v)` 转换后写入
>
> **样式**：不应用任何颜色 / 字体加粗（spec 边界；不引入性能负担）。

---

## API And Behavior

所有接口统一前缀 `/api`，路径使用复数名词；上传走 multipart/form-data；JSON 通信走 `application/json`。

### 端点总览（v0.6.0）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST   | `/api/cross-table-fill/jobs` | 上传 target + base 两张 xlsx，返回 job_id 与 headers |
| GET    | `/api/cross-table-fill/jobs/{job_id}` | 查询 job 状态 + 元数据 |
| PATCH  | `/api/cross-table-fill/jobs/{job_id}/config` | 提交主键 + 映射配置；含 overwrite 时强制 confirm_token |
| POST   | `/api/cross-table-fill/jobs/{job_id}/execute` | 执行匹配，返回前 1000 行预览 + download_token（5 min TTL） |
| GET    | `/api/cross-table-fill/jobs/{job_id}/download` | 流式下载执行后的 xlsx（需 token） |
| DELETE | `/api/cross-table-fill/jobs/{job_id}` | 主动清理（级联） |
| GET    | `/api/cross-table-fill/jobs?status=&page=&size=` | 列表（按 id 倒序）— 管理用，前端默认不展示 |

### POST /api/cross-table-fill/jobs 入参（multipart/form-data）

| 字段 | 类型 | 必填 | 校验 |
|------|------|------|------|
| `target_file` | File | 是 | `.xlsx`；MIME = `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`；size ≤ 20 MB |
| `base_file` | File | 是 | 同上 |
| `expires_in_hours` | int (1-168) | 否 | 默认 24；最长 168（7 天） |

> **两个文件分离校验**：任一文件 MIME / size 不符 → 422（FastAPI 自动）；
> 任一文件工作簿无 sheet / 第一行无任何 cell → 422；
> 任一文件表头去重后为空 / 含重复名 → 422。

### POST 上传响应 201

```json
{
  "job_id": 12,
  "target_filename": "员工列表.xlsx",
  "base_filename": "员工档案.xlsx",
  "target_headers": ["工号", "姓名", "部门"],
  "base_headers": ["EID", "Name", "Department", "Email"],
  "target_row_count": 1240,
  "base_row_count": 1200,
  "status": "pending",
  "created_at": "2026-07-23",
  "expires_at": "2026-07-24"
}
```

> **不返回 data**：避免大数据量进入前端。

### GET /api/cross-table-fill/jobs/{job_id} 响应

```json
{
  "id": 12,
  "target_filename": "员工列表.xlsx",
  "base_filename": "员工档案.xlsx",
  "target_headers": ["工号", "姓名", "部门"],
  "base_headers": ["EID", "Name", "Department", "Email"],
  "target_row_count": 1240,
  "base_row_count": 1200,
  "status": "configured",
  "result_row_count": null,
  "filled_count": null,
  "unmatched_count": null,
  "multi_match_count": null,
  "created_at": "2026-07-23",
  "updated_at": "2026-07-23",
  "expires_at": "2026-07-24"
}
```

> **`status='executed'` 时** `result_row_count` / `filled_count` / `unmatched_count` / `multi_match_count` 才有值。

### PATCH /api/cross-table-fill/jobs/{job_id}/config 入参（JSON）

```json
{
  "target_keys": ["工号"],
  "base_keys": ["EID"],
  "mappings": [
    {"base_field": "Department", "target_field": "部门", "mode": "overwrite"},
    {"base_field": "Email",      "target_field": "邮箱", "mode": "new_column"}
  ],
  "join_mode": "left",
  "match_mode": "merge_multi",
  "case_sensitive": true,
  "trim_strings": true,
  "confirm_token": null
}
```

> **`confirm_token` 强制规则**：
> - mappings 任一 `mode='overwrite'` 时 `confirm_token` **必填**（UUIDv4 字符串，1-64 字符）→ 否则 409
> - mappings 全为 `new_column` 时 `confirm_token` **必须为 None**（不传或显式 null）→ 否则 409
>
> **默认字段**：`join_mode='left'` / `match_mode='merge_multi'` / `case_sensitive=true` / `trim_strings=true` / `confirm_token=null`。前端不传则用默认。

### PATCH 响应 200

```json
{
  "job_id": 12,
  "status": "configured",
  "config_digest": {
    "target_keys": ["工号"],
    "base_keys": ["EID"],
    "mapping_count": 2,
    "has_overwrite": true,
    "has_new_column": true
  },
  "warnings": []
}
```

> **`warnings` 用途**：
> - `base_field` 在 base 表中全部为 None / 空字符串 → `"字段 '<name>' 在 base 表无任何有效填充值，仍保留在 mappings 中（将不会填到 target）"`；
> - `target_keys` 列在 target 表中部分行为空 → `"target_keys 在 target 表有 N 个空键值行，运行时将判为 unmatched"`（仅警告，不阻断）；
> - `mappings` 含 `new_column` 且 `target_field` 与现有 target 列同名 → `"字段 '<name>' 与 target 已有列同名，将自动加 _filled 后缀"`。

### POST /api/cross-table-fill/jobs/{job_id}/execute 响应

```json
{
  "job_id": 12,
  "status": "executed",
  "summary": {
    "target_row_count": 1240,
    "result_row_count": 1240,
    "filled_count": 1200,
    "unmatched_count": 40,
    "multi_match_count": 5
  },
  "preview_headers": ["工号", "姓名", "部门", "邮箱_filled"],
  "preview": [
    {"工号": "E001", "姓名": "张三", "部门": "研发", "邮箱_filled": "zhangsan@x.com"},
    {"工号": "E002", "姓名": "李四", "部门": "测试", "邮箱_filled": "lisi@x.com"}
  ],
  "download_token": "AbCdEf...（32 chars）",
  "download_url": "/api/cross-table-fill/jobs/12/download?token=AbCdEf..."
}
```

> **`preview` 长度上限**：前 1000 行（按 target 原始顺序）。超过 1000 行的剩余部分仅在 xlsx 中可见。
>
> **`multi_match` 行高亮**：前端在预览列表中对 `multi_match_count` 影响的行打橙色 `el-tag`「该主键在 base 命中 N 次，已合并」。

### GET /api/cross-table-fill/jobs/{job_id}/download 响应

| 项 | 值 |
|----|----|
| Method | GET |
| Query | `token` （必填；URL-safe 32 字符；5 min TTL） |
| Success | 200 + StreamingResponse + `Content-Disposition: attachment; filename="cross_table_fill_12_filled_20260723143000.xlsx"` |
| Failure | 401 (token 不存在 / 过期) / 404 (job 不存在) / 409 (job.status != 'executed') |

> **token 存储**：进程内 `dict[job_id, token]` + `(created_at)`；启动时清空；TTL 由请求时间与 `(created_at + 300s)` 对比。

### DELETE /api/cross-table-fill/jobs/{job_id}

| 项 | 值 |
|----|----|
| Success | 204 |
| Failure | 404 |
| 副作用 | 级联清 `cross_table_fill_rows` 与 `cross_table_fill_configs` |

### GET /api/cross-table-fill/jobs（管理用）

| Query | 说明 |
|-------|------|
| `status` | 可选；`pending / configured / executed / failed / expired` |
| `page` | ≥1，默认 1 |
| `size` | 1-100，默认 20 |

> **前端默认不展示**：仅供运维 / 未来 dashboard 用。

### 错误约定

| HTTP | 场景 |
|------|------|
| 400 | 文件 ≤ 20 MB 但 `openpyxl` 解析抛底层错误（非预期异常封装）；数据行 cell 含 datetime 等不支持类型 |
| 401 | download token 不存在 / 过期 |
| 404 | job_id 不存在 |
| 409 | 同 job_id 已 `executed` 且不允许重跑 / overwrite mapping 时缺 confirm_token / new_column only 时传 confirm_token / download 请求时 job.status != 'executed' |
| 413 | target_file / base_file 任一 > 20 MB |
| 415 | target_file / base_file 任一 MIME 非 `.xlsx` |
| 422 | 表头为空 / 表头重复名；config 入参：target_keys / base_keys / mappings / 任一字段不在对应 headers；keys 等长校验失败；mode 取值非法；join_mode / match_mode 取值非法；case_sensitive / trim_strings 缺省；Excel 工作簿无 sheet；首行无任何 cell |

> Pydantic 自动 422 与手动抛 422 共存；按既有约定（spec §5.3）返回中文 detail。

---

## 不实现的组件（明确范围）

- **不支持登录 / 多用户 / 权限**；维持单用户本地版；
- **不支持近似匹配 / 模糊匹配 / 正则匹配**（仅 exact）；
- **不支持 VLOOKUP 风格的"列号匹配"**（仅字段名匹配）；
- **不支持 base 表去重 / 聚合 / 派生列**（merge_multi 仅做值拼接，不做运算）；
- **不支持透视 / 跨表统计 / 排序**（本模块是 ETL，非分析）；
- **不支持公式注入保护**（写入 Excel 字符串时若以 `=` 开头不会被 openpyxl 识别为公式——因为直接调用 `.value = "=..."` openpyxl 会写为字面字符串，不解析）；
- **不支持 date / datetime 字段**（既有 spec 边界；如用户 Excel 含，422 阻断）；
- **不支持跨批次合并 / 历史回放**：每个 job 独立；24h 后清理；
- **不支持 PATCH /config 后的字段热更新**：每次 PATCH **整体覆盖** configs（包括 mappings、keys、mode、case_sensitive、trim_strings），不允许部分字段更新；
- **不支持多张 base 表关联**：仅一对 target + base；
- **不支持 Unicode normalization**（NFC / NFD 等）：用户 Excel 通常是同一软件导出，无需处理；
- **不支持 download token 持久化**：进程内 dict；服务重启后 token 失效（用户需重跑 execute 拿新 token）；
- **不支持后台执行**：execute 同步阻塞；任务量大（>5 万 target 行）可能耗时 > 5 秒，前端按钮需 loading 防重；
- **不支持 overwrite 的白名单字段**：一旦 mapping.mode='overwrite' 强制 confirm_token；不做"哪些列绝对不能覆盖"的二次校验。

---

## Test Plan

> 测试位于 `backend/tests/test_cross_table_fill.py`，使用 pytest + httpx AsyncClient + openpyxl。
> 用 `backend/tests/fixtures/` 下挂 1 个真实小样本 + 多个手工合成的 workbook。
> 测试夹具（conftest.py）复用 `app.database.Base.metadata.create_all`，每测试 case 隔离 DB（与既有约定一致）。

### 1. 上传 + 解析

- 201：双文件上传成功；target_headers / base_headers 正确（顺序保留，strip 已应用）；row_count 准确；
- 400：底层 openpyxl 抛 `BadZipFile`（伪文件）→ 400 + 中文 detail；
- 413：任一文件 > 20 MB（monkeypatch 限制阈值）；
- 415：任一文件 MIME 非 `.xlsx`（如 `text/plain`）；
- 422：sheet 名无 / 工作簿空 / 表头为空 / 表头重复名 / 表头 cell 含 `datetime` → 各自 detail。

### 2. PATCH /config

- 200：完整合法配置写入；`status=configured`；返回 `config_digest`；
- 422：target_keys 含不存在字段 → 422；
- 422：base_keys 长度与 target_keys 不等 → 422 + detail `"target_keys and base_keys must have equal length"`；
- 422：mapping.base_field 不在 base_headers → 422；
- 422：mapping.target_field 不在 target_headers → 422；
- 422：mapping.mode 取值非法（如 `"append"`）→ 422；
- 409：mapping 含 `overwrite` 但缺 `confirm_token` → 409 + 中文 detail；
- 409：mapping 全为 `new_column` 但 `confirm_token` 非 None → 409；
- warnings：target_keys 在 target 表有 N 个空键值行 → 200 + warnings 含 `"target_keys 在 target 表有 N 个空键值行…"`。

### 3. execute 匹配算法

- **exact match 命中**：target 单行 + base 单行同 key → target 该行得到正确填充；
- **left join**：base 缺该 key → target 该行 unmatched+1、fill 列保持原值；
- **first match**：`match_mode='first'` + base 3 行同 key → 取 candidates[0]；
- **last match**：`match_mode='last'` + base 3 行同 key → 取 candidates[-1]；
- **merge_multi 默认**：`match_mode='merge_multi'` + base 3 行同 key → 填值用 `";".join(map(str, vals))`；multi_match_count += 1；
- **join_mode='inner'**：target 行 base 不存在 → 结果不包含该行；result_row_count 减少；
- **空键值**：target 主键空 / None → unmatched；base 主键空 → 不入 index；
- **大小写**：`case_sensitive=false` + base 表 `E001` 与 target 表 `e001` 命中；
- **空格**：`trim_strings=true` + base 表 `"E001"` 与 target 表 `" E001 "` 命中；
- **overwrite**：mapping.mode='overwrite' → target 原列值被覆盖；
- **new_column**：mapping.mode='new_column' → target 末尾追加新列；列名 = target_field；
- **new_column 冲突**：mapping.mode='new_column' + target_field 与 target 原列同名 → 列名变 `<field>_filled`；
- **new_column 多次冲突**：同一字段在不同 mapping 重复 → 后缀升级为 `_filled_2` / `_filled_3`；
- **类型归一化**：base `1`（int）与 target `"1"`（str）→ 命中；
- **类型归一化（显式不同）**：base `1.0` 与 target `1` → 不命中（视作不同）；
- **多匹配计数**：2 个 target 行均命中 3 行 base → multi_match_count = 2；
- **filled_count**：target 1000 行，base 缺 5 个 key，5 行 unmatched；剩下 995 行只要至少有 1 个 mapping 命中就 +1 → 995。

### 4. 双轨交付

- execute 响应 `preview` 长度 ≤ 1000 + `download_token` 存在 + `download_url` 路径正确；
- 调 download（带正确 token）→ 200 + `Content-Disposition: attachment; filename="cross_table_fill_{id}_filled_*.xlsx"` + 文件可被 openpyxl 读回；headers / rows 与计算一致；
- download token 不带 / 错误 / 过期 → 401；
- download 时 status != 'executed' → 409。

### 5. 状态机 + 生命周期

- pending → configured → executed；
- executed 后再调 PATCH /config → 409（不允许重配）；
- 过期 job：monkeypatch 把 `expires_at` 改为昨日；查询 / config / execute → 409 + detail `"job expired (expires_at=...)"`；
- DELETE 之后 GET → 404；CASCADE 验证 `cross_table_fill_rows` 与 `cross_table_fill_configs` 清空。

### 6. 列表 / 单查

- GET 列表：默认按 id 倒序；status filter 生效；
- GET 单查：404（job 不存在）。

### 7. SQL 日期函数不出现

- 解析 / 查询路径 SQL 文本不出现 `CURDATE()` / `NOW()` / `CURRENT_DATE` / `GETDATE()`（沿用既有约定）。

---

## Assumptions

1. **单用户本地版**维持不变：不引入登录、不引入多租户；
2. **同库同 schema**：复用现有 MySQL `sparkmemo`；新表由 `Base.metadata.create_all` 自动创建，老库走幂等 `CREATE TABLE IF NOT EXISTS`；
3. **新依赖**：项目已含 `openpyxl` / `pandas` / `fastapi` / `pydantic`，无需新增 pip 包；如未来引入 `python-dotenv` 通用配置已在用；
4. **CASCADE**：删除 `cross_table_fill_jobs` 自动级联删 `cross_table_fill_rows` 与 `cross_table_fill_configs`（SQLAlchemy `cascade="all, delete-orphan"` + DB 端 `ON DELETE CASCADE`）；
5. **跨表 schema 差异**：base 比 target 字段多就忽略（无匹配 base_field 不报错）；target 比 base 字段多就仅作 target 原列保留，不主动填空；
6. **`source_filename` 占位**：本模块 `target_filename` / `base_filename` 仅展示与审计用，不参与业务；
7. **类型归一化仅 strip 与 case**：不引入 unicode normalization / 半角全角转换；
8. **JSON 列存储**：MySQL `JSON` 类型；SQLite 测试环境走 `JSON` 类型（SQLAlchemy 2.0 自动适配）；
9. **不持久化历史匹配结果**：执行后的 xlsx 不入 DB；仅前端预览 + 短期下载；
10. **24h 过期**：默认 `expires_in_hours=24`，上限 168（7 天）；前端在该时间内可任意重 execute（PATCH 已 executed → 409，详见 §状态机 + 409 约定）；
11. **同步 execute**：本版本不支持后台任务；execute 同步阻塞，预计 < 5 秒（5 万行 × 简单匹配测试基准）；
12. **`merge_multi` 仅做值拼接**：不做求和 / 求平均 / 取众数；
13. **overwrite 的二次确认**：业务级安全约束；前端 `ElMessageBox.confirm` → 生成 UUIDv4 → 后端 409 阻断无 token；
14. **download token 进程内**：服务重启后所有 token 失效；这是可控风险（仅用于短期下载；若用户操作跨越服务重启，重新 execute 即可）；
15. **不支持公式注入保护**：openpyxl 默认 `.value = "=A1+1"` 写为字面字符串而非公式，无需额外处理。

---

## 文件落地清单

| 路径 | 类型 | 预估行数 |
|------|------|----------|
| `backend/spec/cross_table_fill.md` | 新增 | 本文档 |
| `backend/app/models.py` | +3 类 | +30 行 |
| `backend/app/schemas.py` | +9 类 | +120 行 |
| `backend/app/services/cross_table_fill.py` | 新增 | ~280 行 |
| `backend/app/crud/cross_table_fill.py` | 新增 | ~150 行 |
| `backend/app/api/cross_table_fill.py` | 新增 | ~250 行 |
| `backend/app/main.py` | +1 行注册 | +1 行 |
| `backend/tests/test_cross_table_fill.py` | 新增 | ~400 行 |
| `backend/openapi/cross_table_fill.json` | 自动生成 | — |

---

## 修订记录

### v0.6.0（首次发布）

- 新增「跨表数据填充」模块；
- 后端 7 个端点（`POST /jobs`、`GET /jobs/{id}`、`PATCH /jobs/{id}/config`、`POST /jobs/{id}/execute`、`GET /jobs/{id}/download`、`DELETE /jobs/{id}`、`GET /jobs`）；
- 数据模型 3 张新表（`jobs` / `rows` / `configs`）；
- 默认 `join_mode='left'`（VLOOKUP 语义）+ `match_mode='merge_multi'`（多匹配值用 `;` 拼接并计入 `multi_match_count`）；
- mapping.mode 强制显式 `overwrite` / `new_column`，`overwrite` 模式强制 `confirm_token` 二次确认；
- 24h 任务过期；CASCADE 清理。
