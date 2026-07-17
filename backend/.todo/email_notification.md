# 邮件通知模块 Todo List

> 适配规格：`backend/spec/email_notification.md`（SparkMemo v0.3）
> 本版本范围：**仅邮箱配置 CRUD**（`email_config` 表 + `GET/PUT /api/email-config`）。不实现 SMTP 发送、不实现定时调度、不实现 dispatcher。
> 测试策略：按 spec §5.1，**先全红后全绿**。Phase 2 产物仅 `backend/tests/`，运行 `pytest` 期望全部失败（含 `ImportError` / `AttributeError` / `404`）。
> 测试 DB：复用 conftest 的 TRUNCATE 列表，需要追加 `email_config`。

## 总体阶段

- [x] **Phase 0**  规格定稿（`backend/spec/email_notification.md`）
- [x] **Phase 1**  生成 Todo List（本文件）
- [x] **Phase 2**  测试驱动 - 全红（`backend/tests/test_email_config.py` 全失败）
- [x] **Phase 3**  后端实现 - 全绿（`app/` 代码让 pytest 全过）
- [x] **Phase 4**  生成 OpenAPI（`backend/openapi/email_notification.json`）
- [x] **Phase 5**  收尾（更新 Todo / 清理）

---

## Phase 2 — 测试驱动（全红）

### 2.1 测试用例文件

- [x] **2.1.1** 新建 `backend/tests/test_email_config.py`
  - 用例 1：`test_get_when_not_exists` — 未配置 GET → 200 + `exists=false` + 所有字段 null
  - 用例 2：`test_put_upsert_when_not_exists` — 首次 PUT → 200 + DB 1 行 + `exists=true`
  - 用例 3：`test_get_after_upsert` — PUT 后 GET → 200 + `exists=true` + `smtp_password_set=true` + 响应无 `smtp_password` 字段
  - 用例 4：`test_put_updates_existing` — 第二次 PUT → DB 仍 1 行 + 字段同步
  - 用例 5：`test_put_empty_password_keeps_old` — PUT `smtp_password=""` → 旧密码保留（`smtp_password_set=true`）
  - 用例 6：`test_put_invalid_port[0/-1/99999/100000]` — 端口越界 → 400
  - 用例 7：`test_put_invalid_sender_email` — `sender_email="not-an-email"` → 400
  - 用例 8：`test_put_invalid_recipient_email` — `recipient_email="not-an-email"` → 400
  - 用例 9：`test_put_invalid_smtp_host_length` — `smtp_host` > 128 字符 → 400
  - 用例 10：`test_put_invalid_sender_name_length` — `sender_name` > 64 字符 → 400
  - 用例 11：`test_password_never_in_response` — GET/PUT 响应递归扫描无 `smtp_password` 字段

### 2.2 conftest 扩展

- [x] **2.2.1** `backend/tests/conftest.py` 的 `db` fixture TRUNCATE 列表追加 `email_config`

---

## Phase 3 — 后端实现（全绿）

### 3.1 数据模型

- [x] **3.1.1** `backend/app/models.py` 追加 `EmailConfig` 模型（10 字段）

### 3.2 Pydantic Schema

- [x] **3.2.1** `backend/app/schemas.py` 追加 `EmailConfigRead` / `EmailConfigWrite`
  - 邮箱字段用正则校验（不引入 `email-validator` 依赖）

### 3.3 CRUD

- [x] **3.3.1** 新建 `backend/app/crud/email_config.py`
  - `get_email_config(db)` 按 id=1 查单行
  - `upsert_email_config(db, payload)` 单行 upsert（密码留空保留旧值）

### 3.4 API 路由

- [x] **3.4.1** 新建 `backend/app/api/email_config.py`
  - `GET ""` → `EmailConfigRead`（`exists=false` 或完整结构）
  - `PUT ""` → `EmailConfigRead`（调 upsert）

### 3.5 main.py 挂载

- [x] **3.5.1** `backend/app/main.py` 挂载新路由 + 增加 `RequestValidationError` 处理器（`/api/email-config` 下 422→400，其他路由保持 422）

---

## Phase 4 — OpenAPI

- [x] **4.1** 导出 `backend/openapi/email_notification.json`（含 `GET/PUT /api/email-config` 契约 + `EmailConfigWrite` / `EmailConfigRead` schema）

---

## Phase 5 — 收尾

- [x] **5.1** 跑一遍完整测试，确认 14 个 email_config 用例全绿且未破坏其他模块（**全套 128 用例全过**）
- [x] **5.2** 更新本 Todo List，所有 `[ ]` 标 `[x]`

---

## 测试结果

```
============================= 128 passed in 3.79s ==============================
```

其中 `test_email_config.py` 14 个用例全部通过；其余 114 个既有模块用例无回归。

---

## 延后项（明确不在本版本范围）

- SMTP 发送封装（`services/mailer.py`）
- 今日提醒生成（`services/email_dispatcher.py`）
- 发送接口（`POST /api/email/send`）
- APScheduler 邮件 Job（`services/scheduler.py` 扩展）
- 多账号 / 多模板 / 发送日志表 / 前端页面