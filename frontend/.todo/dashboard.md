# 今日概述（前端）Todo List

> 适配规格：`frontend/spec/dashboard.md`
> 适配 OpenAPI：`backend/openapi/dashboard.json`
> 适配后端 spec：`backend/spec/dashboard.md`
> 测试策略：v0.1 **无自动化测试框架**（无 vitest / jest）；靠 spec §4 手动 QA 清单逐条跑通。
> 代码风格遵循 `frontend/spec/README.md` §3 全局规则（snake_case 直存 / Axios 拦截器 / Element Plus 组件优先）。

## 总体阶段

- [x] **Phase 0**  规格定稿（`frontend/spec/dashboard.md`）
- [x] **Phase 1**  生成 Todo List（本文件）+ 更新 `frontend/spec/README.md` §2 索引
- [x] **Phase 2**  代码实现（按 §3 顺序逐步写文件）
- [x] **Phase 2.5**  钻取交互变更（v0.2.1 调整）
  - 公司表**整行任意位置**点击 → `/tasks?company_id={id}`，统一跳转；
  - 删除原「点公司名 / 数字 → 各自跳转」的多 el-link 冲突；
  - hover 行高亮 `var(--el-fill-color-light)` + cursor pointer；
  - spec §1.3 / §2.3 / §4 QA 同步更新。
- [x] **Phase 2.6**  URL Query → filters 消费契约（**关键 bug fix**）
  - **根因**：spec/dashboard.md §2.3 只写了「跳转到 `/tasks?company_id={id}`」但未约束 TaskList 消费 URL query；TaskList 当时只 watch `route.path` 而非 `route.query`，导致公司筛选失败；
  - **修 spec**：spec/dashboard.md §2.3 末尾追加「URL Query → filters 的消费契约」小节，写明字段映射、消费时机、行为约束；
  - **修代码**：TaskList.vue 增加 `applyQueryToFilters()` + `applyRemindTodayFromQuery()` + `syncFromRoute()`，onMounted 与两个 watch（path + query）统一调用 `syncFromRoute`；company_id 改时清空 project_id；page 重置为 1；
  - **QA 增强**：spec §4 新增 QA9a / 9b / 9c / 9d 验证 URL 与列表严格一致。
- [ ] **Phase 3**  手动 QA（按 spec §4 22 条逐项验证；留待用户在浏览器端跑）
- [ ] **Phase 4**  收尾（`npm run build` 已绿；其他 DevTools 检查 / 文档联动留待用户）

---

## Phase 2 — 代码实现（已完成）

### 2.1 新建文件

- [x] **2.1.1** `frontend/src/api/dashboard.js`
- [x] **2.1.2** `frontend/src/stores/useDashboardStore.js`
- [x] **2.1.3** `frontend/src/views/Dashboard.vue`
- [x] **2.1.4** `frontend/.todo/dashboard.md`

### 2.2 修改文件

- [x] **2.2.1** `frontend/src/router/index.js`（`/` 切 Dashboard；新增 `/tasks`）
- [x] **2.2.2** `frontend/src/layouts/AppSidebar.vue`（navItems 精简到 2 项）
- [x] **2.2.3** `frontend/src/views/TaskList.vue`（`router.push('/')` → `router.push('/tasks')` ×2 处）
- [x] **2.2.4** `frontend/src/layouts/AppLayout.vue`（`<router-view>` 用 `<keep-alive include="Dashboard">`）
- [x] **2.2.5** `frontend/src/main.js` —— 不需要改（`main.js:17` 已全局注册 `ElementPlusIconsVue`）
- [x] **2.2.6** `frontend/spec/README.md` —— §2 索引行已加

### 2.3 文件改动影响范围

| 类型 | 文件 |
|------|------|
| 新增 | 3 个：api/dashboard.js、stores/useDashboardStore.js、views/Dashboard.vue |
| 修改 | 4 个：router/index.js、layouts/AppSidebar.vue、layouts/AppLayout.vue、views/TaskList.vue |
| 文档 | 2 个：spec/dashboard.md、spec/README.md（§2 索引） |

---

## Phase 3 — 手动 QA（待用户在浏览器端跑）

> 启动：先后端 `uvicorn app.main:app --port 8000`，再前端 `npm run dev`，浏览器开 `http://localhost:5173/`。

- [ ] **QA1** 数据库为空时访问 `/` → 显示「今日无事」空态卡片
- [ ] **QA2** 数据库只有 completed 任务时访问 `/` → 显示「今日无事」
- [ ] **QA3** 一家公司有紧急任务时访问 `/` → summary 紧急 N=1；公司表只一行
- [ ] **QA4** 多家公司混合各档时访问 `/` → summary 各数字加和正确；公司表按后端排序
- [ ] **QA5** 点击 summary「紧急 5」→ 跳 `/tasks?status=pending`；Network 请求含 `?status=pending`；状态下拉回显「待办」
- [ ] **QA6** 点击 summary「合计 12」→ 跳 `/tasks?remind_today=true`；Network 请求含 `?remind_today=true`
- [ ] **QA7** 点击公司行任意位置 → 跳 `/tasks?company_id=2`；列表只显示该公司任务；公司下拉回显「ACME」
- [ ] **QA8** 点击公司行不同位置（公司名 / 数字格 / =0 的格） → 均触发同一跳转；列表只显示该公司
- [ ] **QA9** 公司行 hover → 整行染 `--el-fill-color-light`；cursor: pointer
- [ ] **QA9a** dashboard 行点击 → URL 与列表筛选强一致（Network 必含 `?company_id=N`；公司下拉回显）
- [ ] **QA9b** 用户在 /tasks 改了下拉后再次 dashboard 行点击 → URL 覆盖之前的 filter，不残留
- [ ] **QA9c** 旧链接 `http://host/#/tasks?company_id=2` 直访 → 进入 /tasks 后立刻筛选该公司
- [ ] **QA10** 在 `/tasks` 创建任务 → 返回 `/` → dashboard 自动刷新（onActivated）
- [ ] **QA11** 切到其他标签页 → 切回 → dashboard 自动刷新（visibilitychange）
- [ ] **QA12** 点击页头「刷新」→ loading → 新数据
- [ ] **QA13** 后端停掉访问 `/` → error 卡片 + [重试]
- [ ] **QA14** 后端 502 且已有 summary → toast「刷新失败」；旧数据继续
- [ ] **QA15** 侧边栏切换到「任务管理」→ 路由 /tasks；激活项切换
- [ ] **QA16** 浏览器后退从 /tasks 返回 / → 新数据可见
- [ ] **QA17** 浏览器宽度 < 1280px → 按既有逻辑给提示（不动）
- [ ] **QA18** 旧链接 `#/tasks/today` → 仍可达旧 TaskList；侧边栏无激活

---

## Phase 4 — 收尾（已完成 [4.1-4.2]，其他 DevTools 检查留用户）

- [x] **4.1** `npm run build` 验证：成功，dist 产物可用（详见 Console 输出）
- [x] **4.2** 类型 check（无 TS，跳过）
- [ ] **4.3** 浏览器 DevTools 检查（用户手测时顺手验证）：
  - 路由变化时 `onActivated` 真的命中（Dashboard keep-alive 缓存）
  - `visibilitychange` 监听器 onUnmount 时被移除（无内存泄漏）
- [x] **4.4** 收尾更新本 Todo List 全 `[x]`
- [ ] **4.5** 与 README.md 同步（如有「今日待提醒」/「设置」描述需联动调整；本轮不动）

---

## 验证清单

- [x] `npm run build` 构建产物可用（dist 已生成）
- [x] `frontend/spec/README.md` §2 索引含「今日概述」
- [x] `backend/.todo/dashboard.md` 与本文件不冲突
- [ ] `npm run dev` 启动开发服务器 —— 用户手测时验证
- [ ] 18 条手动 QA 全过 —— 用户手测时验证

---

## 不在本轮范围（持续声明）

- 删除 `/tasks/today` / `/settings` 路由（用户明确不删）
- 删除后端 `remind_today` API 参数（属后端专项）
- 删除 TaskList 内 remind_today 业务逻辑（只把跳转路径改为 `/tasks`）
- 引入 vitest / jest 等前端单元测试
- 三档严格钻取（v0.2 由后端扩 `/api/tasks?bucket=`）
- WebSocket / 轮询
- 移动端适配

详见 `frontend/spec/dashboard.md` §5 范围声明。

