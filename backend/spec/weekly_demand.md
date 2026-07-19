# 周需求管理模块规格（v0.5.9 — 新增「Demand 跨版本 diff 过滤」）

> 适配规格：SparkMemo v0.5.4
> 适用范围：单用户本地版，无登录。
> **数据库可移植性约束**：所有日期字段统一使用 10 字符字符串 `YYYY-MM-DD`；不依赖任何数据库内置日期函数（沿用既有项目约定，详见 `task_management.md` §约束）。

> **v0.5.4 模块重命名 + 子模块新增**：
> 1. 原「DSP 上传」模块更名为「**周需求管理**」（`Weekly Demand Management`，简称 WDM）。
> 2. 「DSP 上传」降级为周需求管理的**子功能**之一（同 `vendor / item / sub_item / version_date` 4 个关键字段语义）；其它两个子功能为「**查询**」（按相同 4 字段查询已存在的批次 + 事实行）和「**删除**」（按相同 4 字段预览后删除）。
> 3. 前端路由层级：`/dsp-uploads` 作为 hub 页（含 3 张功能卡片），子路由 `/dsp-uploads/upload`、`/dsp-uploads/query`、`/dsp-uploads/delete` 分别落地三个子功能页。
> 4. 后端 API：`GET /api/dsp-uploads` 增加可选 query 参数 `vendor / item / sub_item / version_date`，前端用它做精确查找；删除仍走既有的 `DELETE /api/dsp-uploads/{id}`（前端先查再删）。
> 5. 字段名规范化沿用 v0.5.3（`ym` / `vendor / item / sub_item / version_date`）；保留 v0.5.3 的列头文本匹配 + 跳过隐藏列说明。
>
> **v0.5.6 新增「透视查询」子模块**（独立模块，不挂在 `/api/dsp-uploads` 下）：
> 1. 新增独立 API 端点 `POST /api/pivot-query`，对应 `app/api/pivot_query.py`。
> 2. 新增 CRUD 模块 `app/crud/pivot_query.py`，实现三子查询 CTE 共享 + 笛卡尔积预检。
> 3. 新增 ORM 模型 `WeekDt`（只读引用外部维表 `sparkmemo.week_dt`，不通过 `create_all` 创建）。
> 4. 横向 = 业务行（country/category/config_code/config_name/data_type/version_date/ttl），纵向 = week_dt（year/month/week/dt），交叉点 = quantity（COALESCE 兜底 0）。
> 5. v0.5.6 固定 `data_type='Demand'`；`pivot_type='demand_plus_supply'` 占位待后续实现。
> 6. 严格级联校验：业务行 `config_names → categories → countries`；时间 `weeks → (months AND years) → years`；必须至少传一个时间维度。
>
> **v0.5.9 新增「Demand 跨版本 diff 过滤」**（仅 `pivot_type='demand'` 生效，`demand_plus_supply` 不接通）：
> 1. `PivotQueryRequest` 新增可选布尔字段 `query_diff: bool = True`（默认开启）；`query_diff=false` 沿用 v0.5.7 baseline 行为，完全向后兼容。
> 2. SQL 主路径不变；在 `_query_demand` 末尾新增纯 Python 后处理函数 `_apply_diff_filter`：按业务维度 `(country, category, config_code, config_name, data_type, ttl)` 聚合 `row_groups`，对每个业务组求「跨 version_date 的 quantity 全等」日期集合并从 `period_columns` 与各 `quantities` 中剪除；若 len(version_dates) ≤ 1 直接跳过过滤。
> 3. 「变化」语义：**全部版本相互对比**——任一日期 N 个 quantity 中只要有 2 个不同即视为「有变化」；N 个 quantity 全等视为「无变化」，该日期从响应中移除。
> 4. 「展示形式」：**保留原 quantity**（不计算 delta），仅控制列/字段是否出现；过滤后为空的 row_group（`quantities={}`）**保留**，用于诊断"该版本存在但与其它版本无任何差异日期"。
> 5. 与 `POST /api/pivot-query/export` 自动协同：`excel_export.py::build_pivot_xlsx` 沿用过滤后的 `period_columns` 出列，导出 xlsx 列数同步缩短。
> 6. 仅 `pivot_type='demand'` 接通；`demand_plus_supply` 不调用 `_apply_diff_filter`，保持 v0.5.7 4 行（Demand/Supply/TTL_GAP/Rolling_TTLGAP）语义不变；如未来需要再开 PR。

v0.5.4 起拆分为三个互相关联的子功能，对应同一个数据模型 `dsp_uploads` / `dsp_upload_rows`：

1. **DSP 上传**（原 v0.5.3 行为，沿用）：用户在前端选择一个 `.xlsx` 文件 + 4 字段表单（`vendor / item / sub_item / version_date`），后端解析入库；命中同版本 → 409，前端编排 `confirm → DELETE → retry`（详见 §DSP 上传 与前端 spec §2.4「409 分支」）。
2. **查询**（v0.5.4 新增）：用户在查询页输入 4 字段，调用 `GET /api/dsp-uploads?vendor=&item=&sub_item=&version_date=` 做精确查找，匹配则返回该批次元数据 + 前 50 条事实行预览。
3. **删除**（v0.5.4 新增）：用户在删除页输入 4 字段，先调查询拿到 `upload_id`，展示"将删除 N 条事实行"预览；用户确认后调 `DELETE /api/dsp-uploads/{id}` 级联清空。

数据展开 / 列头匹配 / 跳过规则等仍由 §DSP 上传 章节描述（v0.5.3 算法不重写）。

---

## Key Changes

### 数据模型

| 表 | 状态 | 字段 |
|----|------|------|
| `dsp_uploads` | 新增 | id / vendor / item / sub_item / version_date / source_filename / row_count / created_at；(vendor, item, sub_item, version_date) 联合唯一 |
| `dsp_upload_rows` | 新增 | id / upload_id(FK, ON DELETE CASCADE) / country / category / config_code / data_type / ttl / ym / week / date / quantity |

> **日期字段统一为 `YYYY-MM-DD` 字符串**：`version_date` / `date` / `created_at` 均为 10 字符定长字符串，不使用数据库原生 `DATE` / `DATETIME` 类型，便于跨数据库移植。
>
> **`ym` 用 7 字符字符串**（如 `2025-01`）；`week` 用 8 字符字符串（如 `WK01`），与 Excel 原文件格式保持一致便于审计。

### `dsp_uploads` 字段

```python
id              Mapped[int]    # 主键，自增
vendor          Mapped[str]    # 64，  非空；文件名第 1 段
item            Mapped[str]    # 128， 非空；文件名第 2 段
sub_item        Mapped[str]    # 128， 非空；文件名第 3 段
version_date    Mapped[str]    # 10，  非空；YYYY-MM-DD；用户输入
source_filename Mapped[str]    # 256， 非空；原始文件名（含 .xlsx）
row_count       Mapped[int]    # 非空；入库事实行数（跳过 0 后）
created_at      Mapped[str]    # 10，  非空；YYYY-MM-DD；批次创建日

__table_args__ = (
    UniqueConstraint(
        "vendor", "item", "sub_item", "version_date",
        name="uk_dsp_upload_version",
    ),
)
```

### `dsp_upload_rows` 字段

```python
id           Mapped[int]    # 主键，自增
upload_id    Mapped[int]    # FK -> dsp_uploads.id，ON DELETE CASCADE
country      Mapped[str|None]  # 64；来源 col 4（去 `*`、strip）
category     Mapped[str|None]  # 128；来源 col 5（strip）
config_code  Mapped[str|None]  # 128；来源 col 6（strip）
config_name  Mapped[str|None]  # 256；来源 col 7（去 `*`、strip），v0.5.5 新增
data_type    Mapped[str|None]  # 64；来源 col 10（strip），仅 `Demand`/`Supply` 入库
ttl          Mapped[int|None]  # 来源 col 11（int；非整数字符串视为空）
ym            Mapped[str]    # 7，"2025-01"，非空
week         Mapped[str]    # 8，"WK01"，非空
date         Mapped[str]    # 10，YYYY-MM-DD，非空
quantity     Mapped[int]    # 非负，非空
```

> **`config_code` 与 `country` 均可为空**：与原 Excel 数据保持一致（不做任何「智能补全」）；但**整行 `Country` 和 `Config Code` 同时为空**的行整体跳过（视为空行）。
>
> **`data_type` 严格匹配**：仅字面量等于 `Demand` 或 `Supply`（大小写敏感、首尾去空白后）的行进入事实表；其余（`Demand PO` / `Demand PR` / `Demand Non-PR` / `Supply PO` / `Supply PR` / `Supply Non-PR` / `GR` / `ASN` / `TTL_GAP` / `Rolling_TTLGAP` 等）整行跳过。

---

## 文件名解析规则

```python
def parse_filename(filename: str) -> tuple[str, str, str]:
    """截掉扩展名后按 '-' 切分，返回前 3 段；段数 < 3 抛 ValueError。"""
    if not filename:
        raise ValueError("filename is required")
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    parts = stem.split("-")
    if len(parts) < 3:
        raise ValueError("filename must contain at least 3 segments separated by '-'")
    return parts[0], parts[1], parts[2]
```

示例：

- `Arista-网络设备DSP横版-机箱-061626.xlsx` → `("Arista", "网络设备DSP横版", "机箱")`
- `foo-bar.xlsx` → `ValueError("filename must contain at least 3 segments separated by '-'")`

---

## Excel 解析规则

### 工作表结构（v0.5.3：行 1 列头文本匹配，不再按字面列号）

工作表固定 1 个，sheet 名必须为 `DSP`，否则 422。

v0.5.3 之前的版本按字面列号硬编码（country=col 4、data_type=col 10 等）；
**v0.5.3 起改为按行 1 列头文本首匹配定位字段**（见 §列头匹配规则），
不同文件即使列位置不一致也能正确解析。

下表仅为「参考示例 / 默认布局」，不再是硬编码：

| 列号 | Excel 列 | 行 1 表头（实际样例） | 用途 | 入库字段 |
|------|----------|----------------------|------|----------|
| 1    | A        | `*BU`                | 丢弃 | — |
| 2    | B        | `*Version`           | 丢弃 | — |
| 3    | C        | `*Region`            | 丢弃 | — |
| **4** | **D**   | `*Country`           | 静态 | `country` |
| **5** | **E**   | `Category`           | 静态 | `category` |
| **6** | **F**   | `Config Code`        | 静态 | `config_code` |
| **7** | **G**   | `*Config Name`       | 静态 | `config_name`（v0.5.5 新增入库） |
| 8    | H        | `Model`              | 丢弃 | — |
| 9    | I        | `*Manufacturer`      | 丢弃 | — |
| **10** | **J** | `Data Type`          | 静态 | `data_type`（过滤） |
| **11** | **K** | `TTL`                | 静态 | `ttl` |
| **12** | **L** | `Update By`          | 参考；不强制 | —（不参与 v0.5.3 解析） |
| **13+** | M+  | `2025-01` / 空 / `2025-02` / … | 周列 | `ym` (行 1) / `week` (行 2) / `date` (行 3) / `quantity` (行 4+) |

> **明确丢弃 5 列**：`BU` / `Version` / `Region` / `Model` / `Manufacturer`。`Update By` **不**在丢弃之列——它在 v0.5.3 之前充当静态列与周列之间的硬编码边界；v0.5.3 起**不再**作为边界——周列起点由行 1 中的 `YYYY-MM` 段起点自动识别（见 §`ym` 段识别）。
>
> **v0.5.5 变更**：`Config Name`（col 7）从"丢弃"改为"入库"，字段名 `config_name`，可选列（缺失时入库为 None）。
>
> **行 1 表头文本不参与解析（v0.5.3 之前的硬约束，v0.5.3 反转）**：v0.5.3 行 1 表头**作为输入**驱动解析；不再按字面列号。

### 列头匹配规则（v0.5.3）

按下列规则在 row 1 中查找目标列：

1. **去首尾空白**；
2. **去前缀 `*`**（如 `*Country` → `Country`）；
3. **大小写不敏感**；
4. **首匹配**：命中第一个满足的 cell 即停。

`_HEADER_TARGETS` 字典（**关键列**，缺一即 `BadHeaderError` → 422；**可选列**缺失时不报错）：

| 业务字段 | 归一化后匹配的别名（任一命中） | 是否必填 |
|----------|-------------------------------|----------|
| `country` | `country` | 必填 |
| `category` | `category` | 必填 |
| `config_code` | `config code`、`configcode` | 必填 |
| `config_name` | `config name`、`configname` | **可选**（v0.5.5 新增） |
| `data_type` | `data type`、`datatype` | 必填 |
| `ttl` | `ttl` | 必填 |

错误消息：`"Excel header missing required column '<name>'"`。

### `ym` 段识别（v0.5.3 替代旧 `update_by` 边界）

扫描 row 1 全 cell：值匹配正则 `^\d{4}-\d{2}$` 即视为「段起点」，其值（如 `2025-01`）作为段标签；
该段起点之后的所有 col 都共享该 ym，直到下一个段起点。
隐藏列（`column_dimensions[letter].hidden=True`）**不**被特殊过滤——见模块顶部 `dsp_parser.py` docstring。

> **故意不引入「跳过隐藏列」**：原 v0.5.3 草稿中曾考虑按 `hidden` 过滤列；但真实样本 `Arista-…xlsx` 把关键列 `Category` 也设为 hidden，若按 hidden 过滤会导致该文件 422 列缺失。Hidden 是 Excel UI 状态，不应影响解析判定。

### 关于隐藏列（hidden columns）

v0.5.3 不根据 `column_dimensions.hidden` 过滤列或 cell：

- 实际 DSP 模板常将结构性 / 已废弃列设为 hidden（如 `*BU` / `Config Name`）做分组视图；这些列本来就不参与 `_HEADER_TARGETS` 匹配，跳不跳不影响解析结果。
- 真实样本 `Arista-…xlsx` 中 `Category` (col E) 也被 hidden，但它是关键列——若按 hidden 过滤会回归挂掉。

所以 hidden 视作 UI 状态；解析层不判定它。未来若"按 hidden 跳列"成为业务需求，扩展点固定在 `_resolve_columns` / `_ym_segments` 内。

### 行布局

| 行 | 用途 | 关键列（v0.5.3 行 1 列头匹配 + ym 段识别） |
|----|------|------------------------------------------|
| 1  | 列头 + `ym` 段标签 | 6 个关键列由列头文本匹配定位（含 `config_name`）；col 13+ 携带稀疏 `YYYY-MM` 段标签 |
| 2  | 周编号 `WK01` / `WK02` / … | `_ym_segments` 识别的有效 col |
| 3  | 周起始日 `YYYY-MM-DD` | `_ym_segments` 识别的有效 col |
| 4..max_row | 数据行 | 通过 `_resolve_columns` 识别的 5 个关键 col；有效周列读 `quantity` |

### `ym` 段识别算法（v0.5.3：全 row 1 扫 `YYYY-MM`，不再从 col 13 起）

行 1 全列扫描：值匹配正则 `^\d{4}-\d{2}$` 即视为段起点，记录该 col = 段标签；段起点之后的所有 col 都继承该 ym，直到下一个段起点。一个示例节选（来自样本文件）：

```
col:  10  11   12   13   14   15   16   17   18   19   20
row1: 'Data Type' 'TTL' 'Update By' '2025-01'  .   .   .   .   '2025-02'  .   .
row2: 'Demand'  4  ''  'WK01' 'WK02' 'WK03' 'WK04' 'WK05' 'WK06' 'WK07' 'WK08' 'WK09'
row3:  ...                   '2024-12-30' '2025-01-06' … '2025-02-03' …
```

**算法**：

```python
import re
_YM_PATTERN = re.compile(r"^\d{4}-\d{2}$")

# 返回 col -> "YYYY-MM"；隐藏列理论上不出现（无 hidden 过滤），但 row 1 中"Update By"等
# 静态字段不会匹配 YYYY-MM，所以天然是空，跳过；继承式前进。
ym_at_col: dict[int, str] = {}
current = ""
for c in range(1, ws.max_column + 1):
    v = _cell_str(ws.cell(row=1, column=c).value)
    if v and _YM_PATTERN.match(v):
        current = v
    if current:
        ym_at_col[c] = current
```

对 `ym_at_col` 字典中所有 key 列（即存在 ym 段的 col）再做一次"行 2 周编号非空 ∧ 行 3 周起始日非空"过滤，得到最终**有效周列**；其 `ym` 取 `ym_at_col[c]`。若没有任何有效周列（R3），事实行集合必为空。

v0.5.3 与旧版差异：旧版硬编码 `range(13, ws.max_column + 1)`，因此列位置变化时周列起点可能错位。新版直接从 row 1 全列扫，自适应列重排 / 缺失 `update_by` 列等情况。

### 跳过规则（命中即跳过；分两层）

**行级跳过（命中后整行 0 条事实记录）**：

- **R1**：该行 `country`（由 `_resolve_columns` 定位的列，strip 后）和 `config_code`（同上）**同时为空**（视为空行）；
- **R2**：该行 `data_type`（由 `_resolve_columns` 定位的列，strip 后）**不等于** `Demand` **也不等于** `Supply`（大小写敏感、首尾空白已 strip；含 `Demand PO` / `GR` / `ASN` / `TTL_GAP` / `Rolling_TTLGAP` / 空字符串 / `None` 等）；
- **R3**：行 1 全列扫不到任何 `YYYY-MM` 段起点（即无任何有效周列；极端情况，正常文件不会出现）。

**周列级跳过（仅影响 (该行 × 该周列) 这一个 cell）**：

- **C1**：该周列 col `c` 的 row 2 `week` 为空 / None；
- **C2**：该周列 col `c` 的 row 3 `date` 为空 / None；
- **C3**：该周列 col `c` 在 `ym_at_col` 中查不到 `ym`（即该 col 在段起点之前；正常文件不会出现）；
- **C4**：该 cell 的 `quantity` 为空字符串 / None / `0`（数值 `0` 也跳；详见 §数值容错）。
- **C5（v0.5.3 草案中曾考虑，不引入）**：若未来按 `column_dimensions.hidden` 过滤列成为业务需求，扩展点固定在 `_resolve_columns` / `_ym_segments` 内。当前**不**按 hidden 过滤——详见 §关于隐藏列。

**注**：C1/C2/C3 整列跳过意味着该 (行 × 列) 组合不入库；该列对**其它**数据行仍然有效（其它行 × 该列 仍正常处理）。

### 数值容错

`quantity` 在行 4+ 各有效周列上的取值与处理（v0.5.3 起不再硬指 col 13+）：

| 取值 | 处理 |
|------|------|
| `None` | 跳过该 cell（C4） |
| 空字符串 `""` | 跳过该 cell（C4） |
| 整数 `0` / 浮点 `0.0` | 跳过该 cell（C4） |
| 整数 `>0` / 浮点 `>0` | 转 `int()` 入库；浮点非整数（如 `1.5`）→ **400** 阻断整次上传 |
| 其它非数字字符串 | **400** 阻断整次上传 |

`ttl`（由 `_resolve_columns` 定位的列，v0.5.3 起不再硬指 col 11）取值与处理：

| 取值 | 处理 |
|------|------|
| `None` / 空字符串 | 入库为 `None` |
| 整数 | 入库为 `int` |
| 浮点整数（如 `4.0`） | 入库为 `int(4)` |
| 其它浮点 / 非数字字符串 | 入库为 `None`（**不**阻断上传——TTL 不参与业务聚合，宽松处理） |

### 展开公式

- 数据行集合 = `{r | r ∈ [4, ws.max_row] ∧ row r 通过 R1 ∧ row r 通过 R2}`，记为 `N` 行；
- 有效周列集合 = `{c | c ∈ [13, ws.max_column] ∧ row 2[c] 非空 ∧ row 3[c] 非空 ∧ ym_at_col[c] 存在}`，记为 `M` 列；
- 事实行集合 = `{ (r, c) | r ∈ 数据行 ∧ c ∈ 有效周列 ∧ row r 的 col c 通过 C4 }`；
- `row_count` = `len(事实行集合)`。

每条事实行入库 `(upload_id, country, category, config_code, data_type, ttl, ym_at_col[c], row 2[c] strip 后, row 3[c] strip 后, int(quantity))`。

---

## 重传策略

| 场景 | 行为 |
|------|------|
| 同 `(vendor, item, sub_item, version_date)` 已存在 | **409 Conflict** |
| 响应 detail | `"version (vendor=A, item=B, sub_item=C, version_date=YYYY-MM-DD) already uploaded (upload_id=N)"`（含现有 upload_id，供前端编排替换流程） |
| 不存在 | 201 创建新批次 |

### "替换"语义（v0.5.2 起，前端编排）

### 查询子模块（v0.5.4 新增）

| 行为 | 后端实现 |
|------|---------|
| 前端在「查询」页输入 `vendor / item / sub_item / version_date`，调 `GET /api/dsp-uploads?vendor=…&item=…&sub_item=…&version_date=…&page=1&size=1` | 后端 `list_uploads(vendor=..., item=..., sub_item=..., version_date=..., page=1, size=1)` |
| 命中（`items.length === 1`）| 返回该批次元数据 `DspUploadRead`；前端再调 `GET /api/dsp-uploads/{id}/rows?page=1&size=50` 拉前 50 条事实行展示 |
| 未命中（`items.length === 0`）| 200 + 空数组；前端显示「未找到该版本」 |
| 4 个字段全部必填校验在前端做；后端不强制全部提供（可单独过滤 `vendor` 等） | — |
| 时间戳 `created_at` / `source_filename` / `row_count` 同步展示 | — |

> 查询**只读**，不修改任何数据；不涉及文件 IO；不依赖 `_ym_segments` 等解析逻辑。

### 删除子模块（v0.5.4 新增）

| 行为 | 后端实现 |
|------|---------|
| 前端「删除」页输入 4 字段 | — |
| 点「查询预览」按钮 | 调 `GET /api/dsp-uploads?…&size=1`（同查询）；命中则返回批次元数据 + `id` |
| 命中：展示元数据 + 「将删除 N 条事实行」预览卡片 + 「删除」按钮（disabled until confirm aware） | — |
| 点「删除」| 弹 `ElMessageBox.confirm("确定删除 vendor=… / item=… / sub_item=… / version_date=… 的 N 条事实行？删除后不可恢复", "删除确认", { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })` |
| 用户确认 | 调 `DELETE /api/dsp-uploads/{id}` |
| 200（实际 204 No Content） | toast「删除成功」，清除预览卡片，路由返回 hub；级联自动清空 `dsp_upload_rows`（FK `ON DELETE CASCADE`）|
| 未命中（前端查不到 id）| toast「该版本不存在，请先确认输入」|

> 删除走的仍是既有 `DELETE /api/dsp-uploads/{id}`；不新增端点，只新增前端 2 个 view（`/dsp-uploads/query` 和 `/dsp-uploads/delete`）。

### DSP 上传（v0.5.3 已稳定的算法核心）

> v0.5.4 模块重命名后，「DSP 上传」作为子功能仍保留 §Excel 解析规则 / §跳过规则 / §数值容错 / §展开公式 / §行布局 等全部章节；下方沿用，**未作 v0.5.4 改动**。

后端**不**新增 `replace` 参数；沿用三步组合：
1. `POST /api/dsp-uploads` → 命中唯一键 → 409 + 含 `upload_id`
2. 前端弹 `ElMessageBox.confirm('该版本已存在，是否替换？…')`
3. 用户选「替换」→ 前端先 `DELETE /api/dsp-uploads/{id}`（CASCADE 清事实行）→ 再 `POST /api/dsp-uploads`

详见 `frontend/spec/dsp_upload.md` §2.4。

---

## API And Behavior

所有接口统一前缀 `/api`，路径使用复数名词；列表接口支持分页 `?page=1&size=20`。

### 端点总览（v0.5.4）

| 方法 | 路径 | 说明 | 子模块 |
|------|------|------|--------|
| POST   | `/api/dsp-uploads` | 上传 multipart/form-data，返回批次摘要 | DSP 上传 |
| GET    | `/api/dsp-uploads?page=&size=&vendor=&item=&sub_item=&version_date=` | 批次列表（按 id 倒序）；4 个可选 filter 参数精确匹配 | 通用 + 查询 |
| GET    | `/api/dsp-uploads/{id}` | 批次详情 | 通用 + 查询 |
| GET    | `/api/dsp-uploads/{id}/rows?page=&size=` | 批次内事实行分页 | 通用 + 查询 / 上传 |
| DELETE | `/api/dsp-uploads/{id}` | 整批删除（CASCADE） | DSP 上传 + 删除 |

> **v0.5.4 新**：`GET /api/dsp-uploads` 增 4 个可选 query 参数 `vendor / item / sub_item / version_date`，全部相等匹配（未提供 → 不作为过滤条件）。前端「查询」子模块用 4 个全提供的方式做精确查找（结果 `items` 通常为 0 或 1 条）。

### POST /api/dsp-uploads 入参（multipart/form-data）— v0.5.1

| 字段 | 类型 | 必填 | 校验 |
|------|------|------|------|
| `file` | File | 是 | `.xlsx`；MIME = `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`；size ≤ 20 MB |
| `vendor` | string | **是** | 1-64 字符；与前端解析/编辑结果一致 |
| `item` | string | **是** | 1-128 字符 |
| `sub_item` | string | **是** | 1-128 字符 |
| `version_date` | string | **是** | `YYYY-MM-DD` |

> v0.5 → v0.5.1 变更：`vendor / item / sub_item` 由「可选（从文件名回退解析）」改为「必填（来自前端 Form）」。`parse_filename` 函数保留但**不再被本路由调用**。
>
> 缺任一必填字段 → FastAPI 自动 `422 Unprocessable Entity`（不是 400，因为这是 Form 必填校验，由 `Form(...)` 在依赖注入阶段触发）。

### POST 成功响应 201

```json
{
  "id": 12,
  "vendor": "Arista",
  "item": "网络设备DSP横版",
  "sub_item": "机箱",
  "version_date": "2026-07-15",
  "source_filename": "Arista-网络设备DSP横版-机箱-061626.xlsx",
  "row_count": 9876,
  "created_at": "2026-07-15"
}
```

### GET /api/dsp-uploads 列表响应

```json
{
  "items": [ /* DspUploadRead[] */ ],
  "total": 5,
  "page": 1,
  "size": 20
}
```

#### 查询参数（v0.5.4 新增）

| 参数 | 类型 | 说明 |
|------|------|------|
| `page` | int (≥1) | 默认 1 |
| `size` | int (1-100) | 默认 20 |
| `vendor` | string（可选） | 精确匹配（大小写敏感，与 DB 一致） |
| `item` | string（可选） | 同上 |
| `sub_item` | string（可选） | 同上 |
| `version_date` | string（可选） | 精确匹配 `YYYY-MM-DD` |

全部 4 个字段都提供时用作精确查找（典型「查询」子模块用法，`size=1` 限制）；未提供则不作为过滤条件，原列表语义保持。

> 注意：在当前 `dsp_uploads` schema 下，`(vendor, item, sub_item, version_date)` 已是唯一索引，精确查找结果至多 1 条；前端用 `items.length === 0` 表示「未找到」、`=== 1` 表示「命中」。

### GET /api/dsp-uploads/{id}/rows 响应

```json
{
  "items": [
    {
      "id": 1,
      "country": "Ireland",
      "category": "机箱",
      "config_code": "BD3300006913",
      "data_type": "Demand",
      "ttl": 4,
      "ym": "2025-01",
      "week": "WK01",
      "date": "2024-12-30",
      "quantity": 4
    }
  ],
  "total": 164,
  "page": 1,
  "size": 100
}
```

> **示例校正**：原规格示例把 `data_type` 写成 `"GR"`，与 §跳过规则 R2 自相矛盾。`GR` 等非 `Demand`/`Supply` 的行不入库，事实行 `data_type` 仅可能为 `"Demand"` 或 `"Supply"`。

### 错误约定

| HTTP | 场景 |
|------|------|
| 400 | `version_date` 非 `YYYY-MM-DD`；`quantity` 含非数字字符串 / 非整数浮点 |
| 404 | 批次不存在 |
| 409 | 同 `(vendor, item, sub_item, version_date)` 已存在 |
| 413 | 文件 > 20 MB |
| 415 | MIME 非 `.xlsx` |
| 422 | Sheet `DSP` 不存在；任一必填 Form 字段缺失；**v0.5.3 新**：Excel 行 1 缺失关键列（country/category/config_code/data_type/ttl 任一）→ detail `"Excel header missing required column '<name>'"` |

---

## 不实现的组件（明确范围）

- 不解析 / 不存储 col 1, 2, 3, 8, 9 的内容（`BU` / `Version` / `Region` / `Model` / `Manufacturer`），也**不解析 col 12 `Update By` 的内容**；
- **v0.5.5 变更**：`Config Name`（col 7）从"丢弃"改为入库字段 `config_name`（可选列，缺失时入库为 None）；
- 不实现文件落盘（上传文件不存到磁盘，仅流式读 `BytesIO` → 解析 → 入库 → 释放）；
- 不实现导入历史回滚 / undo；
- 不实现事实行的编辑（只能整批删除后重传）；
- 不实现跨批次合并 / 透视查询（仅按批次查询，跨批次的统计由未来 dashboard 模块负责）；
- 不实现非 `Demand`/`Supply` 行的事实入库（见 R2）；
- **v0.5.4 新**：查询 / 删除子模块不新增后端端点；走既有 `GET /api/dsp-uploads`（含 4 个可选 filter 参数）与 `DELETE /api/dsp-uploads/{id}`；前端编排两步；
- **v0.5.4 新**：批量删除 / 多选删除不在本轮范围（每次只能删一个版本）；
- **v0.5.4 新**：删除前不强制要求做查询预览（即用户可以选择直接输入 4 字段 + 点删除，确认弹窗会预览，但 UI 不强制先点查询）；后端仍按"先查 id、再 DELETE"两步执行。

---

## Test Plan

> 测试位于 `backend/tests/test_dsp_upload.py`，使用 pytest + httpx AsyncClient + openpyxl 构造 sample 文件。
> 用 `backend/tests/fixtures/` 下挂 1 个真实 Excel 副本 + 多个手工合成的最小 workbook。

### 1. 文件名解析（纯函数）
- `Arista-网络设备DSP横版-机箱-061626.xlsx` → `("Arista", "网络设备DSP横版", "机箱")`；
- `foo-bar.xlsx` → ValueError；
- `no-segments-at-all.xlsx` → ValueError；
- `no-extension` 视为整串 → 按 `-` 切分；
- 空字符串 → ValueError。
### 2. Excel 解析（纯函数）

- 手工构造 4 行 × N 列 worksheet：row 1 含若干 `ym` 标签（中间允许空洞）+ col 4..12 表头文字；row 2 周编号；row 3 周日期；row 4+ 数据；
- 断言展开行数符合预期（按 §展开公式）；
- 跳过规则（v0.5.3 起列号由列头文本匹配定位，下述描述按"实际匹配的列"理解）：

  - **v0.5.3 之前列固定**：col 4=country、col 6=config_code、col 10=data_type、col 11=ttl（其余 detail 不变）

  - R1：`country` 与 `config_code` 同时空 → 该行无事实记录；
  - R2：`data_type = GR` → 该行无事实记录；`data_type = "Demand "`（带尾空格）→ 因 strip 后等于 `Demand` 而保留；
  - C1：row 2[col] 空 → 该 (行 × 列) 不入库，其它列正常；
  - C2：row 3[col] 空 → 同上；
  - C3：行 1 全列扫 `YYYY-MM`，该 col 未匹配（段起点之前） → 该列无效；
  - C4：`quantity = 0` → 跳过；`quantity = None` → 跳过；`quantity = ""` → 跳过；
- 数值容错：`quantity = "abc"` → ValueError（路由层转 400）；`quantity = 1.5` → ValueError。
- **v0.5.3 列头匹配**：参考用例 `test_parse_excel_v0_5_3_reordered_columns_layout_a/b`（v0.5.3 引入）—— Country/Category/Config Code/Data Type/TTL 出现在任意列号都能正确解析。

### 3. POST /api/dsp-uploads
- 201 成功：
  - 用真实文件副本上传，断言返回 `row_count` = 期望值（按 §展开公式手算 N × M − 跳过数）；
  - DB 中 `dsp_uploads` + `dsp_upload_rows` 行数正确；
  - `created_at` = 调用当天（Python 传入，不依赖 DB 函数）；
  - 断言 `data_type` 在事实行中**只有** `Demand` 和 `Supply`；
- 400：
  - `version_date = "2026/07/15"`；
  - 文件名 `foo-bar.xlsx`（段数 < 3）；
  - 手工构造一个 `quantity = "abc"` 的 cell → 整次上传被阻断；
  - MIME 非 `.xlsx`（如 `text/plain`）；
- 413：文件 > 20 MB（用 `monkeypatch` 改 limit）；
- 409：同版本重传；detail 含 `upload_id`；
- 422：sheet 名不是 `DSP`（用只有 sheet `Sheet1` 的 workbook）。

### 4. GET 列表 / 详情 / 行分页
- 列表默认按 id 倒序；
- 行分页 `?page=2&size=100` 返回正确切片；
- `total` 字段准确。

### 5. DELETE
- 删批次后 `dsp_upload_rows` 级联清空；
- 再 GET → 404。

### 6. SQL 日期函数不出现
- 与既有约定一致：解析 / 查询路径 SQL 文本不出现 `CURDATE()` / `NOW()` / `CURRENT_DATE` / `GETDATE()`。

### 7. 真实文件回归
- 用 `backend/tests/fixtures/Arista-网络设备DSP横版-机箱-061626.xlsx` 跑一次完整 POST，断言：
  - `row_count` = 164（= `Demand`/`Supply` 各 82 行 × 1 周列，或具体数 = 681 中 164 行 × 有效周列数 - 0 数减项）；
  - 事实行 `data_type` ∈ {`Demand`, `Supply`}；
  - 任取一行抽查：`(country, category, config_code, data_type, ttl, ym, week, date, quantity)` 与 Excel 原值一致。

---

## Assumptions

1. **单用户本地版**维持不变：不引入登录、不引入多租户；
2. **同库同 schema**：复用现有 MySQL `sparkmemo`，新表由 `Base.metadata.create_all` 自动创建；老库走幂等 `CREATE TABLE IF NOT EXISTS`；
3. **新依赖**：`openpyxl` 加 `backend/requirements.txt`，按 AGENTS.md 在 `dev_env` 安装；
4. **CASCADE**：删除 `dsp_uploads` 自动级联删 `dsp_upload_rows`（SQLAlchemy `cascade="all, delete-orphan"` + DB 端 `ON DELETE CASCADE`）；
5. **v0.5.3 字段定位算法**：6 个关键列（country/category/config_code/config_name/data_type/ttl）的列号由**行 1 列头文本首匹配**决定（去前缀 `*` + 首尾空白 + 大小写不敏感）；不依赖字面列号。因此跨文件即使列位置变化也能正确解析。若 Excel 模板表头文本改名，需同步改本规格 §列头匹配规则 与代码 `_HEADER_TARGETS`。
6. **`source_filename`**：含扩展名的完整原始文件名，仅展示 / 审计用，不参与业务；
7. **`config_code` 可空**：与原 Excel 数据保持一致，不做智能补全；但**整行 Country+ConfigCode 都空**的行整体跳过（R1）；
8. **`data_type` 严格匹配**：仅字面 `Demand` / `Supply` 入库；其它值（含 `Demand PO` 等所有变体）整行跳过（R2）；大小写敏感、首尾空白已 strip；
9. **数字 0 vs NULL**：空字符串 / None / `0` 全部跳过（C4）；非数字 / 非整数浮点 → 400 阻断；
10. **`upload_id` 外键**：先 INSERT 批次拿到 `id`，再批量 INSERT 事实行（两次 commit），保证 CASCADE 关系正确建立；
11. **批量插入**：事实行使用 `bulk_insert_mappings` 或 `session.add_all`，单批 N × M 可能上千行，避免 N 次单条 INSERT；
12. **不上传时落盘**：上传的 `UploadFile` 直接 `read()` 到 `BytesIO`，不写磁盘；
13. **`ttl` 容错**：TTL 单元格的非整数字符串入库为 `None`，不阻断上传——TTL 仅展示，不参与聚合。

---

### 行布局（v0.5.5）

| 行 | 用途 | 关键列 |
|----|------|--------|
| 1  | 列头 + `ym` 段标签 | 行 1 列头文本匹配（6 个关键列，含 `config_name`）；col 13+ 携带稀疏 `YYYY-MM` 段标签 |
| 2  | 周编号 `WK01` / `WK02` / … | `_ym_segments` 识别的有效 col |
| 3  | 周起始日 `YYYY-MM-DD` | `_ym_segments` 识别的有效 col |
| 4..max_row | 数据行 | `_resolve_columns` 识别的 6 个关键 col；有效周列读 `quantity` |

### v0.5.4 → v0.5.5（Config Name 入库）

| 章节 | v0.5.4 | v0.5.5 |
|------|--------|--------|
| §数据模型 | `dsp_upload_rows` 无 `config_name` | **新增** `config_name` 字段（可选列，缺失时入库为 None） |
| §列布局表 | col 7 `*Config Name` 标记为"丢弃" | 改为"静态"，入库字段 `config_name` |
| §`_HEADER_TARGETS` 字典 | 无 `config_name` | **新增** `config_name`（别名 `config name` / `configname`），可选列 |
| §不实现的组件 | 含 "Config Name" 在丢弃列表 | 移除 Config Name，丢弃列从 6 个减为 5 个 |

### v0.5.3 → v0.5.4（模块重命名 + 子模块新增）

| 章节 | v0.5.3 | v0.5.4 |
|------|--------|--------|
| §Summary 标题 | "DSP 上传"单一模块 | **"周需求管理"模块**，下含上传 / 查询 / 删除 3 个子功能 |
| 文件名 | `dsp_upload.md` | `weekly_demand.md` |
| §API | 仅 GET 列表 / POST / DELETE-by-id | **新增 4 个可选 query 参数** `vendor / item / sub_item / version_date` 给 GET 列表；原 5 个端点不变 |
| §新增"查询子模块" | — | `GET /api/dsp-uploads?...&size=1` 精确查找 + `GET /.../{id}/rows?...&size=50` 事实行前 50 条 |
| §新增"删除子模块" | — | 前端「查询预览」→ 拿 id → `ElMessageBox.confirm` → `DELETE /api/dsp-uploads/{id}` |
| §不实现的组件 | 6 项 | 加 3 项：批量删除 / 强制先查询 / 不新增后端端点 |

### v0.5.2 → v0.5.3

| 章节 | v0.5.2 | v0.5.3 |
|------|--------|--------|
| §工作表结构 / §Excel 解析 | 静态列按字面列号（col 4/5/6/10/11/12）硬编码；`update_by` 作为 col 12 的周列起点边界 | **行 1 列头文本首匹配**（去 `*` / strip / 大小写不敏感）；周列起点改为行 1 扫 `YYYY-MM` 段标签；新章节 §列头匹配规则 与 §`ym` 段识别 |
| §跳过规则 | C1-C4 | C1-C4 不变（不再引入 C5 hidden 列跳过） |
| §错误约定 422 | Sheet 不存在 / Form 字段缺失 | **新增**：6 个关键列缺失 → `BadHeaderError` → 422 + detail `"Excel header missing required column '<name>'"` |
| §Assumption 5 | "固定列号"为字段映射唯一依据 | "v0.5.3 字段定位算法"：行 1 列头文本首匹配 |
| §行布局 | col 4..12 硬编码；col 13..max_col 周列 | 6 个关键列按列头匹配；有效周列按 `YYYY-MM` 段识别 |
| §修订记录 | "丢弃 6 列" 表述 | 加 v0.5.3 行（明确"行 1 列头文本"为新算法） |

### v0.5.1 → v0.5.2

| 章节 | v0.5.1 | v0.5.2 |
|------|--------|--------|
| §重传策略 | "删除旧批次后可重传同版本"（要求用户手动删除） | **新增"替换"语义**：由前端在 409 后编排 confirm → DELETE → 重发 POST；后端 API 不变 |
| §错误约定 409 | 仅描述后端返回 | 链接到前端 spec §2.4 的 confirm/replace 流程 |

### v0.5 → v0.5.1（前端接入后）

| 章节 | v0.5（首次发布） | v0.5.1（前端接入） |
|------|---------|---------|
| POST 入参 | `file` + `version_date`；`vendor / item / sub_item` 由后端从文件名解析 | `file` + **4 个必填 Form**：`vendor / item / sub_item / version_date` |
| `parse_filename` 函数 | POST 调用 | **保留但不被 POST 调用**（标记为冗余 / 备用） |
| 错误约定 400 | 含「文件名 < 3 段」 | 移除（前端已在前置校验） |
| 错误约定 422 | 仅「Sheet 'DSP' 不存在」 | **追加**「任一必填 Form 字段缺失」 |

### v0.4 → v0.5（首次发布）

| 章节 | 原版问题 | 修订 |
|------|----------|------|
| Summary §3 | 列头定位表述模糊，混用"列名匹配"和"列号" | 改为**纯列号**定位，明确"表头文本不参与解析" |
| Key Changes / 模型 | `data_type` 可为 `GR`（与 R2 自相矛盾） | 明确仅 `Demand` / `Supply` 入库；示例 JSON 同步修正 |
| 工作表结构 | "col 4, 5, 6, 10, 11, 12" 与"丢弃 7 列（含 Update By）"互斥 | 明确丢弃 6 列（BU/Version/Region/Config Name/Model/Manufacturer），Update By 不丢——它是 col 12 的边界标记，解析时不读不存 |
| Excel 解析 / ym | "col 13+ 第一个非空字符串视为 ym 段起点"含糊 | 给出**完整前向传播算法** + 伪代码 + 样本片段 |
| 跳过规则 | 行级 vs 列级跳过混在一处 | 拆为 R1/R2（行级）和 C1/C2/C3/C4（列级），明确互不影响 |
| 数值容错 | `quantity` 0 与 None 行为未与跳过规则交叉 | 统一并入 C4；新增浮点非整数 / 非数字 → 400 阻断 |
| 数值容错 | `ttl` 容错未定义 | 新增：非整数字符串入库为 `None`，不阻断 |
| §不实现的组件 | "BU/Version/Region/Config Name/Model/Manufacturer/Update By 7 列"包含 Update By | 改为 6 列，明确 Update By 是边界标记，不入丢弃也不入存储 |
| Test Plan §2 | "整行 Country+ConfigCode 都空"行为未明确测 | 拆 R1/R2/C1/C2/C3/C4 6 个独立断言 |
| Test Plan §3 | `data_type = GR` 入库断言 | 改为"事实行 data_type ∈ {Demand, Supply}" |

---

## 透视查询子模块（v0.5.6 新增）

> **定位**：独立模块 `POST /api/pivot-query`，不挂在 `/api/dsp-uploads` 下；与 DSP 上传/查询/删除子功能平级，但**纯只读**，不修改任何数据。

### 1. 业务目标

让用户在前端（未来）通过 `vendor + item + sub_item + 多个 version_date` 定位批次，结合 `country / category / config_name` 等业务行筛选和 `year / month / week` 时间筛选，**对一张已存在的批次矩阵做 OLAP 风格的横向 × 纵向透视**，交叉点显示 `quantity`（缺失默认 0）。

### 2. 数据模型

| 表 | 关系 | 用途 |
|----|------|------|
| `dsp_uploads` | 主表 | 批次维度（vendor+item+sub_item+version_date） |
| `dsp_upload_rows` | 主表 | 横向业务行（country/category/config_code/config_name/data_type/ttl）+ 交叉点 quantity |
| `week_dt` | 外部维表 | 纵向日期维度（year_id/month_id/week_id/dt），`is_week_start=1` 标识周起始日 |

`week_dt` 表结构（外部维护，本项目**只读引用**，不通过 `create_all` 创建）：

```sql
CREATE TABLE `week_dt` (
  `dt` date NOT NULL,
  `year_id` smallint NOT NULL,
  `month_id` tinyint NOT NULL,
  `week_id` tinyint NOT NULL,
  `is_week_start` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`dt`),
  KEY `idx_year_week` (`year_id`,`week_id`),
  KEY `idx_year_month` (`year_id`,`month_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='日期周维度维表';
```

### 3. 核心 SQL 结构（CTE 共享）

```sql
WITH base_rows AS (
    -- 一次扫描 dsp_upload_rows，b 与 d 共享
    SELECT id, upload_id, country, category, config_code, config_name,
           data_type, ttl, date, quantity
    FROM dsp_upload_rows
    JOIN dsp_uploads ON dsp_upload_rows.upload_id = dsp_uploads.id
    WHERE vendor=? AND item=? AND sub_item=? AND version_date IN (?)
      AND data_type IN ('Demand', 'Supply')                  -- v0.5.7: 两模式都查
      AND [country/category/config_code/config_name 筛选]
)
SELECT
    b.country, b.category, b.config_code, b.config_name,
    b.data_type, b.ttl,
    a.version_date,
    c.dt AS period_date,
    COALESCE(d.quantity, 0) AS quantity
FROM (subquery_a) a                                          -- a: dsp_uploads
JOIN (SELECT DISTINCT country, category, ... FROM base_rows) b
    ON b.upload_id = a.upload_id                             -- 横向业务行
CROSS JOIN (subquery_c) c                                    -- 纵向：week_dt
LEFT JOIN (subquery_d) d                                     -- 交叉点 quantity
    ON d.upload_id = a.id AND d.id = b.row_id AND d.date = c.dt
ORDER BY c.dt
```

> **v0.5.7 变更**：
> - `base_rows` CTE 过滤条件从 `data_type = 'Demand'` 改为 `data_type IN ('Demand', 'Supply')`，覆盖两种模式。
> - `demand` 模式下 `b` 子查询 GROUP BY 仍含 `data_type`，保留 `data_type='Demand'` 的去重行；`demand_plus_supply` 模式下 `b` 子查询 GROUP BY **去掉 `data_type`**，仅按业务维度去重，使 Demand 和 Supply 配对到同一业务组（详见 §11）。
> - `demand` 模式的 SQL 主路径不变；`demand_plus_supply` 模式的 TTL_GAP / Rolling_TTLGAP 计算在 Python 层完成（详见 §11.3），不引入额外 SQL 复杂度。
>
> **v0.5.9 变更**：`query_diff` 是纯 Python 层后处理，**SQL 主路径完全不变**——`_query_demand` 末尾调用 `_apply_diff_filter(resp, version_dates_len)`，过滤 `period_columns` 与每个 `row_group.quantities` 的 key 集合；详见 §12。

### 4. 入参 `PivotQueryRequest`

| 字段 | 类型 | 必填 | 校验 |
|------|------|------|------|
| `pivot_type` | `'demand' \| 'demand_plus_supply'` | 是 | `'demand'` 固定过滤 `data_type='Demand'`；`'demand_plus_supply'` 查询 Demand + Supply 并计算 TTL_GAP / Rolling_TTLGAP（见 §11） |
| `vendor` | string (1-64) | 是 | — |
| `item` | string (1-128) | 是 | — |
| `sub_item` | string (1-128) | 是 | — |
| `version_dates` | list[string] | 是 | 每项 `YYYY-MM-DD`；`demand` 模式 1-20 个（多选）；`demand_plus_supply` 模式**仅 1 个**（单选，超限 → 422，见 §11.1） |
| `countries` | list[string] | 否 | — |
| `categories` | list[string] | 否 | **级联**：传 `config_names` 时必填 |
| `config_codes` | list[string] | 否 | — |
| `config_names` | list[string] | 否 | **级联**：传时必填 `categories` → 必填 `countries` |
| `years` | list[int] | 否（必传其一） | **级联**：传 `months` 时必填；传 `weeks` 时必填 |
| `months` | list[int] (1-12) | 否 | **级联**：传 `weeks` 时必填 |
| `weeks` | list[int] (1-53) | 否 | **级联**：传时必填 `years` AND `months` |
| `expand_to_daily` | bool (default false) | 否 | true 时去掉 `is_week_start=1` 过滤，按每天展开 |
| `query_diff` | bool = `True` | 否 | **仅 `pivot_type='demand'` 生效**；true 时按业务组比较所有 version_date 在每个 period_date 上的 quantity：全部相等则该日期从 `period_columns` 与各 `quantities` 中移除，否则保留原值；false 沿用 v0.5.7 baseline；`len(version_dates) <= 1` 时函数内部直接跳过（与配置无关） |

### 5. 出参 `PivotQueryResponse`

`demand` 模式示例：

```json
{
  "period_columns": ["2026-07-06", "2026-07-13", "2026-07-20"],
  "row_groups": [
    {
      "country": "爱尔兰",
      "category": "交换机整机",
      "config_code": "X123",
      "config_name": "32Q-TOR-T3",
      "data_type": "Demand",
      "ttl": 4,
      "version_date": "2026-06-29",
      "quantities": {
        "2026-07-06": 100,
        "2026-07-13": 0,
        "2026-07-20": 50
      }
    }
  ],
  "total_rows": 1,
  "version_dates": ["2026-06-29"],
  "date_granularity": "week"
}
```

`demand_plus_supply` 模式示例（每业务组产出 4 行：Demand / Supply / TTL_GAP / Rolling_TTLGAP）：

```json
{
  "period_columns": ["2026-07-06", "2026-07-13", "2026-07-20"],
  "row_groups": [
    {
      "country": "爱尔兰",
      "category": "交换机整机",
      "config_code": "X123",
      "config_name": "32Q-TOR-T3",
      "data_type": "Demand",
      "ttl": 4,
      "version_date": "2026-06-29",
      "quantities": {
        "2026-07-06": 100,
        "2026-07-13": 80,
        "2026-07-20": 50
      }
    },
    {
      "country": "爱尔兰",
      "category": "交换机整机",
      "config_code": "X123",
      "config_name": "32Q-TOR-T3",
      "data_type": "Supply",
      "ttl": 4,
      "version_date": "2026-06-29",
      "quantities": {
        "2026-07-06": 120,
        "2026-07-13": 90,
        "2026-07-20": 60
      }
    },
    {
      "country": "爱尔兰",
      "category": "交换机整机",
      "config_code": "X123",
      "config_name": "32Q-TOR-T3",
      "data_type": "TTL_GAP",
      "ttl": 4,
      "version_date": "2026-06-29",
      "quantities": {
        "2026-07-06": 20,
        "2026-07-13": 10,
        "2026-07-20": 10
      }
    },
    {
      "country": "爱尔兰",
      "category": "交换机整机",
      "config_code": "X123",
      "config_name": "32Q-TOR-T3",
      "data_type": "Rolling_TTLGAP",
      "ttl": 4,
      "version_date": "2026-06-29",
      "quantities": {
        "2026-07-06": 20,
        "2026-07-13": 30,
        "2026-07-20": 40
      }
    }
  ],
  "total_rows": 4,
  "version_dates": ["2026-06-29"],
  "date_granularity": "week"
}
```

> **v0.5.7 变更**：`demand_plus_supply` 模式下 `row_groups` 中每组业务维度产出 4 行（`data_type` 依次为 `Demand` / `Supply` / `TTL_GAP` / `Rolling_TTLGAP`），TTL_GAP 和 Rolling_TTLGAP 的计算规则详见 §11。

`demand` 模式 + `query_diff=true` 示例（2 个版本，3 个日期中仅 1 个有差异）：

```json
{
  "period_columns": ["2026-07-13"],
  "row_groups": [
    {
      "country": "爱尔兰",
      "category": "交换机整机",
      "config_code": "X123",
      "config_name": "32Q-TOR-T3",
      "data_type": "Demand",
      "ttl": 4,
      "version_date": "2026-06-15",
      "quantities": { "2026-07-13": 80 }
    },
    {
      "country": "爱尔兰",
      "category": "交换机整机",
      "config_code": "X123",
      "config_name": "32Q-TOR-T3",
      "data_type": "Demand",
      "ttl": 4,
      "version_date": "2026-06-29",
      "quantities": { "2026-07-13": 90 }
    }
  ],
  "total_rows": 2,
  "version_dates": ["2026-06-15", "2026-06-29"],
  "date_granularity": "week"
}
```

> **v0.5.9 变更**：`query_diff=true` 时 `period_columns` 仅含跨版本有差异的日期；`quantities` 仅保留这些日期的 key；`quantity` 为原始值（**不**计算 delta）。完整算法 / 边界 / 多业务组示例见 §12。

### 6. 数据量保护

| 保护项 | 触发 | 行为 |
|--------|------|------|
| **笛卡尔积预检** | `\|b\| × \|c\| > 50000` | 422 + detail `"cartesian product estimated N rows exceeds limit 50000; please narrow business row filters or date range"` |
| **必须传时间维度** | `years/months/weeks` 都未传 | Pydantic 422 |
| **级联校验** | 违反任一级联规则 | Pydantic 422 |
| **`week_dt` 表不存在** | 首次访问 | 500（运维责任：本项目不创建该表） |
| **demand_plus_supply 版本日期单选** | `pivot_type='demand_plus_supply'` 且 `len(version_dates) > 1` | Pydantic 422 |

### 7. 错误约定

| HTTP | 场景 |
|------|------|
| 422 | Pydantic 级联校验失败 / 笛卡尔积预检超出 / **`pivot_type='demand_plus_supply'` 时 `version_dates` 超过 1 个** |
| 500 | SQLAlchemy 异常（如 `week_dt` 表不存在 / DB 不可达） |

### 8. 不实现的组件（明确范围）

- **透视结果缓存**：首次实现不引入。
- **按行/列细粒度排序**：默认 `ORDER BY c.dt`（period_date 升序），不支持自定义排序。
- **`week_dt` 表创建**：外部依赖，由调用方保证表存在。
- **跨版本 quantity 合并**：每个 `version_date` 独立成行（`row_groups` 中是分开的对象），不合并求和。
- **透视结果分页**：单次响应无分页，硬上限通过笛卡尔积预检保证。
- **多表 JOIN 优化**：使用 CTE 共享 dsp_upload_rows 一次扫描；不引入物化视图。
- **TTL_GAP / Rolling_TTLGAP 落库**：两个派生 data_type 是纯运算结果，不写入 `dsp_upload_rows`，每次查询实时计算（详见 §11.4）。
- **空 row_group 保留**（v0.5.9 新增）：`query_diff=true` 过滤后某业务组的某些 row_group 可能 `quantities={}`（该版本的全部日期均被剪除），**仍保留**该 row_group 的元信息（country/category/config_code/config_name/data_type/ttl/version_date），仅 quantities 为空。目的：保留"该版本存在但与其它版本无任何差异日期"的诊断信号；如未来用户希望彻底丢弃，单独开 PR（不沿用 §11 的"保留"约定是因为 §11 的"4 行"是数据语义而非诊断语义）。

### 9. Test Plan（新增）

测试位于 `backend/tests/test_pivot_query.py`：

1. **级联校验失败**：
   - 传 `config_names` 不传 `categories` → 422
   - 传 `categories` 不传 `countries` → 422
   - 传 `weeks` 不传 `years` / `months` → 422
   - 传 `months` 不传 `years` → 422
   - 时间维度一个都不传 → 422
   - `version_dates` 含非法日期格式 → 422
   - `months` 含 13 / `weeks` 含 54 → 422
2. **`estimate_size` 正确性**：
   - 无业务行 → 估算 = 0
   - `|b|` 和 `|c|` 分别为 2 / 3 → 估算 = 6
   - 传 `countries=['爱尔兰']` 过滤 → 估算只数 `country='爱尔兰'` 行
3. **`MAX_CARTESIAN` 超限**（monkeypatch 调低阈值）→ API 422
4. **正常路径**：
   - 单版本 + 单业务行 + 多周起始日 → COALESCE 兜底为 0
   - `expand_to_daily=True` → 7 列（周一至周日），只有当天有数据
   - 多版本 → 每个版本独立 row_group
   - `Supply` 行被 `data_type='Demand'` 过滤
   - 空数据（version_date 不存在）→ 空 `row_groups`
   - `countries` 过滤生效
5. **API 端到端**：POST `/api/pivot-query` 正常返回 / 级联校验失败 / 笛卡尔积超限

#### 9.5 `query_diff` 过滤（v0.5.9 新增）

1. **`test_query_diff_default_true_single_version`**：默认 `query_diff=True` + `len(version_dates)=1` → 函数内部判定 → 跳过过滤，输出与 v0.5.7 baseline 完全相同。
2. **`test_query_diff_false_keeps_baseline`**：显式 `query_diff=False` + 多版本 → v0.5.7 行为不变：所有日期保留、各 row_group `quantities` 为原值。
3. **`test_query_diff_strict_equal_drops_date`**：`query_diff=True` + 2 个版本 + 某日期两版 quantity 相同 → 该日期从 `period_columns` 移除，并从**所有**业务组所有 row_group 的 `quantities` 中移除。
4. **`test_query_diff_partial_diff_keeps_date`**：3 个日期中 2 个有差异、1 个全等 → 2 个差异日期进入 `period_columns`、1 个全等日期移除；`quantities[p]` 为原值（**不**是 delta）。
5. **`test_query_diff_multi_business_groups_union_columns`**：业务组 A 仅有 p1 差异、业务组 B 仅有 p2 差异 → `period_columns = [p1, p2]`（并集）；A 的 quantities 仅含 `p1`，B 的 quantities 仅含 `p2`。
6. **`test_query_diff_does_not_affect_demand_plus_supply`**：`pivot_type='demand_plus_supply'` + `query_diff=True` → 仍输出 4 行（Demand/Supply/TTL_GAP/Rolling_TTLGAP），`period_columns` 全保留。

### 10. Assumptions

1. **`week_dt` 表由外部系统维护**，本项目不创建、不修改、不删除。
2. **MySQL `tinyint(1)` ↔ SQLAlchemy `Boolean`** 映射兼容；SQLite 测试用 0/1 模拟。
3. **不引入新的依赖**：透视查询全部走 SQLAlchemy + Python 标准库；不需要 `pandas`。
4. **`MAX_CARTESIAN=50000`** 是经验值，预留空间给后续 GROUP BY / 排序优化；如有需要可调。
5. **`config_code` 同样可作筛选字段**：虽不在前端 UI 必选字段内，但 SQL 层支持精确匹配。
6. **CTE 在 SQLite/MySQL 上语法兼容**：本项目所有 SQL 文本不出现 `CURDATE()` / `NOW()` 等数据库内置日期函数。
7. **单用户本地版**维持不变：不引入登录、不引入多租户。

---

### 11. Demand+Supply 计算规则（v0.5.7 新增）

> `pivot_type='demand_plus_supply'` 时启用以下逻辑；`pivot_type='demand'` 时完全不受影响，沿用 §3 的主查询路径。

#### 11.1 入参约束

- `version_dates` 仅允许 1 个元素（单选）；Pydantic 校验 `len(version_dates) > 1` → 422（详见 §6 / §7）。
- 其余字段（vendor / item / sub_item / countries / categories / years / months / weeks / expand_to_daily）与 `demand` 模式一致。

#### 11.2 数据查询

- `base_rows` CTE 过滤条件：`data_type IN ('Demand', 'Supply')`（不再固定为 `'Demand'`），一次扫描同时取两种 data_type。
- `b` 子查询 GROUP BY **去掉 `data_type` 与 `ttl`**，仅按 `(upload_id, country, category, config_code, config_name)` 去重，使同一业务维度（含不同 ttl 的事实行）配对到同一组；TTL 在响应作为展示字段，b 子查询 SELECT 用 `COALESCE(MAX(ttl), 0)` 兜底（NULL 当 0）——v0.5.7.4 修订：ttl 不再作为分组 key，业务上 ttl 是「总数」语义而非产品配置。
- `d` 子查询保留 `data_type` 字段，供 Python 层区分 Demand / Supply。
- `a` / `c` 子查询与 `demand` 模式完全相同。

> **v0.5.7.4 修订**：ttl 字段语义是「总数」（不是产品配置参数）。同一 `(country, category, config_code, config_name, version_date)` 下若存在 `ttl=100` 与 `ttl=NULL` 两条事实行（例如不同周的事实行分别入库时 ttl 一致为 100 / 另一周被推断为 NULL），聚合为同一组；TTL 列展示值取 `MAX(ttl)` 兜底（NULL 当 0）。修复前 group_key 含 ttl 会导致同 (country, cat, code, name, version_date) 因 ttl 差异拆出多组（每组 4 行），用户看到"重复"。

#### 11.3 Python 层后计算

SQL 返回原始行后，Python 层按以下步骤生成最终 `row_groups`：

1. **分组**：按 `(country, category, config_code, config_name, version_date)` 分组（**v0.5.7.4** 去掉 ttl）。
2. **拆分**：每组内按 `data_type` 拆为 Demand 行和 Supply 行。
3. **缺失兜底**：某组只有 Demand 没有 Supply → Supply quantity 视为 0；反之亦然。
4. **生成原始行**：保留 Demand 行和 Supply 行（与 `demand` 模式格式一致）。
5. **计算 TTL_GAP**：
   - 按 `period_date` 升序排列所有日期。
   - `TTL_GAP[period_date] = Supply.quantity[period_date] − Demand.quantity[period_date]`。
   - 生成一行 `data_type='TTL_GAP'` 的记录，其余业务维度与该组相同。
6. **计算 Rolling_TTLGAP**：
   - 按 `period_date` 升序排列 TTL_GAP。
   - `Rolling_TTLGAP[0] = TTL_GAP[0]`。
   - `Rolling_TTLGAP[i] = Rolling_TTLGAP[i−1] + TTL_GAP[i]`（i ≥ 1）。
   - 生成一行 `data_type='Rolling_TTLGAP'` 的记录。
7. **合并**：每组最终产出 4 行（Demand / Supply / TTL_GAP / Rolling_TTLGAP），全部加入 `row_groups`。

#### 11.4 TTL_GAP / Rolling_TTLGAP 不落库

TTL_GAP 和 Rolling_TTLGAP 是纯运算结果，**不写入** `dsp_upload_rows` 表。每次查询实时计算，仅在响应中返回。

#### 11.5 date_granularity 兼容

TTL_GAP / Rolling_TTLGAP 的计算基于 `period_date`，与 `demand` 模式完全一致：
- `expand_to_daily=False`（默认）→ `period_date` 为周起始日，按周聚合。
- `expand_to_daily=True` → `period_date` 为每一天，按日聚合。

#### 11.6 示例

假设某分组 `(Country=爱尔兰, Category=交换机整机, ConfigCode=X123, ConfigName=32Q-TOR-T3, TTL=4)` 在版本日期 `2026-06-29` 下：

| period_date | Demand | Supply | TTL_GAP | Rolling_TTLGAP |
|-------------|--------|--------|---------|----------------|
| 2026-07-06  | 100    | 120    | 20      | 20             |
| 2026-07-13  | 80     | 90     | 10      | 30             |
| 2026-07-20  | 50     | 60     | 10      | 40             |

该分组在 `row_groups` 中产出 4 行，每行含 3 个 `period_date` 的 `quantity`：
- `data_type='Demand'` 行：`{06: 100, 13: 80, 20: 50}`
- `data_type='Supply'` 行：`{06: 120, 13: 90, 20: 60}`
- `data_type='TTL_GAP'` 行：`{06: 20, 13: 10, 20: 10}`
- `data_type='Rolling_TTLGAP'` 行：`{06: 20, 13: 30, 20: 40}`

完整 JSON 示例见 §5。

---

## Demand 跨版本 diff 过滤（v0.5.9 新增）

> **定位**：在 v0.5.7 「透视查询 - demand 模式」既有 `_query_demand` 主路径末尾追加 1 个纯 Python 后处理函数 `_apply_diff_filter`，按业务维度把多 version_date 的 row_groups 聚合，对每个 period_date 比较所有版本 quantity 是否全部相等；**全等则该日期移除，否则保留**。
>
> **范围声明**：SQL 主路径 0 改动；新字段 `query_diff: bool = True` 仅 `PivotQueryRequest` 增 1 行；`POST /api/pivot-query` 入口不变；`POST /api/pivot-query/export` 自动协同。
>
> **作用域**：**仅** `pivot_type='demand'` 接通；`demand_plus_supply` 与该特性正交，不调用该函数。

### 12.1 业务目标

用户在前端同时选多个版本日期（典型 2~5 个，v0.5.6 上限 20）做横向对比时，绝大多数日期的 quantity 在版本之间是稳定的（无变化），期望：

- **有变化**的日期：保留在 `period_columns`，各 row_group `quantities[p]` 用原值，让前端渲染"这一行出现了 N 个非等值"，方便定位差异点；
- **无变化**的日期：**剪除**，避免满屏无意义空白 / 重复值，让用户把注意力聚焦在差异上。

不做 delta（差异值）计算——保留原值由前端自由渲染（高亮 / 上色 / 标记）。

### 12.2 「变化」语义

```
对每个 (业务维度组 G, period_date p):
  Q = { quantity of (G, v, p) | v ∈ version_dates }   # 取各版本在该日的 quantity，缺则视作 0
  变化 ⇔ |Q| > 1 且 max(Q) ≠ min(Q)                   # 即 set(Q) 元素数 ≥ 2
  无变化 ⇔ set(Q) 大小 == 1
```

判定等价于 Python：`len({row.quantities.get(p, 0) for row in group_rows}) > 1` 为保留。

### 12.3 算法

```python
def _apply_diff_filter(
    resp: PivotQueryResponse,
    version_dates_len: int,
) -> PivotQueryResponse:
    """query_diff 后处理；纯函数，对响应按业务维度聚合后裁掉全等日期。"""
    if version_dates_len <= 1:
        return resp  # 单版本无对比对象，沿用 baseline

    BIZ_KEY = ("country", "category", "config_code", "config_name",
               "data_type", "ttl")

    # 1. 按业务维度聚合 row_groups（跨 version_date）
    groups: dict[tuple, list[PivotRow]] = {}
    for r in resp.row_groups:
        k = tuple(getattr(r, k) for k in BIZ_KEY)
        groups.setdefault(k, []).append(r)

    # 2. 对每个业务组求保留日期集合
    new_rows: list[PivotRow] = []
    global_kept: set[str] = set()
    for rows in groups.values():
        all_dates: set[str] = set()
        for r in rows:
            all_dates.update(r.quantities.keys())

        kept_for_group: set[str] = {
            p for p in all_dates
            if len({r.quantities.get(p, 0) for r in rows}) > 1
        }
        global_kept |= kept_for_group

        for r in rows:
            r.quantities = {p: v for p, v in r.quantities.items()
                            if p in kept_for_group}
            new_rows.append(r)
            # 注意：quantities={} 也保留，详见 §12.5 边界

    new_period_columns = sorted(global_kept)
    return PivotQueryResponse(
        period_columns=new_period_columns,
        row_groups=new_rows,
        total_rows=len(new_rows),
        version_dates=resp.version_dates,
        date_granularity=resp.date_granularity,
    )
```

调用点：`_query_demand()` 末尾在 `req.query_diff is True and len(req.version_dates) > 1` 时调用一次；`_query_demand_plus_supply()` **不**调用（保持 §11 语义）。

### 12.4 步骤示意

1. SQL 按 v0.5.7 `_query_demand` 主路径查 `base_rows`，输出 `PivotQueryResponse`：
   - `period_columns` = 所有版本所有 period_date 的日期（按字典序排）
   - `row_groups` 每条含 `(业务维度, version_date, quantities: {date: qty})`
2. 按 `BIZ_KEY` 把 row_groups 分组（每组跨 N 个 version_date）。
3. 对每个业务组求 `kept_for_group`（全集减去全等日期）。
4. 各 row_group 的 `quantities` 过滤为 `kept_for_group` 子集（**含空**）。
5. `period_columns` 取所有业务组 `kept_for_group` 的**并集**，排序。

### 12.5 边界与陷阱

| 场景 | 行为 |
|------|------|
| `len(version_dates) <= 1` | 函数入口直接返回 baseline；即使 `query_diff=true` 也无变化，便于「同一接口多版本复用」 |
| 单版本多业务组 | `version_dates_len <= 1` 守卫直接命中 → baseline |
| 多版本但某业务组 N 个 quantity 全为 0 | 同版本即视作「全等」，该日期被剪除（0 等于 0） |
| 多版本某行不存在该日期（None） | 该版本 quantity 视作 0（`quantities.get(p, 0)`），参与比对 |
| 过滤后某 row_group quantities 为空 | **仍保留该 row_group**（quantities={}），用于诊断；如未来需丢弃另开 PR |
| 多业务组保留集不同 | `period_columns` 取**并集**；不在某组保留集的日期对应 group 的 `quantities` 不含该 key |
| `expand_to_daily=True` | 算法对日/周通用——`period_date` 字符串按字典序等价日期序 |
| `quantity` 类型 | 入库即 `int`（COALESCE 兜底），不出现浮点歧义 |
| `week_dt` 表不存在 | 沿用既有 500 行为；`_apply_diff_filter` 在 SQL 之后运行 |
| 笛卡尔积预检 | 沿用 `MAX_CARTESIAN=50000`；**预检在 SQL 之前**，不受 `_apply_diff_filter` 影响 |

### 12.6 多业务组示例

输入：2 个版本 `[2026-06-15, 2026-06-29]`，2 个业务组 A 与 B（业务维度不同），3 个日期：

```
业务组 A (爱尔兰 / 交换机整机 / X123 / 32Q-TOR-T3):
  period_date    v1 (06-15)   v2 (06-29)
  2026-07-06     100          100   # 全等
  2026-07-13     80           90    # 差异
  2026-07-20     50           50    # 全等

业务组 B (马来西亚 / 光模块 / Y456 / 100G-LR4):
  period_date    v1 (06-15)   v2 (06-29)
  2026-07-06     30           30    # 全等
  2026-07-13     50           50    # 全等
  2026-07-20     20           35    # 差异
```

`query_diff=true` 输出：

- `period_columns = ["2026-07-13", "2026-07-20"]`（并集）
- 业务组 A 的 2 个 row_group：`quantities = {"2026-07-13": 80}` 与 `{"2026-07-13": 90}`
- 业务组 B 的 2 个 row_group：`quantities = {"2026-07-20": 20}` 与 `{"2026-07-20": 35}`

注意每个 row_group **不包含**对方业务组的差异日期 key，符合"按业务组局部判定"的算法。

### 12.7 与 `POST /api/pivot-query/export` 协同

`excel_export.py::build_pivot_xlsx` 沿用同一 `query_pivot` 路径，对 `demand` 模式自动应用 `_apply_diff_filter`——`period_columns` 缩短 → 导出 xlsx 列数同步减少。`Sheet 1` 的列结构已按 `period_columns` 动态生成（v0.5.8 §5.1），无须改 `excel_export.py`。

> **`demand_plus_supply` 模式 + `query_diff=true`**：配置允许但 `_apply_diff_filter` 不接通，等价于 baseline。前端若误传不影响 4 行（Demand/Supply/TTL_GAP/Rolling_TTLGAP）的业务语义。

### 12.8 不实现的组件（明确范围）

- ❌ **delta / 差异值计算**：保留原 quantity，不输出 `delta` / `change` 字段；如未来需要另开 PR。
- ❌ **`query_diff` 在 `demand_plus_supply` 模式下生效**：刻意不接通，保持 4 行结构稳定；如未来需要再扩展。
- ❌ **「首版绝对值差异标记」**：仅做"剪除"语义，不在响应中标注"该日首次出现变化是哪个版本"；前端可用 `version_date` 配合 `quantities` 反推。
- ❌ **`query_diff` 仅剪不留**：空 row_group 不删除（保留诊断信息）。
- ❌ **新版 Pydantic 校验规则**：不新增 §6 数据量保护项；笛卡尔积上限仍以「过滤前」为基数。
- ❌ **OpenAPI 拆分**：不引入新的 sub-route（如 `/api/pivot-query/diff`）；特性作为 `PivotQueryRequest` 字段内嵌。

### 12.9 Test Plan

详见 §9.5 的 6 条用例：

1. `test_query_diff_default_true_single_version`
2. `test_query_diff_false_keeps_baseline`
3. `test_query_diff_strict_equal_drops_date`
4. `test_query_diff_partial_diff_keeps_date`
5. `test_query_diff_multi_business_groups_union_columns`
6. `test_query_diff_does_not_affect_demand_plus_supply`

### 12.10 Assumptions（新增）

1. **应用前判定**：`len(version_dates) <= 1` 时 `_apply_diff_filter` 直接 no-op；与 `query_diff` 配置无关，保证"配置开启但单版本调用"的常见场景不改变响应。
2. **业务维度 key 固定为 6 字段** `(country, category, config_code, config_name, data_type, ttl)`，与 §11.3 步骤 1 一致（v0.5.7.4 修订后 ttl 不入 group_key，但 diff 过滤仍保留 ttl 作为「不同 ttl = 不同业务组」语义）。
3. **「缺失视为 0」语义**：与 SQL `COALESCE(d.quantity, 0)` 一致；diff 过滤内 `quantities.get(p, 0)` 亦遵循此约定。
4. **排序等价**：ISO 日期 `YYYY-MM-DD` 字符串字典序等价于日期序，`sorted(global_kept)` 即 `sorted(period_dates)`。
5. **不影响 `estimate_size`**：笛卡尔积预检在 `_query_demand` 入口处独立运行（`estimate_size` 用 `b_cols × c_rows`），与过滤无关；通过也不保证响应小，仅保证 SQL 安全。
6. **单用户本地版**沿用既有约束；不引入登录、多租户。

---

## Excel 导出子模块（v0.5.8 新增）

> **定位**：在 v0.5.7 既有「周需求 - 查询」与「透视查询」两个**只读**子模块上各加一个独立 export 端点，把查询结果直接转成 `.xlsx` 二进制流供浏览器下载。
>
> **范围声明**：仅导出；不写库，不影响上传 / 删除子功能；不引入异步任务、不落盘、不做样式美化。

### 1. 业务目标

让用户在前端对查询 / 透视结果一键下载 Excel，便于：
- 跨版本日期的对照（pivot export）；
- 跨业务行的批量数据分析（rows export）；
- 与本地 Excel 模板拼接后再做二次处理。

### 2. 新增依赖

| 包 | 版本约束 | 用途 |
|----|----------|------|
| `pandas` | `>=2.0` | 构造 DataFrame；通过 `engine='openpyxl'` 写 xlsx |
| `openpyxl` | 已存在 (`>=3.1`) | pandas 写 xlsx 的底层引擎；不直接 import |

按 AGENTS.md §Python 环境 写入 `backend/requirements.txt` 并在 `dev_env` 安装。

### 3. 端点总览

| 方法 | 路径 | 对应 JSON 端点 | 子模块 |
|------|------|----------------|--------|
| GET  | `/api/dsp-uploads/{id}/rows/export` | `GET /api/dsp-uploads/{id}/rows` | 周需求 - 查询 |
| POST | `/api/pivot-query/export` | `POST /api/pivot-query` | 透视查询 |

> 选「独立 export 端点」而不是 `?format=xlsx` 拼接：响应类型从 JSON 切到 binary 走 `StreamingResponse`，与原路由的 JSON serializer 解耦，避免一个路由里同时维护两套序列化路径。

### 4. GET /api/dsp-uploads/{id}/rows/export

| 项 | 值 |
|----|----|
| Path param | `id: int`（batch 主键） |
| Query param | 无 |
| 响应类型 | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| 响应体 | 二进制 xlsx 流（`StreamingResponse` 包 `BytesIO`） |
| 响应头 | `Content-Disposition: attachment; filename="dsp_upload_{id}_rows_{YYYYMMDD_HHMMSS}.xlsx"` |
| 行数上限 | `MAX_DSP_EXPORT_ROWS = 200_000`（超过 → 422） |

#### 4.1 Sheet 「事实行」（单 sheet）

| 列 | 来源 | 备注 |
|----|------|------|
| ID | `dsp_upload_rows.id` | 自增主键 |
| 上传批次ID | `upload_id` | 与 batch.id 一致 |
| 国家 | `country` | `None → ""` |
| 类别 | `category` | |
| 配置代码 | `config_code` | |
| 配置名称 | `config_name` | v0.5.5 新 |
| 数据类型 | `data_type` | 仅 `Demand` / `Supply` |
| TTL | `ttl` | `None → ""` |
| 年月 | `ym` | `YYYY-MM` |
| 周编号 | `week` | `WK01` |
| 周起始日 | `date` | `YYYY-MM-DD` |
| 数量 | `quantity` | int |

#### 4.2 错误约定

| HTTP | 场景 |
|------|------|
| 404 | batch 不存在 |
| 422 | 事实行 > 200,000；detail：`"导出行数 N 超过上限 200000；请缩小时间范围或拆分批次"` |
| 500 | SQLAlchemy / pandas / openpyxl 异常 |

### 5. POST /api/pivot-query/export

| 项 | 值 |
|----|----|
| Body | 与 `POST /api/pivot-query` 字段完全相同（复用 `PivotQueryRequest`，不重新定义 schema） |
| 响应类型 | 同 §4，xlsx 二进制 |
| 文件名 | `pivot_{pivot_type}_{YYYYMMDD_HHMMSS}.xlsx`（纯 ASCII，不嵌入 vendor/item 等可能含中文的字段，避免 RFC 5987 编码歧义） |
| 限制 | 仍走 `MAX_CARTESIAN = 50_000`（路由层 `estimate_size` 预检，超限 → 422） |

#### 5.1 Sheet 1「透视结果」

| 列 | 来源 |
|----|------|
| 国家 | `row.country` |
| 类别 | `row.category` |
| 配置代码 | `row.config_code` |
| 配置名称 | `row.config_name` |
| 数据类型 | `row.data_type`（`Demand` / `Supply` / **`TTL_GAP`** / **`Rolling_TTLGAP`**，与 `row_groups` 顺序一致） |
| TTL | `row.ttl` |
| 版本日期 | `row.version_date` |
| `<period_date_1>` | `row.quantities[period_columns[0]]` |
| ... | ... |
| `<period_date_N>` | `row.quantities[period_columns[N-1]]` |

按 v0.5.8 决策：`TTL_GAP` / `Rolling_TTLGAP` 作为 4 行之一，**不折叠为列**——与 `row_groups` 1:1 对应，用户用透视查询得到 N 行，导出的 sheet 也是 N 行；保留 data_type 维度一致性。

#### 5.2 Sheet 2「查询参数快照」（审计用）

| pivot_type | vendor | item | sub_item | version_dates |
|------------|--------|------|----------|---------------|
| `demand` / `demand_plus_supply` | `str` | `str` | `str` | `; ` 拼接的 `YYYY-MM-DD` 列表 |

固定 1 行 5 列；v0.5.8 不支持 query 参数关掉，先固定包含。

#### 5.3 错误约定

| HTTP | 场景 |
|------|------|
| 422 | Pydantic 级联校验失败 / 笛卡尔积超限 / `demand_plus_supply` 多 version_date |
| 500 | SQLAlchemy / pandas / openpyxl 异常 |

### 6. 通用约定（两端点共享）

1. **内存流式生成**：`pandas.DataFrame.to_excel(BytesIO(), index=False, engine='openpyxl')` → FastAPI `StreamingResponse(BytesIO(getvalue()), media_type=...)`；不落盘，不引入异步任务。
2. **时间戳格式**：`_export_timestamp()` 输出 `YYYYMMDD_HHMMSS`，由 Python `datetime.now()` 生成，**不依赖** DB 函数（与项目 `created_at` 惯例一致）。
3. **空数据**：`row_groups=[]` 或 `fact_rows=[]` → 仍返回带表头的 xlsx，前端可正常打开。
4. **行号字段**：导出 DspUploadRow 时**不**包含「行号」自增列（避免与 `id` 语义混淆）；用户按 `id` 排序即可还原原始顺序。
5. **列宽自适应**：每列宽 = `max(len(header), max(len(str(cell)) for cell in col)) + 2`，上限 50；不识别中英文宽度比（中文 1 字 ≈ 1 字符），v0.5.8 不做精确宽度测算。
6. **`pivot_type` 不影响列结构**：Demand / Demand+Supply 共用同一份 schema；`TTL_GAP` / `Rolling_TTLGAP` 行仅在 `demand_plus_supply` 时出现。
7. **公式注入防护**：字符串 cell 若首字符 ∈ `{=, +, -, @, \t, \r}` → 加单引号前缀（`'='123'`），避免 Excel 误执行；数值 cell 不防护。

### 7. 文件结构新增

```
backend/app/
├── api/
│   ├── dsp_uploads.py        # 新增 rows_export_endpoint
│   └── pivot_query.py        # 新增 pivot_export_endpoint
└── services/
    └── excel_export.py       # 新增：build_dsp_rows_xlsx / build_pivot_xlsx /
                              #       _export_timestamp / _sanitize_formula
```

`excel_export.py` 是纯函数模块，不依赖 DB / FastAPI，便于单测。两个端点都通过它构造 BytesIO。

### 8. 不实现的组件（明确范围）

- ❌ 不生成 CSV / PDF；只支持 `.xlsx`
- ❌ 不支持用户自定义文件名 / 自定义列顺序
- ❌ 不做样式美化（颜色 / 边框 / 合并单元格 / 冻结窗格）
- ❌ 不做异步任务 / 进度查询（同步阻塞返回；单文件通常 < 5 MB）
- ❌ 不做服务端压缩（`.xlsx` 本身已 zip 压缩）
- ❌ 不支持远程 OSS / 邮件发送下载链接
- ❌ DspUploadRow 导出**不**附加查询参数快照 sheet（仅 pivot 导出有）
- ❌ 不暴露内部 pandas / openpyxl 异常给前端，统一 500 + 中文 detail
- ❌ 不实现 sheet 2「查询参数快照」的开关 query 参数（v0.5.8 固定包含）

### 9. Test Plan（新增）

文件：`backend/tests/test_dsp_export.py` 和 `backend/tests/test_pivot_export.py`。

#### 9.1 DspUploadRow 导出

1. **200 正常路径**：构造 batch + 10 行 → 下载 → 用 openpyxl 重新打开 → 断言列头、行数、单元格内容与 JSON 端点 `GET /api/dsp-uploads/{id}/rows` 一致
2. **200 空数据**：构造 batch（0 行）→ 表头 12 列、1 行（表头行）
3. **404**：`id` 不存在
4. **422 超限**：构造 batch 含 200,001 行 → 422 + 中文 detail `"导出行数 N 超过上限 200000；…"`
5. **响应头检查**：`Content-Type == application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`；`Content-Disposition` 含 `filename="dsp_upload_{id}_rows_*.xlsx"`
6. **公式注入防护**：构造一行 `country='=1+1'` → 打开后 cell 值前缀 `'=`

#### 9.2 透视导出

1. **200 demand 模式**：sheet 1 列头 = `[7 列基础] + period_columns`，行数 = `len(row_groups)`
2. **200 demand_plus_supply 模式**：sheet 1 含 `TTL_GAP` / `Rolling_TTLGAP` 行（每业务组 4 行）
3. **200 sheet 2 快照**：内容为 `pivot_type / vendor / item / sub_item / version_dates`，version_dates 用 `; ` 拼接
4. **422 级联校验失败**：与 JSON 端点行为一致（沿用既有 pivot 测试 fixture）
5. **422 笛卡尔积超限**：`monkeypatch` 调低 `MAX_CARTESIAN` → 422
6. **422 demand_plus_supply 多 version_date**：与 JSON 端点行为一致
7. **200 空数据**：`row_groups=[]` → sheet 1 只有表头 1 行，sheet 2 快照仍正确

### 10. Assumptions（新增）

1. pandas 与 openpyxl 在 dev_env 已安装；按 AGENTS.md §Python 环境约束。
2. 单次导出同步返回，不引入 Celery / Redis 等异步队列。
3. 200,000 行 / 50,000 笛卡尔积的硬上限沿用既有 §MAX_CARTESIAN 设计思路，作为内存安全阈值。
4. Excel 列宽自适应算法是「字符串宽度」，不识别中英文宽度比。如未来需要精确宽度，加 `wcwidth` 或 Pillow 测算（v0.5.8 不做）。
5. 公式注入防护遵循 OWASP「CSV Injection」思路，扩展到 Excel；规则与 §6.7 一致。
6. sheet 2「查询参数快照」是 v0.5.8 固定包含；如未来需要关掉，可加 `?include_params_snapshot=false` query 参数（v0.5.8 不实现）。
7. 路径参数 `id` 仍走 `crud.dsp_upload.get_upload(db, id)` 校验存在性，与 `GET /api/dsp-uploads/{id}` 同源；`None → 404`。

---

### v0.5.5 → v0.5.6（新增透视查询子模块）

| 章节 | v0.5.5 | v0.5.6 |
|------|--------|--------|
| §Summary | 仅周需求管理三子功能（上传/查询/删除） | **新增**：第四子功能「透视查询」（独立模块） |
| §Key Changes / 模型 | `dsp_uploads` + `dsp_upload_rows` + `config_name` | **新增 `WeekDt` ORM 模型**（只读引用外部表） |
| §API 总览 | 5 个 DSP 上传端点 | **追加 1 个独立端点**：`POST /api/pivot-query` |
| §新章节「透视查询子模块」 | 不存在 | **新增整章**：含 SQL 结构 / 入参出参 / 数据量保护 / 错误约定 / Test Plan / Assumptions |
| §不实现的组件 | 11 项 | **追加 8 项**（pivot_type='demand_plus_supply' 待定、不引入前端、不创建 week_dt 表等） |
| 后端代码 | `crud/dsp_upload.py` + `api/dsp_uploads.py` | **新增 `crud/pivot_query.py` + `api/pivot_query.py`** |
| 测试 | `test_dsp_upload.py` | **新增 `test_pivot_query.py`** |

### v0.5.6 → v0.5.7（实现 demand_plus_supply 模式）

| 章节 | v0.5.6 | v0.5.7 |
|------|--------|--------|
| §3 核心 SQL | `base_rows` 过滤 `data_type = 'Demand'` | 改为 `data_type IN ('Demand', 'Supply')`；`demand_plus_supply` 模式下 `b` 子查询 GROUP BY 去掉 `data_type` |
| §4 入参 `pivot_type` | `'demand'` 固定；`'demand_plus_supply'` 占位 | `'demand'` 固定过滤 Demand；`'demand_plus_supply'` 查询 Demand + Supply 并计算 TTL_GAP / Rolling_TTLGAP |
| §4 入参 `version_dates` | 1-20 个 | `demand_plus_supply` 模式**仅 1 个**（单选，超限 → 422） |
| §5 出参示例 | 仅 `demand` 模式 | **新增 `demand_plus_supply` 模式 JSON 示例**（每组 4 行：Demand / Supply / TTL_GAP / Rolling_TTLGAP） |
| §6 数据量保护 | 4 项 | **追加**：`demand_plus_supply` 版本日期单选校验 → 422 |
| §7 错误约定 | 422 / 500 | **追加**：422 新场景（`version_dates` 超过 1 个） |
| §8 不实现 | 含 `demand_plus_supply` 占位 | **删除**该占位项；**新增**「TTL_GAP / Rolling_TTLGAP 不落库」 |
| §11 Demand+Supply 计算规则 | 不存在 | **新增整章**：入参约束 / 数据查询 / Python 层后计算 7 步流程 / 不落库 / date_granularity 兼容 / 完整示例 |
| 后端代码 | `pivot_query.py` 仅 demand 主路径 | **追加** `demand_plus_supply` 分支（base_rows 过滤 + b/d 子查询调整 + Python 层 TTL_GAP / Rolling_TTLGAP 计算） |
| LEFT JOIN | d 子查询 JOIN 条件含 ttl | **v0.5.7.4 追加**：从 LEFT JOIN 条件删除 `sub_d.c.ttl == sub_b.c.ttl`——b.ttl 是 `COALESCE(MAX(ttl), 0)` 的值，d.ttl 是原始值（可能 NULL），`NULL == 100` 不匹配导致 Supply 被过滤；去掉 ttl 后改用业务维度 5 字段匹配，不会重复（同业务组只有 1 Demand + 1 Supply per row_date） |
| 测试 | `test_pivot_query.py` 仅 demand 用例 | **追加**：`demand_plus_supply` 正常路径 / 缺失 Supply / 缺失 Demand / 多日期 Rolling 累计 / version_dates > 1 → 422 / demand 模式回归 |

---

### v0.5.7.3 → v0.5.7.4（group_key 去掉 ttl）

> 用户报告：同一 (country=马来西亚, config_name=8Q-TOR-T4, date=2026-06-29) 下，db 中含 ttl=100 的 Demand 行 + ttl=NULL 的 Supply 行，期望前端渲染出 1 组 4 行（Demand/Supply/TTL_GAP/Rolling）；但实际看到 2 组 8 行（每组 4 行，第二组全部 quantity=0 兜底）—— 这是因为 ttl 拆分出了第二组。

| 章节 | v0.5.7.3 | v0.5.7.4 |
|------|----------|----------|
| §11.2 b 子查询 | GROUP BY `(upload_id, country, category, config_code, config_name, ttl)` | GROUP BY `(upload_id, country, category, config_code, config_name)`；b SELECT 用 `COALESCE(MAX(ttl), 0)` 兜底（NULL → 0） |
| §11.3 步骤 1 | 分组 key 含 ttl：`group_key = (country, cat, code, name, ttl, version_date)` | 分组 key 去 ttl：`group_key = (country, cat, code, name, version_date)` |
| ttl 展示 | - | 保留为展示字段；NULL 值在响应中呈现 0 |
| 前端 | - | 无变更（前端 PivotQuery 已支持 ttl=null/0） |

**后端代码改动**：
- `app/crud/pivot_query.py::_query_demand_plus_supply`：sub_b 改造 + Python group_key 去 ttl
- `app/crud/pivot_query.py::estimate_size`：b_cols 同步去 ttl

**测试改动**：
- `tests/test_pivot_query.py` 新增 `test_demand_plus_supply_merge_diff_ttl`：1 组业务 + 多 ttl（100 / NULL）+ Demand+Supply → row_groups 4 行，TTL 展示 100，TTL_GAP = -10

**前端 / OpenAPI / 数据库无改动**。

### v0.5.7 → v0.5.8（新增 Excel 导出子模块）

| 章节 | v0.5.7 | v0.5.8 |
|------|--------|--------|
| 端点总览 | 5 个 dsp-uploads + 1 个 pivot-query | **+ 2 个 export 端点**（`GET /api/dsp-uploads/{id}/rows/export` + `POST /api/pivot-query/export`） |
| `requirements.txt` | 无 pandas | **新增** `pandas>=2.0` |
| §不实现的组件 | — | 新增 9 条 export 相关明确范围（见 §8） |
| 文件结构 | `app/services/` 无 excel 模块 | **新增** `app/services/excel_export.py` |
| §新章节「Excel 导出子模块」 | 不存在 | **新增整章** §1~§10：业务目标 / 依赖 / 端点总览 / GET rows/export / POST pivot-query/export / 通用约定 / 文件结构 / 不实现的组件 / Test Plan / Assumptions |
| 测试 | `test_dsp_upload.py` + `test_pivot_query.py` | **新增** `test_dsp_export.py`（6 用例）+ `test_pivot_export.py`（7 用例） |
| 数据库 / OpenAPI schema / 前端 | 既有 | 无新增 schema 字段；OpenAPI 由 FastAPI 自动生成时含 2 个新端点 |

### v0.5.7.4 → v0.5.9（Demand 跨版本 diff 过滤）

| 章节 | v0.5.7.4 | v0.5.9 |
|------|----------|--------|
| §摘要标题 | v0.5.6 — 新增透视查询子模块 | **v0.5.9 — 新增 Demand 跨版本 diff 过滤** |
| §摘要调用块 | 6 条 | **追加** 6 条 v0.5.9 总览（仅 demand 生效、SQL 不变、空 row_group 保留、与 export 自动协同、不接通 demand_plus_supply） |
| §3 核心 SQL | v0.5.7 注释 | **追加** "v0.5.9 变更：`query_diff` 是纯 Python 层后处理，SQL 主路径完全不变" |
| §4 `PivotQueryRequest` 入参 | 11 行 | **追加 1 行** `query_diff \| bool = True`：仅 demand 生效，全等日期从 period_columns / quantities 中移除 |
| §5 出参示例 | demand + demand_plus_supply 两个示例 | **追加** `query_diff=true` + 2 版本示例；`period_columns` 缩短至仅差异日期，`quantities` 仅含差异日期 key |
| §8 不实现的组件 | 7 条 | **追加 1 条**「空 row_group 保留以保留元信息」 |
| §9.5 Test Plan（新增小节） | 不存在 | **新增** §9.5「`query_diff` 过滤」6 条用例（默认 true 单版本守卫 / false baseline / 全等剪除 / 部分差异保留原值 / 多业务组并集 / 不影响 demand_plus_supply） |
| §新章节「Demand 跨版本 diff 过滤」 | 不存在 | **新增整章** §12：业务目标 / 「变化」语义 / 算法（含 Python 伪代码）/ 步骤示意 / 边界与陷阱 / 多业务组示例 / 与 export 协同 / 不实现的组件 / Test Plan 引用 / Assumptions 6 条 |
| §11.6 demand_plus_supply 兼容性 | — | §12.7 补充说明：`demand_plus_supply + query_diff=true` 不接通，等价 baseline |
| 后端代码 | `pivot_query.py` 不变 | **追加** `_apply_diff_filter(resp, version_dates_len)` 纯函数；`_query_demand()` 末尾在 `query_diff=True and len(version_dates)>1` 时调用 |
| Schema | `PivotQueryRequest` 11 行 | **追加** 字段 `query_diff: bool = True`；class docstring 同步说明 |
| 测试 | `test_pivot_query.py` 既有用例 | **追加 6 用例**（§9.5） |
| 前端 / Excel 导出 / 数据库 | 既有 | **联动**：`excel_export.py::build_pivot_xlsx` 无需改动，自动随 `period_columns` 缩短出列；前端 `PivotQueryRequest` 类型自动同步新字段（可选 TypeScript regenerate） |