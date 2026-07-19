# DSP 上传模块 Todo List

> 适配规格：`backend/spec/dsp_upload.md`（SparkMemo v0.5）
> 测试策略：理论上按 spec §5.1，**先全红后全绿**。但本模块在实操中**同时落地了测试与实现**，未严格走 red 阶段；详见下方「TDD 偏差说明」。
> 测试 DB：复用开发 MySQL Schema `sparkmemo`（与开发库同名）；`tests/conftest.py` 用 SQLite 兜底，per-test `DELETE FROM` 两表（外键依赖顺序）。
> 测试组织：单文件 `tests/test_dsp_upload.py`，覆盖 spec §Test Plan §1~§7。
> 真实文件 fixture：`tests/fixtures/Arista-网络设备DSP横版-机箱-061626.xlsx`（用户上传的真实样本）用于 §7 回归断言 `row_count = 366`。

## 总体阶段

- [x] **Phase 0**  规格定稿（`backend/spec/dsp_upload.md`）
- [x] **Phase 1**  生成 Todo List（本文件）
- [x] **Phase 2**  测试驱动 —— **部分偏差**（见下方说明）
- [x] **Phase 3**  后端实现 - 全绿（`app/` 代码让 pytest 全过；43/43）
- [x] **Phase 4**  生成 OpenAPI（`backend/openapi/dsp_uploads.json`）
- [x] **Phase 6**  收尾（更新 Todo / 补 docstring / 复核 spec 一致性）

> Phase 5（前端按契约生成）不在本模块范围内。

---

## TDD 偏差说明

按 `backend/spec/README.md` §5.1，本模块的 Phase 2 应是「先在 `tests/` 写用例，运行 `pytest` 期望全部失败」，再进入 Phase 3 实现。

**实际执行**：Phase 2 / Phase 3 同步进行 —— 测试与实现代码在同一回合中产出。

**根因**：执行首次开发会话时未先读 `backend/spec/README.md`，仅按 `dsp_upload.md` 单独规格展开；事后审计 README §5 时发现该偏差。

**补救与承诺**：
- 已回溯把 43 条测试在 Phase 2 段逐一 `[x]` 列出，作为可审计的产物；
- 下个新模块（如有任何 v0.5+ 增量）将严格按 red → green 执行：先写测试、运行 `pytest -q` 看到全红（含 `ImportError` / `AttributeError` / `404`），再开始 Phase 3。

---

## Phase 2 — 测试驱动（已落地，43 条）

> 文件：`backend/tests/test_dsp_upload.py`
> 公共 fixture：`tests/conftest.py` 增加 `make_dsp_upload` 工厂 + DB 清理覆盖 `dsp_upload_rows` / `dsp_uploads` 两表（dsp_upload_rows 先于 dsp_uploads 删除以避开 FK 依赖）。
> 仅复用既有 `client` / `db` / `today` fixture，无需新增基础设施。

### 2.1 文件名解析（spec §Test Plan 1）

- [x] **2.1.1** `test_parse_filename_arista` 真实样例 → `("Arista", "网络设备DSP横版", "机箱")`
- [x] **2.1.2** `test_parse_filename_two_segments_raises` `foo-bar.xlsx` → ValueError
- [x] **2.1.3** `test_parse_filename_no_extension_splits_on_dash` `no-extension`（2 段）→ ValueError
- [x] **2.1.4** `test_parse_filename_empty_raises` 空串 → ValueError
- [x] **2.1.5** `test_parse_filename_three_segments_ok` `foo-bar-baz.xlsx` → 3 段
- [x] **2.1.6** `test_parse_filename_four_segments_drops_tail` 第 4 段及之后丢弃

### 2.2 Excel 解析（spec §Test Plan 2）

- [x] **2.2.1** `test_parse_excel_basic_two_rows_three_weeks` 最小正向：1 行 × 3 周列 = 3 条
- [x] **2.2.2** `test_parse_excel_R1_country_and_config_both_empty_skips_row` R1
- [x] **2.2.3** `test_parse_excel_R1_only_country_empty_kept` R1（仅 Country 空保留）
- [x] **2.2.4** `test_parse_excel_R2_strict_demand_supply` R2（非 Demand/Supply 整行跳过）
- [x] **2.2.5** `test_parse_excel_R2_strips_whitespace_before_compare` `"Demand "` 保留
- [x] **2.2.6** `test_parse_excel_C1_week_number_empty_skips_column` C1
- [x] **2.2.7** `test_parse_excel_C2_date_empty_skips_column` C2
- [x] **2.2.8** `test_parse_excel_C4_quantity_zero_skipped` C4（数值 0 跳过）
- [x] **2.2.9** `test_parse_excel_C4_quantity_none_and_empty_skipped` C4（None / 空字符串）
- [x] **2.2.10** `test_parse_excel_quantity_nonnumeric_raises` 非数字 → 抛
- [x] **2.2.11** `test_parse_excel_quantity_non_integer_float_raises` 浮点非整数 → 抛
- [x] **2.2.12** `test_parse_excel_quantity_string_int_accepted` 数字字符串入库 int
- [x] **2.2.13** `test_parse_excel_quantity_string_zero_skipped` `"0"` 跳过
- [x] **2.2.14** `test_parse_excel_ttl_invalid_string_becomes_none` TTL 容错（不阻断）
- [x] **2.2.15** `test_parse_excel_ttl_float_integer_rounded` `4.0` → int(4)
- [x] **2.2.16** `test_parse_excel_ym_propagation_with_gap` `ym` 前向传播 + 空洞
- [x] **2.2.17** `test_parse_excel_sheet_missing_raises` 非 DSP sheet → SheetMissingError
- [x] **2.2.18** `test_parse_excel_no_valid_week_columns_returns_empty` R3（无有效周列 → 0 事实）

### 2.3 POST /api/dsp-uploads（spec §Test Plan 3）

- [x] **2.3.1** `test_post_upload_201_success` 201 + DB 落地
- [x] **2.3.2** `test_post_upload_400_version_date_bad_format` 400
- [x] **2.3.3** `test_post_upload_400_filename_too_few_segments` 400
- [x] **2.3.4** `test_post_upload_400_quantity_nonnumeric` 400
- [x] **2.3.5** `test_post_upload_415_wrong_mime` 415
- [x] **2.3.6** `test_post_upload_413_oversize` 413（monkeypatch 阈值）
- [x] **2.3.7** `test_post_upload_409_duplicate_version` 409 + detail 含 `upload_id`
- [x] **2.3.8** `test_post_upload_422_wrong_sheet` 422
- [x] **2.3.9** `test_post_upload_then_resubmit_after_delete_succeeds` 删除后可重传

### 2.4 GET / 详情 / 行分页（spec §Test Plan 4）

- [x] **2.4.1** `test_get_list_default_desc_by_id` 列表默认 id 倒序
- [x] **2.4.2** `test_get_list_pagination` `?page=2&size=10`
- [x] **2.4.3** `test_get_detail` 批次详情
- [x] **2.4.4** `test_get_detail_404` 不存在 → 404
- [x] **2.4.5** `test_get_rows_pagination` 行分页 + total
- [x] **2.4.6** `test_get_rows_404_when_upload_missing` 批次不存在 → 404

### 2.5 DELETE 级联（spec §Test Plan 5）

- [x] **2.5.1** `test_delete_cascades_to_rows` 删批 → 行清空
- [x] **2.5.2** `test_delete_404` 不存在 → 404

### 2.6 SQL 日期函数不出现（spec §Test Plan 6）

- [x] **2.6.1** `test_no_sql_date_functions_in_module_source` `inspect.getsource` 扫 `CURDATE(` / `NOW()` / `CURRENT_DATE` / `GETDATE(`

### 2.7 真实文件回归（spec §Test Plan 7）

- [x] **2.7.1** `test_real_file_regression` 上传真实样本 → `row_count = 366`，data_type ∈ {Demand, Supply}

---

## Phase 3 — 后端实现（已落地）

### 3.1 数据模型

- [x] **3.1.1** `DspUpload`：`dsp_uploads` 表 + 联合唯一 `(vendor, item, sub_item, version_date)` 约束 `uk_dsp_upload_version`
- [x] **3.1.2** `DspUploadRow`：`dsp_upload_rows` 表 + `ForeignKey("dsp_uploads.id", ondelete="CASCADE")` + `index=True`
- [x] **3.1.3** 关系：`DspUpload.rows` ↔ `DspUploadRow.upload` 双 `relationship`，ORM 端 `cascade="all, delete-orphan"` + `passive_deletes=True`（双轨保证级联）
- [x] **3.1.4** 字段命名避坑：`(year_month)` → `(ym)` —— MySQL 不接受 `year_month` 作为字段名

### 3.2 Pydantic Schema

- [x] **3.2.1** `DspUploadRead`：批次响应；`from_attributes=True`
- [x] **3.2.2** `DspUploadListResponse`：`items` + `total` + `page` + `size`
- [x] **3.2.3** `DspUploadRowRead`：事实行响应；含 `ym` 字段
- [x] **3.2.4** `DspUploadRowListResponse`：事实行分页响应

### 3.3 纯函数解析器

- [x] **3.3.1** `parse_filename`：截扩展名 → 按 `-` 切 → 取前 3 段，< 3 段抛 `ValueError`
- [x] **3.3.2** `parse_excel`：openpyxl + `data_only=True` → `_ym_propagation` → R1/R2 行级 + C1/C2/C3/C4 列级
- [x] **3.3.3** 自定义异常 `SheetMissingError`（→ 422）、`BadQuantityError`（→ 400）由路由层映射
- [x] **3.3.4** TTL 容错：非整数字符串 → `None`，不阻断上传
- [x] **3.3.5** `quantity` 数值容错：非数字 / 非整数浮点 → `BadQuantityError`

### 3.4 CRUD 层

- [x] **3.4.1** `find_by_version`：按联合唯一键查批次
- [x] **3.4.2** `create_upload`：`IntegrityError` 直接抛（路由层 409 兜底）
- [x] **3.4.3** `bulk_insert_rows`：`session.add_all` 一次性 INSERT
- [x] **3.4.4** `list_uploads` / `list_rows` / `get_upload` / `delete_upload`

### 3.5 路由层

- [x] **3.5.1** `POST /api/dsp-uploads`：multipart 接收，校验顺序为 `version_date → MIME → size → filename → sheet → quantity → 409 → INSERT`
- [x] **3.5.2** `GET /api/dsp-uploads` 列表 + `GET /api/dsp-uploads/{id}` 详情 + `GET /api/dsp-uploads/{id}/rows` 行分页
- [x] **3.5.3** `DELETE /api/dsp-uploads/{id}` 级联删除
- [x] **3.5.4** 错误映射 400 / 404 / 409 / 413 / 415 / 422 全到位
- [x] **3.5.5** 注册 router 到 `app/main.py`

### 3.6 测试基础设施

- [x] **3.6.1** `tests/conftest.py` 增 `make_dsp_upload` 工厂
- [x] **3.6.2** DB 清理顺序：SQLite / MySQL 两条分支都加 `dsp_upload_rows` + `dsp_uploads`
- [x] **3.6.3** `tests/fixtures/Arista-网络设备DSP横版-机箱-061626.xlsx` 真实样本副本

### 3.7 依赖

- [x] **3.7.1** `requirements.txt` 加 `openpyxl>=3.1`（已预装于 trae_env / dev_env 不在 bcrypt 路径，无 AGENTS.md §历史教训 风险）

### 3.8 测试

- [x] **3.8.1** `pytest backend/tests/test_dsp_upload.py` 43/43 全绿
- [x] **3.8.2** 全量 `pytest -q` 193/193 无回归

---

## Phase 4 — OpenAPI

- [x] **4.1** 启动 FastAPI，导出 `backend/openapi/dsp_uploads.json`（基于 `app.openapi()`）
- [x] **4.2** 验证覆盖 spec §API And Behavior 全部端点（POST/GET/list/detail/rows/DELETE）
- [x] **4.3** schema 中字段名为 `ym`（不在路径中用 `year_month`）

---

## Phase 6 — 收尾

- [x] **6.1** 复查 Todo List（本文件），把 Phase 2 / 3 / 4 已完成项标记 `[x]`
- [x] **6.2** `requirements.txt` 已包含 `openpyxl>=3.1`
- [x] **6.3** `README.md` §4 模块表追加 DSP 上传行
- [x] **6.4** §5.2 注释规范：api / crud / services 的 docstring 已扩展为「参数 / 返回 / 异常」三段中文
- [x] **6.5** 改名 `year_month` → `ym` 的整链路审计：spec / 模型 / schema / route / tests / crud / OpenAPI 零残留
- [x] **6.6** 全量 `pytest -q` 193/193 无回归

---

## 验证清单（每 PR）

- [x] `pytest backend/tests` 全绿（193/193）
- [x] `grep -r "year_month" backend/` 无残留
- [x] `requirements.txt` 含 `openpyxl>=3.1`
- [x] `backend/openapi/dsp_uploads.json` 存在
- [x] `backend/.todo/dsp_upload.md`（本文件）所有阶段 `[x]`

---

## v0.5.7（实现 demand_plus_supply 模式）

> 适配规格：`backend/spec/weekly_demand.md` §11（Demand+Supply 计算规则）
> 触发范围：仅 `pivot_query` 子模块；其它子功能不受影响。
> TDD：本阶段严格执行 README §5.1「先 RED → 后 GREEN」流程——先在 `tests/test_pivot_query.py`
> 追加 6 条新用例运行确认全红，再进入 Phase 3 实现。修复了 Phase 2 历史 TDD 偏差
> （见本文件顶部「TDD 偏差说明」）。
> 完整分析见会话内 plan：Phase RED 6 用例 → Phase GREEN 2 文件 → OpenAPI 1 文件 → 收尾 1 步。

### Phase 0 — 规格定稿
- [x] `backend/spec/weekly_demand.md` §11 已写入（spec 已于 v0.5.7 定稿）

### Phase 1 — Todo List（本文件）
- [x] 在本文件追加 v0.5.7 阶段章节

### Phase 2 — 测试驱动（RED）
> 文件：`backend/tests/test_pivot_query.py` 末尾追加 `TestDemandPlusSupply` 类，共 7 条用例
> （TC07-1 拆为 API 版本 + Pydantic 版本，因此实测 7 条，比计划多 1 条）。

- [x] **TC07-RED-1** `test_demand_plus_supply_422_multi_versions`（+ `test_demand_plus_supply_multi_versions_pydantic`）pivot_type='demand_plus_supply' + 2 个 version_dates → 422
- [x] **TC07-RED-2** `test_demand_plus_supply_basic_4_rows` 1 组业务维度 + Demand+Supply 双数据 → row_groups 产出 4 行（Demand / Supply / TTL_GAP / Rolling_TTLGAP）
- [x] **TC07-RED-3** `test_demand_plus_supply_missing_supply_treated_as_zero` 只有 Demand 无 Supply → Supply 视为 0，TTL_GAP = 0 - Demand
- [x] **TC07-RED-4** `test_demand_plus_supply_missing_demand_treated_as_zero` 只有 Supply 无 Demand → Demand 视为 0，TTL_GAP = Supply - 0
- [x] **TC07-RED-5** `test_demand_plus_supply_rolling_ttlgap_cumulative` 多日期 → Rolling_TTLGAP[i] = Rolling_TTLGAP[i-1] + TTL_GAP[i]（首期 = TTL_GAP[0]）
- [x] **TC07-RED-6** `test_demand_mode_unchanged_by_demand_plus_supply_branch` + `test_demand_plus_supply_api_basic` demand 模式防回归 + demand_plus_supply API 端到端

### Phase 3 — 后端实现（GREEN）

- [x] **3.1** `app/schemas.py` 在 `PivotQueryRequest` 的 `model_validator(mode="after")` 内追加：
  `pivot_type == 'demand_plus_supply'` 且 `len(version_dates) != 1` → Pydantic 422
- [x] **3.2** `app/crud/pivot_query.py` `_build_base_rows_filters` 在 `demand_plus_supply` 时把 `data_type == 'Demand'` 改为 `data_type.in_(['Demand', 'Supply'])`
- [x] **3.3** `app/crud/pivot_query.py` `query_pivot` 拆为两条路径：
  - `demand`：原实现（b 子查询 GROUP BY 含 data_type），迁出为 `_query_demand`
  - `demand_plus_supply`：b 子查询 GROUP BY **去掉 data_type**；d 子查询保留 data_type；Python 层按 §11.3 七步产出 4 行/组（迁出为 `_query_demand_plus_supply`）
- [x] **3.4** `app/api/pivot_query.py` docstring 删除「`pivot_type='demand_plus_supply'` 占位」字样，改为「支持」

### Phase 4 — OpenAPI
- [x] **4.1** 重新生成 `backend/openapi/pivot_query.json`，删除 v0.5.6 占位描述，补上 v0.5.7 §11 行为说明（52 KB）
- [x] **4.2** 验证 schema 字段（PivotQueryRequest / PivotRow / PivotQueryResponse）无新增字段（说明派生字段在 Python 层实现）

### Phase 6 — 收尾

- [x] **6.1** todo list（本文件）所有 `[ ]` 改 `[x]`
- [x] **6.2** 全量 `pytest -q` 254/254 全绿，零回归（其中 pivot_query 40/40：原 33 + 新增 7）
- [x] **6.3** `grep "占位"` 在 `app/crud/pivot_query.py` / `app/schemas.py` / `app/api/pivot_query.py` 三处全部 0 命中
- [x] **6.4** 检查 `backend/openapi/pivot_query.json` 内不再含「占位」/「placeholder」字样（0 命中）

---

## v0.5.8（新增 Excel 导出子模块）

> 适配规格：`backend/spec/weekly_demand.md` §Excel 导出子模块（v0.5.8 新增）
> 触发范围：仅周需求「查询」子模块 + 透视查询子模块；其它子功能不受影响。
> TDD：严格按 README §5.1「先 RED → 后 GREEN」流程（沿用 v0.5.7 阶段的承诺）
> 库选型：pandas + openpyxl（pandas 作为 DataFrame 容器，openpyxl 作为 xlsx 写引擎；沿用既有 `openpyxl>=3.1`）

### Phase 0 — 规格定稿

- [x] `backend/spec/weekly_demand.md` §Excel 导出子模块（§1~§10）已写入
- [x] `backend/spec/weekly_demand.md` 末尾追加 `v0.5.7 → v0.5.8` 修订记录表

### Phase 1 — Todo List（本文件）

- [x] 在本文件追加 v0.5.8 阶段章节

### Phase 2 — 测试驱动（RED）

> 文件：`backend/tests/test_dsp_export.py` + `backend/tests/test_pivot_export.py`
> 目标：13 条用例，pytest 期望全部红（404 / 422 / 含 ImportError）
> **RED 实测**：13/13 全红（404 / AttributeError），符合 TDD 期望。

#### 2.1 DspUploadRow 导出（6 条）

- [x] **2.1.1** `test_rows_export_200_basic` 构造 batch + 10 行 → 200，下载文件用 openpyxl 重新打开 → 断言列头与单元格内容与 JSON 端点一致
- [x] **2.1.2** `test_rows_export_200_empty` 0 行 batch → 200，sheet 仅表头 1 行
- [x] **2.1.3** `test_rows_export_404_unknown_id` 不存在的 id → 404
- [x] **2.1.4** `test_rows_export_422_over_limit` 200,001 行 → 422 + 中文 detail `"导出行数 N 超过上限 200000；…"`
- [x] **2.1.5** `test_rows_export_headers` 断言 `Content-Type` + `Content-Disposition` 含 `filename="dsp_upload_{id}_rows_*.xlsx"`
- [x] **2.1.6** `test_rows_export_formula_injection` `country='=1+1'` → 打开后 cell 值前缀 `'=`

#### 2.2 透视导出（7 条）

- [x] **2.2.1** `test_pivot_export_200_demand` `pivot_type='demand'` → sheet 1 列头 = `[7 列基础] + period_columns`，行数 = `len(row_groups)`
- [x] **2.2.2** `test_pivot_export_200_demand_plus_supply` 4 行/组，含 `TTL_GAP` / `Rolling_TTLGAP`
- [x] **2.2.3** `test_pivot_export_sheet2_snapshot` sheet 2 5 列快照，version_dates 用 `; ` 拼接
- [x] **2.2.4** `test_pivot_export_422_cascade_validation` 级联校验失败（config_names 缺 categories 等）
- [x] **2.2.5** `test_pivot_export_422_cartesian_overflow` `monkeypatch` 调低 `MAX_CARTESIAN` → 422
- [x] **2.2.6** `test_pivot_export_422_demand_plus_supply_multi_versions` `demand_plus_supply` + 2 version_dates → 422
- [x] **2.2.7** `test_pivot_export_200_empty_row_groups` `row_groups=[]` → sheet 1 仅 7 列基础表头，sheet 2 快照仍正确

### Phase 3 — 后端实现（GREEN）

#### 3.1 依赖

- [x] `backend/requirements.txt` 加 `pandas>=2.0`
- [x] 在 dev_env 安装：`pandas 3.0.3` + 依赖 `numpy 2.4.6` + `python-dateutil 2.9.0.post0`

#### 3.2 services 层

- [x] `app/services/excel_export.py` 新建：
  - `_export_timestamp() -> str` 返回 `YYYYMMDD_HHMMSS`
  - `_sanitize_formula(value: object) -> object` 字符串首字符 ∈ `{=, +, -, @, \t, \r}` → 加 `'` 前缀
  - `_auto_width(headers: list[str], rows: list[list]) -> list[float]` 列宽自适应
  - `build_dsp_rows_xlsx(rows: Iterable[DspUploadRow]) -> bytes` → 单 sheet「事实行」BytesIO
  - `build_pivot_xlsx(req: PivotQueryRequest, resp: PivotQueryResponse) -> bytes` → sheet 1「透视结果」+ sheet 2「查询参数快照」

#### 3.3 路由层

- [x] `app/api/dsp_uploads.py` 新增 `rows_export_endpoint`：
  - `GET /api/dsp-uploads/{id}/rows/export`
  - 校验 `crud.dsp_upload.get_upload(db, id)` → None 时 404
  - 拉全部行 `crud.dsp_upload.list_rows_all(db, id)` → 超 `MAX_DSP_EXPORT_ROWS=200_000` → 422
  - 调 `excel_export.build_dsp_rows_xlsx` → `StreamingResponse` + `Content-Disposition`
  - 文件名 `dsp_upload_{id}_rows_{_export_timestamp()}.xlsx`

- [x] `app/api/pivot_query.py` 新增 `pivot_export_endpoint`：
  - `POST /api/pivot-query/export`
  - 复用既有 `PivotQueryRequest` body（**不**重新定义 schema）
  - 路由层 `estimate_size` 预检 → 超 `MAX_CARTESIAN=50_000` → 422
  - 调 `crud.pivot_query.query_pivot` 拿 `PivotQueryResponse`
  - 调 `excel_export.build_pivot_xlsx` → `StreamingResponse`
  - 文件名 `pivot_{pivot_type}_{_export_timestamp()}.xlsx`

- [x] `app/crud/dsp_upload.py` 新增 `list_rows_all(db, upload_id) -> list[DspUploadRow]`（不分页版本）

#### 3.4 测试基础设施

- [x] `backend/tests/test_dsp_export.py` 新建（6 用例）
- [x] `backend/tests/test_pivot_export.py` 新建（7 用例）
- [x] 复用既有 `client` / `db` / `make_dsp_upload` / `make_week_dt` 等 fixture，不新建基础设施
- [x] 跑 `pytest backend/tests/test_dsp_export.py backend/tests/test_pivot_export.py -v` 13/13 全绿

### Phase 4 — OpenAPI

- [x] 启动 FastAPI，重新生成 `backend/openapi/pivot_query.json` 与 `backend/openapi/dsp_uploads.json`（含 2 个新端点）
- [x] 验证 schema：`PivotQueryRequest` 字段未新增（export 复用同一 schema）；`MAX_DSP_EXPORT_ROWS=200_000` 不出现在 schema（仅 Python 常量）

### Phase 6 — 收尾

- [x] todo list（本文件）所有 `[ ]` 改 `[x]`
- [x] 全量 `pytest -q` 无回归（在 v0.5.7 的 254/254 基础上 +14 = 268/268，含真实文件回归）
- [x] `grep -r "openpyxl" backend/app/` 仅 docstring 命中 + `app/services/excel_export.py` 实际 import（路由层无直接 import，符合 §7）
- [x] `requirements.txt` 含 `pandas>=2.0` + `openpyxl>=3.1`
- [x] 更新 `backend/spec/weekly_demand.md` 顶部版本号（如项目惯例要求 v0.5.8 顶层标识）

---

### 验证清单（每 PR）

- [x] `pytest backend/tests` 全绿（268/268）
- [x] `requirements.txt` 含 `pandas>=2.0`
- [x] `app/services/excel_export.py` 存在
- [x] `backend/openapi/*.json` 含 2 个新端点
- [x] `backend/.todo/weekly_demand.md`（本文件）v0.5.8 阶段全部 `[x]`
