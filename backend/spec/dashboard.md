# 今日概述模块规格

> 适配规格：SparkMemo 任务提醒系统 v0.2
> 适用范围：单用户本地版，无登录。**主页面 - 今日概述**，按公司维度展示今日需要关注的 pending 任务计数。
> 范围：**仅后端新增一个聚合接口** `GET /api/dashboard/today`，不涉及前端、不修改既有实体表结构、不引入新表。
> **数据库可移植性约束**：所有日期字段统一使用 10 字符字符串 `YYYY-MM-DD`；任何涉及「当前日期」「+3 天」的 SQL 计算由 Python 层完成并作为命名参数传入，**不**使用 `CURDATE()` / `NOW()` / `CURRENT_DATE` / `GETDATE()` 等数据库内置函数。

---

## Summary

实现一个**只读聚合接口** `GET /api/dashboard/today`：

1. 输入无参；后端在请求处理时通过 `get_today()`（来自 `app.services.scheduler`）取 `today`（`YYYY-MM-DD`），并在 Python 层计算 `soon_cutoff = today + 3 days`；
2. **严格基线** 过滤：`tasks.status = 'pending' AND tasks.remind_start_at <= today AND tasks.due_at >= today`；
3. 在基线之上按 `due_at` 划分三档：
   - **紧急 urgent**：`due_at == today`；
   - **临期 due_soon**：`today < due_at <= soon_cutoff`；
   - **尚早 early**：`due_at > soon_cutoff`；
4. 按 `companies` **全量列出**（LEFT JOIN），即使该公司今日没有任何任务也要出现，计数全 0；
5. 响应同时返回 `summary`（全公司合计）和 `companies[]`（按 `total DESC, urgent DESC, company_name ASC` 排序）；`summary` 在 Python 层由 `companies` 求和得到，保持唯一真理源。

---

## Key Changes

### 数据库

> **不修改任何既有表，不新增任何表。** 本模块是纯读取聚合接口。

`companies`、`projects`、`task_types`、`tasks` 四张表的字段定义与既有 `task_management.md` 完全一致。

### 新增模块文件

| 路径 | 作用 |
|------|------|
| `backend/app/crud/dashboard.py` | 聚合查询：`count_tasks_by_company_for_today(db, today)` |
| `backend/app/schemas.py`（追加） | `DashboardCompanyCount` / `DashboardSummary` / `DashboardTodayResponse` |
| `backend/app/api/dashboard.py` | 路由：`router = APIRouter(prefix='/api/dashboard', tags=['dashboard'])`；暴露 `GET /today` |
| `backend/app/main.py`（编辑） | 挂载路由：`from app.api import dashboard` + `app.include_router(dashboard.router)` |

### `DashboardCompanyCount` 字段

```python
company_id    Mapped[int]       # companies.id
company_name  Mapped[str]       # companies.name
urgent        Mapped[int]       # 该公司今日紧急任务数；>=0
due_soon      Mapped[int]       # 该公司今日临期任务数；>=0
early         Mapped[int]       # 该公司今日尚早任务数；>=0
total         Mapped[int]       # 上述三档之和；>=0
```

### `DashboardSummary` 字段

```python
urgent    Mapped[int]       # 全局紧急任务数；= sum(companies[].urgent)
due_soon  Mapped[int]       # 全局临期任务数；= sum(companies[].due_soon)
early     Mapped[int]       # 全局尚早任务数；= sum(companies[].early)
total     Mapped[int]       # 全局总数；= sum(companies[].total)
```

### `DashboardTodayResponse` 字段

```python
today      Mapped[str]                  # YYYY-MM-DD；服务端返回值
summary    Mapped[DashboardSummary]
companies  Mapped[list[DashboardCompanyCount]]  # 长度 == companies 表行数
```

---

## 三档分桶规则（**严格基线**）

> 所有分桶先经过同一基线过滤；分桶谓词只是在基线之上再加上 `due_at` 的范围。

### 基线（不变式）

```
status = 'pending'
AND remind_start_at <= today
AND due_at         >= today
```

> **严格基线后果**：`due_at < today` 的 pending 任务（即「已逾期但尚未被后台标为 `overdue_done`」的任务）**不会出现在今日概述中**。
> 这是拍板的取舍：避免与「任务管理」列表的 `overdue_done` 状态重复呈现；用户如有需要可在 `/api/tasks` 列表里以 `status='pending' AND due_from='' AND due_to=''` 自行查看。

### 档位 SQL 谓词

| 档位 | 路径 | 分桶谓词 |
|------|------|---------|
| **urgent** | `due_at == today` | `due_at <= today`（与基线 `due_at >= today` 并存 ⇒ 等价 `due_at == today`） |
| **due_soon** | `today < due_at <= soon_cutoff` | `due_at > today AND due_at <= soon_cutoff` |
| **early** | `due_at > soon_cutoff` | `due_at > soon_cutoff` |

其中 `soon_cutoff` 的计算：

```python
# Python 层（不写入 SQL）
soon_cutoff = (date.fromisoformat(today) + timedelta(days=3)).isoformat()
```

### 三档互斥穷尽性

> 在严格基线 + `due_at >= today` 的前提下，`due_at == today`、`today < due_at <= today + 3`、`due_at > today + 3` 三段互斥穷尽。同一任务不可能同时落入两档。

### 计算口径（与既有约定保持一致）

- `today` 取 `services.scheduler.get_today()`，与 `check_overdue_tasks` Job / `remind_today=true` 列表接口一致；
- 测试通过 `monkeypatch scheduler.date` 把 `today` 固定为 `'2026-08-10'`（与既有 `conftest.py` 完全一致，无需新增 fixture）；
- `today` 与 `soon_cutoff` 作为命名参数 `:today` / `:soon_cutoff` 传入 SQL；
- SQL 文本断言：不含 `CURDATE()` / `NOW()` / `CURRENT_DATE` / `GETDATE()`（与现有 `test_overdue_job.py` 测试约定保持一致）。

---

## SQL（单次聚合 + LEFT JOIN 含全公司）

```sql
SELECT
  c.id   AS company_id,
  c.name AS company_name,
  SUM(CASE
        WHEN t.status = 'pending'
         AND t.remind_start_at <= :today
         AND t.due_at >= :today
         AND t.due_at <= :today
        THEN 1 ELSE 0 END) AS urgent,
  SUM(CASE
        WHEN t.status = 'pending'
         AND t.remind_start_at <= :today
         AND t.due_at >= :today
         AND t.due_at > :today
         AND t.due_at <= :soon_cutoff
        THEN 1 ELSE 0 END) AS due_soon,
  SUM(CASE
        WHEN t.status = 'pending'
         AND t.remind_start_at <= :today
         AND t.due_at >= :today
         AND t.due_at > :soon_cutoff
        THEN 1 ELSE 0 END) AS early,
  SUM(CASE
        WHEN t.status = 'pending'
         AND t.remind_start_at <= :today
         AND t.due_at >= :today
        THEN 1 ELSE 0 END) AS total
FROM companies c
LEFT JOIN tasks t
       ON t.company_id = c.id
GROUP BY c.id, c.name
ORDER BY total DESC, urgent DESC, c.name ASC;
```

### 实现要点

- 走原生 `sqlalchemy.text()` + 命名参数，不引入 ORM 聚合模型；
- 一次 DB round-trip 拿到所有公司在三档上的分布；`summary` 在 Python 层 `sum()` 得到，避免双源真理；
- LEFT JOIN 的 `total = 0` 行（`SUM(CASE WHEN 0 ELSE 0 END)` 全部为 0）也会出现在结果里，**0 公司也会被列出**（满足"全部列出"约束）；
- 排序由 SQL 完成，前端无需再做；
- 不引入新的 cron / APScheduler Job（**无任何后台写动作**）。

---

## API And Behavior

所有路径以 `/api` 前缀；本模块只有一个**只读**接口。

### Dashboard

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/dashboard/today` | 今日概述：返回 `today` + `summary` + `companies[]` |

### `GET /api/dashboard/today`

**请求**
- 无路径参数；
- 无 query 参数。

**响应 200**
```jsonc
{
  "today": "2026-08-10",
  "summary": {
    "urgent": 1,
    "due_soon": 4,
    "early": 5,
    "total": 10
  },
  "companies": [
    { "company_id": 2, "company_name": "ACME 集团", "urgent": 1, "due_soon": 3, "early": 2, "total": 6 },
    { "company_id": 7, "company_name": "Beta 科技", "urgent": 0, "due_soon": 0, "early": 0, "total": 0 }
  ]
}
```

**行为约定**
- `today` 字段值始终等于 **响应生成那一刻** Python 层的 `date.today().isoformat()`，与既有 `scheduler.get_today()` 一致；测试通过 `monkeypatch` 注入；
- `companies[]` 长度恒等于 `companies` 表行数（即使无任务，全表也出齐）；
- `summary` 字段值恒等于 `companies[]` 同名字段的求和；
- `companies[i].total == companies[i].urgent + companies[i].due_soon + companies[i].early`（服务层断言，防止 COUNT/SUM 失误）。

### 错误约定

| HTTP | 场景 |
|------|------|
| 405 | 非 GET 方法（本路由**只允许 GET**） |
| 500 | DB 连接 / SQL 异常（由 FastAPI 默认处理） |

> 本接口无业务校验失败分支——所有日期与分桶均经过 SQL 参数化，无用户输入；200 always（除非后端异常）。

---

## Test Plan

> 测试位于 `backend/tests/test_dashboard.py`，**先全红后全绿**，与既有 `test_tasks.py` 同组织。
> 测试数据库与 `conftest.py` 的 `db` fixture 同源（per-test TRUNCATE 四表）；`today` 由既有 `@pytest.fixture(autouse=True) today` 自动注入为 `'2026-08-10'`。

### 单元 / 集成

| # | 用例 | 测试目的 | 关键断言 |
|---|------|---------|---------|
| 1 | `test_response_shape` | 保证前端拿到的 JSON 结构稳定（字段名/嵌套形态稳定，前后端协作的最低要求） | 200；响应含 `today`/`summary`/`companies[]`；`summary` 含 `urgent`/`due_soon`/`early`/`total`；`companies[0]` 含 `company_id`/`company_name`/`urgent`/`due_soon`/`early`/`total` |
| 2 | `test_summary_equals_sum_of_companies` | 防止 `summary` 与 `companies[]` 出现双源真理——任何显示给用户的「今日总数」必须唯一来自 companies 求和 | 多公司多任务下，`summary.urgent == sum(c.urgent for c in companies)`，其余三档同理 |
| 3 | `test_company_total_equals_bucket_sum` | 防止 SQL 聚合时 `total` 漏写 CASE 条件导致分桶统计与 total 不一致 | `companies[i].total == companies[i].urgent + companies[i].due_soon + companies[i].early` |
| 4 | `test_urgent_only_due_today` | 验证「紧急」分桶谓词只命中 `due_at == today`，边界 `today-1`/`today+1` 不混进 urgent | 同一公司：`due_at = today-1`、`due_at = today`、`due_at = today+1`，确认仅 `today` 落入 urgent |
| 5 | `test_urgent_excludes_overdue_pending`（严格基线） | 验证严格基线一致性——`due_at < today` 的任务不应出现在今日概述，与产品决策一致 | `due_at = today-1` 的 pending 任务**不**出现在任何公司任何档（基线先排除） |
| 6 | `test_due_soon_within_3d` | 验证「临期 = `(today, today+3]`」闭开区间正确（含 `today+3`） | `due_at = today+1`、`today+2`、`today+3` 各 1 条 ⇒ 该公司 `due_soon = 3` |
| 7 | `test_due_soon_excludes_today` | 验证今日到期优先归 urgent 而非 due_soon，三档边界严格不重叠 | `due_at = today` ⇒ 进 urgent 不进 due_soon |
| 8 | `test_early_due_after_3d` | 验证「尚早 = `due_at > today+3`」下界正确 | `due_at = today+4`、`today+10` ⇒ 进 early |
| 9 | `test_buckets_mutually_exclusive` | 端到端校验三档互斥——同一条任务不可能三档中有非零计数 | 同一条任务三档仅落一档（通过遍历 `tasks` 表 + 比较 `companies[]` 对应公司汇总得到） |
| 10 | `test_excludes_completed` | 验证已完成任务不被今日概述打扰（用户已主动处置） | `status='completed'` 不计入任何档 |
| 11 | `test_excludes_overdue_done` | 验证后台自动结案的任务不进任何档（避免与列表页重复呈现） | `status='overdue_done'` 不计入任何档 |
| 12 | `test_excludes_remind_in_future` | 验证严格基线上界——「还没开始提醒」的任务不计入今日概述 | `remind_start_at = today+1` 不计入任何档 |
| 13 | `test_empty_company_included_with_zero_counts` | 验证 LEFT JOIN 自然处理 0 任务公司：UI 可以一眼看出「今日该客户无事」 | 新建 `ACME` 公司但无任务 ⇒ 出现在 `companies[]`，`urgent/due_soon/early/total` 均为 0 |
| 14 | `test_sort_total_desc_then_urgent_then_name` | 验证排序契约——前端可以直接信任顺序，不需要二次排序 | 构造 3 家公司 `total` 不同 / `urgent` 不同 / `name` 不同，断言最终顺序 |
| 15 | `test_sql_no_db_date_func` | 守护数据库可移植性约束——与既有 `check_overdue_tasks` Job 同等要求 | 通过拦截 `sqlalchemy.text` 或扫描最终执行的 SQL 字符串，断言不含 `CURDATE()` / `NOW()` / `CURRENT_DATE` / `GETDATE()`；两个日期参数 `:today` 与 `:soon_cutoff` 必须在绑定参数中 |
| 16 | `test_empty_db_returns_zero_summary_empty_companies` | 验证空库边界——不出现 500 / KeyError / NoneType | 全空数据库（清空 `companies` 与 `tasks`，但保留至少 1 家公司确保非空数组分支） ⇒ `summary` 全 0；删除全部 `companies` ⇒ 响应仍合法，`companies` 长度 0；`summary` 全 0（注：保留 1 家公司=0 任务的版本作另一个用例） |
| 17 | `test_today_field_reflects_python_today` | 确保 `today` 字段语义与 `scheduler.get_today()` 一致（同源），不是 SQL 取的 | 不依赖 monkeypatch 子，直接调用端点，断言响应 `today == '2026-08-10'`（与 conftest 注入一致） |

### SQL 文本无 DB 日期函数（用例 15 实施细节）

- 用 `SQLAlchemy.event.listens_for(engine, "before_cursor_execute")` 在 conftest 已注册的事件外**临时**注册一个监听器，捕获该请求执行的最终 SQL 字符串；
- 断言 `sql_text` 中不含 `CURDATE()` / `NOW()` / `CURRENT_DATE` / `GETDATE()`；
- 断言 `params` 中含 `:today = '2026-08-10'` 与 `:soon_cutoff = '2026-08-13'`；
- 不影响其它用例的事件链（teardown 时 remove listener）。

### 排序用例 14 实施细节

构造：

```text
公司 A  total=10 urgent=3 name='ACME'
公司 B  total=10 urgent=2 name='Beta'
公司 C  total=5  urgent=0 name='Gamma'
公司 D  total=5  urgent=0 name='Delta'
```

期望顺序：`A, B, C, D`（先 `total desc`，平局按 `urgent desc`，再平局按 `name asc`）。

---

## Assumptions

1. **单用户本地版**维持不变：不引入登录、不引入多租户；
2. **数据库可移植性**：所有 SQL 中涉及「当前日期 / 时间」「+3 天」的位置均由 Python 层计算后作为命名参数（`:today` / `:soon_cutoff` 等）传入；不依赖 `CURDATE()` / `NOW()` / `CURRENT_DATE` / `GETDATE()` 等数据库内置函数；
3. **严格基线**：今日概述只关心 `remind_start_at <= today <= due_at` 的 pending 任务。**已逾期**（`due_at < today`）的 pending 不在今日概述中——它们会在「任务管理」列表以 `status='pending'` 配合 `due_to` 过滤器呈现；如逾期未处理满 3 天，会被后台 Job 标记为 `overdue_done`，同样不计入今日概述；
4. **「截止日 = 今天」算紧急**：严格基线下，紧急档只含 `due_at == today`；
5. **三档互斥穷尽**：在三档各自的 SQL 谓词之下，三段 `[due_at == today]` / `[today < due_at <= today+3]` / `[due_at > today+3]` 互斥且穷尽；
6. **`soon_cutoff` 写死 3 天**：本日后端不接受 query 参数定制；若以后需要可配置，再单独迭代（在本版本范围外）；
7. **空公司全量列出**：LEFT JOIN 保证 DB 自然输出全部 companies 行；即使该公司今日 0 任务也出现，计数全 0；
8. **不引入缓存层**：单次聚合 SQL 性能优先；数据规模在「数十家公司、数百条任务」量级下，单次 `GROUP BY` 是 ms 级；如未来出现性能瓶颈再考虑物化视图 / Redis 缓存；
9. **不引入新的后台 Job / WebSocket**：本模块纯只读，不触发任何写入或推送；
10. **不修改既有实体表**：companies / projects / task_types / tasks 四表的字段与索引保持不变；
11. **不暴露 `remind_rule` 字段**：与既有 `task_management.md` Assumptions 一致——`remind_rule` 仅写入路径上的业务意图，不入库；
12. **`summary` 单一真理源**：`summary` 字段在 Python 层从 `companies[]` 求和得到，避免 SQL 与 Python 双源计算结果不一致；
13. **`companies[]` 排序由 SQL 完成**：固定为 `total DESC, urgent DESC, company_name ASC`；前端不做二次排序；
14. **本次 spec 范围内不实现前端**：仅交付后端接口；前端视图与导航项留给后续 spec 单独写。
