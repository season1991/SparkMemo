# 升级：提醒规则 (`remind_rule`) 改造

> 适配规格：`backend/spec/task_management.md`（已更新，含 `remind_rule` 7 档预设）
> 前端契约：`frontend/spec/task_management.md`（已更新，TaskForm 改用 `<el-select>`）
> OpenAPI：`backend/openapi/task_management.json`（已更新，新增 `RemindRule` / `TaskCreate` / `TaskUpdate` schema）
>
> 本文件追踪本次升级涉及的**代码 / 测试改造**工作（spec 已对齐，不再列）。

---

## 0. 升级要点

- 入参从 `remind_start_at: 'YYYY-MM-DD'` 改为 `remind_rule` (枚举) + 可选 `custom_remind_start_at`；
- 新增 `app/services/reminders.py::resolve_remind_start_at(due_at, remind_rule, custom_remind_start_at=None) -> str`；
- 新增 `app/services/reminders.py::shift_month(d, months=-1) -> date` 月份偏移纯函数（含 clamp）；
- `TaskCreate` / `TaskUpdate` 入参 schema 改造；`TaskRead` 响应**不变**（仍含 `remind_start_at`，不含 `remind_rule`）；
- 编辑表单前端反推 `remind_rule`（按 `due_at − remind_start_at`）；反推失败一律归 `custom`。

---

## 1. 后端代码（`backend/app/`）

- [ ] **1.1** `app/services/reminders.py` 新增 `shift_month(d, months=-1) -> date` 月份偏移函数（含月末 clamp）。
- [ ] **1.2** `app/services/reminders.py` 新增 `REMIND_RULES` 常量表（key=`on_due`/`before_1d`/.../`custom`，value=`(kind, value)`）。
- [ ] **1.3** `app/services/reminders.py` 新增 `resolve_remind_start_at(due_at, remind_rule, custom_remind_start_at=None) -> str` 纯函数；`custom` 模式但缺 `custom_remind_start_at` 抛 `ValueError`。
- [ ] **1.4** `app/schemas.py` 新增 `RemindRule` 枚举（String + `Literal["on_due","before_1d","before_2d","before_3d","before_1w","before_1m","custom"]`）。
- [ ] **1.5** `app/schemas.py` 改造 `TaskCreate`：移除 `remind_start_at`；新增 `remind_rule`（必填，枚举）+ `custom_remind_start_at`（可选，str | None）；保留 `title` / `description` / `task_type_id` / `company_id` / `project_id` / `due_at`。
- [ ] **1.6** `app/schemas.py` 改造 `TaskUpdate`：同 1.5；`custom_remind_start_at` 沿用相同语义。
- [ ] **1.7** `app/schemas.py` 改造 `TaskRead`：**不变**（继续含 `remind_start_at` / 不含 `remind_rule`），仅复核 Python 字段顺序与 OpenAPI 一致。
- [ ] **1.8** `app/api/tasks.py::create_task` / `update_task`：移除对 `payload.remind_start_at` 的直接使用；调用 `resolve_remind_start_at(payload.due_at, payload.remind_rule, payload.custom_remind_start_at)`；捕获 `ValueError` 转 400；写入 `task.remind_start_at = resolved`。
- [ ] **1.9** `app/api/tasks.py::get_task` 实时计算 `reminders` 的逻辑**不变**；仅复核依赖入参。
- [ ] **1.10** `app/crud/task.py`：保留 `create_task` / `update_task` 的字段白名单但去掉 `remind_start_at`（由路由层翻译后传入）。

---

## 2. 后端测试（`backend/tests/`）

> 全部用例沿用现有数据库与 `conftest.py`，仅替换入参语义。

### 2.0 新增 `test_remind_rule.py`

- [ ] **2.0.1** `test_resolve_on_due` `due='2026-08-15'` + `'on_due'` → `'2026-08-15'`
- [ ] **2.0.2** `test_resolve_before_1d_2d_3d` → 分别为 `'2026-08-14'` / `'2026-08-13'` / `'2026-08-12'`
- [ ] **2.0.3** `test_resolve_before_1w` → 固定 7 天：`'2026-08-08'`
- [ ] **2.0.4** `test_resolve_before_1m_normal` `due='2026-08-15'` → `'2026-07-15'`
- [ ] **2.0.5** `test_resolve_before_1m_month_end_clamp_non_leap` `due='2026-03-31'` → `'2026-02-28'`
- [ ] **2.0.6** `test_resolve_before_1m_month_end_clamp_leap` `due='2024-03-31'` → `'2024-02-29'`
- [ ] **2.0.7** `test_resolve_custom_with_date` `due='2026-08-15'` + `'custom'` + `custom_remind_start_at='2026-08-10'` → `'2026-08-10'`
- [ ] **2.0.8** `test_resolve_custom_missing_date_raises` `due='2026-08-15'` + `'custom'` + 缺 `custom_remind_start_at` → `ValueError`
- [ ] **2.0.9** `test_shift_month_pure_function` 边界用例：`y/m/d` 经 `months=-1` 后正确 clamp

### 2.1 `test_tasks.py` 入参改造

> 现有所有 `payload = {... "remind_start_at": "2026-08-08" ...}` 改为 `payload = {... "remind_rule": "before_1d", "custom_remind_start_at": None ...}`；如目标 `remind_start_at` ≠ 后端翻译值，则同步修改。

- [ ] **2.1.1** `test_create_task_invalid_remind_start_format` 删除（语法不再适用）
- [ ] **2.1.2** `test_create_task_remind_start_after_due` 改名为 `test_create_task_custom_after_due`（`due='2026-08-10'` + `custom_remind_start_at='2026-08-16'`）→ 400
- [ ] **2.1.3** `test_create_task_default_remind_start_at` 改名为 `test_create_task_default_remind_rule_before_1d`，改为 `payload` 不带 `remind_rule` → 400（spec 已要求 `remind_rule` 必填）；并新增 `test_create_task_default_rule_before_1d`（`remind_rule='before_1d'`，不传 `custom_remind_start_at`）→ 成功，`remind_start_at` 翻译为 `due_at − 1 day`
- [ ] **2.1.4** `test_create_task_due_at_stored_as_10_char` 增加 `remind_start_at` 长度断言（值由翻译得到）
- [ ] **2.1.5** `test_create_task_*` 全部 payload 的 `remind_start_at` → `remind_rule + custom_remind_start_at` 替换；按需要新增：
  - `test_create_task_invalid_remind_rule` `remind_rule='before_5d'` → 400
  - `test_create_task_custom_missing_date` → 400
- [ ] **2.1.6** `test_update_task_invalid_dates` `remind_start_at > due_at` → 400 改写为 `custom_remind_start_at='2026-08-21'`，`due='2026-08-15'` → 400
- [ ] **2.1.7** `test_complete_task_*` 字段无关，无需改

### 2.2 `test_reminders.py`

- [ ] **2.2.1** 所有 fixture 在 `make_task` 后增加 `update_task` 或 fixture 直接用 `remind_start_at` 入库 → 同步入参改造
- [ ] **2.2.2** `test_get_task_includes_reminders` 入参 `due='2026-08-15'` + 不再传 `remind_start_at`，改用后台 `TaskUpdate`（或 fixtures 服务端 direct DB 写入 `remind_start_at='2026-08-08'`）；响应 assertion 不变
- [ ] **2.2.3** `test_update_task_reminders_reflect_new_plan` PUT body 改用 `remind_rule`；步骤断言 POST/PUT body 的 `remind_rule` 字段

### 2.3 `test_overdue_job.py`

- [ ] **2.3.1** 该文件入参 `remind_start_at` 是构造 fixture 用语；直接保留（数据库层仍用 `remind_start_at`），仅复核无关联修改。

---

## 3. 前端代码（`frontend/src/`，非 spec 但实现需要同步）

> 本节不在 spec 范围内，仅作为开发提示；实施时按 frontend/spec §2.4/§2.5 实现。

- [ ] **3.1** `components/TaskForm.vue`：「提前提醒」`el-select`（7 档），「特定提醒日期」`el-date-picker`（`v-if` 受控）
- [ ] **3.2** `components/TaskForm.vue`：默认 `remind_rule='before_1d'`；`on_due` 等不可见日期字段
- [ ] **3.3** `stores/useTaskStore.js`：`resolveRemindRuleOnEdit(due_at, remind_start_at)` 工具（精确匹配 7 档 → 任一档；不匹配 → `'custom' + 强制回填 custom_remind_start_at`）
- [ ] **3.4** `api/tasks.js`：POST/PUT body 序列化：`{ ..., remind_rule, custom_remind_start_at }`
- [ ] **3.5** 列表列渲染保持 `task.remind_start_at` 字符串（字段名/列名不变）
- [ ] **3.6** Playwright TC-TM-04 系列（4 / 4b / 4c / 4d，见 frontend/spec §3.3）落地

---

## 4. 验证清单

- [ ] `pytest backend/tests -v` 全绿
- [ ] `pytest -q --collect-only` 用例数与 `backend/.todo/task_management.md` Phase 2 一致基础上，新增 `test_remind_rule.py` 用例
- [ ] `python -c "import json; json.load(open('backend/openapi/task_management.json'))"` 不报错
- [ ] 手工 curl：`POST /api/tasks` body `{due_at:'2026-08-15', remind_rule:'before_1m', ...}` 响应 `remind_start_at='2026-07-15'`
- [ ] 前端 `npm run dev`：新建 / 编辑 / 翻页 / 提醒区间筛选 均正常
