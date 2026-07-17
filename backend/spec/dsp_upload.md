# DSP Excel 上传入库模块规格

> 适配规格：SparkMemo v0.5
> 适用范围：单用户本地版，无登录。
> **数据库可移植性约束**：所有日期字段统一使用 10 字符字符串 `YYYY-MM-DD`；不依赖任何数据库内置日期函数（沿用既有项目约定，详见 `task_management.md` §约束）。

---

## Summary

实现一个面向「网络设备 DSP 周预测 Excel」的上传与入库模块：

1. **文件上传**：用户在前端选择一个 `.xlsx` 文件 + 一个 `version_date`（YYYY-MM-DD），后端接收 multipart 上传；
2. **文件名解析**：截掉扩展名后按 `-` 切分，**前 3 段**作为 `vendor` / `item` / `sub_item`，第 4 段及之后丢弃；
3. **Excel 解析**：单 sheet（sheet 名固定 `DSP`）；第 1 行列头定位 `Country` / `Category` / `Config Code` / `Data Type` / `TTL` / `Update By`；第 2 行周编号；第 3 行周起始日；从第 4 行起为数据行；col 13+ 每个 cell 是 (该行 × 该周列) 的数量；
4. **数据展开**：每条数据行 × 每个非空周列 = 一条事实记录入库；`quantity` 为空 / None / `0` 全部跳过（详见 §跳过规则）；
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
country      Mapped[str|None]  # 64；来源 col4，可空字符串入库
category     Mapped[str|None]  # 128；来源 col5，可空字符串入库
config_code  Mapped[str|None]  # 128；来源 col6；可空（与原表行为一致）
data_type    Mapped[str|None]  # 64；来源 col10，可空字符串入库
ttl          Mapped[int|None]  # 来源 col11，可空
year_month   Mapped[str]    # 7，"2025-01"，非空
week         Mapped[str]    # 8，"WK01"，非空
date         Mapped[str]    # 10，YYYY-MM-DD，非空
quantity     Mapped[int]    # 非负，非空
```

> **`config_code` 与 `country` 均可为空**：与原 Excel 数据保持一致（不做任何「智能补全」）；但**整行 `Country` 和 `Config Code` 同时为空**的行整体跳过（视为空行）。

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

### 工作表结构

| 行 | 用途 | 必读列 |
|----|------|--------|
| 1  | 列头；定位关键列；col 13+ 第一个非空字符串视为 `year_month` 段起点 | 4, 5, 6, 10, 11, 12 |
| 2  | 周编号 `WK01` / `WK02` / … | 13..max_col |
| 3  | 周起始日 `YYYY-MM-DD` | 13..max_col |
| 4+ | 数据行 | 4, 5, 6, 10, 11 读静态字段；13..max_col 读 `quantity` |

### 列头匹配

按下列规则在第 1 行中查找目标列：

1. **去前缀 `*`**（如 `*Country` → `Country`）；
2. **去首尾空白**；
3. **大小写不敏感**；
4. **首匹配**：命中第一个满足的 cell 即停。

| 业务字段 | Excel 列名（大小写不敏感、去 `*`、去空白后） |
|----------|---------------------------------------------|
| `country` | `country` |
| `category` | `category` |
| `config_code` | `config code` |
| `data_type` | `data type` |
| `ttl` | `ttl` |
| `update_by` | `update by`（仅用于定位 col 13+ 起点，不入库） |

任一关键列未找到 → **422 Unprocessable Entity**。

### 跳过规则（任一命中即跳过该 (数据行 × 周列) 组合）

- 该周列对应的 **row 2 `week` 为空 / None**；
- 该周列对应的 **row 3 `date` 为空 / None**；
- 该数据行 **`Country` 和 `Config Code` 同时为空**（视为空行，整行所有周列均跳过）；
- 该数据行 **`Data Type` 不是 `Demand` 也不是 `Supply`**（如 `GR` 等其他值 → 整行所有周列均跳过；空白视为不匹配，整行跳过）；
- 该周列的 **`quantity` 为空 / None / `0`** → 跳过该 cell，但不影响该行其它周列。

### 数值容错

- `quantity` 是数字（包括 0）→ 直接落库；0 被跳过（见上）；
- `quantity` 是空字符串 / None → 跳过；
- `quantity` 是其它非数字字符串 → **400** 阻断整次上传。

### 展开公式

设数据行数 = `N`（从 row 4 开始到 `ws.max_row` 中含静态字段的行数），周列数 = `M`（col 13..max_col 中 row 2 与 row 3 都非空的列数），事实行数 = `N × M − 跳过的总数`。每条事实行入库 `(upload_id, country, category, config_code, data_type, ttl, year_month, week, date, quantity)`。

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
      "data_type": "GR",
      "ttl": 4,
      "year_month": "2026-01",
      "week": "WK04",
      "date": "2026-01-19",
      "quantity": 4
    }
  ],
  "total": 9876,
  "page": 1,
  "size": 100
}
```

### 错误约定

| HTTP | 场景 |
|------|------|
| 400 | 文件名 < 3 段；`version_date` 非 `YYYY-MM-DD`；`quantity` 含非数字字符串 |
| 404 | 批次不存在 |
| 409 | 同 `(vendor, item, sub_item, version_date)` 已存在 |
| 413 | 文件 > 20 MB |
| 415 | MIME 非 `.xlsx` |
| 422 | 列头匹配失败；Sheet `DSP` 不存在 |

---

## 不实现的组件（明确范围）

- 不解析 Excel 的 `BU / Version / Region / Config Name / Model / Manufacturer / Update By` 这 7 列；
- 不实现文件落盘（上传文件不存到磁盘，仅流式读 `BytesIO` → 解析 → 入库 → 释放）；
- 不实现导入历史回滚 / undo；
- 不实现事实行的编辑（只能整批删除后重传）；
- 不实现跨批次合并 / 透视查询（仅按批次查询）。

---

## Test Plan

> 测试位于 `backend/tests/test_dsp_upload.py`，使用 pytest + httpx AsyncClient + openpyxl 构造 sample 文件。

### 1. 文件名解析（纯函数）
- `Arista-网络设备DSP横版-机箱-061626.xlsx` → `("Arista", "网络设备DSP横版", "机箱")`；
- `foo-bar.xlsx` → ValueError；
- `no-segments-at-all.xlsx` → ValueError；
- `no-extension` 视为整串 → 按 `-` 切分；
- 空字符串 → ValueError。

### 2. Excel 解析（纯函数）
- 给定 sample BytesIO（手工构造的 3 行 × N 列 worksheet），断言展开行数符合预期；
- 跳过规则：
  - 行全 0 → 该行不产生事实记录；
  - week/date 头缺失 → 该列不产生事实记录；
  - quantity 非数字字符串 → **抛 ValueError**（由路由层捕获并转 400）；
  - 整行 Country+ConfigCode 都空 → 该行整体跳过；
- 数值容错：None、空字符串、`0` 均跳过。

### 3. POST /api/dsp-uploads
- 201 成功：返回 `row_count` = 期望值；DB 中 `dsp_uploads` + `dsp_upload_rows` 行数正确；`created_at` = 调用当天（由 Python 传入，不依赖 DB 函数）；
- 400：
  - `version_date` 非 `YYYY-MM-DD`；
  - 文件名段数 < 3；
  - quantity 含非数字字符串；
  - MIME 非 `.xlsx`；
- 413：文件 > 20 MB（构造大文件较慢，用 `monkeypatch` 改 limit）；
- 409：同版本重传；detail 含 `upload_id`；
- 422：列头匹配失败 / sheet 名不是 `DSP`。

### 4. GET 列表 / 详情 / 行分页
- 列表默认按 id 倒序；
- 行分页 `?page=2&size=100` 返回正确切片；
- `total` 字段准确。

### 5. DELETE
- 删批次后 `dsp_upload_rows` 级联清空；
- 再 GET → 404。

### 6. SQL 日期函数不出现
- 与既有约定一致：解析 / 查询路径 SQL 文本不出现 `CURDATE()` / `NOW()` / `CURRENT_DATE` / `GETDATE()`。

---

## Assumptions

1. **单用户本地版**维持不变：不引入登录、不引入多租户；
2. **同库同 schema**：复用现有 MySQL `sparkmemo`，新表由 `Base.metadata.create_all` 自动创建；老库走幂等 `CREATE TABLE IF NOT EXISTS`；
3. **新依赖**：`openpyxl` 加 `backend/requirements.txt`，按 AGENTS.md 在 `dev_env` 安装；
4. **CASCADE**：删除 `dsp_uploads` 自动级联删 `dsp_upload_rows`（SQLAlchemy `cascade="all, delete-orphan"` + DB 端 `ON DELETE CASCADE`）；
5. **不入库的 7 列**：`BU / Version / Region / Config Name / Model / Manufacturer / Update By` 整列丢弃，不预留扩展字段；
6. **`source_filename`**：含扩展名的完整原始文件名，仅展示 / 审计用，不参与业务；
7. **`config_code` 可空**：与原 Excel 数据保持一致，不做智能补全；但**整行 Country+ConfigCode 都空**的行整体跳过；
8. **数字 0 vs NULL**：空字符串 / None / `0` 全部跳过；非数字 → 400 阻断；
9. **`upload_id` 外键**：先 INSERT 批次拿到 `id`，再批量 INSERT 事实行（两次 commit），保证 CASCADE 关系正确建立；
10. **批量插入**：事实行使用 `bulk_insert_mappings` 或 `session.add_all`，单批 N × M 可能上万行，避免 N 次单条 INSERT；
11. **不上传时落盘**：上传的 `UploadFile` 直接 `read()` 到 `BytesIO`，不写磁盘。