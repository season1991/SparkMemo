# 跨表数据填充模块 Todo List

> 适配规格：`backend/spec/cross_table_fill.md`（SparkMemo v0.6.0）
> 测试策略：**严格 red → green**（先写测试，运行 `pytest -q` 期望全部 `ImportError`/`404`/失败，再实现）。
> 测试 DB：复用开发 MySQL Schema `sparkmemo`；`tests/conftest.py` 兜底 SQLite，per-test `DELETE FROM` 三张新表（FK 依赖顺序）。
> 测试组织：单文件 `tests/test_cross_table_fill.py`，覆盖 spec §Test Plan §1~§7。

## 总体阶段

- [x] **Phase 0** 规格定稿（`backend/spec/cross_table_fill.md`）
- [x] **Phase 1** 生成 Todo List（本文件）
- [x] **Phase 2** 测试驱动（红） —— 49 条测试写完，pytest 首跑全红（含 ImportError / no such table）
- [x] **Phase 3** 后端实现（绿） —— 49/49 通过；既有 304 条测试无回归（合计 353/353）
- [x] **Phase 4** 生成 OpenAPI（`backend/openapi/cross_table_fill.json`，含 7 端点 + 12 schemas）
- [x] **Phase 6** 收尾（更新 Todo / 清理闲 import / 复核 spec 一致性）
- [x] **Phase 7** hot fix v0.6.0.0.2（缺表 500 → 手工建表）—— 项目级硬约束升格：`backend/sql/dev_sql.sql` 单一汇总点；`spec/README.md` §4 落地；同步修订 `cross_table_fill.md` §Assumption 2 + `email_notification.md`。app 代码无改动。

---

## Phase 2 — 测试驱动（红）

> 文件：`backend/tests/test_cross_table_fill.py`
> 公共 fixture：`tests/conftest.py` 新增 `make_xlsx` 工厂 + DB 清理覆盖 3 张新表。

### 2.1 上传 + 解析（spec §Test Plan 1）

- [ ] **TC01** `test_upload_201_success` 双文件上传成功；`target_headers` / `base_headers` 顺序保留；`row_count` 准确；status=pending
- [ ] **TC02** `test_upload_415_bad_mime` MIME 非 `.xlsx` → 422 / 415
- [ ] **TC03** `test_upload_413_too_large` 文件 > 20 MB → 413
- [ ] **TC04** `test_upload_422_empty_workbook` 工作簿无 sheet → 422
- [ ] **TC05** `test_upload_422_duplicate_headers` 表头重复名 → 422 + 中文 detail
- [ ] **TC06** `test_upload_422_empty_headers` 表头全空 → 422
- [ ] **TC07** `test_upload_400_bad_zip` 伪文件 → 400 / 422
- [ ] **TC08** `test_upload_headers_strip_and_order` headers 含前后空格 → 自动 strip；order 保留

### 2.2 PATCH /config（spec §Test Plan 2）

- [ ] **TC09** `test_config_200_success` 合法完整配置 → 200 + config_digest + status=configured
- [ ] **TC10** `test_config_422_target_keys_unknown_field` target_keys 不在 target_headers → 422
- [ ] **TC11** `test_config_422_keys_length_mismatch` target_keys 与 base_keys 长度不等 → 422
- [ ] **TC12** `test_config_422_mapping_base_unknown` mapping.base_field 不在 base_headers → 422
- [ ] **TC13** `test_config_422_mapping_target_unknown` mapping.target_field 不在 target_headers → 422
- [ ] **TC14** `test_config_422_bad_mode` mapping.mode 取值非法 → 422
- [ ] **TC15** `test_config_409_overwrite_no_token` overwrite mapping 缺 confirm_token → 409
- [ ] **TC16** `test_config_409_new_column_with_token` 仅 new_column 模式但传 confirm_token → 409
- [ ] **TC17** `test_config_warnings_empty_target_keys` target_keys 在 target 表有空键值行 → 200 + warnings
- [ ] **TC18** `test_config_digest_reflects_options` join_mode / match_mode / case_sensitive / trim_strings digest 字段

### 2.3 execute 匹配算法（spec §Test Plan 3）

- [ ] **TC20** `test_match_exact_hit` exact 单行命中 → target 该行字段正确填充
- [ ] **TC21** `test_match_left_join_unmatched` base 缺该 key → unmatched + 1, fill 保持原值
- [ ] **TC22** `test_match_first_mode_pick_first` match_mode=first, base 3 行 → candidates[0]
- [ ] **TC23** `test_match_last_mode_pick_last` match_mode=last, base 3 行 → candidates[-1]
- [ ] **TC24** `test_match_merge_multi_default` base 3 行 → `";".join(map(str, vals))`；multi_match_count+=1
- [ ] **TC25** `test_match_inner_join_drops_unmatched` join_mode=inner → result_row_count 减少
- [ ] **TC26** `test_match_empty_target_key` target 主键空 → unmatched, fill 不动
- [ ] **TC27** `test_match_empty_base_key_excluded_from_index` base 主键空 → 该行不入 index
- [ ] **TC28** `test_match_case_insensitive` case_sensitive=false → "E001" / "e001" 命中
- [ ] **TC29** `test_match_trim_strings` trim_strings=true → " E001 " / "E001" 命中
- [ ] **TC30** `test_match_overwrite_mode` mapping.mode=overwrite → target 原列值被覆盖
- [ ] **TC31** `test_match_new_column_no_collision` new_column → 末尾追加新列
- [ ] **TC32** `test_match_new_column_with_collision` new_column target_field 与 target 原列同名 → 加 `_filled` 后缀
- [ ] **TC33** `test_match_new_column_multi_collision` 多次冲突 → `_filled_2` / `_filled_3`
- [ ] **TC34** `test_match_type_normalize_int_vs_str` base 1(int) vs target "1"(str) → 命中
- [ ] **TC35** `test_match_type_normalize_strict_float_int` base 1.0 vs target 1 → 不命中
- [ ] **TC36** `test_match_multi_match_count` 2 target 行均命中 3 行 base → multi_match_count=2
- [ ] **TC37** `test_match_filled_count` 部分 mapping 全部为空 / 缺 base_field → 不计 filled

### 2.4 双轨交付（spec §Test Plan 4）

- [ ] **TC40** `test_execute_response_preview_and_token` execute 响应 preview ≤ 1000 + download_token + download_url 路径正确
- [ ] **TC41** `test_download_with_token` 带正确 token → 200 + Content-Disposition + 文件可被 openpyxl 读回
- [ ] **TC42** `test_download_token_invalid` token 不带 / 错误 → 401
- [ ] **TC43** `test_download_status_not_executed` status != executed → 409

### 2.5 状态机 + 生命周期（spec §Test Plan 5）

- [ ] **TC50** `test_status_machine_pending_to_executed` pending → configured → executed
- [ ] **TC51** `test_config_after_executed_blocked` executed 后再 PATCH /config → 409
- [ ] **TC52** `test_expired_job_blocked` monkeypatch expires_at 为昨日 → query/config/execute → 409
- [ ] **TC53** `test_delete_cascade` DELETE 后 rows / configs 清空；CASCADE 验证
- [ ] **TC54** `test_get_job_404` 不存在 job_id → 404

### 2.6 列表 / 单查（spec §Test Plan 6）

- [ ] **TC60** `test_list_jobs_pagination_and_filter` status filter + page + size
- [ ] **TC61** `test_list_jobs_default_order_by_id_desc` 默认按 id 倒序

### 2.7 SQL 日期函数不出现（spec §Test Plan 7）

- [ ] **TC70** `test_no_sql_date_functions` 解析 / 查询 / 执行 SQL 文本不含 CURDATE / NOW / GETDATE

---

## Phase 3 — 后端实现

### 3.1 ORM 模型（`app/models.py` 新增）

- [ ] **3.1.1** `CrossTableFillJob` 类（含 status enum 注释）
- [ ] **3.1.2** `CrossTableFillRow` 类（FK CASCADE + index）
- [ ] **3.1.3** `CrossTableFillConfig` 类（PK & FK 合一，UNIQUE on job_id）

### 3.2 Pydantic schemas（`app/schemas.py` 新增）

- [ ] **3.2.1** `CrossTableFillUploadResponse`
- [ ] **3.2.2** `CrossTableFillJobRead` / `CrossTableFillJobListResponse`
- [ ] **3.2.3** `CrossTableFillMappingItem`（含 base_field / target_field / mode 必填 + Literal mode）
- [ ] **3.2.4** `CrossTableFillConfigRequest`（含 case_sensitive / trim_strings / confirm_token 校验）
- [ ] **3.2.5** `CrossTableFillConfigDigest` / `CrossTableFillConfigResponse`
- [ ] **3.2.6** `CrossTableFillPreviewRow`（dict 形态）
- [ ] **3.2.7** `CrossTableFillExecuteResponse`

### 3.3 Service（`app/services/cross_table_fill.py`）

- [ ] **3.3.1** `parse_table(content, role) -> (headers, list[dict])` —— 解析 xlsx；异常类 `BadCellTypeError` / `EmptyHeadersError` / `DuplicateHeadersError`
- [ ] **3.3.2** `_normalize(value, configs)` —— 主键归一化
- [ ] **3.3.3** `execute_match(job, configs, db) -> ExecuteResult` —— 索引 + 遍历 + 列冲突处理
- [ ] **3.3.4** `build_xlsx(headers, rows) -> bytes` —— 输出 xlsx

### 3.4 CRUD（`app/crud/cross_table_fill.py`）

- [ ] **3.4.1** `create_job` / `get_job` / `list_jobs` / `delete_job`
- [ ] **3.4.2** `bulk_insert_rows`（role + data） / `get_rows` / `update_row_key_value`
- [ ] **3.4.3** `upsert_config`
- [ ] **3.4.4** token store（`put_token` / `take_token` / `pop_token`）；进程内 dict + 5min TTL

### 3.5 API（`app/api/cross_table_fill.py`）

- [ ] **3.5.1** `POST /api/cross-table-fill/jobs`（multipart 双文件 + expires_in_hours）
- [ ] **3.5.2** `GET /api/cross-table-fill/jobs/{job_id}`
- [ ] **3.5.3** `PATCH /api/cross-table-fill/jobs/{job_id}/config`
- [ ] **3.5.4** `POST /api/cross-table-fill/jobs/{job_id}/execute`
- [ ] **3.5.5** `GET /api/cross-table-fill/jobs/{job_id}/download`
- [ ] **3.5.6** `DELETE /api/cross-table-fill/jobs/{job_id}`
- [ ] **3.5.7** `GET /api/cross-table-fill/jobs?status=&page=&size=`
- [ ] **3.5.8** `app/main.py` `app.include_router(cross_table_fill.router)` + version bump 至 0.6.0

### 3.6 跑全测到 GREEN

- [ ] **3.6.1** `pytest backend/tests/test_cross_table_fill.py -v` 全过
- [ ] **3.6.2** `pytest backend/tests -v` 不破坏其它模块

### 3.7 收尾

- [x] **3.7.1** 所有 docstring 中文 + 章节注释
- [x] **3.7.2** `backend/spec/README.md` 模块表保留 v0.6.0 待开发 → 改为已发布
- [x] **3.7.3** spec 文档自我审计一遍（如有偏差同步更新）

---

## Phase 7 — hot fix：缺表 500 → 手工建表

**问题（v0.6.0.0.2）**：用户首次部署到生产 MySQL `sparkmemo` 时，POST /jobs 上传两步走通后，INSERT 阶段报 `Table 'sparkmemo.cross_table_fill_jobs' doesn't exist` → 500。根因是项目从未给新表手工建表（spec 声称 create_all 自动但 lifespan 没调）。

**修复完成清单**：

- [x] 新增 `backend/sql/dev_sql.sql`：含 v0.6.0 三张表完整 `CREATE TABLE IF NOT EXISTS`（含 COMMENT / FK CASCADE / 索引）
- [x] `backend/spec/README.md` §4 新增「数据库表手工建表规范」全局硬约束
- [x] `backend/spec/cross_table_fill.md` §Assumption 2 改文本指向 dev_sql.sql
- [x] `backend/spec/cross_table_fill.md` §11 v0.6.0.0.2 增补修订记录
- [x] `backend/spec/email_notification.md` 引用 README §4
- [x] `backend/.todo/cross_table_fill.md` 本文件标记完成
- [ ] **（用户侧）人工跑 SQL**：在 MySQL `sparkmemo` 执行 `mysql -u root sparkmemo < backend/sql/dev_sql.sql`（或 pymysql 等价），重启 uvicorn，验证上传可 201
