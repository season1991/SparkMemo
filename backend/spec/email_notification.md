# 邮件通知模块规格

> 适配规格：SparkMemo 任务提醒系统 v0.3
> 适用范围：单用户本地版，无登录。
> **本版本范围**：仅交付邮箱配置（`email_config`）的存储与 CRUD——`GET /api/email-config` 与 `PUT /api/email-config`。
> **本版本不实现任何发送功能**：不实现 SMTP 发送封装（`mailer`）、不发邮件、不实现「今日提醒」渲染、不实现发送接口。邮件的「实际发送」与「定时跑批」均留待后续版本。
> **数据库可移植性约束**：所有日期字段统一使用 10 字符字符串 `YYYY-MM-DD`；任何涉及「当前日期」的 SQL 查询由 Python 层计算后作为参数传入，不使用 `CURDATE()` / `NOW()` / `CURRENT_DATE` 等数据库内置函数，以避免切换数据库时函数名差异导致报错。

---

## Summary

实现一个最小化的「邮箱配置存储」模块，包含：

1. **邮箱配置 `email_config`（单行表）**：存储 SMTP 凭证（host / port / user / password / use_tls）、发件人、收件人；**不含** `send_time` / `active` 等任何字段；
2. **配置 CRUD（单行 upsert）**：`GET /api/email-config` 取当前配置；`PUT /api/email-config` upsert 单行；密码不回明文、留空保留旧值。

**不在本版本范围（明确延后）**：

- SMTP 发送封装（`mailer`）；
- 「今日待办提醒」拉取与 HTML 渲染（`dispatcher`）；
- 任何发送接口（如 `POST /api/email/send`）；
- APScheduler 定时调度；
- 多账号、多模板、发送日志表；
- 前端配置页面。

---

## Key Changes

### 数据库

> 新增**一张**表 `email_config`，设计为「**单行表**」——应用层以 `id = 1` 作为固定主键，重复写入走 update；语义上等同于 KV。
> 本版本字段只承担「凭证 + 发件人 + 收件人」的存储职责，**不**含任何调度 / 启用开关字段。

#### `email_config` 字段

```python
id              Mapped[int]        # 主键，自增；应用层固定以 id=1 读写；unique
smtp_host       Mapped[str]        # SMTP 服务器地址，如 'smtp.qq.com'；1-128 字符
smtp_port       Mapped[int]        # SMTP 端口，常见 465(SSL) / 587(STARTTLS) / 25(明文)；1-65535
smtp_user       Mapped[str]        # 登录账号，通常与发件人地址相同；1-128 字符
smtp_password   Mapped[str]        # 授权码 / 密码；明文存库；API 不返回明文；1-256 字符
use_tls         Mapped[bool]       # 是否启用 SSL/STARTTLS；true -> 端口 465 用 SMTP_SSL；端口 587 用 SMTP + starttls
sender_email    Mapped[str]        # From 头邮箱地址；1-128 字符
sender_name     Mapped[str]        # 发件人显示名；1-64 字符
recipient_email Mapped[str]        # 收件人邮箱；1-128 字符
recipient_name  Mapped[str|None]   # 收件人显示名，可空
created_at      Mapped[str]        # YYYY-MM-DD，10 字符
updated_at      Mapped[str]        # YYYY-MM-DD，10 字符
```

> **单行表约束**：`id = 1` 唯一。`PUT /api/email-config` 在应用层等价于「读 → 若不存在 INSERT 一行并令 id=1；若存在 UPDATE」；DB 唯一约束由 `id` 自带 + 应用层不主动递增保证。
>
> **密码不回明文**：所有 GET 响应里的 `smtp_password` 字段不出；用派生字段 `smtp_password_set: bool` 表示「密码是否已设置」。前端 PUT 时若 `smtp_password` 留空字符串 → 视为「保留旧值」（避免前端没改密码时被强制覆盖为 null）。

### 新增模块文件

| 路径 | 作用 |
|------|------|
| `backend/app/crud/email_config.py` | 单行 CRUD：`get_email_config(db)` / `upsert_email_config(db, payload)` |
| `backend/app/schemas.py`（追加） | `EmailConfigRead` / `EmailConfigWrite` |
| `backend/app/api/email_config.py` | 路由：`router = APIRouter(prefix='/api/email-config', tags=['email-config'])`；暴露 `GET` 与 `PUT` |
| `backend/app/main.py`（编辑） | 挂载新路由 |

### 修改既有表

> **不修改任何既有表**。`companies` / `projects` / `task_types` / `tasks` 四张表的字段与索引保持不变。

### 调度器 / 服务层

> **本版本不修改 `services/scheduler.py`**，不新增任何 service 文件（`mailer.py` / `email_dispatcher.py` 都不存在）。APScheduler 仍只跑 `check_overdue_tasks`（每日 00:00 逾期自动完成）这一个 Job。

---

## API And Behavior

所有路径以 `/api` 前缀。

### 邮箱配置 Email Config

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/api/email-config` | 取当前配置；不存在 → `{ "exists": false, ... }`；已存在 → 完整结构（**密码不回明文**） |
| PUT  | `/api/email-config` | upsert 单行；不影响任何调度器（**本版本无调度器集成**） |

#### `GET /api/email-config`

**响应 200（未配置）**
```jsonc
{
  "exists": false,
  "smtp_host": null,
  "smtp_port": null,
  "smtp_user": null,
  "smtp_password_set": false,
  "use_tls": false,
  "sender_email": null,
  "sender_name": null,
  "recipient_email": null,
  "recipient_name": null,
  "created_at": null,
  "updated_at": null
}
```

**响应 200（已配置）**
```jsonc
{
  "exists": true,
  "id": 1,
  "smtp_host": "smtp.qq.com",
  "smtp_port": 465,
  "smtp_user": "user@qq.com",
  "smtp_password_set": true,        // 不返回 smtp_password 明文
  "use_tls": true,
  "sender_email": "user@qq.com",
  "sender_name": "SparkMemo",
  "recipient_email": "user@qq.com",
  "recipient_name": null,
  "created_at": "2026-08-10",
  "updated_at": "2026-08-10"
}
```

#### `PUT /api/email-config`

**请求（完整 upsert）**
```jsonc
{
  "smtp_host": "smtp.qq.com",
  "smtp_port": 465,
  "smtp_user": "user@qq.com",
  "smtp_password": "abcdefghijklmnop",   // 留空字符串或 null 视为「保留旧值」
  "use_tls": true,
  "sender_email": "user@qq.com",
  "sender_name": "SparkMemo",
  "recipient_email": "user@qq.com",
  "recipient_name": "我自己"
}
```

**服务端处理顺序**
1. 字段级 Pydantic 校验（邮箱格式 / 端口范围）；
2. 若 `exists=false`：INSERT 一行；
3. 若 `exists=true` 且 `smtp_password` 为空 / null：保留旧密码；其他字段 UPDATE；
4. 若 `exists=true` 且 `smtp_password` 非空：覆盖密码；
5. 提交后**不触发任何调度器动作**（本版本无调度器集成，也无发送能力）；
6. 返回与 GET 一致的响应（密码不回明文）。

**响应 200**：与 GET 已配置响应同结构。

### 错误约定

| HTTP | 场景 |
|------|------|
| 400 | `smtp_port` 越界（`<1` 或 `>65535`）；邮箱格式非法 |
| 500 | 数据库错误 |

> **本版本没有 404 场景**：`GET / PUT /api/email-config` 在「未配置」时都返回 200（GET 返回 `exists=false`，PUT 走 INSERT 路径）。
> **本版本没有 422 场景**：本接口不涉及 SMTP 发送，所有失败仅来自字段校验或 DB 错误。

---

## Test Plan

> 测试位于 `backend/tests/`，使用 pytest + httpx AsyncClient；按 README §5.1 先全红后全绿。
> 测试数据库与 `conftest.py` 的 `db` fixture 同源；`email_config` 表需要在 conftest 的 TRUNCATE 列表里追加。

### `test_email_config.py` — 邮箱配置 CRUD + 字段校验

| # | 用例 | 测试目的 | 关键断言 |
|---|------|---------|---------|
| 1 | `test_get_when_not_exists` | 未配置时 GET 返回约定结构（`exists=false`，字段均为 null） | 200；`exists=false`；`smtp_password_set=false` |
| 2 | `test_put_upsert_when_not_exists` | 首次 PUT 创建一行 | 200；DB 中 `email_config` 仅 1 行且 id=1；响应 `exists=true` |
| 3 | `test_get_after_upsert` | PUT 后 GET 拿到完整结构 | 200；`exists=true`；`smtp_password_set=true`；**响应无 `smtp_password` 字段** |
| 4 | `test_put_updates_existing` | 第二次 PUT 覆盖字段 | DB 行数仍为 1；`updated_at` 推进；`smtp_host` / `smtp_port` 同步到新值 |
| 5 | `test_put_empty_password_keeps_old` | PUT 时 `smtp_password=""` → 保留旧密码 | 重新 GET 后 `smtp_password_set=true`（旧密码未被清空） |
| 6 | `test_put_invalid_port` | `smtp_port=0` / `99999` → 400 | 均 400 |
| 7 | `test_put_invalid_email` | `sender_email="not-an-email"` → 400 | 400 |
| 8 | `test_put_invalid_recipient_email` | `recipient_email="not-an-email"` → 400 | 400 |
| 9 | `test_put_invalid_smtp_host_length` | `smtp_host` 超过 128 字符 → 400 | 400 |
| 10 | `test_put_invalid_sender_name_length` | `sender_name` 超过 64 字符 → 400 | 400 |
| 11 | `test_password_never_in_response` | 守护安全约束——任何 GET / PUT 响应里都不出明文密码 | 扫描响应 JSON 的所有字段名 + 值，无 `smtp_password` |

---

## Assumptions

1. **单用户本地版**维持不变：不引入登录、不引入多租户、不引入用户偏好设置表；
2. **SMTP 凭证存库是配置存储，不是发送能力**：本版本仅提供凭证的存取；不实现任何 SMTP 发送、连接、认证逻辑；凭证的实际用途留待后续版本；
3. **单行配置表 `email_config`**：应用层固定以 `id = 1` 读写；不设计多账号 / 多模板 / 按公司分流；
4. **SMTP 密码明文存库**：本地单用户场景下简化处理；API 层一律不回明文，PUT 时支持「留空保留旧值」；
5. **本版本不实现任何发送能力**：`services/mailer.py` 与 `services/email_dispatcher.py` 均**不**存在；不引入发送接口；不在 `requirements.txt` 新增依赖；模块只是「配置存储」语义，与「发送」解耦；
6. **本版本不实现定时调度**：`email_config` 表中**不**含 `send_time` / `active` 等调度字段；不修改 `services/scheduler.py`；
7. **应用启动无邮件相关副作用**：`main.py` lifespan 启动时**不**调用任何邮件初始化逻辑；email_config 缺失不影响应用启动；
8. **数据库可移植性**：本版本邮件模块不新增任何业务 SQL（不查询任务、不查询公司），故不涉及 `CURDATE()` / `NOW()` 等数据库内置函数问题；该约束沿用既有 spec 写法继续生效；
9. **依赖零新增**：本模块**不**引入 SMTP 库（`smtplib` 等），所有逻辑仅靠 ORM + Pydantic + FastAPI 既有依赖；`requirements.txt` 保持不变；
10. **OpenAPI 输出**：测试全绿后导出至 `backend/openapi/email_notification.json`；
11. **本次 spec 范围内不实现前端**：仅交付后端接口与 OpenAPI；前端「设置 → 邮箱配置」页面留给后续 spec 单独写。

---

## 后续版本演进项（明确延后）

下列内容**不在本版本实现**，仅作记录，方便后续 spec 启动时衔接：

- **SMTP 发送封装**：`services/mailer.py` + `MailerError` + `send_html(...)`，覆盖 465 SSL / 587 STARTTLS / 25 明文三种 transport；
- **「今日待办提醒」生成**：`services/email_dispatcher.py` + 严格基线 SQL + 按公司分组 HTML 模板；
- **统一发送接口**：`POST /api/email/send`（手动按钮 + 未来 Job 共用入口）；
- **APScheduler 每日定时邮件 Job**：`email_config` 增 `send_time` / `active` 字段、`services/scheduler.py` 增 `email_daily_dispatch_job`；
- **多账号 / 多模板 / 按公司分流**；
- **发送日志表 `mail_logs`**；
- **前端「设置 → 邮箱配置」页面**。