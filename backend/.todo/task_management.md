# 任务管理模块 Todo List

> 适配规格：`backend/spec/task_management.md`（SparkMemo v0.1）
> 测试策略：按 spec §5.1，**先全红后全绿**。Phase 2 产物仅 `backend/tests/`，运行 `pytest` 期望全部失败（含 `ImportError` / `AttributeError` / `404`）。
> 测试 DB：复用开发 MySQL Schema `sparkmemo`（与开发库同名）；per-test TRUNCATE 四表做隔离。
> 测试组织：按实体分文件（`test_companies` / `test_projects` / `test_task_types` / `test_tasks` / `test_reminders` / `test_overdue_job`）。

## 总体阶段

- [x] **Phase 0**  规格定稿（`backend/spec/`）
- [x] **Phase 1**  生成 Todo List（本文件）
- [x] **Phase 2**  测试驱动 - 全红（`backend/tests/` 全失败）
- [ ] **Phase 3**  后端实现 - 全绿（`app/` 代码让 pytest 全过）
- [ ] **Phase 4**  生成 OpenAPI（`backend/openapi/`）
- [ ] **Phase 6**  收尾（更新 Todo / 清理）

> Phase 5（原「前端按契约生成」）已删除，不在本模块范围内。

---

## Phase 2 — 测试驱动（全红）

### 2.0 测试基础设施

- [x] **2.0.1** 新建 `backend/tests/__init__.py`（空）
- [x] **2.0.2** 新建 `backend/tests/conftest.py`
  - 沿用 `settings.DATABASE_URL`（Schema = `sparkmemo`，与开发库一致）
  - `db` fixture：每用例 `TRUNCATE` 四张表（依赖外键时先关 FK_CHECKS）
  - `client` fixture：`httpx.AsyncClient(app=app, base_url='http://testserver')`
  - 工厂函数：`make_company(db, name, notes=None)` / `make_project` / `make_task_type` / `make_task`
  - `@pytest.fixture(autouse=True)` 注入 `today`：monkeypatch `app.services.scheduler.date` 类的 `today()` 返回固定 `'2026-08-10'`
- [x] **2.0.3** 新建 `pytest.ini`：`asyncio_mode = auto`、`testpaths = tests`
- [x] **2.0.4** 新建 `backend/requirements-dev.txt`：`pytest`、`pytest-asyncio`、`httpx`

### 2.1 公司 Companies（对应 spec §Test Plan 1）→ `test_companies.py`

- [x] **2.1.1** `test_create_company_success` → 201
- [x] **2.1.2** `test_create_company_missing_name` → 422
- [x] **2.1.3** `test_create_company_duplicate_name` → 409
- [x] **2.1.4** `test_list_companies_keyword_fuzzy` `?keyword=AC` 仅模糊匹配
- [x] **2.1.5** `test_list_companies_pagination` `?page=2&size=10`
- [x] **2.1.6** `test_get_company_detail`
- [x] **2.1.7** `test_get_company_not_found` → 404
- [x] **2.1.8** `test_update_company`
- [x] **2.1.9** `test_delete_company_success`
- [x] **2.1.10** `test_delete_company_referenced_by_project` → 409
- [x] **2.1.11** `test_delete_company_referenced_by_task` → 409

### 2.2 项目 Projects（§Test Plan 2）→ `test_projects.py`

- [x] **2.2.1** `test_create_project_success`
- [x] **2.2.2** `test_create_project_missing_company_id` → 400
- [x] **2.2.3** `test_create_project_invalid_company_id` → 422
- [x] **2.2.4** `test_create_project_duplicate_in_same_company` → 409
- [x] **2.2.5** `test_create_project_same_name_different_company` 允许
- [x] **2.2.6** `test_list_projects_filter_by_company`
- [x] **2.2.7** `test_list_projects_keyword`
- [x] **2.2.8** `test_get_project_detail`
- [x] **2.2.9** `test_update_project`
- [x] **2.2.10** `test_delete_project`

### 2.3 任务类型 Task Types（§Test Plan 3）→ `test_task_types.py`

- [x] **2.3.1** `test_list_task_types_no_pagination` 全量
- [x] **2.3.2** `test_create_task_type_success`
- [x] **2.3.3** `test_create_task_type_duplicate_name` → 409
- [x] **2.3.4** `test_update_task_type`
- [x] **2.3.5** `test_get_task_type_detail`
- [x] **2.3.6** `test_get_task_type_not_found`
- [x] **2.3.7** `test_delete_task_type_success`
- [x] **2.3.8** `test_delete_task_type_referenced_by_task` → 409

### 2.4 任务 Tasks 字段校验（§Test Plan 4）→ `test_tasks.py`

- [x] **2.4.1** `test_create_task_missing_company_id` → 400
- [x] **2.4.2** `test_create_task_missing_project_id` → 400
- [x] **2.4.3** `test_create_task_remind_start_after_due` → 400
- [x] **2.4.4** `test_create_task_invalid_due_at_format` → 400
- [x] **2.4.5** `test_create_task_invalid_remind_start_format` → 400
- [x] **2.4.6** `test_create_task_invalid_company_id` → 422
- [x] **2.4.7** `test_create_task_invalid_project_id` → 422
- [x] **2.4.8** `test_create_task_invalid_task_type_id` → 422
- [x] **2.4.9** `test_create_task_due_at_stored_as_10_char` 入库长度断言

### 2.5 任务 Tasks CRUD（§Test Plan 5）→ `test_tasks.py`

- [x] **2.5.1** `test_create_task_success` → 201，`status='pending'`
- [x] **2.5.2** `test_create_task_default_remind_start_at` 缺省 → `due_at − 1 天`
- [x] **2.5.3** `test_update_task` 修改无副作用
- [x] **2.5.4** `test_update_task_invalid_dates` `remind_start > due` → 400
- [x] **2.5.5** `test_delete_task` → 204
- [x] **2.5.6** `test_complete_task` → `status='completed'`，`completed_at=today`
- [x] **2.5.7** `test_complete_task_already_completed` → 409（防非法跃迁）

### 2.6 提醒计划计算（§Test Plan 6）→ `test_reminders.py`

- [x] **2.6.1** `test_compute_reminders_unit_8_days` `due=08-15, start=08-08` → 8 条
- [x] **2.6.2** `test_compute_reminders_unit_2_days` → 2 条
- [x] **2.6.3** `test_compute_reminders_unit_same_day` → 1 条
- [x] **2.6.4** `test_get_task_includes_reminders` 响应 `reminders` 与实时计算一致
- [x] **2.6.5** `test_update_task_reminders_reflect_new_plan` 修改后立即反映

### 2.7 列表筛选 `remind_today=true`（§Test Plan 7）→ `test_reminders.py`

- [x] **2.7.1** `test_remind_today_returns_in_window` 注入 `today='2026-08-10'`
- [x] **2.7.2** `test_remind_today_excludes_completed`
- [x] **2.7.3** `test_remind_today_excludes_overdue_done`
- [x] **2.7.4** `test_remind_today_excludes_not_started` `remind_start > today`
- [x] **2.7.5** `test_remind_today_excludes_finished_window` `due < today`
- [x] **2.7.6** `test_remind_today_sql_no_db_date_func` 断言 SQL 文本不含 `CURDATE()` / `NOW()` / `CURRENT_DATE` / `GETDATE()`

### 2.8 逾期自动完成 Job（§Test Plan 8）→ `test_overdue_job.py`

- [x] **2.8.1** `test_overdue_marks_task_overdue_done` `due=08-10, today=08-15` → `overdue_done`，`completed_at=08-15`
- [x] **2.8.2** `test_overdue_skips_within_3_days` `due=08-13` 不动
- [x] **2.8.3** `test_overdue_skips_completed`
- [x] **2.8.4** `test_overdue_skips_already_overdue_done`
- [x] **2.8.5** `test_overdue_idempotent`
- [x] **2.8.6** `test_overdue_sql_no_db_date_func` 日期必须参数化
- [x] **2.8.7** `test_overdue_scheduler_registered` APScheduler 注册 `check_overdue_tasks` cron（每日 00:00）

---

## Phase 3 — 后端实现（全绿）

- [ ] **3.1** `app/models.py`：Company / Project / TaskType / Task（含 FK、unique、`status` 默认 `pending`）
- [ ] **3.2** `app/schemas.py`：Pydantic v2 Schema；`field_validator` 校验 `YYYY-MM-DD`
- [ ] **3.3** `app/database.py`：engine + `create_all` + `get_db` 依赖
- [ ] **3.4** `app/crud/`：四实体 CRUD
- [ ] **3.5** `app/api/`：四套路由挂到 `main.py`
- [ ] **3.6** `app/services/reminders.py`：`compute_reminders` 纯函数
- [ ] **3.7** `app/services/scheduler.py`：`check_overdue_tasks(db, today)` + APScheduler 注册
- [ ] **3.8** `pytest backend/tests` 全绿

---

## Phase 4 — OpenAPI

- [ ] **4.1** 启动服务导出 `backend/openapi/task_management.{json,yaml}`
- [ ] **4.2** 校验覆盖 spec §API And Behavior 所有端点

---

## Phase 6 — 收尾

- [ ] **6.1** 复查 Todo List，把 Phase 2 / 3 / 4 已完成项标记 `[x]`
- [ ] **6.2** 复核 `.gitignore` 策略（OpenAPI 进版本、tests 进版本）
- [ ] **6.3** `requirements.txt` / `requirements-dev.txt` 同步到位

---

## 验证清单（每 PR）

- [ ] `pytest backend/tests` 全绿
- [ ] `pytest -q --collect-only` 用例数与 Phase 2 一致
- [ ] `requirements.txt` / `requirements-dev.txt` 同步