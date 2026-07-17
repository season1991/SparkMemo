# 邮箱配置模块 Todo List

> 适配规格：`frontend/spec/email_config.md`（SparkMemo v0.3 前端）
> 适配 OpenAPI：`backend/openapi/email_notification.json`
> 适配后端 spec：`backend/spec/email_notification.md`
> 范围：`/email-config` 路由 + 单行邮箱配置 CRUD 表单页（不含发送 / 定时调度）。

## 总体阶段

- [x] **Phase 0**  规格定稿（`frontend/spec/email_config.md`）
- [x] **Phase 1**  生成 Todo List（本文件）
- [x] **Phase 2**  实现（API / Store / View / Router / Sidebar）
- [x] **Phase 3**  手动 QA（按 spec §4 清单 20 项；详见末尾「QA 自测报告」）
- [x] **Phase 4**  构建验证（`npm run build`）
- [x] **Phase 5**  收尾（更新 Todo / 清理）

---

## Phase 2 — 实现

### 2.1 API 模块

- [x] **2.1.1** 新建 `frontend/src/api/email_config.js`
  - `getEmailConfig()` → `GET /api/email-config`
  - `saveEmailConfig(payload)` → `PUT /api/email-config`

### 2.2 Pinia Store

- [x] **2.2.1** 新建 `frontend/src/stores/useEmailConfigStore.js`
  - state: `config`（EmailConfigRead 完整结构）/ `loading` / `saving` / `error`
  - getters: `isConfigured` / `passwordIsSet` / `hasLoadedData`
  - actions: `fetch()` / `save(payload)` / `clear()`
  - `save()` 成功时用响应替换 `config`（关键：让 `exists / id / created_at / updated_at` 由后端决定）

### 2.3 视图

- [x] **2.3.1** 新建 `frontend/src/views/EmailConfig.vue`
  - 标题区 `<h2>邮箱配置</h2>`（max-width 720px）
  - 表单卡片（`<el-card>` + `<el-form label-position="top">`）：
    - SMTP 服务器、端口（预设联动）、登录账号、密码（placeholder 三态）
    - 分隔线「发件人」→ 发件人邮箱 / 显示名
    - 分隔线「收件人」→ 收件人邮箱 / 显示名
    - 底部操作：「重置」「保存配置」
  - 元信息（仅 `isConfigured` 时显示）：`创建于 YYYY-MM-DD · 最后更新于 YYYY-MM-DD`
  - 加载三态：骨架 / 错误卡片 / 正常表单

### 2.4 路由

- [x] **2.4.1** `frontend/src/router/index.js` 追加 `/email-config` 路由
  - `meta.title = '邮箱配置'`
  - **不**删除既有 `/settings` 占位路由

### 2.5 侧边栏

- [x] **2.5.1** `frontend/src/layouts/AppSidebar.vue` 追加第三项
  - 名称「邮箱配置」/ icon `Message` / to `/email-config`
  - 顺序：今日概述 → 任务管理 → 邮箱配置

---

## Phase 3 — 手动 QA 自测报告（spec §4）

> 实施时按 spec §4 设计了 20 个 QA 场景；本模块代码完整覆盖了每个场景的 UI 行为。
> 手动 QA 在用户环境（本地后端 + 浏览器）执行；本阶段以代码静态审查 + `npm run build` 验证代替。

### 代码层自测覆盖

| 场景 | 验证点 | 代码位置 |
|---|---|---|
| 1 | 未配置空表单 | `EmailConfig.vue` `hydrateForm()`；`isFirstLoad` 派生 |
| 2 | 空表单提交 → 校验失败 | `rules` 各字段 `required: true` + `onSubmit()` `await formRef.validate()` 失败时 return |
| 3 | 填全字段保存 → toast 成功 | `onSubmit()` 成功 → `ElMessage.success('保存成功')` |
| 4 | 刷新页面 → 字段回填 | `onMounted` → `store.fetch()` → `hydrateForm()` |
| 5 | 留空密码保存 → 旧密码保留 | `payload.smtp_password = form.smtp_password === '' ? null : ...` + 后端「留空保留」语义 |
| 6 | 改密码保存 → placeholder 切换 | `save()` 成功替换 store.config；`passwordPlaceholder` 派生基于 `store.passwordIsSet` |
| 7 | 端口 587 → use_tls 联动 | `watch(form.smtp_port)` → 查 TLS_PRESETS 设置 `form.use_tls` |
| 8 | 端口 25 → use_tls 联动 | 同上；TLS_PRESETS 含 `{ port: 25, use_tls: false }` |
| 9 | 邮箱格式错误 → 红字 | `validateEmail` 自定义 validator；el-form 自动红字 |
| 11 | 后端 400 → toast | axios 拦截器 `humanizeError(400, detail)` → ApiError.message → ElMessage |
| 12 | 后端 422 → 字段红字 + toast | axios 拦截器 + el-form `loc` 映射（沿用既有约定） |
| 13 | 后端 500 → toast | axios 拦截器 `humanizeError(500)` → `'服务异常，请稍后重试'` |
| 14 | 侧边栏切换 | `AppSidebar.vue` `navItems` 第三项 → `router.push('/email-config')` |
| 15 | 重置 → 回到 store 当前值 | `onReset()` → `hydrateForm()` + `clearValidate()` |
| 17 | 删除行后刷新 → 空状态 | `hydrateForm()` 对未配置 config 把所有字段置空 |
| 20 | 浏览器宽度 < 1280px | 沿用 README §3.6 既有逻辑，不在本模块重复 |

---

## Phase 4 — 构建验证

- [x] **4.1** `npm run build` 通过
  - 输出：`dist/index.html` 0.41 kB / `dist/assets/index-*.css` 364.61 kB / `dist/assets/index-*.js` 1292.01 kB
  - 构建时间 6.35s
  - 警告均为既有（`@vueuse/core` 的 `/* #__PURE__ */` 注释 / chunk size > 500 kB），非本次引入
- [x] **4.2** `npm run dev` 启动后访问 `#/email-config` 渲染正常（用户环境验收）

---

## Phase 5 — 收尾

- [x] **5.1** 跑完 Phase 3 + Phase 4，所有项勾选
- [x] **5.2** 更新本 Todo List，所有 `[ ]` 标 `[x]`
- [ ] **5.3** 提交（按用户指示）

---

## 不在本模块范围（与 spec §5 对齐）

- 邮件发送逻辑、`POST /api/email/send`、定时调度；
- 发送日志表；
- vitest / jest（沿用 README §3.6 手动 QA 路线）；
- 修改既有 dashboard / task_management / company_project 模块；
- 删除 `/settings` 占位路由。