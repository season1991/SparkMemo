# DSP Excel 上传入库模块规格

> 适配规格：SparkMemo v0.5
> 适用范围：单用户本地版，无登录。
> **数据库可移植性约束**：所有日期字段统一使用 10 字符字符串 `YYYY-MM-DD`；不依赖任何数据库内置日期函数（沿用既有项目约定，详见 `task_management.md` §约束）。

---

## Summary

实现一个面向「网络设备 DSP 周预测 Excel」的上传与入库模块：

1. **文件上传**：用户在前端选择一个 `.xlsx` 文件 + 一个 `version_date`（YYYY-MM-DD），后端接收 multipart 上传；
2. **文件名解析**：截掉扩展名后按 `-` 切分，**前 3 段**作为 `vendor` / `item` / `sub_item`，第 4 段及之后丢弃；
3. **Excel 解析**：单 sheet（sheet 名固定 `DSP`）；按 **固定列号** 读取静态字段（`Country` 在 col 4、`Category` 在 col 5、`Config Code` 在 col 6、`Data Type` 在 col 10、`TTL` 在 col 11、`Update By` 在 col 12），col 13+ 为周列；第 1 行列头在 col 13+ 携带 `year_month` 段标签，第 2 行周编号，第 3 行周起始日，从第 4 行起为数据行；
4. **数据展开**：每条数据行 × 每个有效周列 = 一条事实记录入库；`quantity` 为空 / None / `0` / 非 `Demand`-`Supply` 行 全部跳过（详见 §跳过规则）；
5. **元数据存档**：批次级字段 `vendor` / `item` / `sub_item` / `version_date` / `source_filename` 入 `dsp_uploads` 表；
6. **重传阻断**：同 `(vendor, item, sub_item, version_date)` 已存在 → 409，强制用户先删旧批次；
7. **事实行查询**：支持批次列表、批次详情、批次内事实行分页查询；删除整批级联清空事实行。

---

## Key Changes

### 数据模型

| 表 | 状态 | 字段 |
|----|------|------|
| `dsp_uploads` | 新增 | id / vendor / item / sub_item / version_date / source_filename / row_count / created_at；(vendor, item, sub_item, version_date) 联合唯一 |
| `dsp_upload_rows` | 新增 | id / upload_id(FK, ON DELETE CASCADE) / country / category / config_code / data_type / ttl / year_month / week / date / quantity |

> **日期字段统一为 `YYYY-MM-DD` 字符串**：`version_date` / `date` / `created_at` 均为 10 字符定长字符串，不使用数据库原生 `DATE` / `DATETIME` 类型，便于跨数据库移植。
>
> **`year_month` 用 7 字符字符串**（如 `2025-01`）；`week` 用 8 字符字符串（如 `WK01`），与 Excel 原文件格式保持一致便于审计。

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
year_month   Mapped[str]    # 7，"2025-01"，非空
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

### 工作表结构（列号固定，不做列头文本搜索）

工作表固定 1 个，sheet 名必须为 `DSP`，否则 422。列布局如下：

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
| **12** | **L** | `Update By`          | 边界标记 | —（不存，仅用于划定 col 13+ 起点） |
| **13+** | M+  | `2025-01` / 空 / `2025-02` / … | 周列 | `year_month` (行 1) / `week` (行 2) / `date` (行 3) / `quantity` (行 4+) |

> **明确丢弃 6 列**：`BU` / `Version` / `Region` / `Config Name` / `Model` / `Manufacturer`。`Update By` **不**在丢弃之列——它位于 col 12，充当静态列与周列之间的固定分界（解析时不读其内容，也不入库）。
>
> **行 1 表头文本不参与解析**：解析只依赖上述列号；表头文本用于人工审计与未来 schema 校验（如加了 row 1 断言「`D1 == '*Country'`」），不参与字段定位。本规格不要求运行时强制校验表头文本。

### 行布局

| 行 | 用途 | 关键列 |
|----|------|--------|
| 1  | 列头 + `year_month` 段标签 | col 4..12 表头；col 13+ 携带 `year_month`（稀疏） |
| 2  | 周编号 `WK01` / `WK02` / … | col 13..max_col |
| 3  | 周起始日 `YYYY-MM-DD` | col 13..max_col |
| 4..max_row | 数据行 | col 4, 5, 6, 10, 11（静态）；col 13+（`quantity`） |

### `year_month` 前向传播算法（行 1 col 13+）

行 1 在 col 13+ 的单元格里**只**在月份分界处写值，其余列为空。一个示例节选（来自样本文件）：

```
col:  13   14   15   16   17   18   19   20   21   22
row1: '2025-01'  .   .   .   .   '2025-02'  .   .   .
row2: 'WK01' 'WK02' 'WK03' 'WK04' 'WK05' 'WK06' 'WK07' 'WK08' 'WK09'
row3: '2024-12-30' '2025-01-06' … '2025-02-03' …
```

**算法**：

```python
year_month_at_col: dict[int, str] = {}   # col -> "YYYY-MM"
current = ""
for c in range(13, ws.max_column + 1):
    v = ws.cell(row=1, column=c).value
    if v is not None and str(v).strip() != "":
        current = str(v).strip()
    if current != "":
        year_month_at_col[c] = current
```

对 col 13..max_col 中所有同时满足"行 2 周编号非空 ∧ 行 3 周起始日非空"的列（即有效周列），其 `year_month` 取 `year_month_at_col[c]`；若该 col 没有 `year_month`（即遇到 col 13 之前所有行 1 cell 都为空、且 col 13 本身也为空），该列无效，整列跳过。

### 跳过规则（命中即跳过；分两层）

**行级跳过（命中后整行 0 条事实记录）**：

- **R1**：该行 `Country`（col 4，strip 后）和 `Config Code`（col 6，strip 后）**同时为空**（视为空行）；
- **R2**：该行 `Data Type`（col 10，strip 后）**不等于** `Demand` **也不等于** `Supply`（大小写敏感、首尾空白已 strip；含 `Demand PO` / `GR` / `ASN` / `TTL_GAP` / `Rolling_TTLGAP` / 空字符串 / `None` 等）；
- **R3**：col 13+ 完全无任何有效周列（极端情况，正常文件不会出现）。

**周列级跳过（仅影响 (该行 × 该周列) 这一个 cell）**：

- **C1**：该周列 col `c` 的 row 2 `week` 为空 / None；
- **C2**：该周列 col `c` 的 row 3 `date` 为空 / None；
- **C3**：该周列 col `c` 在 `year_month_at_col` 中查不到 `year_month`（即 col 13 起 row 1 全空的情况，正常文件不会出现）；
- **C4**：该 cell 的 `quantity` 为空字符串 / None / `0`（数值 `0` 也跳；详见 §数值容错）。

**注**：C1/C2/C3 整列跳过意味着该 (行 × 列) 组合不入库；该列对**其它**数据行仍然有效（其它行 × 该列 仍正常处理）。

### 数值容错

`quantity` 在行 4+ col 13+ 单元格的取值与处理：

| 取值 | 处理 |
|------|------|
| `None` | 跳过该 cell（C4） |
| 空字符串 `""` | 跳过该 cell（C4） |
| 整数 `0` / 浮点 `0.0` | 跳过该 cell（C4） |
| 整数 `>0` / 浮点 `>0` | 转 `int()` 入库；浮点非整数（如 `1.5`）→ **400** 阻断整次上传 |
| 其它非数字字符串 | **400** 阻断整次上传 |

`ttl`（col 11）取值与处理：

| 取值 | 处理 |
|------|------|
| `None` / 空字符串 | 入库为 `None` |
| 整数 | 入库为 `int` |
| 浮点整数（如 `4.0`） | 入库为 `int(4)` |
| 其它浮点 / 非数字字符串 | 入库为 `None`（**不**阻断上传——TTL 不参与业务聚合，宽松处理） |

### 展开公式

- 数据行集合 = `{r | r ∈ [4, ws.max_row] ∧ row r 通过 R1 ∧ row r 通过 R2}`，记为 `N` 行；
- 有效周列集合 = `{c | c ∈ [13, ws.max_column] ∧ row 2[c] 非空 ∧ row 3[c] 非空 ∧ year_month_at_col[c] 存在}`，记为 `M` 列；
- 事实行集合 = `{ (r, c) | r ∈ 数据行 ∧ c ∈ 有效周列 ∧ row r 的 col c 通过 C4 }`；
- `row_count` = `len(事实行集合)`。

每条事实行入库 `(upload_id, country, category, config_code, data_type, ttl, year_month_at_col[c], row 2[c] strip 后, row 3[c] strip 后, int(quantity))`。

---

## 重传策略

| 场景 | 行为 |
|------|------|
| 同 `(vendor, item, sub_item, version_date)` 已存在 | **409 Conflict** |
| 响应 detail | `"version (vendor=A, item=B, sub_item=C, version_date=YYYY-MM-DD) already uploaded (upload_id=N)"` |
| 不存在 | 201 创建新批次 |

删除旧批次后可重传同版本（删除走 `DELETE /api/dsp-uploads/{id}`）。

---

## API And Behavior

所有接口统一前缀 `/api`，路径使用复数名词；列表接口支持分页 `?page=1&size=20`。

### DSP 上传 DspUploads

| 方法 | 路径 | 说明 |
|------|------|------|
| POST   | `/api/dsp-uploads` | 上传 multipart/form-data，返回批次摘要 |
| GET    | `/api/dsp-uploads?page=&size=` | 批次列表（按 id 倒序） |
| GET    | `/api/dsp-uploads/{id}` | 批次详情 |
| GET    | `/api/dsp-uploads/{id}/rows?page=&size=` | 批次内事实行分页 |
| DELETE | `/api/dsp-uploads/{id}` | 整批删除（CASCADE） |

### POST /api/dsp-uploads 入参（multipart/form-data）

| 字段 | 类型 | 必填 | 校验 |
|------|------|------|------|
| `file` | File | 是 | `.xlsx`；MIME = `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`；size ≤ 20 MB |
| `version_date` | string | 是 | `YYYY-MM-DD` |

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

### GET 列表响应

```json
{
  "items": [ /* DspUploadRead[] */ ],
  "total": 5,
  "page": 1,
  "size": 20
}
```

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
      "year_month": "2025-01",
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
| 400 | 文件名 < 3 段；`version_date` 非 `YYYY-MM-DD`；`quantity` 含非数字字符串 / 非整数浮点 |
| 404 | 批次不存在 |
| 409 | 同 `(vendor, item, sub_item, version_date)` 已存在 |
| 413 | 文件 > 20 MB |
| 415 | MIME 非 `.xlsx` |
| 422 | Sheet `DSP` 不存在 |

---

## 不实现的组件（明确范围）

- 不解析 / 不存储 col 1, 2, 3, 7, 8, 9 的内容（`BU` / `Version` / `Region` / `Config Name` / `Model` / `Manufacturer`），也**不解析 col 12 `Update By` 的内容**；
- 不实现文件落盘（上传文件不存到磁盘，仅流式读 `BytesIO` → 解析 → 入库 → 释放）；
- 不实现导入历史回滚 / undo；
- 不实现事实行的编辑（只能整批删除后重传）；
- 不实现跨批次合并 / 透视查询（仅按批次查询）；
- 不实现非 `Demand`/`Supply` 行的事实入库（见 R2）。

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
- 手工构造 4 行 × N 列 worksheet：row 1 含若干 `year_month` 标签（中间允许空洞）+ col 4..12 表头文字；row 2 周编号；row 3 周日期；row 4+ 数据；
- 断言展开行数符合预期（按 §展开公式）；
- 跳过规则：
  - R1：`Country` 与 `Config Code` 同时空 → 该行无事实记录；
  - R2：`Data Type = GR` → 该行无事实记录；`Data Type = "Demand "`（带尾空格）→ 因 strip 后等于 `Demand` 而保留；
  - C1：row 2[col] 空 → 该 (行 × 列) 不入库，其它列正常；
  - C2：row 3[col] 空 → 同上；
  - C3：col 13 起 row 1 全空、且 col 13 row 1 为空 → 该列无效；
  - C4：`quantity = 0` → 跳过；`quantity = None` → 跳过；`quantity = ""` → 跳过；
- 数值容错：`quantity = "abc"` → ValueError（路由层转 400）；`quantity = 1.5` → ValueError。

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
  - 任取一行抽查：`(country, category, config_code, data_type, ttl, year_month, week, date, quantity)` 与 Excel 原值一致。

---

## Assumptions

1. **单用户本地版**维持不变：不引入登录、不引入多租户；
2. **同库同 schema**：复用现有 MySQL `sparkmemo`，新表由 `Base.metadata.create_all` 自动创建；老库走幂等 `CREATE TABLE IF NOT EXISTS`；
3. **新依赖**：`openpyxl` 加 `backend/requirements.txt`，按 AGENTS.md 在 `dev_env` 安装；
4. **CASCADE**：删除 `dsp_uploads` 自动级联删 `dsp_upload_rows`（SQLAlchemy `cascade="all, delete-orphan"` + DB 端 `ON DELETE CASCADE`）；
5. **固定列号**：col 4/5/6/10/11/12 为字段映射的**唯一**依据；表头文本不参与解析。本规格不要求对表头文本做运行时断言。若未来 Excel 模板列号变化，需同步改本规格并改代码；
6. **`source_filename`**：含扩展名的完整原始文件名，仅展示 / 审计用，不参与业务；
7. **`config_code` 可空**：与原 Excel 数据保持一致，不做智能补全；但**整行 Country+ConfigCode 都空**的行整体跳过（R1）；
8. **`data_type` 严格匹配**：仅字面 `Demand` / `Supply` 入库；其它值（含 `Demand PO` 等所有变体）整行跳过（R2）；大小写敏感、首尾空白已 strip；
9. **数字 0 vs NULL**：空字符串 / None / `0` 全部跳过（C4）；非数字 / 非整数浮点 → 400 阻断；
10. **`upload_id` 外键**：先 INSERT 批次拿到 `id`，再批量 INSERT 事实行（两次 commit），保证 CASCADE 关系正确建立；
11. **批量插入**：事实行使用 `bulk_insert_mappings` 或 `session.add_all`，单批 N × M 可能上千行，避免 N 次单条 INSERT；
12. **不上传时落盘**：上传的 `UploadFile` 直接 `read()` 到 `BytesIO`，不写磁盘；
13. **`ttl` 容错**：TTL 单元格的非整数字符串入库为 `None`，不阻断上传——TTL 仅展示，不参与聚合。

---

## 修订记录（相对原版）

| 章节 | 原版问题 | 修订 |
|------|----------|------|
| Summary §3 | 列头定位表述模糊，混用"列名匹配"和"列号" | 改为**纯列号**定位，明确"表头文本不参与解析" |
| Key Changes / 模型 | `data_type` 可为 `GR`（与 R2 自相矛盾） | 明确仅 `Demand` / `Supply` 入库；示例 JSON 同步修正 |
| 工作表结构 | "col 4, 5, 6, 10, 11, 12" 与"丢弃 7 列（含 Update By）"互斥 | 明确丢弃 6 列（BU/Version/Region/Config Name/Model/Manufacturer），Update By 不丢——它是 col 12 的边界标记，解析时不读不存 |
| Excel 解析 / year_month | "col 13+ 第一个非空字符串视为 year_month 段起点"含糊 | 给出**完整前向传播算法** + 伪代码 + 样本片段 |
| 跳过规则 | 行级 vs 列级跳过混在一处 | 拆为 R1/R2（行级）和 C1/C2/C3/C4（列级），明确互不影响 |
| 数值容错 | `quantity` 0 与 None 行为未与跳过规则交叉 | 统一并入 C4；新增浮点非整数 / 非数字 → 400 阻断 |
| 数值容错 | `ttl` 容错未定义 | 新增：非整数字符串入库为 `None`，不阻断 |
| §不实现的组件 | "BU/Version/Region/Config Name/Model/Manufacturer/Update By 7 列"包含 Update By | 改为 6 列，明确 Update By 是边界标记，不入丢弃也不入存储 |
| Test Plan §2 | "整行 Country+ConfigCode 都空"行为未明确测 | 拆 R1/R2/C1/C2/C3/C4 6 个独立断言 |
| Test Plan §3 | `data_type = GR` 入库断言 | 改为"事实行 data_type ∈ {Demand, Supply}" |