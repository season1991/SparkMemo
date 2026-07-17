# 任务管理模块规格

> 适配规格：SparkMemo 任务提醒系统 v0.1
> 适用范围：单用户本地版，无登录。
> 当前范围：**仅任务管理**（CRUD + 提醒计划实时计算 + 逾期自动完成）。**通知推送（WebSocket + 实时扫描）暂不实现**，待后续版本。
> **数据库可移植性约束**：所有日期字段统一使用 10 字符字符串 `YYYY-MM-DD`；任何涉及「当前日期」的 SQL 查询由 Python 层计算后作为参数传入，不使用 `CURDATE()` / `NOW()` / `CURRENT_DATE` 等数据库内置函数，以避免切换数据库时函数名差异导致报错。

---

## Summary

实现一个面向「多公司、多项目并行协作」场景的任务管理模块，包含：

1. **任务 CRUD**：创建、修改、删除、完成；提供 `status` 字段标识「是否完成」（`pending` / `completed` / `overdue_done`）；
2. **任务类型用户自定义**（`task_types`）：增删改查；
3. **公司与项目作为一等实体**（`companies`、`projects`）：独立 CRUD，被任务外键引用；项目隶属于公司；
4. **deadline + 提醒规则（`remind_rule`）**：用户在创建/编辑任务时只表达"什么时候开始提醒"的业务意图（7 档预设之一 + 特定日期），由后端按 `due_at` 与 `remind_rule` 翻译成最终 `remind_start_at`（10 字符 `YYYY-MM-DD`）入库；不持久化 `remind_rule` 本身。从 `remind_start_at` 至 `due_at` 闭区间内每天对应一条提醒计划，由后端实时计算返回，不持久化提醒计划；
5. **逾期自动完成**：调度器每日 00:00 检查，`due_at` 距今超过 3 天且仍为 `pending` 的任务，自动标记为 `overdue_done`。

---

## Key Changes

### 数据模型

| 表 | 状态 | 字段 |
|----|------|------|
| `companies` | 新增 | id / name(uniq) / notes / created_at / updated_at |
| `projects` | 新增 | id / company_id(FK) / name / notes / created_at / updated_at；(company_id, name) 联合唯一 |
| `task_types` | 新增 | id / name(uniq) / created_at / updated_at |
| `tasks` | 新增 | id / title / description / task_type_id / company_id / project_id / **`due_at`** / **`remind_start_at`** / status / created_at / updated_at / completed_at |（`remind_rule` 只作为**入参**使用，不入库；最终值 `remind_start_at` 入库） |

> **日期字段统一为 `YYYY-MM-DD` 字符串**：所有 `created_at` / `updated_at` / `due_at` / `remind_start_at` / `completed_at` 均为 10 字符定长字符串，不使用数据库原生 `DATE` / `DATETIME` 类型，便于跨数据库移植。
>
> **不引入 `notifications` 表**：提醒计划无需持久化，每次查询时按 `tasks.due_at` 与 `tasks.remind_start_at` 实时计算。亦无需后台扫描 Job 写入。

### `companies` 字段
```python
id         Mapped[int]       # 主键，自增
name       Mapped[str]       # 公司名称，全表唯一，1-128 字符
notes      Mapped[str|None]  # 备注
created_at Mapped[str]       # YYYY-MM-DD，10 字符
updated_at Mapped[str]       # YYYY-MM-DD，10 字符
```

### `projects` 字段
```python
id         Mapped[int]       # 主键，自增
company_id Mapped[int]       # FK -> companies.id
name       Mapped[str]       # 项目名称，同公司下唯一
notes      Mapped[str|None]  # 备注
created_at Mapped[str]       # YYYY-MM-DD，10 字符
updated_at Mapped[str]       # YYYY-MM-DD，10 字符
```

### `task_types` 字段
```python
id         Mapped[int]
name       Mapped[str]       # 类型名称，全表唯一，1-64 字符
created_at Mapped[str]       # YYYY-MM-DD，10 字符
updated_at Mapped[str]       # YYYY-MM-DD，10 字符
```

### `tasks` 字段
```python
id              Mapped[int]            # 主键，自增
title           Mapped[str]            # 标题，1-200 字符
description     Mapped[str|None]       # 描述，可空
task_type_id    Mapped[int|None]       # FK -> task_types.id，可空
company_id      Mapped[int]            # FK -> companies.id，必填
project_id      Mapped[int]            # FK -> projects.id，必填
due_at          Mapped[str]            # YYYY-MM-DD，10 字符；截止日；用于计算 + 列表展示 + 逾期判断
remind_start_at Mapped[str]            # YYYY-MM-DD，10 字符；由后端按 remind_rule + due_at 翻译出来；提醒计划起点；必须 <= due_at
status          Mapped[str]            # pending / completed / overdue_done
created_at      Mapped[str]            # YYYY-MM-DD，10 字符
updated_at      Mapped[str]            # YYYY-MM-DD，10 字符
completed_at    Mapped[str|None]       # YYYY-MM-DD，10 字符；仅 completed / overdue_done 时填充
```

> **不存 `remind_rule`**：数据库列只有 `due_at` / `remind_start_at` 两个日期字段。`remind_rule` 是写入路径上的**业务意图**，由后端通过 `resolve_remind_start_at` 翻译为最终 `remind_start_at` 后入库；读响应（`GET`）只回 `remind_start_at`，不回 `remind_rule`。

### 提醒计划计算规则（按需计算，不存储）

提醒计划由后端在 `GET /api/tasks/{id}` 时**实时生成**：

```python
def compute_reminders(remind_start_at: str, due_at: str) -> list[dict]:
    """
    返回 [remind_start_at, due_at] 闭区间内每日一条的提醒计划。
    入参与返回均为 'YYYY-MM-DD' 字符串。
    """
    start = date.fromisoformat(remind_start_at)
    end = date.fromisoformat(due_at)
    days = (end - start).days + 1   # 闭区间，含两端
    return [
        {"remind_at": (start + timedelta(days=i)).isoformat()}
        for i in range(days)
    ]
```

### `remind_rule` 翻译规则（写入路径专用函数）

创建 / 更新任务时，前端只传**业务意图** `remind_rule`（不传 `remind_start_at`）。后端在入库前调用下面这个**纯函数**翻译成最终日期：

```python
def resolve_remind_start_at(
    due_at: str,
    remind_rule: str,
    custom_remind_start_at: str | None = None,
) -> str:
    """
    根据 remind_rule 把用户的「什么时候开始提醒」翻译为具体 YYYY-MM-DD。
    返回值必须满足 <= due_at（不满足时由调用方判 400）。
    """
    end = date.fromisoformat(due_at)
    rule = REMIND_RULES[remind_rule]                  # 查表得到 (kind, value)
    kind, value = rule

    if kind == "on_due":
        return end.isoformat()                         # 当天
    if kind == "days_before":
        return (end - timedelta(days=value)).isoformat()  # N 天前
    if kind == "weeks_before":
        return (end - timedelta(days=value * 7)).isoformat()  # 7 天为单位，写死 N×7
    if kind == "months_before":
        return shift_month(end, months=-value).isoformat()   # 按日历月减，目标日超过目标月末时 clamp 到月末
    if kind == "custom":
        if not custom_remind_start_at:
            raise ValueError("custom 模式必须传 custom_remind_start_at")
        return custom_remind_start_at

    raise ValueError(f"unknown remind_rule: {remind_rule}")
```

#### `remind_rule` 取值与含义

| 取值 | 中文 label（前端） | 翻译口径 | 入参必填 |
|------|------|------|------|
| `on_due` | 当天 | `remind_start_at = due_at` | — |
| `before_1d` | 提前 1 天 | `due_at − 1 day` | — |
| `before_2d` | 提前 2 天 | `due_at − 2 day` | — |
| `before_3d` | 提前 3 天 | `due_at − 3 day` | — |
| `before_1w` | 提前 1 周 | `due_at − 7 day`（**固定 7 天**，不按周历） | — |
| `before_1m` | 提前 1 个月 | `due_at − 1 month`（**按日历月**；月末 clamp，例如 2026-03-31 → 2026-02-28） | — |
| `custom` | 特定（用户自选） | 取 `custom_remind_start_at` | ✅ **必须传 `custom_remind_start_at`** |

#### 月份偏移纯函数（用于 `before_1m`）

```python
def shift_month(d: date, months: int = -1) -> date:
    """日历月偏移；目标日超过目标月末时 clamp 到该月最后一天。"""
    y, m = d.year, d.month + months
    while m <= 0:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    # 求目标月最后一天：取下月 1 日减 1 day
    if m == 12:
        next_month_first = date(y + 1, 1, 1)
    else:
        next_month_first = date(y, m + 1, 1)
    last_day = (next_month_first - timedelta(days=1)).day
    return date(y, m, min(d.day, last_day))
```

#### 关键不变量

- 翻译后必须再次校验 `remind_start_at <= due_at`；不满足返回 400；
- 任何规则翻译后若 `remind_start_at` 早于今天，仍允许（任务可以是历史 + 现在补登 + 后续还要在 `due_at` 当天/前几天提醒的情况），仅日志记录，不阻断；
- 修改 `due_at` 时，**`remind_start_at` 不会自动跟着移动**：依赖调用方重新提交 `remind_rule` 或 `custom_remind_start_at`，由后端按当时的 `due_at` 重新翻译；
- 修改 `remind_rule` 但不传 `custom_remind_start_at`（且规则非 custom） → 后端按新规则用当前 `due_at` 重新翻译；
- 规则 `custom` 但没传 `custom_remind_start_at` → **400 阻断**。

列表筛选「今天该提醒谁」之类的查询：**当前日期由 Python 层计算后作为参数传入 SQL**，不使用数据库内置函数：

```python
# Python 层计算当前日期并传入
today = date.today().isoformat()            # 例如 '2026-08-10'
rows = db.execute(
    text("""
        SELECT * FROM tasks
        WHERE status = 'pending'
          AND remind_start_at <= :today
          AND due_at >= :today
    """),
    {"today": today},
).fetchall()
```

- 修改 `due_at` / `remind_start_at` → 下次查询自然反映新值，无副作用；
- 任务删除 / 完成 → SQL `WHERE status='pending'` 自动排除，无需清理；
- 无 `notifications` 表、无扫描 Job、无 WebSocket 推送、无需任何后台写动作。

### 状态机

```
        用户主动完成（POST /complete）
pending ─────────────────────────────► completed
   │
   │  today - due_at >= 3 days
   │  （check_overdue_tasks 自动触发；today 由 Python 传入）
   ▼
overdue_done
```

- `pending → completed`：用户调用 `POST /api/tasks/{id}/complete`；
- `pending → overdue_done`：后台 Job 每日检查触发；
- `completed` 与 `overdue_done` 之间不互相转换；
- 不提供「重开」接口；如需恢复，只能删除后重建。

### 逾期自动完成 Job（唯一保留的后台 Job）

| 项 | 内容 |
|----|------|
| Job 名 | `check_overdue_tasks` |
| 触发频率 | 每日 00:00 |
| 签名 | `def check_overdue_tasks(db: Session, today: str \| None = None)`，`today` 缺省时由 Python `date.today().isoformat()` 计算 |
| 处理逻辑 | 1. 计算 `cutoff = today − 3 天`；<br>2. 用参数 `:today` 与 `:cutoff` 查询 `status='pending' AND due_at <= :cutoff` 的任务；<br>3. 将其状态置为 `overdue_done`；<br>4. 写入 `completed_at = today` |
| 幂等性 | 通过状态过滤保证，已是 `completed` / `overdue_done` 的任务不会被重复处理 |

```python
# 伪代码
def check_overdue_tasks(db: Session, today: str | None = None):
    today = today or date.today().isoformat()
    cutoff = (date.fromisoformat(today) - timedelta(days=3)).isoformat()
    overdue = db.execute(
        text("""
            SELECT id FROM tasks
            WHERE status = 'pending' AND due_at <= :cutoff
        """),
        {"cutoff": cutoff},
    ).fetchall()
    for row in overdue:
        db.execute(
            text("""
                UPDATE tasks
                SET status = 'overdue_done', completed_at = :today, updated_at = :today
                WHERE id = :id AND status = 'pending'
            """),
            {"id": row.id, "today": today},
        )
    db.commit()
```

### 不实现的组件（明确范围）

以下**不在本版本**实现，留待后续版本：

- `ws_manager.py` / `ws.py`（WebSocket 连接管理与端点）；
- `notifications` 表（按需 SQL 计算，无需持久化）；
- `scan_reminders` APScheduler Job；
- 浏览器 `Notification API` 集成；
- 「用户所属公司 / 团队」默认值机制（不在本版本设计；任务创建时 `company_id` / `project_id` 由调用方显式传入）。

---

## API And Behavior

所有接口统一前缀 `/api`，路径使用复数名词；列表接口支持分页 `?page=1&size=20`。

### 公司 Companies

| 方法 | 路径 | 说明 |
|------|------|------|
| GET    | `/api/companies?keyword=&page=&size=` | 公司列表（名称模糊搜索） |
| POST   | `/api/companies` | 新建；`name` 必填且全表唯一 |
| GET    | `/api/companies/{id}` | 详情 |
| PUT    | `/api/companies/{id}` | 修改 |
| DELETE | `/api/companies/{id}` | 删除；被任务 / 项目引用则 409 |

**POST /api/companies 请求**
```json
{ "name": "ACME 集团", "notes": "主要客户 A" }
```

### 项目 Projects

| 方法 | 路径 | 说明 |
|------|------|------|
| GET    | `/api/projects?company_id=&keyword=&page=&size=` | 列表（按公司筛选） |
| POST   | `/api/projects` | 新建；`company_id` 必填；同公司下 `name` 唯一 |
| GET    | `/api/projects/{id}` | 详情 |
| PUT    | `/api/projects/{id}` | 修改 |
| DELETE | `/api/projects/{id}` | 删除 |

### 任务类型 Task Types

| 方法 | 路径 | 说明 |
|------|------|------|
| GET    | `/api/task-types` | 全量列表（体量小，无分页） |
| POST   | `/api/task-types` | 新建；`name` 全表唯一 |
| PUT    | `/api/task-types/{id}` | 修改 |
| DELETE | `/api/task-types/{id}` | 删除；被任务引用则 409 |

### 任务 Tasks

| 方法 | 路径 | 说明 |
|------|------|------|
| GET    | `/api/tasks?status=&company_id=&project_id=&task_type_id=&due_from=&due_to=&keyword=&remind_today=&page=&size=` | 列表；`remind_today=true` 时仅返回「今天在提醒区间内」的 pending 任务（`today` 由后端 Python 计算并作为 SQL 参数传入） |
| POST   | `/api/tasks` | 新建；`company_id` / `project_id` **必填** |
| GET    | `/api/tasks/{id}` | 详情（含实时计算的 `reminders` 提醒计划数组） |
| PUT    | `/api/tasks/{id}` | 修改 |
| DELETE | `/api/tasks/{id}` | 删除 |
| POST   | `/api/tasks/{id}/complete` | 标记完成；写入 `completed_at` |

**POST /api/tasks 请求**
```json
{
  "title": "ACME Q3 订单评审",
  "description": "与采购张总对齐 Q3 备货计划",
  "task_type_id": 1,
  "company_id": 2,
  "project_id": 5,
  "due_at": "2026-08-15",
  "remind_rule": "before_3d",
  "custom_remind_start_at": null
}
```

> **`due_at` 与 `remind_rule` 必填**；`custom_remind_start_at` 仅在 `remind_rule='custom'` 时必传，其余情况可空。
> 前端只在「特定」分支才让用户填日期，其余分支 UI 层不渲染日期控件，提交时把 `custom_remind_start_at` 设为 `null`。

**服务端处理顺序（POST / PUT）**
1. 校验 `due_at` 是合法 `YYYY-MM-DD`；
2. 校验 `remind_rule` 是合法枚举值（`on_due` / `before_1d` / `before_2d` / `before_3d` / `before_1w` / `before_1m` / `custom`）；
3. 若 `remind_rule='custom'`，校验 `custom_remind_start_at` 是合法 `YYYY-MM-DD`；
4. 调用 `resolve_remind_start_at(due_at, remind_rule, custom_remind_start_at)` 翻译出最终 `remind_start_at`；
5. 校验翻译结果 `remind_start_at <= due_at`，否则 400；
6. 校验必填字段 `company_id` / `project_id` 已传入且对应记录存在；
7. 校验其余外键存在（`task_type_id`，可空）；
8. 写入或更新 `tasks`（`status='pending'`），**只存 `remind_start_at`，不回存 `remind_rule`**。

**GET /api/tasks/{id} 响应**
```json
{
  "id": 42,
  "title": "ACME Q3 订单评审",
  "task_type": { "id": 1, "name": "会议" },
  "company":  { "id": 2, "name": "ACME 集团" },
  "project":  { "id": 5, "name": "Q3 备货" },
  "due_at": "2026-08-15",
  "remind_start_at": "2026-08-12",
  "status": "pending",
  "reminders": [
    { "remind_at": "2026-08-12" },
    { "remind_at": "2026-08-13" },
    { "remind_at": "2026-08-14" },
    { "remind_at": "2026-08-15" }
  ]
}
```


### 错误约定

| HTTP | 场景 |
|------|------|
| 400 | `due_at` / `custom_remind_start_at` 非 `YYYY-MM-DD`；`remind_rule` 非合法枚举；`remind_rule='custom'` 但 `custom_remind_start_at` 为空；翻译后 `remind_start_at > due_at`；`company_id` / `project_id` 缺省 |
| 404 | 资源不存在 |
| 409 | 唯一约束冲突 / 删除被引用资源 |
| 422 | 外键无效 |

---

## Test Plan

> 测试位于 `backend/tests/`，使用 pytest + httpx AsyncClient；按 README §5.1 先全红后全绿。

### 单元 / 集成

1. **companies**
   - CRUD 全链路；`name` 重复 → 409；删除被任务 / 项目引用 → 409；
   - 列出 `companies?keyword=AC` 模糊匹配。
2. **projects**
   - 必须带 `company_id`；`(company_id, name)` 重复 → 409。
3. **task_types**
   - CRUD 全链路；被任务引用时删除 → 409。
4. **tasks 字段校验**
   - `remind_rule` 非合法枚举 → 400；
   - `remind_rule='custom'` 但 `custom_remind_start_at` 为空 / 非 `YYYY-MM-DD` → 400；
   - `due_at` 非 `YYYY-MM-DD` → 400；
   - 翻译后 `remind_start_at > due_at` → 400；
   - `company_id` 或 `project_id` 缺省 → 400；
   - 外键 `company_id` / `project_id` / `task_type_id` 不存在 → 422。
5. **tasks CRUD**
   - 创建成功 → `status='pending'`，`remind_rule` 不入库；`remind_start_at` 入库即 10 字符（由后端翻译）；
   - 修改任意字段 → 无任何隐藏副作用；
   - 删除任务 → 任务消失，无关联数据；
   - `complete` → 状态 `completed`，`completed_at` 写入（值为调用当天的 `YYYY-MM-DD`）；
   - 响应体 **不含** `remind_rule` 字段（仅含最终 `remind_start_at`）。
6. **`resolve_remind_start_at` 翻译（核心纯函数）**
   - `due_at='2026-08-15'` + `remind_rule='on_due'` → `'2026-08-15'`；
   - `due_at='2026-08-15'` + `remind_rule='before_1d'` → `'2026-08-14'`；
   - `due_at='2026-08-15'` + `remind_rule='before_3d'` → `'2026-08-12'`；
   - `due_at='2026-08-15'` + `remind_rule='before_1w'` → `'2026-08-08'`（固定 7 天，不按周历）；
   - `due_at='2026-08-31'` + `remind_rule='before_1m'` → `'2026-07-31'`（按日历月减 1 月）；
   - `due_at='2026-03-31'` + `remind_rule='before_1m'` → `'2026-02-28'`（平年 clamp 到月末）；
   - `due_at='2024-03-31'` + `remind_rule='before_1m'` → `'2024-02-29'`（2024 是闰年，clamp 到月末）；
   - `due_at='2026-08-15'` + `remind_rule='custom'` + `custom_remind_start_at='2026-08-10'` → `'2026-08-10'`；
   - `due_at='2026-08-15'` + `remind_rule='custom'` + 缺 `custom_remind_start_at` → 抛 `ValueError`（由路由层捕获并返 400）。
7. **提醒计划计算（核心）**
   - 入库 `due_at=2026-08-15, remind_start_at=2026-08-12` → `reminders` 4 条：`2026-08-12 … 2026-08-15`；
   - 入库 `due_at=2026-08-15, remind_start_at=2026-08-14` → 2 条；
   - 入库 `due_at` 与 `remind_start_at` 同日 → 1 条；
   - `GET /api/tasks/{id}` 返回的 `reminders` 数组与实时计算结果一致；
   - PUT 修改 `due_at` 后再次 `GET`，`reminders` 立即反映新计划（注意：后端不会自动重算 `remind_start_at`，除非前端重新提交 `remind_rule`）。
8. **入参 → 入库端到端**
   - `POST /api/tasks` body `{due_at:'2026-08-15', remind_rule:'before_1m', ...}` → 入库 `remind_start_at='2026-07-15'`；
   - `POST` body 漏 `remind_rule` → 400；
   - `POST` body `remind_rule='on_due'` + `due_at='2026-08-15'` → 入库 `remind_start_at='2026-08-15'`；
   - 编辑表单（前端 §2.5）通过 `due_at` + `remind_start_at` 反推 `remind_rule`（`on_due`/`before_1d`/…/`custom`）不匹配时 → 提交时 `custom_remind_start_at` 必须带具体日期，不能为 `null`。
9. **列表筛选 `remind_today=true`**
   - 测试通过 monkeypatch 注入 `today='2026-08-10'`，`remind_today=true` 时返回所有 `status='pending'` 且 `remind_start_at <= 2026-08-10 <= due_at` 的任务；
   - `status='completed'` / `'overdue_done'` 的任务被自动排除；
   - `remind_start_at > today` 或 `due_at < today` 的任务被排除；
   - **SQL 文本中不出现 `CURDATE()` / `NOW()` / `CURRENT_DATE` 等数据库函数**。
10. **逾期自动完成 Job `check_overdue_tasks`**
   - 直接调用 `check_overdue_tasks(db, today='2026-08-15')`：任务 `due_at=2026-08-10` 且 `status='pending'` → 被标记 `overdue_done`，`completed_at='2026-08-15'`；
   - 任务 `due_at='2026-08-13'` 且 `status='pending'` → 不被处理（仅 2 天）；
   - 状态已是 `completed` / `overdue_done` → 不重复处理；
   - Job 多次执行幂等；
   - **SQL 文本中不出现 `CURDATE()` / `NOW()` 等数据库函数**，所有日期为参数。

---

## Assumptions

1. **单用户本地版**维持不变：不引入登录、不引入多租户；
2. **不设独立 teams 表**：本规格不设计「所属团队」字段；
3. **所有日期字段统一为 10 字符字符串 `YYYY-MM-DD`**：`due_at` / `remind_start_at` / `created_at` / `updated_at` / `completed_at` 均不入数据库原生 `DATE` / `DATETIME` 类型；
4. **数据库可移植性**：所有 SQL 中涉及「当前日期 / 时间」的位置均由 Python 层 `date.today().isoformat()` 计算后作为命名参数（`:today` / `:cutoff` 等）传入；不依赖 `CURDATE()` / `NOW()` / `CURRENT_DATE` / `GETDATE()` 等数据库内置函数，避免切换数据库（MySQL / PostgreSQL / SQLite 等）时函数名差异导致报错；
5. **`remind_rule` 7 档预设**：`on_due` / `before_1d` / `before_2d` / `before_3d` / `before_1w` / `before_1m` / `custom`；其中 `before_1w` 固定 7 天，`before_1m` 按日历月（目标日超过目标月末时 clamp 到该月最后一天）；`custom` 必须配 `custom_remind_start_at`；不存数据库，仅写入路径上翻译用；
6. **`remind_start_at` 步长固定为 1 天**：从 `remind_start_at` 到 `due_at` 闭区间内每日一条；不支持小时级粒度（v0.2 演进项）；
7. **「deadline 当天」算一次提醒**：闭区间包含 `due_at`；`remind_start_at = due_at` 时生成 1 条；
8. **修改任务零副作用**：修改 `due_at` 后，后端**不会**自动重算 `remind_start_at`——重算依赖调用方重新提交 `remind_rule` 或 `custom_remind_start_at`；remind_start_at 在 PUT 后下次查询自然反映新值；
9. **删除公司 / 任务类型采用「软阻断」**：被引用时返回 409；
10. **APScheduler 仅一个 Job**：每日 00:00 跑 `check_overdue_tasks`；签名接受 `today` 参数便于测试注入；
11. **状态机**：`pending → completed`（用户主动）、`pending → overdue_done`（自动）；两者不互通；不提供 reopen；
12. **提醒计划实时计算，不持久化**：每次 `GET /api/tasks/{id}` 由后端按 `due_at` 与 `remind_start_at` 实时生成 `reminders` 数组，列表接口可通过 `?remind_today=true` 用 SQL 筛选「今日待提醒」；不存在 `notifications` 表；
13. **任务创建时 `company_id` / `project_id` 必填**：本版本不维护「用户所属」默认值，由调用方在新建任务时显式传入；
14. **编辑模式反推 `remind_rule`**：GET 响应不含 `remind_rule`，前端编辑打开时按 `(due_at − remind_start_at)` 反推最近匹配（`on_due`/`before_1d`/…/`custom`）；反推失败的边缘情况一律归为 `custom`，UI 必须显示具体日期输入框（不得静默归为某档预设），由用户主动确认。