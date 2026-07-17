# 邮箱配置模块规格（前端）

> 适配 OpenAPI：[../../backend/openapi/email_notification.json](../../backend/openapi/email_notification.json)（路径 `/api/email-config`、schema `EmailConfigRead` / `EmailConfigWrite`）
> 适配后端 spec：[../../backend/spec/email_notification.md](../../backend/spec/email_notification.md)
> 页面入口：`views/EmailConfig.vue`（路由 `/email-config`）
> 全局规则遵循 [./README.md](./README.md)；本文档只描述本模块特有的页面拆解、功能点交互与测试案例。

---

## 1. 整体页面结构拆解

### 1.1 路由与视图

| 路径 | 视图 | 侧边栏激活项 | `meta.title` | 说明 |
|------|------|------------|--------------|------|
| `/email-config` | `views/EmailConfig.vue` | 邮箱配置 | 邮箱配置 | 单行表单页：管理 SMTP 凭证与收发件人 |

> **既有路由保留**：旧 `/settings` 路由仍可达（保持历史链接兼容），不在本模块侧边栏中显示。本模块**不**做删除操作。

### 1.2 侧边栏

| 顺序 | 名称 | icon | to |
|------|------|------|----|
| 1 | 今日概述 | `DataAnalysis` | `/` |
| 2 | 任务管理 | `List` | `/tasks` |
| 3 | 邮箱配置 | `Message` | `/email-config` |

> - 图标全部走 `@element-plus/icons-vue`，按需 import；
> - 激活态判断为 `route.path === item.to`；
> - 样式遵循 [README §5.2](./README.md#52-布局)：左 3px 主色竖条 + 浅主色背景 `#ecf5ff` + 文字主色 `#409eff`。

### 1.3 主页 DOM 结构

布局遵循 [README §5.2](./README.md#52-布局)：左 220px 导航 + 右侧 56px 页面页头 + 主内容区。

```
<AppLayout>
  <AppSidebar>                          ← 220px 固定（3 项，详见 §1.2）
    ├─ Logo 区（64px）：⚡ SparkMemo
    └─ 导航项（44px × 3，间距 4px）
         - 今日概述  (icon: DataAnalysis)
         - 任务管理  (icon: List)
         - 邮箱配置  (icon: Message)
  </AppSidebar>
  <AppPage>                             ← 右侧容器
    <AppHeader>                         ← 56px 页面页头
      └─ 左：<h1>{{ route.meta.title }}</h1>  ← "邮箱配置"
    </AppHeader>
    <AppMain>                           ← max-width 1440px, padding 16 24
      <EmailConfigView>
        ┌─ 标题区（max-width 720px）─────────────────────┐
        │ <h2>邮箱配置</h2>                              │
        └────────────────────────────────────────────────┘
        ┌─ 表单卡片（max-width 720px）───────────────────┐
        │ <el-card shadow="never">                       │
        │   <el-form :model="form" :rules="rules"        │
        │            ref="formRef" label-position="top"> │
        │                                                │
        │   ┌─ SMTP 服务器 ─────────────────────────┐     │
        │   │ <el-form-item label="SMTP 服务器"     │     │
        │   │                  prop="smtp_host">     │     │
        │   │   <el-input v-model="form.smtp_host" />│    │
        │   │ </el-form-item>                       │     │
        │   └───────────────────────────────────────┘     │
        │   ┌─ 端口 ────────────────────────────────┐     │
        │   │ <el-form-item label="端口"            │     │
        │   │                  prop="smtp_port">    │     │
        │   │   <el-select v-model="form.smtp_port">│     │
        │   │     <el-option :value="465" .../>     │     │
        │   │     <el-option :value="587" .../>     │     │
        │   │     <el-option :value="25"  .../>     │     │
        │   │   </el-select>                        │     │
        │   │   <span class="hint">                 │     │
        │   │     已加密方式与端口联动，保存即生效   │     │
        │   │   </span>                             │     │
        │   └───────────────────────────────────────┘     │
        │   ┌─ 登录账号 ────────────────────────────┐     │
        │   │ <el-form-item label="登录账号"        │     │
        │   │                  prop="smtp_user">    │     │
        │   │   <el-input v-model="form.smtp_user"/>│     │
        │   │ </el-form-item>                       │     │
        │   └───────────────────────────────────────┘     │
        │   ┌─ 密码 ────────────────────────────────┐     │
        │   │ <el-form-item label="密码"            │     │
        │   │                  prop="smtp_password">│     │
        │   │   <el-input                          │     │
        │   │     v-model="form.smtp_password"      │     │
        │   │     type="password"                   │     │
        │   │     show-password                     │     │
        │   │     :placeholder="passwordPlaceholder"│     │
        │   │   />                                  │     │
        │   │   <span class="hint">                 │     │
        │   │     不修改密码请留空；新密码将覆盖原值。│     │
        │   │   </span>                             │     │
        │   └───────────────────────────────────────┘     │
        │                                                │
        │   <el-divider>发件人</el-divider>              │
        │                                                │
        │   ┌─ 发件人邮箱 ────────────────────────┐       │
        │   │ <el-form-item label="发件人邮箱"     │       │
        │   │                  prop="sender_email">│      │
        │   │   <el-input v-model="form.sender_email"│    │
        │   │           type="email" />            │     │
        │   │ </el-form-item>                      │     │
        │   └──────────────────────────────────────┘     │
        │   ┌─ 发件人显示名 ───────────────────────┐      │
        │   │ <el-form-item label="发件人显示名"   │      │
        │   │                  prop="sender_name"> │      │
        │   │   <el-input v-model="form.sender_name"/>│    │
        │   │ </el-form-item>                      │     │
        │   └──────────────────────────────────────┘     │
        │                                                │
        │   <el-divider>收件人</el-divider>              │
        │                                                │
        │   ┌─ 收件人邮箱 ────────────────────────┐       │
        │   │ <el-form-item label="收件人邮箱"     │       │
        │   │                  prop="recipient_email">│    │
        │   │   <el-input v-model="form.recipient_email"│  │
        │   │           type="email" />            │     │
        │   │ </el-form-item>                      │     │
        │   └──────────────────────────────────────┘     │
        │   ┌─ 收件人显示名 ───────────────────────┐      │
        │   │ <el-form-item label="收件人显示名（可选）"│  │
        │   │                  prop="recipient_name"> │   │
        │   │   <el-input v-model="form.recipient_name"/>│  │
        │   │ </el-form-item>                      │     │
        │   └──────────────────────────────────────┘     │
        │ </el-form>                                    │
        │                                                │
        │ <div class="form-actions">                    │
        │   <el-button @click="onReset">重置</el-button> │
        │   <el-button type="primary"                   │
        │              :loading="store.saving"          │
        │              :disabled="store.saving"         │
        │              @click="onSubmit">               │
        │     保存配置                                  │
        │   </el-button>                                │
        │ </div>                                        │
        │ </el-card>                                    │
        └────────────────────────────────────────────────┘
        ┌─ 元信息（仅已配置时显示，max-width 720px）─────┐
        │ <div class="meta" v-if="store.isConfigured">  │
        │   创建于 {{ store.config.created_at }}        │
        │   ·  最后更新于 {{ store.config.updated_at }} │
        │ </div>                                        │
        └────────────────────────────────────────────────┘
      </EmailConfigView>
    </AppMain>
  </AppPage>
</AppLayout>
```

### 1.4 模块涉及组件与 store

| 类型 | 名称 | 职责 |
|------|------|------|
| Layout | `layouts/AppLayout.vue` | 整体布局容器：左 Sidebar + 右侧 Page |
| Layout | `layouts/AppSidebar.vue` | 左侧导航条（Logo + 导航项），**追加「邮箱配置」第三项** |
| Layout | `layouts/AppHeader.vue` | 页面页头，左侧渲染 `route.meta.title` |
| View | `views/EmailConfig.vue` | 主页骨架，承载标题区、表单卡片、元信息 |
| Store | `stores/useEmailConfigStore.js` | 单行邮箱配置的 state / actions / getters |
| API | `api/email_config.js` | `getEmailConfig()` / `saveEmailConfig(payload)` |

> 不引入额外的公共组件；本模块体量小，表单直接放在 view 内部。

---

## 2. 页面的功能点

### 2.1 功能点：进入邮箱配置页

#### 入口
- 浏览器直接访问 `#/email-config`；
- 左侧导航条点击「邮箱配置」→ `router.push('/email-config')`。

#### 静态展示规则
- 左侧导航条：Logo「⚡ SparkMemo」在顶部；当前路由对应项激活（左侧 3px 主色竖条 + 浅主色背景）；
- 页面页头：左侧显示 `route.meta.title`（`邮箱配置`）；右侧信息展示位 v0.1 留空；
- 标题区：`<h2>邮箱配置</h2>` + 灰色 hint 文字；
- 表单卡片：详见 §1.3；
- 「保存配置」按钮始终文案一致（不区分 insert / update）。

#### 交互逻辑：首次加载

| 阶段 | 内容 |
|------|------|
| 操作前 | 路由切换完成，组件 mount |
| 触发动作 | `EmailConfig.vue` 的 `onMounted` 触发 `store.fetch()` |
| 接口请求 | `GET /api/email-config` |
| 成功逻辑（未配置） | `store.config.exists = false`；表单字段全空；按钮「保存配置」可用；底部元信息隐藏 |
| 成功逻辑（已配置） | `store.config.exists = true`；表单字段填充（密码框空）；按钮「保存配置」可用；底部显示 `created_at · updated_at` |
| 失败逻辑（无旧数据） | error 卡片显示「加载失败 [重试]」；点击重试 → `store.fetch()` |
| 失败逻辑（有旧数据） | toast `ElMessage.warning('加载失败')`；保留旧表单内容 |

### 2.2 功能点：表单填写与端口联动

#### 字段填写
- 用户在表单中按需修改字段；
- 字段失焦（`blur`）+ 提交（`submit`）触发校验，输入中不打断（沿用 [README §3.3](./README.md#33-表单通用校验规则)）；
- 字段下方红字提示由 `el-form-item` 的 `error` 自动渲染。

#### 端口 ↔ TLS 联动

| 端口选项 | 显示 label | `use_tls` |
|---|---|---|
| `465` | `SSL (465)` | `true` |
| `587` | `STARTTLS (587)` | `true` |
| `25` | `无加密 (25)` | `false` |

| 阶段 | 内容 |
|------|------|
| 操作前 | 当前端口值 |
| 触发动作 | 用户切换端口下拉 |
| 接口请求 | 无（纯前端联动） |
| 成功逻辑 | `form.use_tls` 自动跟随端口预设更新；UI 不显式渲染 use_tls 控件（仅在提交 payload 时携带） |
| 失败逻辑 | — |

#### 密码框 placeholder 策略

| 状态 | placeholder 文案 |
|---|---|
| `config.exists === false` | `(请输入)` |
| `config.exists === true && passwordIsSet === true` | `(已设置，留空表示不修改)` |
| `config.exists === true && passwordIsSet === false` | `(请输入)` |

### 2.3 功能点：保存配置

#### 入口
- 表单卡片底部「保存配置」按钮。

#### 交互逻辑：保存提交

| 阶段 | 内容 |
|------|------|
| 操作前 | 表单字段已填写 |
| 触发动作 | 点击「保存配置」 |
| 前端校验 | `el-form.validate()` 失败 → 字段红字 + 按钮恢复可用（不弹 toast） |
| 接口请求 | `PUT /api/email-config` body（snake_case）：<br>`{ smtp_host, smtp_port, smtp_user, smtp_password?, use_tls, sender_email, sender_name, recipient_email, recipient_name? }`<br>其中：<br>• `smtp_password` 在用户**实际输入**时为字符串，否则为 `null`<br>• `recipient_name` 空时为 `null` |
| 成功逻辑 | `ElMessage.success('保存成功')`；用响应替换 `store.config`；密码框 placeholder 切到「已设置」；底部元信息 `created_at / updated_at` 同步刷新 |
| 失败逻辑（400） | `ElMessage.error(detail)`（detail 由 axios 拦截器 humanize 后为字符串）；表单不重置 |
| 失败逻辑（422） | 字段红字按 `detail[].loc` 映射（沿用既有约定）；顶部 toast 聚合 `msg` |
| 失败逻辑（5xx / 网络） | `ElMessage.error('服务异常，请稍后重试')` 或 `'网络异常，请稍后重试'` |

#### 按钮状态

| 场景 | 「保存配置」 | 「重置」 |
|---|---|---|
| 默认 | 可点 | 可点 |
| 保存中（`store.saving === true`） | loading + 禁用 | 禁用 |
| 加载中（首屏骨架） | 禁用（连同表单一起不可见） | 禁用 |

### 2.4 功能点：重置表单

#### 入口
- 表单卡片底部「重置」按钮。

#### 交互逻辑

| 阶段 | 内容 |
|------|------|
| 操作前 | 用户可能改过表单字段 |
| 触发动作 | 点击「重置」 |
| 接口请求 | 无 |
| 成功逻辑 | 表单所有字段**回滚到当前 `store.config` 的值**（不是清空）；`el-form.clearValidate()` 清空红字；密码框回到空字符串，placeholder 恢复 |
| 失败逻辑 | — |

> 「重置」语义：**撤销未保存的修改**，回到「当前 store 中保存的版本」，不是「清空表单」。这与一般表单习惯略不同，hint 文字可考虑加 `不保存时点击重置可恢复上次保存值`（可选 v0.4）。

### 2.5 功能点：侧边栏导航切换

| 阶段 | 内容 |
|------|------|
| 操作前 | 任意路由 |
| 触发动作 | 点击侧边栏「邮箱配置」 |
| 路由跳转 | `router.push('/email-config')` |
| 组件行为 | 路由切换完成 → `EmailConfig.vue` mount → `onMounted` 触发 `store.fetch()` |
| 失败逻辑 | 与 §2.1 一致 |

### 2.6 功能点：浏览器后退 / 直接访问

| 场景 | 期望 |
|---|---|
| 在 `/email-config` 点浏览器后退 | 路由回退；**不**弹二次确认（v0.3 简化） |
| 直接访问 `#/email-config` | 同 §2.1 首次加载行为 |
| 直接访问 `#/email-config` 时后端 500 | error 卡片 + 「重试」按钮（无旧数据场景） |

---

## 3. 字段契约（与 OpenAPI 对齐）

`useEmailConfigStore.config` 与 OpenAPI `EmailConfigRead` 完全 snake_case 直存；表单 `form` 字段命名与 OpenAPI `EmailConfigWrite` 对齐。

### 3.1 store.config ↔ EmailConfigRead

| state 字段 | 类型 | 来源 | 备注 |
|----------|------|------|------|
| `config.exists` | `bool` | GET / PUT 响应 | 必填字段（响应里 `required: ["exists"]`） |
| `config.id` | `int \| null` | GET / PUT 响应 | `exists=true` 时非空；未配置时 `null` |
| `config.smtp_host` | `string \| null` | GET / PUT | |
| `config.smtp_port` | `int \| null` | GET / PUT | 1-65535 |
| `config.smtp_user` | `string \| null` | GET / PUT | 1-128 字符 |
| `config.smtp_password_set` | `bool` | **仅 GET 响应字段** | PUT payload 不含此字段 |
| `config.use_tls` | `bool` | GET / PUT | 默认 `false`（GET 未配置时）；PUT 时跟随端口联动 |
| `config.sender_email` | `string \| null` | GET / PUT | 邮箱格式 |
| `config.sender_name` | `string \| null` | GET / PUT | 1-64 字符 |
| `config.recipient_email` | `string \| null` | GET / PUT | 邮箱格式 |
| `config.recipient_name` | `string \| null` | GET / PUT | 可空；1-64 字符 |
| `config.created_at` | `string \| null` | GET / PUT 响应 | `YYYY-MM-DD`；渲染于底部元信息 |
| `config.updated_at` | `string \| null` | GET / PUT 响应 | `YYYY-MM-DD`；渲染于底部元信息 |

### 3.2 form ↔ EmailConfigWrite

PUT payload 字段映射：

| 表单字段 | payload 字段 | 备注 |
|---|---|---|
| `form.smtp_host` | `smtp_host` | 必填 |
| `form.smtp_port` | `smtp_port` | 数字；必填 |
| `form.smtp_user` | `smtp_user` | 必填 |
| `form.smtp_password` | `smtp_password` | **仅在用户实际输入时为字符串**；其余传 `null`（后端「留空保留旧值」） |
| `form.use_tls` | `use_tls` | 跟随端口联动；不显式渲染控件 |
| `form.sender_email` | `sender_email` | 必填 |
| `form.sender_name` | `sender_name` | 必填 |
| `form.recipient_email` | `recipient_email` | 必填 |
| `form.recipient_name` | `recipient_name` | 空时传 `null` |

> **空字符串 vs null**：表单字段全用字符串；提交前做一次转换：
> - `smtp_password === ''` → `null`（用户没改）；
> - `recipient_name === ''` → `null`（用户没填）。
> 其余空字符串场景在前端 el-form 校验阶段已被必填规则拦下，不会进入 payload。

### 3.3 表单 el-form rules

| 字段 | rule |
|---|---|
| `smtp_host` | `[{ required: true, message: '请输入 SMTP 服务器', trigger: 'blur' }, { min: 1, max: 128, message: '长度 1-128 字符', trigger: 'blur' }]` |
| `smtp_port` | `[{ required: true, message: '请选择端口', trigger: 'change' }]` |
| `smtp_user` | `[{ required: true, message: '请输入登录账号', trigger: 'blur' }, { min: 1, max: 128, message: '长度 1-128 字符', trigger: 'blur' }]` |
| `smtp_password` | `[{ validator: validatePasswordOptional, trigger: 'blur' }]`（非必填；非空时 1-256 字符） |
| `sender_email` | `[{ required: true, message: '请输入发件人邮箱', trigger: 'blur' }, { validator: validateEmail, trigger: 'blur' }]` |
| `sender_name` | `[{ required: true, message: '请输入发件人显示名', trigger: 'blur' }, { min: 1, max: 64, message: '长度 1-64 字符', trigger: 'blur' }]` |
| `recipient_email` | `[{ required: true, message: '请输入收件人邮箱', trigger: 'blur' }, { validator: validateEmail, trigger: 'blur' }]` |
| `recipient_name` | `[{ validator: validateOptionalName, trigger: 'blur' }]`（非必填；非空时 1-64 字符） |

`validateEmail` 自定义函数复用后端正则 `^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$`。

---

## 4. 手动 QA 清单

> 前端 v0.3 不引入 vitest / jest（沿用 [README §3.6](./README.md#36-兼容要求)）。本节列出开发自测与产品验收的统一基线。

| # | 场景 | 期望 |
|---|---|---|
| 1 | 数据库无 `email_config` 行 → 访问 `#/email-config` | 表单字段全空；「保存配置」可点；底部无元信息 |
| 2 | 空表单点击「保存配置」 | el-form 校验失败：所有必填字段红字；**不**触发 API |
| 3 | 填全字段（端口选 465）→ 保存 | toast「保存成功」；表单保留值；底部显示「创建于 YYYY-MM-DD」；密码框 placeholder 切到「已设置」 |
| 4 | 刷新页面 | 表单字段回填；密码框空；placeholder 显示「已设置，留空表示不修改」 |
| 5 | 不改密码只改端口 → 保存 | toast 成功；DB 中 `smtp_password` 未变；`smtp_port` 与 `use_tls` 更新 |
| 6 | 输入新密码 → 保存 | toast 成功；`updated_at` 推进；GET 仍 `smtp_password_set=true` |
| 7 | 端口下拉选 587 → 切换时 `use_tls` 联动为 `true` | 字段不可见但 payload 含 `use_tls: true` |
| 8 | 端口下拉选 25 → 联动 `use_tls: false` | payload 含 `use_tls: false` |
| 9 | 邮箱格式错误（`not-an-email`） | 字段红字「请输入正确的邮箱」；保存禁用 |
| 10 | 端口选 25 后手动改 store 绕过下拉（极端） | el-form 校验拦截；不触发 API |
| 11 | 后端 400（如 `smtp_port=0`） | 顶层 toast 展示后端 `detail`；表单不重置；密码框不清空 |
| 12 | 后端 422 | 字段红字映射到对应字段；聚合 `detail[].msg` 顶部 toast |
| 13 | 后端 500 / 网络断 | toast「服务异常 / 网络异常」；表单保留；按钮恢复可点 |
| 14 | 侧边栏点击「邮箱配置」 | 路由 `/email-config`；激活态切换；表单重新加载 |
| 15 | 在表单改了若干字段 → 点「重置」 | 表单回到 store.config 当前值；密码框清空；placeholder 恢复；红字消失 |
| 16 | 在 `/email-config` 点浏览器后退 | 路由回退；**不**弹二次确认 |
| 17 | 删除所有 `email_config` 行（DB 操作）→ 刷新 | 重新进入「未配置」空状态；底部元信息隐藏 |
| 18 | GET 响应中 `smtp_password_set=false` 但其他字段已设置 | placeholder 显示「请输入」（提示必须设置密码）；保存后 `smtp_password_set=true` |
| 19 | 保存中（`store.saving === true`）切路由到其他页 | 表单状态保留在内存中（路由切换不丢 store）；返回时仍可继续操作 |
| 20 | 浏览器宽度 < 1280px | 按 [README §3.6](./README.md#36-兼容要求) 给提示（既有逻辑不动） |

---

## 5. 范围声明

### 在范围内（本模块实现）

- 新建 `views/EmailConfig.vue`（主页骨架 + 表单卡片）；
- 新建 `api/email_config.js`（`getEmailConfig` / `saveEmailConfig`）；
- 新建 `stores/useEmailConfigStore.js`（state + getters + actions）；
- 路由表追加 `/email-config`；
- 侧边栏 `navItems` 追加「邮箱配置」第三项（icon: `Message`）；
- 端口 ↔ `use_tls` 联动（下拉预设）；
- 密码框 placeholder 动态切换（未配置 / 已设置未改 / 已设置可改）；
- 加载 / 保存三态（[README §5.5 加载与错误三态](frontend/spec/dashboard.md) 约定）；
- 前端表单 el-form rules + 后端 400 / 422 兜底；
- 「保存配置」按钮统一文案（不区分 insert / update）；
- 「重置」按钮回到 store.config 当前值；
- 手动 QA 清单（§4）。

### 不在本模块范围（与本次 email_config 同步声明）

- **不**实现任何邮件发送逻辑（前端不调发送接口；后端 mailer / dispatcher 留待后续版本）；
- **不**渲染历史发送记录 / 发送日志表（spec 已延后）；
- **不**实现定时调度 UI（属后端 APScheduler 扩展）；
- **不**删除 `/settings` 占位路由（保持向后兼容）；
- **不**改既有模块（dashboard / task_management / company_project）的任何代码；
- **不**引入 vitest / jest（沿用 [README §3.6](./README.md#36-兼容要求) 的手动 QA 路线）；
- **不**改 [README §3 全局通用规则](./README.md#3-全局通用规则)（分页 / 筛选 / 表单 / 弹窗等既有约定对单行表单页天然不适用，本模块仅引用「表单通用校验规则」与「错误文案」子节）。

### v0.4+ 演进项（不在本轮）

- 「重置」按钮语义扩展：增加 `ElMessageBox.confirm` 二次确认（v0.4）；
- 表单 dirty 检测 + 路由切换 / 关闭前二次确认；
- 「测试发送」按钮（依赖后端 `POST /api/email/send` 上线）；
- 「定时发送」开关（依赖后端 `email_config.send_time` / `active` 字段上线）；
- 多账号 / 多模板支持；
- i18n / 移动端适配。

---

## 6. 关联文档

| 文档 | 位置 |
|------|------|
| 前端全局规则 | [./README.md](./README.md) |
| 后端模块 spec | [../../backend/spec/email_notification.md](../../backend/spec/email_notification.md) |
| OpenAPI 接口契约 | [../../backend/openapi/email_notification.json](../../backend/openapi/email_notification.json) |
| 今日概述前端 spec | [./dashboard.md](./dashboard.md)（参考其三态约定） |
| 任务管理前端 spec | [./task_management.md](./task_management.md)（参考其表单 / 校验 / toast 约定） |