# 今日概述（前端）Todo List

> 适配规格：`frontend/spec/dashboard.md`
> 适配 OpenAPI：`backend/openapi/dashboard.json`
> 适配后端 spec：`backend/spec/dashboard.md`
> 测试策略：v0.1 **无自动化测试框架**（无 vitest / jest）；靠 spec §4 手动 QA 清单逐条跑通。
> 代码风格遵循 `frontend/spec/README.md` §3 全局规则（snake_case 直存 / Axios 拦截器 / Element Plus 组件优先）。

## 总体阶段

- [x] **Phase 0**  规格定稿（`frontend/spec/dashboard.md`）
- [x] **Phase 1**  生成 Todo List（本文件）+ 更新 `frontend/spec/README.md` §2 索引
- [ ] **Phase 2**  代码实现（按 §3 顺序逐步写文件）
- [ ] **Phase 3**  手动 QA（按 spec §4 18 条逐项验证）
- [ ] **Phase 4**  收尾（lint / 类型 check / 顺手改的 TaskList 路径更新）

---

## Phase 2 — 代码实现

### 2.1 新建文件

- [ ] **2.1.1** `frontend/src/api/dashboard.js`
  - 单函数 `getDashboardToday()`，调用 `client.get('/dashboard/today')`
  - 文件头部 JSDoc 注明：后端实现见 `backend/openapi/dashboard.json`
- [ ] **2.1.2** `frontend/src/stores/useDashboardStore.js`
  - state: `{ today, summary, companies, loading, error }`
  - getters: `isEmpty`（summary.total === 0）、`companyCount`、`hasAnyCount`
  - actions: `async fetch()` 写入 + 错误兜底（保留旧数据，error 写入）
  - 写入前对 `res.summary`、`res.companies` 做 `|| {}` / `|| []` 默认值兜底
- [ ] **2.1.3** `frontend/src/views/Dashboard.vue`
  - `<script setup>`:
    - `import { useDashboardStore }`、`import { getDashboardToday }`（如需要直接调用，可不引入 API，store 已封装）
    - `import { onMounted, onActivated, onBeforeUnmount }` from 'vue'
    - `import { useRouter }` from 'vue-router'
    - `import { ElMessage }` from 'element-plus'
    - 实现 `refresh()` 函数：`store.fetch().catch(() => ElMessage.warning('刷新失败'))`
    - 实现 `goTo(path)` 函数：`router.push(path)`
    - 实现 `nFormatter(n)`：千分位显示（>=1000 用 1,234，否则原样）
    - 实现 `isPositive(n)`：`n > 0`
    - onMounted / onActivated：`store.fetch()`
    - onMounted：`document.addEventListener('visibilitychange', handler)`，`handler` 在 `!document.hidden` 时调用 `refresh()`
    - onBeforeUnmount：`document.removeEventListener('visibilitychange', handler)`
  - `<template>`:
    - 页头插槽 `right`：`<span class="dashboard-today">{{ store.today }}</span>` + `el-button @click="refresh" :loading="store.loading" plain`
    - summary 区：`el-row :gutter="16"` + 4 个 `el-col :span="6"`；每个 `MetricCard` 内联 = 卡片 + 大数字 + 标签
    - 三态切换：
      - `store.loading && !store.companies.length` → `<el-skeleton :rows="4" />`
      - `store.error && !store.companies.length` → error 卡片 + 重试按钮
      - `store.summary && store.summary.total === 0` → 空态卡片（✨ 今日无事 + [+ 新建任务]）
      - else → 渲染 summary + 公司表
    - 公司表：`el-table :data="store.companies" stripe`，5 列：公司（可点击 el-link 整格）/ 紧急 / 临期 / 尚早 / 合计；数字 `> 0` 用 `el-link type="primary" @click`，`= 0` 用 `el-text type="info"`
  - `<style scoped>`：与 `frontend/views/TaskList.vue` 同风格（padding / 圆角 / 卡片间距）
- [ ] **2.1.4** `frontend/.todo/dashboard.md` 本身（本文件，复盘已完成）

### 2.2 修改文件

- [ ] **2.2.1** `frontend/src/router/index.js`
  - import 增加 `import Dashboard from '../views/Dashboard.vue'`
  - `/` → Dashboard，`meta: { title: '今日概述' }`
  - 新增 `/tasks` → TaskList（同组件），`meta: { title: '任务管理' }`
  - 其余路由保持现状（`/tasks/today` / `/settings`）
- [ ] **2.2.2** `frontend/src/layouts/AppSidebar.vue`
  - import 增加 `DataAnalysis`
  - 删除原 `Bell` / 不需要的 icon 引用
  - navItems 改为 2 项：
    ```js
    const navItems = [
      { name: '今日概述', icon: DataAnalysis, to: '/' },
      { name: '任务管理', icon: List, to: '/tasks' }
    ]
    ```
  - `activeTo` 仍为 `route.path`；旧 `route.path === '/tasks/today'` / `'/settings'` 不会激活任何项，符合预期（无视觉回归）
- [ ] **2.2.3** `frontend/src/views/TaskList.vue`
  - 修改 `onRemindTodayChange`：把 `router.push('/')` 替换为 `router.push('/tasks')`，让原 `remind_today` 开关仍能跳到合法页面
  - 修改 `onRemoveFilter` 中 `route.push('/')` 为 `route.push('/tasks')`
  - 不动 store 业务逻辑
- [ ] **2.2.4** `frontend/src/layouts/AppLayout.vue`
  - 在 `<main class="app-main">` 内 `<router-view v-slot="{ Component }">` 改成 `keep-alive include="Dashboard"` 包裹，让 Dashboard 的 `onActivated` 生效
  - 即：
    ```html
    <router-view v-slot="{ Component }">
      <keep-alive include="Dashboard">
        <component :is="Component" />
      </keep-alive>
    </router-view>
    ```
  - 其余 layout 不动
- [ ] **2.2.5** `frontend/src/main.js`
  - 不需要改（如果原来没注册 `DataAnalysis` 图标则补 import）
- [ ] **2.2.6** `frontend/spec/README.md` — §2 索引加今日概述行（已写）

### 2.3 文件改动影响范围

| 类型 | 文件 |
|------|------|
| 新增 | 3 个：api/dashboard.js、stores/useDashboardStore.js、views/Dashboard.vue |
| 修改 | 4 个：router/index.js、layouts/AppSidebar.vue、layouts/AppLayout.vue、views/TaskList.vue |
| 文档 | 2 个：spec/dashboard.md（本轮已写）、spec/README.md（本轮已写） |

---

## Phase 3 — 手动 QA

> 按 `frontend/spec/dashboard.md` §4 的 18 条逐项验证。每一条勾 `[x]` 表示已通过。

- [ ] **QA1** 数据库为空时访问 `/` → 显示「今日无事」空态卡片
- [ ] **QA2** 数据库只有 completed 任务时访问 `/` → 显示「今日无事」
- [ ] **QA3** 一家公司有紧急任务时访问 `/` → summary 紧急 N=1；公司表只一行
- [ ] **QA4** 多家公司混合各档时访问 `/` → summary 各数字加和正确；公司表按后端排序
- [ ] **QA5** 点击 summary「紧急 5」→ 跳 `/tasks?status=pending`
- [ ] **QA6** 点击 summary「合计 12」→ 跳 `/tasks?remind_today=true`
- [ ] **QA7** 点击公司名「ACME」→ 跳 `/tasks?company_id=2`
- [ ] **QA8** 点击公司行某格非零数字 → 跳 `/tasks?company_id=2&status=pending`
- [ ] **QA9** 点击数字 = 0 的格 → 无反应，灰色
- [ ] **QA10** 在 `/tasks` 创建任务 → 返回 `/` → dashboard 自动刷新
- [ ] **QA11** 切到其他标签页 → 切回 → dashboard 自动刷新
- [ ] **QA12** 点击页头「刷新」→ loading → 新数据
- [ ] **QA13** 后端停掉访问 `/` → error 卡片 + [重试]
- [ ] **QA14** 后端 502 且已有 summary → toast「刷新失败」；旧数据继续
- [ ] **QA15** 侧边栏切换到「任务管理」→ 路由 /tasks；激活项切换
- [ ] **QA16** 浏览器后退从 /tasks 返回 / → 新数据可见
- [ ] **QA17** 浏览器宽度 < 1280px → 按既有逻辑给提示（不动）
- [ ] **QA18** 旧链接 #/tasks/today → 仍可达旧 TaskList；侧边栏无激活

---

## Phase 4 — 收尾

- [ ] **4.1** 代码 lint（如有 eslint 配置）：
  ```bash
  cd frontend
  npm run lint
  ```
- [ ] **4.2** 类型 check（无 TS，跳过）
- [ ] **4.3** 浏览器 DevTools 检查：
  - 路由变化时 `onActivated` 真的命中（Dashboard keep-alive 缓存）
  - `visibilitychange` 监听器 onUnmount 时被移除（无内存泄漏）
  - `error === null && loading === false` 时，2 处 ref 引用稳定，无不必要 re-render
- [ ] **4.4** 收尾更新本 Todo List 全 `[x]`
- [ ] **4.5** 与 README.md 同步：本模块不删除任何旧路由，README §4（功能模块）如有「今日待提醒」/「设置」描述需联动调整

---

## 验证清单（每 PR）

- [ ] `npm run dev` 启动开发服务器
- [ ] 18 条手动 QA 全过
- [ ] `npm run build` 构建产物可用（`dist/` 含 Dashboard chunk）
- [ ] `frontend/spec/README.md` §2 索引含「今日概述」
- [ ] `backend/.todo/dashboard.md` 不与本文件冲突（路径 `frontend/.todo/` 互不影响）

---

## 与既有文件的关系

| 既有文件 | 本模块对其的影响 |
|---------|-------------|
| `backend/openapi/dashboard.json` | 仅作为契约来源，不修改 |
| `backend/spec/dashboard.md` | 仅作为契约来源，不修改 |
| `frontend/spec/README.md` §2 索引新增一行 |
| `frontend/spec/task_management.md` | 不修改；但 TaskList.vue 路径调整会影响其路由示例注释（如有） |
| `frontend/spec/company_project.md` | 不修改 |
| `frontend/src/views/Settings.vue` | 不修改；路由 `/settings` 保留可达但侧边栏不再显示 |

---

## 不在本轮范围

- 删除 `/tasks/today` / `/settings` 路由（用户明确不删）
- 删除后端 `remind_today` API 参数（属后端专项）
- 删除 TaskList 内 remind_today 业务逻辑（只把跳转路径改为 `/tasks`）
- 引入 vitest / jest 等前端单元测试
- 三档严格钻取（v0.2 由后端扩 `/api/tasks?bucket=`）
- WebSocket / 轮询
- 移动端适配

详见 `frontend/spec/dashboard.md` §5 范围声明。
