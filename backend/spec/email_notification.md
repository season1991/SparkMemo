# 邮件通知模块规格

> 适配规格：SparkMemo 任务提醒系统 v0.4
> 适用范围：单用户本地版，无登录。
> **本版本范围**：邮箱配置 CRUD（`email_config` 单行表）+ 调度字段（`send_time` / `active`）+ SMTP 发送封装（`services/mailer.py`）+ 测试发送接口（`POST /api/email/send-test`）+ APScheduler 每日邮件 Job（占位渲染，正式提醒模板另行定义）。
> **数据库可移植性约束**：所有日期字段统一使用 10 字符字符串 `YYYY-MM-DD`；任何涉及「当前日期」的 SQL 查询由 Python 层计算后作为参数传入，不使用 `CURDATE()` / `NOW()` / `CURRENT_DATE` 等数据库内置函数，以避免切换数据库时函数名差异导致报错。

---

## Summary

实现一个最小化的「邮箱配置 + 邮件发送基础设施」模块，包含：

1. **邮箱配置 `email_config`（单行表）**：存储 SMTP 凭证（host / port / user / password / use_tls）、发件人、收件人、**调度字段**（`send_time` / `active`）；
2. **配置 CRUD（单行 upsert）**：`GET /api/email-config` 取当前配置；`PUT /api/email-config` upsert 单行；密码不回明文、留空保留旧值；调度字段每次 PUT 显式覆盖；提交后同步 APScheduler Job；
3. **SMTP 发送封装**：`services/mailer.py` 提供 `send_html(config, subject, html)`，覆盖 465 SSL / 587 STARTTLS / 25 明文三种 transport；
4. **测试发送接口**：`POST /api/email/send-test`，先自动保存入参配置，再向 `recipient_email` 发送固定模板的连通性测试邮件；
5. **APScheduler 每日邮件 Job**：`services/scheduler.py` 注册 `email_daily_dispatch`，按 `send_time` cron 触发，仅当 `active=true` 时执行；当前为占位渲染（`render_daily_dispatch`），业务提醒模板另行定义。

**不在本版本范围（明确延后）**：

- 正式「今日提醒」HTML 模板（按公司分组渲染）；
- 任何「统一发送正式邮件」接口（如 `POST /api/email/send`）；
- 多账号 / 多模板 / 按公司分流；
- 发送日志表 `mail_logs`；
- 前端配置页面；
- 启动脚本 `start.bat` / `start.sh` 补全。

---

## 版本变更

### v0.4 相对 v0.3 的增量

- **数据库**：`email_config` 表新增两列 `send_time VARCHAR(5) DEFAULT '08:00'`、`active TINYINT(1) DEFAULT 0`；
- **Schema**：`EmailConfigWrite` / `EmailConfigRead` 增加 `send_time`（24h 零填充 `HH:MM`）与 `active`（bool）字段，新增正则校验 `^([01]\d|2[0-3]):[0-5]\d$`；
- **CRUD**：`upsert_email_config` 提交后立即调 `scheduler.sync_email_dispatch_job(config)` 重设 / 暂停 Job；
- **API**：
  - `GET /api/email-config` 响应新增两字段；
  - `PUT /api/email-config` 接受两字段；写后调度器同步生效；
  - 新增 `POST /api/email/send-test`（不在 `/api/email-config` 前缀下，沿用 FastAPI 默认 422）；
- **服务层**：新增 `services/mailer.py`（`MailerError` + `send_html`）与 `services/email_dispatcher.py`（占位 `render_daily_dispatch`）；
- **调度器**：`services/scheduler.py` 注册 `email_daily_dispatch` Job，模块加载时 `pause_job`，由 `sync_email_dispatch_job(config)` 按 `active` 切换 run/pause；
- **生命周期**：`app/main.py` lifespan 启动时执行幂等 `ALTER TABLE email_config ADD COLUMN ...`（MySQL `information_schema` / SQLite `PRAGMA table_info` 探测），随后按 DB 现状 resume / 保持 paused；
- **测试**：新增 17 个用例（目标总数 145 passed）。

### v0.3 已实现且继续生效

- `email_config` 单行表语义、`id=1` 固定主键、密码明文存库 / API 不回明文；
- `GET` / `PUT` 字段校验（邮箱正则、端口范围、长度限制）；
- `/api/email-config` 路径下 `RequestValidationError` → 400 映射。

---

## Key Changes

### 数据库

> v0.3 设计：单行表 `email_config` 承担「凭证 + 发件人 + 收件人」存储。v0.4 在此基础上追加调度字段，应用层仍以 `id=1` 作为固定主键，重复写入走 update；语义上等同于 KV。

#### `email_config` 字段（v0.4）

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
send_time       Mapped[str]        # 每日发送时间，HH:MM 24h 零填充；默认 '08:00'
active          Mapped[bool]       # 调度启用开关；默认 false（v0.3 行升级后保持关闭）
created_at      Mapped[str]        # YYYY-MM-DD，10 字符
updated_at      Mapped[str]        # YYYY-MM-DD，10 字符
```

> **单行表约束**：`id = 1` 唯一。`PUT /api/email-config` 在应用层等价于「读 → 若不存在 INSERT 一行并令 id=1；若存在 UPDATE」；DB 唯一约束由 `id` 自带 + 应用层不主动递增保证。
>
> **密码不回明文**：所有 GET 响应里的 `smtp_password` 字段不出；用派生字段 `smtp_password_set: bool` 表示「密码是否已设置」。前端 PUT 时若 `smtp_password` 留空字符串 → 视为「保留旧值」（避免前端没改密码时被强制覆盖为 null）。
>
> **调度字段语义**：`send_time` 与 `active` **每次 PUT 显式覆盖**（与 `smtp_password` 的「留空保留旧值」行为不同），确保 UI 显式开关能可靠切换。`active=false` 时调度器 Job `paused`，不发邮件。

#### 幂等 ALTER TABLE（已存在库升级）

> 仓库**未引入 Alembic**；首次启动依赖 `Base.metadata.create_all()`。新列在空库 / 测试 SQLite 场景自动出现，但**已有 MySQL 实例不会自动加列**。

**采用方案**：`app/main.py` lifespan 启动时、scheduler.start() **之前**执行幂等 `ALTER TABLE`：

```python
# 伪代码（在 lifespan 中调用 _ensure_email_config_columns(engine)）
def _ensure_email_config_columns(engine):
    table = "email_config"
    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            cols = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()}
            if "send_time" not in cols:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN send_time VARCHAR(5) NOT NULL DEFAULT '08:00'")
            if "active" not in cols:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN active BOOLEAN NOT NULL DEFAULT 0")
        else:  # MySQL
            for col, ddl in [
                ("send_time", "VARCHAR(5) NOT NULL DEFAULT '08:00'"),
                ("active",    "TINYINT(1) NOT NULL DEFAULT 0"),
            ]:
                exists = conn.exec_driver_sql(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
                    (table, col),
                ).first()
                if not exists:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
```

- 对**已有 `email_config` 行**：`send_time` 回填 `'08:00'`、`active` 回填 `false`——**避免升级后立即触发邮件**（用户需手动开 `active=true`）；
- 函数在启动时执行一次，开销可忽略；
- 函数不引入新依赖，仅 stdlib + SQLAlchemy 既有 `engine`。

### 新增模块文件

| 路径 | 作用 |
|------|------|
| `backend/app/services/mailer.py` | SMTP 发送封装：`MailerError` + `send_html(config, subject, html)`，三段式 transport |
| `backend/app/services/email_dispatcher.py` | 占位渲染：`render_daily_dispatch(today, db) -> (subject, html)`，业务模板另行定义 |
| `backend/app/api/email_send.py` | 发送相关路由：`POST /api/email/send-test` |

### 修改既有文件

| 路径 | 改动 |
|------|------|
| `backend/app/models.py` | `EmailConfig` 增加 `send_time` / `active` 两列 |
| `backend/app/schemas.py` | `EmailConfigWrite` 加 `send_time` / `active` + 24h 正则校验；`EmailConfigRead` 加同名两字段 |
| `backend/app/crud/email_config.py` | INSERT/UPDATE 覆盖两字段；commit 后调 `scheduler.sync_email_dispatch_job(row)` |
| `backend/app/api/email_config.py` | `_to_read` 增加两字段映射 |
| `backend/app/services/scheduler.py` | 新增 `sync_email_dispatch_job(config)` + `email_daily_dispatch` Job；模块加载时 `pause_job` |
| `backend/app/main.py` | lifespan 内 `_ensure_email_config_columns(engine)` + `sync_email_dispatch_job(cfg)`；`include_router(email_send.router)`；`RequestValidationError` 处理器维持 `/api/email-config` 前缀转 400 语义 |

### 修改既有表

> **不修改任何既有表**（`companies` / `projects` / `task_types` / `tasks` 字段与索引保持不变）。
> `email_config` 仅追加列，不删除 / 改名任何既有列。

### 调度器 / 服务层

> v0.4 起 `services/scheduler.py` 持有两个 Job：
>
> 1. `check_overdue_tasks`：每日 00:00 标记逾期任务为 `overdue_done`（v0.1 既有，**不变**）；
> 2. `email_daily_dispatch`：按 `email_config.send_time` 触发，仅当 `active=true` 时执行；调用 `email_dispatcher.render_daily_dispatch(...)` 取得占位 `(subject, html)` 后 `mailer.send_html(...)`；SMTP 失败静默吞掉（`MailerError` 不抛出、不写库），待 `mail_logs` 延后项落地后再处理。

---

## API And Behavior

所有路径以 `/api` 前缀。

### 邮箱配置 Email Config

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/api/email-config` | 取当前配置；不存在 → `{ "exists": false, ... }`；已存在 → 完整结构（**密码不回明文**，含 `send_time` / `active`） |
| PUT  | `/api/email-config` | upsert 单行；写后同步 `email_daily_dispatch` Job（按 `active` 切换 run/pause） |
| POST | `/api/email/send-test` | 先自动保存入参配置（等价于 PUT），再向 `recipient_email` 发送固定测试邮件；返回 `{ok, sent_at, recipient}` |

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
  "send_time": "08:00",
  "active": false,
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
  "smtp_password_set": true,
  "use_tls": true,
  "sender_email": "user@qq.com",
  "sender_name": "SparkMemo",
  "recipient_email": "user@qq.com",
  "recipient_name": null,
  "send_time": "08:00",
  "active": false,
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
  "smtp_password": "abcdefghijklmnop",
  "use_tls": true,
  "sender_email": "user@qq.com",
  "sender_name": "SparkMemo",
  "recipient_email": "user@qq.com",
  "recipient_name": "我自己",
  "send_time": "08:00",
  "active": false
}
```

**服务端处理顺序**
1. 字段级 Pydantic 校验（邮箱格式 / 端口范围 / `send_time` 24h 正则）；
2. 若 `exists=false`：INSERT 一行；
3. 若 `exists=true` 且 `smtp_password` 为空 / null：保留旧密码；其他字段 UPDATE；
4. 若 `exists=true` 且 `smtp_password` 非空：覆盖密码；
5. `send_time` / `active` **每次 PUT 显式覆盖**（不沿用「留空保留」语义）；
6. 提交后调用 `scheduler.sync_email_dispatch_job(row)`：
   - `active=true` → `add_job(replace_existing=True)`，`trigger=CronTrigger(hour=h, minute=m, timezone="Asia/Shanghai")`；
   - `active=false` → `pause_job("email_daily_dispatch")`；
7. 返回与 GET 一致的响应（密码不回明文）。

**响应 200**：与 GET 已配置响应同结构。

#### `POST /api/email/send-test`

**请求**：与 `EmailConfigWrite` 同结构（接受完整 payload，**含 `smtp_password` 明文**）。

**服务端处理顺序**
1. 字段级 Pydantic 校验（同 PUT）；
2. 调用 `upsert_email_config` 持久化入参（幂等，写后同步调度器）；
3. 重新读取最新 `EmailConfig` 行（含密码）；
4. 构造测试 HTML：
   ```
   <h3>SparkMemo 邮件连通性测试</h3>
   <p>这是一封来自 SparkMemo 的测试邮件。</p>
   <p>发送时间：<ISO8601></p>
   <p>收件人：<recipient_email></p>
   ```
5. `mailer.send_html(...)`；
6. 失败 `MailerError` → 500 `{"detail": "<错误信息>"}`；
7. 成功 → 200 `{"ok": true, "sent_at": "<ISO8601>", "recipient": "<recipient_email>"}`。

> **不受 `active` 开关约束**：`active=false` 也允许调用（语义是验证 SMTP 连通性，与调度开关无关）。仅当 `email_config` 行**不存在**时（首次 PUT 前）应返回 4xx；当前实现采用「接受完整 payload 并自动写入」，等价于「总是先 upsert 再发」，因此始终返回 200 / 422 / 500。

### 错误约定

| HTTP | 场景 |
|------|------|
| 400 | `/api/email-config` 路径下 `RequestValidationError` → 400（`smtp_port` 越界 / 邮箱非法 / `send_time` 非 24h 正则 / 长度越界） |
| 422 | `/api/email/send-test` 路径下字段校验失败（沿用 FastAPI 默认；与 `tasks` 模块一致） |
| 500 | SMTP 连接 / 认证 / 超时失败（`MailerError` 透传 message） |

> `/api/email-config` 路径**没有 404 / 422 场景**：未配置 GET 返回 200 + `exists=false`；PUT 走 INSERT 路径。
> `/api/email/send-test` 路径**没有 404 场景**：未配置时也走 upsert → 发送；首次配置与首次测试可一次性完成。

---

## Service 层

### `services/mailer.py`

```python
class MailerError(Exception): ...

def send_html(config: models.EmailConfig, subject: str, html_body: str) -> None:
    """三段式 transport:
    - use_tls=True  & port=465 → SMTP_SSL
    - use_tls=True  & port=587 → SMTP + starttls
    - use_tls=False            → SMTP 明文
    失败：捕获 SMTPAuthenticationError / SMTPException / socket.timeout → MailerError
    """
```

- 仅依赖 stdlib `smtplib` + `email.mime.text.MIMEText`，**`requirements.txt` 零变更**；
- 固定 `timeout=10s`（便于测试 mock 与失败快速反馈）；
- 不写日志表（`mail_logs` 仍延后）。

### `services/email_dispatcher.py`

```python
def render_daily_dispatch(today: str, db) -> tuple[str, str]:
    """占位渲染：返回 (subject, html)。

    当前版本只构造一个最小 HTML，明确标注'提醒模板即将上线'，
    避免发送完整但不正确的内容。等业务模板确定后再展开。
    """
    return (
        f"SparkMemo 每日提醒 · {today}",
        f"<h3>SparkMemo 每日提醒</h3><p>日期：{today}</p>"
        f"<p>提醒内容正在生成中，详细模板将在后续版本上线。</p>"
    )
```

- 接受 `today: str`（**不调 `date.today()`**），与 `crud/dashboard.py:29` 风格一致；
- 本规格**不**做 SQL 业务查询，避免引入 `CURDATE()` / SQLite 兼容问题。

### `services/scheduler.py`（增量）

```python
from apscheduler.triggers.cron import CronTrigger

def _email_dispatch_wrapper() -> None:
    """APScheduler Job：读 email_config；active=true 才发；SMTP 失败不抛。"""
    from app.database import SessionLocal
    from app.crud.email_config import get_email_config
    from app.services.mailer import send_html, MailerError

    db = SessionLocal()
    try:
        cfg = get_email_config(db)
        if cfg is None or not cfg.active:
            return
        today_str = get_today()
        subject, html = email_dispatcher.render_daily_dispatch(today_str, db)
        try:
            send_html(cfg, subject, html)
        except MailerError:
            pass  # v0.4 不持久化失败日志
    finally:
        db.close()


def sync_email_dispatch_job(config: models.EmailConfig | None) -> None:
    """根据 DB 里的 (active, send_time) 重设 / 暂停 Job。CRUD 提交后调用。"""
    job = apscheduler_instance.get_job("email_daily_dispatch")
    if config is None or not config.active:
        if job:
            apscheduler_instance.pause_job("email_daily_dispatch")
        return
    h, m = config.send_time.split(":")
    apscheduler_instance.add_job(
        _email_dispatch_wrapper,
        trigger=CronTrigger(hour=int(h), minute=int(m), timezone="Asia/Shanghai"),
        id="email_daily_dispatch",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )

# 模块加载时预注册（paused）—— 保证 Job id 存在，CRUD 调用可重设
apscheduler_instance.add_job(
    _email_dispatch_wrapper,
    trigger=CronTrigger(hour=8, minute=0, timezone="Asia/Shanghai"),
    id="email_daily_dispatch",
    replace_existing=True,
    coalesce=True,
    misfire_grace_time=3600,
)
apscheduler_instance.pause_job("email_daily_dispatch")
```

关键设计：
- **Job id 永远存在**，仅在 `active=true` 时 `replace_existing + run`；`active=false` 时 `pause_job`；
- `coalesce=True` + `misfire_grace_time=3600`：进程停机过夜后启动只补一次，不会轰炸；
- 测试期 `SCHEDULER_DISABLED=1`（`conftest.py:13`）保持不变，确保单测不实际触发发送。

### `app/main.py` lifespan 启动顺序

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """启动顺序：幂等 ALTER → 按 DB 现状同步调度器 → 启动调度器。"""
    _ensure_email_config_columns(engine)
    cfg = crud.email_config.get_email_config(...)
    sync_email_dispatch_job(cfg)
    apscheduler_instance.start()
    try:
        yield
    finally:
        if apscheduler_instance.running:
            apscheduler_instance.shutdown(wait=False)
```

---

## Test Plan

> 测试位于 `backend/tests/`，使用 pytest + httpx AsyncClient；按 README §5.1 先全红后全绿。
> 测试数据库与 `conftest.py` 的 `db` fixture 同源；`email_config` 表需要在 conftest 的 TRUNCATE 列表里追加。

### 既有 `test_email_config.py`（11 用例 + 4 端口 parametrize → 14 计数）继续保留，新增 4 用例：

| # | 用例 | 测试目的 | 关键断言 |
|---|------|---------|---------|
| 12 | `test_get_default_send_time_and_active` | 未配置 GET 回显默认值 | `send_time='08:00'`、`active=false` |
| 13 | `test_put_send_time_24h_regex_rejects_invalid` | `send_time='25:00'` / `'24:60'` / `'9:00'` / `'ab:cd'` → 400 | 均 400 |
| 14 | `test_put_persists_send_time_and_active` | 合法 PUT 后 GET 回显新值 | `send_time='08:30'`、`active=true` |
| 15 | `test_put_send_time_overrides_each_call` | 第二次 PUT 即使只改 `active`，`send_time` 也覆盖 | `send_time='09:30'` 显式覆盖成功 |

### 新增 `test_mailer.py`（6 用例）

| # | 用例 | 测试目的 | 关键断言 |
|---|------|---------|---------|
| 1 | `test_send_html_uses_smtp_ssl_for_465` | `use_tls=true, port=465` → `smtplib.SMTP_SSL` 被调用 | mock `SMTP_SSL` 调用 1 次且 host/port 正确；未调 `starttls` |
| 2 | `test_send_html_uses_starttls_for_587` | `use_tls=true, port=587` → `SMTP` + `starttls()` | mock `SMTP` + `starttls()` 调用 1 次 |
| 3 | `test_send_html_uses_plain_for_25` | `use_tls=false, port=25` → 明文 | mock `SMTP` 调用 1 次；未调 `starttls` / `SMTP_SSL` |
| 4 | `test_send_html_raises_mailer_error_on_smtp_exception` | SMTP 抛 `SMTPException` → `MailerError` | `pytest.raises(MailerError)` |
| 5 | `test_send_html_raises_mailer_error_on_timeout` | `socket.timeout` → `MailerError` | `pytest.raises(MailerError)` |
| 6 | `test_send_html_message_headers` | 验证 Subject / From / To 字段 | 抓 mock 的 `send_message` 入参断言 |

### 新增 `test_send_test.py`（4 用例）

| # | 用例 | 测试目的 | 关键断言 |
|---|------|---------|---------|
| 1 | `test_send_test_invalid_field_returns_422` | 字段校验失败 → 422（非 `/api/email-config` 前缀） | 422 + detail 含错误 |
| 2 | `test_send_test_smtp_failure_returns_500` | mock `smtplib.SMTP` 抛 `SMTPException` → 500 | 500 + detail 含 SMTP 错误 |
| 3 | `test_send_test_success_response` | 完整入参 → 200 | `{ok: true, sent_at, recipient}`；`recipient_email` 与入参一致 |
| 4 | `test_send_test_persists_config_before_send` | send-test 先写入 DB | mock `smtplib.SMTP` 触发后 `db.query(EmailConfig)` 行存在且字段一致 |

### 新增 `test_scheduler_sync.py`（3 用例）

| # | 用例 | 测试目的 | 关键断言 |
|---|------|---------|---------|
| 1 | `test_sync_with_active_true_reschedules_job` | `active=true, send_time='08:30'` → Job `replace_existing` | `apscheduler_instance.get_job("email_daily_dispatch").trigger` 反映 `08:30`；`next_run_time` 字段非 None |
| 2 | `test_sync_with_active_false_pauses_job` | `active=false` → Job paused | `apscheduler_instance.get_job(...)` 存在但 `paused`；`next_run_time is None`（按 APScheduler paused 行为） |
| 3 | `test_sync_with_none_config_pauses_job` | 无配置 → Job paused | 同上 |

总计新增 **17 个用例**；与既有 128 叠加，目标 **145 passed**。

`conftest.py`：
- 既有 TRUNCATE 列表已含 `email_config`，无需改；
- 新增 `make_email_config` 工厂 fixture（与 `make_company` 风格一致）；
- 不引入 SMTP mock 全局 fixture——`unittest.mock.patch("smtplib.SMTP")` 已够用。

---

## Assumptions

1. **单用户本地版**维持不变：不引入登录、不引入多租户、不引入用户偏好设置表；
2. **SMTP 凭证存库是配置存储**：API 层一律不回明文，PUT 时支持「留空保留旧值」；
3. **单行配置表 `email_config`**：应用层固定以 `id = 1` 读写；不设计多账号 / 多模板 / 按公司分流；
4. **`send_time` 时区**：与既有 APScheduler 统一为 `Asia/Shanghai`，存裸 `HH:MM`；
5. **`active` 默认 `false`**：升级后不会立即发送任何邮件，必须显式启用；
6. **`send_time` / `active` 每次 PUT 覆盖**：与 `smtp_password` 的「留空保留旧值」行为不同——避免 UI 误触导致调度丢失；
7. **测试发送接受完整 `EmailConfigWrite` 入参并先持久化再发送**：避免重复传输密码；`active=false` 也允许调用；
8. **正式发送模板仅占位**：等业务内容确定后再展开；当前 Job 即便被触发也只发「提醒内容正在生成中，详细模板将在后续版本上线」；
9. **不引入 Alembic**：加列靠 lifespan 幂等 ALTER；
10. **`mail_logs` 表继续延后**：仅做 `MailerError` 静默吞掉，不写库；
11. **零新增依赖**：`smtplib` stdlib，`requirements.txt` 不动；
12. **不修改 `start.bat` / `start.sh`**：本规格不涉及启动脚本；
13. **APScheduler 在测试期禁用**：`conftest.py:13` 的 `SCHEDULER_DISABLED=1` 保持不变；`sync_email_dispatch_job` 测试仅断言 Job 状态（pause/run / trigger），不等待真实触发；
14. **OpenAPI 输出**：测试全绿后导出至 `backend/openapi/email_notification.json`。

---

## 后续版本演进项（明确延后）

- 正式提醒内容模板（按公司分组 HTML，参考 `crud/dashboard.py:31` 的 SQL）；
- 多账号 / 多模板 / 按公司分流；
- `mail_logs` 发送日志表；
- 失败重试 / 退避策略；
- `POST /api/email/send` 手动触发正式邮件接口；
- 启动脚本 (`start.bat` / `start.sh`) 补全；
- 前端「设置 → 邮箱配置」页面（已有独立 spec 路径）。

---

## 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 已有 MySQL 实例升级失败（缺列） | 启动崩溃 / 旧库不可用 | lifespan 幂等 `ALTER TABLE`，双方言分支 + `information_schema` / `PRAGMA` 探测 |
| 升级后误发邮件 | 用户被打扰 | `active` 默认 `false`，需显式启用 |
| `send_time` 修改后调度未生效 | 用户感知"改了没用" | `crud/email_config.py` commit 后立即 `sync_email_dispatch_job` |
| SMTP 凭证错误导致 Job 每日报错 | 日志噪音 | `MailerError` 静默吞掉（占位策略），未来接 `mail_logs` |
| 测试邮件泄漏真实凭证 | 安全 | `unittest.mock.patch("smtplib.SMTP")` 全测覆盖；测试夹具禁止真发 |
| 跨数据库 ALTER 语法差 | MySQL 8 / SQLite 行为不一致 | 双方言分支 + `information_schema` / `PRAGMA` 探测 |
| 占位邮件被升级用户视为正式 | 体验不佳 | subject / body 显式标注「提醒内容正在生成中」 |