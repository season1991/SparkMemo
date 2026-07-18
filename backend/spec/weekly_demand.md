# 周需求管理模块规格（v0.5.4 — 替代原「DSP 上传」）

> 适配规格：SparkMemo v0.5.4
> 适用范围：单用户本地版，无登录。
> **数据库可移植性约束**：所有日期字段统一使用 10 字符字符串 `YYYY-MM-DD`；不依赖任何数据库内置日期函数（沿用既有项目约定，详见 `task_management.md` §约束）。

> **v0.5.4 模块重命名 + 子模块新增**：
> 1. 原「DSP 上传」模块更名为「**周需求管理**」（`Weekly Demand Management`，简称 WDM）。
> 2. 「DSP 上传」降级为周需求管理的**子功能**之一（同 `vendor / item / sub_item / version_date` 4 个关键字段语义）；其它两个子功能为「**查询**」（按相同 4 字段查询已存在的批次 + 事实行）和「**删除**」（按相同 4 字段预览后删除）。
> 3. 前端路由层级：`/dsp-uploads` 作为 hub 页（含 3 张功能卡片），子路由 `/dsp-uploads/upload`、`/dsp-uploads/query`、`/dsp-uploads/delete` 分别落地三个子功能页。
> 4. 后端 API：`GET /api/dsp-uploads` 增加可选 query 参数 `vendor / item / sub_item / version_date`，前端用它做精确查找；删除仍走既有的 `DELETE /api/dsp-uploads/{id}`（前端先查再删）。
> 5. 字段名规范化沿用 v0.5.3（`ym` / `vendor / item / sub_item / version_date`）；保留 v0.5.3 的列头文本匹配 + 跳过隐藏列说明。

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
| 7    | G        | `*Config Name`       | 丢弃 | — |
| 8    | H        | `Model`              | 丢弃 | — |
| 9    | I        | `*Manufacturer`      | 丢弃 | — |
| **10** | **J** | `Data Type`          | 静态 | `data_type`（过滤） |
| **11** | **K** | `TTL`                | 静态 | `ttl` |
| **12** | **L** | `Update By`          | 参考；不强制 | —（不参与 v0.5.3 解析） |
| **13+** | M+  | `2025-01` / 空 / `2025-02` / … | 周列 | `ym` (行 1) / `week` (行 2) / `date` (行 3) / `quantity` (行 4+) |

> **明确丢弃 6 列**：`BU` / `Version` / `Region` / `Config Name` / `Model` / `Manufacturer`。`Update By` **不**在丢弃之列——它在 v0.5.3 之前充当静态列与周列之间的硬编码边界；v0.5.3 起**不再**作为边界——周列起点由行 1 中的 `YYYY-MM` 段起点自动识别（见 §`ym` 段识别）。
>
> **行 1 表头文本不参与解析（v0.5.3 之前的硬约束，v0.5.3 反转）**：v0.5.3 行 1 表头**作为输入**驱动解析；不再按字面列号。

### 列头匹配规则（v0.5.3）

按下列规则在 row 1 中查找目标列：

1. **去首尾空白**；
2. **去前缀 `*`**（如 `*Country` → `Country`）；
3. **大小写不敏感**；
4. **首匹配**：命中第一个满足的 cell 即停。

`_HEADER_TARGETS` 字典（**关键列**，缺一即 `BadHeaderError` → 422）：

| 业务字段 | 归一化后匹配的别名（任一命中） |
|----------|-------------------------------|
| `country` | `country` |
| `category` | `category` |
| `config_code` | `config code`、`configcode` |
| `data_type` | `data type`、`datatype` |
| `ttl` | `ttl` |

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
| 1  | 列头 + `ym` 段标签 | 5 个关键列由列头文本匹配定位；col 13+ 携带稀疏 `YYYY-MM` 段标签 |
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

- 不解析 / 不存储 col 1, 2, 3, 7, 8, 9 的内容（`BU` / `Version` / `Region` / `Config Name` / `Model` / `Manufacturer`），也**不解析 col 12 `Update By` 的内容**；
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
5. **v0.5.3 字段定位算法**：5 个关键列（country/category/config_code/data_type/ttl）的列号由**行 1 列头文本首匹配**决定（去前缀 `*` + 首尾空白 + 大小写不敏感）；不依赖字面列号。因此跨文件即使列位置变化也能正确解析。若 Excel 模板表头文本改名，需同步改本规格 §列头匹配规则 与代码 `_HEADER_TARGETS`。
6. **`source_filename`**：含扩展名的完整原始文件名，仅展示 / 审计用，不参与业务；
7. **`config_code` 可空**：与原 Excel 数据保持一致，不做智能补全；但**整行 Country+ConfigCode 都空**的行整体跳过（R1）；
8. **`data_type` 严格匹配**：仅字面 `Demand` / `Supply` 入库；其它值（含 `Demand PO` 等所有变体）整行跳过（R2）；大小写敏感、首尾空白已 strip；
9. **数字 0 vs NULL**：空字符串 / None / `0` 全部跳过（C4）；非数字 / 非整数浮点 → 400 阻断；
10. **`upload_id` 外键**：先 INSERT 批次拿到 `id`，再批量 INSERT 事实行（两次 commit），保证 CASCADE 关系正确建立；
11. **批量插入**：事实行使用 `bulk_insert_mappings` 或 `session.add_all`，单批 N × M 可能上千行，避免 N 次单条 INSERT；
12. **不上传时落盘**：上传的 `UploadFile` 直接 `read()` 到 `BytesIO`，不写磁盘；
13. **`ttl` 容错**：TTL 单元格的非整数字符串入库为 `None`，不阻断上传——TTL 仅展示，不参与聚合。

---

### 行布局（v0.5.3）

| 行 | 用途 | 关键列 |
|----|------|--------|
| 1  | 列头 + `ym` 段标签 | 行 1 列头文本匹配（5 个关键列）；col 13+ 携带稀疏 `YYYY-MM` 段标签 |
| 2  | 周编号 `WK01` / `WK02` / … | `_ym_segments` 识别的有效 col |
| 3  | 周起始日 `YYYY-MM-DD` | `_ym_segments` 识别的有效 col |
| 4..max_row | 数据行 | `_resolve_columns` 识别的 5 个关键 col；有效周列读 `quantity` |

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
| §错误约定 422 | Sheet 不存在 / Form 字段缺失 | **新增**：5 个关键列缺失 → `BadHeaderError` → 422 + detail `"Excel header missing required column '<name>'"` |
| §Assumption 5 | "固定列号"为字段映射唯一依据 | "v0.5.3 字段定位算法"：行 1 列头文本首匹配 |
| §行布局 | col 4..12 硬编码；col 13..max_col 周列 | 5 个关键列按列头匹配；有效周列按 `YYYY-MM` 段识别 |
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