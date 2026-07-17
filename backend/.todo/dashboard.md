# 今日概述模块 Todo List

# 今日概述模块 Todo List

> 适配规格：`backend/spec/dashboard.md`（SparkMemo v0.2）
> 测试策略：按 spec §Test Plan 17 条用例，**先全红后全绿**。Phase 2 产物仅 `backend/tests/test_dashboard.py`，运行 `pytest backend/tests/test_dashboard.py -v` 期望全部失败（端点 404 / `ImportError`）。
> 测试 DB：复用开发 MySQL Schema `sparkmemo`（与开发库同名）；per-test TRUNCATE 四表做隔离（沿用 `tests/conftest.py`）。
> 测试 today：沿用既有 `@pytest.fixture(autouse=True) today`，自动注入 `'2026-08-10'`。

## 总体阶段

- [x] **Phase 0**  规格定稿（`backend/spec/dashboard.md`）
- [x] **Phase 1**  生成 Todo List（本文件）
- [x] **Phase 2**  测试驱动 - 全红（`backend/tests/test_dashboard.py` 全 17 条失败）
- [x] **Phase 3**  后端实现 - 全绿（`app/crud/dashboard.py` + `app/schemas.py` + `app/api/dashboard.py` + `app/main.py`）
- [x] **Phase 4**  生成 OpenAPI（`backend/openapi/`）
- [x] **Phase 6**  收尾（更新 Todo / 清理）

---

## Phase 2 — 测试驱动（全红）

> 写入 `backend/tests/test_dashboard.py`，共 17 条覆盖 spec §Test Plan。

### 2.1 基础设施 / 响应结构

- [x] **2.1.1** `test_response_shape` —— 验证响应字段 `today` / `summary` / `companies[]` 完整
- [x] **2.1.2** `test_summary_equals_sum_of_companies` —— `summary == sum(companies)`
- [x] **2.1.3** `test_company_total_equals_bucket_sum` —— `companies[i].total == urgent + due_soon + early`

### 2.2 三档分桶

- [x] **2.2.1** `test_urgent_only_due_today` —— 仅 `due_at == today` 入 urgent
- [x] **2.2.2** `test_urgent_excludes_overdue_pending` —— `due_at < today` 的 pending 不入任何档（严格基线）
- [x] **2.2.3** `test_due_soon_within_3d` —— `today < due_at <= today+3` 入 due_soon
- [x] **2.2.4** `test_due_soon_excludes_today` —— `due_at == today` 进 urgent 不进 due_soon
- [x] **2.2.5** `test_early_due_after_3d` —— `due_at > today+3` 入 early
- [x] **2.2.6** `test_buckets_mutually_exclusive` —— 同一条任务三档仅一档非零

### 2.3 状态过滤

- [x] **2.3.1** `test_excludes_completed`
- [x] **2.3.2** `test_excludes_overdue_done`
- [x] **2.3.3** `test_excludes_remind_in_future`

### 2.4 边界 / 排序 / SQL 守护

- [x] **2.4.1** `test_empty_company_included_with_zero_counts`
- [x] **2.4.2** `test_sort_total_desc_then_urgent_then_name`
- [x] **2.4.3** `test_sql_no_db_date_func` —— SQL 不含 `CURDATE()` / `NOW()` / `CURRENT_DATE` / `GETDATE()`
- [x] **2.4.4** `test_empty_db_returns_zero_summary_empty_companies` —— 两种空库形态（保留 1 家公司 / 全空）
- [x] **2.4.5** `test_today_field_reflects_python_today` —— `today == '2026-08-10'`

---

## Phase 3 — 后端实现（全绿）

- [x] **3.1** `app/crud/dashboard.py`：新增 `count_tasks_by_company_for_today(db, today)`，单次聚合 SQL（含 LEFT JOIN、CASE WHEN 三档、命名参数 `:today` / `:soon_cutoff`）
- [x] **3.2** `app/schemas.py`：新增 `DashboardCompanyCount` / `DashboardSummary` / `DashboardTodayResponse`
- [x] **3.3** `app/api/dashboard.py`：新增 `router = APIRouter(prefix='/api/dashboard', tags=['dashboard'])`；`@router.get('/today')`
- [x] **3.4** `app/main.py`：`from app.api import dashboard` + `app.include_router(dashboard.router)`
- [x] **3.5** `pytest backend/tests/test_dashboard.py -v` 全 18 条绿（含 parametrize ×2）

---

## Phase 4 — OpenAPI

- [x] **4.1** 直接调 `app.openapi()` 导出 `backend/openapi/dashboard.json`（与既有的 `task_management.json` 同等位置）
- [x] **4.2** 校验 `/api/dashboard/today` 出现在导出文件，`DashboardTodayResponse` / `DashboardSummary` / `DashboardCompanyCount` schema 完整

---

## Phase 6 — 收尾

- [x] **6.1** 复查 Todo List 把 Phase 2 / 3 / 4 完成项标 `[x]`
- [x] **6.2** 复核 `README.md` §4 功能模块把「今日概述」标 `[x]`
- [x] **6.3** `requirements.txt` 同步（无新增依赖）

---

## 验证清单（每 PR）

- [x] `pytest backend/tests -v` 全绿（114 条：96 旧 + 18 新）
- [x] `pytest -q --collect-only` 用例数比上一基线多 18 条（含 parametrize）
- [x] OpenAPI 导出文件含 `/api/dashboard/today`
