# 今日概述模块规格（前端）

> 适配 OpenAPI：[../../backend/openapi/dashboard.json](../../backend/openapi/dashboard.json)（路径 `/api/dashboard/today`、schema `DashboardTodayResponse` / `DashboardSummary` / `DashboardCompanyCount`）
> 适配后端 spec：[../../backend/spec/dashboard.md](../../backend/spec/dashboard.md)
> 页面入口：`views/Dashboard.vue`（路由 `/`）
> 全局规则遵循 [./README.md](./README.md)；本文档只描述本模块特有的页面拆解、功能点交互与测试案例。

---

## 1. 整体页面结构拆解

### 1.1 路由与视图

| 路径 | 视图 | 侧边栏激活项 | `meta.title` | 说明 |
|------|------|------------|--------------|------|
| `/` | `views/Dashboard.vue` | 今日概述 | 今日概述 | 主页：按公司统计紧急 / 临期 / 尚早 |
| `/tasks` | `views/TaskList.vue` | 任务管理 | 任务管理 | 任务列表（默认全部状态） |

> **既有路由保留**：旧路径 `/tasks/today` 与 `/settings` 路由仍可达（保持历史链接兼容），但不在本模块的侧边栏导航中出现。本模块**不**做删除操作，清理动作另行专项。

### 1.2 侧边栏

| 顺序 | 名称 | icon | to |
|------|------|------|----|
| 1 | 今日概述 | `DataAnalysis` | `/` |
| 2 | 任务管理 | `List` | `/tasks` |

> - 图标全部走 `@element-plus/icons-vue`，按需 import；
> - 激活态判断为 `route.path === item.to`；
> - 样式遵循 [README §5.2](./README.md#52-布局)：左 3px 主色竖条 + 浅主色背景 `#ecf5ff` + 文字主色 `#409eff`。

### 1.3 主页 DOM 结构

布局遵循 [README §5.2](./README.md#52-布局)：左 220px 导航 + 右侧 56px 页面页头 + 主内容区。

```
<AppLayout>
  <AppSidebar>                          ← 220px 固定（仅 2 项，详见 §1.2）
    ├─ Logo 区（64px）：⚡ SparkMemo
    └─ 导航项（44px × 2，间距 4px）
         - 今日概述  (icon: DataAnalysis)
         - 任务管理  (icon: List)
  </AppSidebar>
  <AppPage>                             ← 右侧容器
    <AppHeader>                         ← 56px 页面页头
      ├─ 左：<h1>{{ route.meta.title }}</h1>
      └─ 右 slot="right"：
            <span class="today">{{ store.today }}</span>
            <el-button @click="refresh" :loading="store.loading">
              刷新
            </el-button>
    </AppHeader>
    <AppMain>                           ← max-width 1440px, padding 16 24
      <DashboardView>
        ┌─ Summary 卡片 ─────────────────────────────┐
        │ <el-row :gutter="16">
        │   <MetricCard label="紧急"   :value="summary.urgent"   />
        │   <MetricCard label="临期"   :value="summary.due_soon" />
        │   <MetricCard label="尚早"   :value="summary.early"    />
        │   <MetricCard label="合计"   :value="summary.total"    />
        │ </el-row>                                  │
        │   N >= 1 → el-link type="primary" 可点击   │
        │   N == 0 → el-text type="info"  灰色不点击 │
        └────────────────────────────────────────────┘
        ┌─ 公司表 ───────────────────────────────────┐
        │ <el-table                                │
        │     @row-click="onRowClick"               │
        │     row-class-name 标识可点击 hover 高亮>  │
        │   列：公司 / 紧急 / 临期 / 尚早 / 合计    │
        │   整行任意位置点击 → router.push(         │
        │     /tasks?company_id={company_id})       │
        │   数字 > 0: 主色（非链接，仅视觉强调）    │
        │   数字 = 0: 灰色 el-text                  │
        └────────────────────────────────────────────┘
        ┌─ 空态（仅 summary.total === 0） ──────────┐
        │ ✨ 今日无事                                │
        │ 当前没有需要处理的任务提醒。                │
        │ [+ 新建任务]  → router.push('/tasks')      │
        └────────────────────────────────────────────┘
        ┌─ 加载中（store.loading 且首屏） ──────────┐
        │ <el-skeleton :rows="4" />                  │
        └────────────────────────────────────────────┘
        ┌─ 加载失败（store.error 且无旧数据） ────────┐
        │ 加载失败                                   │
        │ [重试]                                     │
        └────────────────────────────────────────────┘
      </DashboardView>
    </AppMain>
  </AppPage>
</AppLayout>

浮层：无（Dashboard 只读，不弹任何 modal / drawer）
```

### 1.4 组件 / store / API 清单

| 类型 | 名称 | 职责 |
|------|------|------|
| View | `views/Dashboard.vue` | 主页骨架；含 summary 区、公司表、空态、加载 / 错误三态切换 |
| Store | `stores/useDashboardStore.js` | `today` / `summary` / `companies` / `loading` / `error` 状态 + `fetch()` action |
| API | `api/dashboard.js` | `getDashboardToday()` 单函数 |
| （依赖）| `api/client.js` | axios 实例与 ApiError；与既有共用 |
| （依赖）| `router/index.js` | `/` → Dashboard；新增 `/tasks` 走 TaskList |
| （依赖）| `layouts/AppSidebar.vue` | navItems 调整（顺序与 to）；删除不再使用的 nav 项 |
| （依赖）| `layouts/AppLayout.vue` | `<router-view>` 用 `<keep-alive include="Dashboard">` 包裹，让 `onActivated` 生效 |

无新增公共组件；`MetricCard` 内联在 `Dashboard.vue` 里（结构简单，不拆 component；如未来页内复用再抽）。

### 1.5 状态机

无状态机；Dashboard 只读展示，所有数据来自后端聚合接口。

---

## 2. 页面的功能点

### 2.1 功能点：进入主页（首次加载）

#### 入口
- 浏览器访问 `/`；
- 侧边栏点击「今日概述」。

#### 静态展示规则
- 页头左侧显示「今日概述」；右侧显示 `store.today` 与「刷新」按钮；
- Summary 区：4 个 metric 卡片，水平排列（`el-row :gutter="16"` + `el-col :span="6"`），卡片内容 `数字（大字 24px） + 标签（14px 次要色）`；
- 公司表：`<el-table :data="store.companies" stripe>`，5 列；列宽：`公司 min-width="180"`，其余各 `width="120"`；行高 44px；空数据时显示标准 `el-table` empty；
- 当 `summary.total === 0` 时，公司表**不渲染**，主区域替换为空态卡片；
- 当首屏 `store.loading === true` 且 `store.companies.length === 0` 时渲染 `<el-skeleton :rows="4" />`，其他元素不渲染。

#### 交互逻辑：首次加载

| 阶段 | 内容 |
|------|------|
| 操作前 | 路由切换完成，组件 mount |
| 触发动作 | `Dashboard.onMounted` → `dashboardStore.fetch()` |
| 接口请求 | `GET /api/dashboard/today` |
| 成功逻辑 | store 写入 `today` / `summary` / `companies`；UI 渲染对应区块 |
| 失败逻辑 | `error = msg`；UI 显示 error 区（不替换主内容），保留上次数据可视化（旧数据为空时显示「加载失败 [重试]」按钮） |

### 2.2 功能点：刷新

#### 入口
- 页头「🔄 刷新」按钮（el-button，size="small"，plain）；
- 路由切换：从 `/tasks` 回到 `/` 时，`onActivated` 钩子被命中（keep-alive 生效）；
- 浏览器标签页从隐藏切回可见：`document.visibilitychange` 事件触发。

#### 交互逻辑

| 触发 | 动作 |
|------|------|
| `onMounted` | `dashboardStore.fetch()` |
| 路由从 `/tasks` 回到 `/` | `onActivated`（keep-alive 命中）触发 `store.fetch()` |
| `visibilitychange → !document.hidden` | `store.fetch()` |
| 页头「刷新」按钮 `@click="refresh"` | `store.fetch()` |

- 刷新期间按钮 `disabled` + `loading`；
- fetch 失败不重试，弹 `ElMessage.warning('刷新失败')`，保留旧数据可视化；
- `onMounted` 时**注册** `visibilitychange` 监听；`onBeforeUnmount` 时**移除**（避免内存泄漏）。

### 2.3 功能点：钻取到任务列表（coarse-grained）

#### 入口
- summary 卡片数字（`> 0`）点击；
- 公司表**整行任意位置**点击（最简化交互）。

#### 跳转规则

| 点击位置 | 跳转到 | 说明 |
|---------|-------|------|
| summary「紧急 N」「临期 N」「尚早 N」（N > 0） | `/tasks?status=pending` | 全局待办 |
| summary「合计 N」（N > 0） | `/tasks?remind_today=true` | 全局提醒区间内任务 |
| 公司表**整行任意位置**（row-click） | `/tasks?company_id={company_id}` | 该公司全部任务 |
| 公司表内任何单元格 / 公司名 / 数字格 | 同上：整行行为统一 | 不再有「数字 → 公司+pending」分支 |

#### 不再有的旧行为
- ~~公司行某格 `> 0` → `/tasks?company_id={id}&status=pending`~~
- 这一钻取分支已合并到「整行 → company_id」，与 coarse-grained 简化方案一致。

#### 视觉提示
- 公司表行 `cursor: pointer`，hover 时整行染上 Element Plus 主色浅背景（`--el-fill-color-light`）；
- 公司名 cell 仍是主色文本，但**仅是视觉强调，不响应点击**（点击会冒泡到行）；
- 数字 `> 0` 时仍是主色，`= 0` 时灰色 `el-text` —— 都是文本，不再是 link。

#### Coarse-grained 限制说明
> 任务列表 API `/api/tasks` 当前不区分「紧急 / 临期 / 尚早」三档语义。本 spec 内的钻取粒度最大为「该公司全部任务」或「全局待办 / 全局提醒」，不展示严格三档子集。**v0.2 由后端扩展 `/api/tasks?bucket=urgent|due_soon|early` 参数**，配合本前端做精细化筛选。

#### URL Query → filters 的消费契约（**关键，遗漏会导致筛选失效**）

跳转 URL 是表达「筛选意图」的唯一通道，TaskList 视图**必须**消费 `route.query` 并写回 `taskStore.filters`：

| Query 字段 | 落到 `taskStore.filters` | 类型 | 默认 |
|-----------|-------------------------|------|------|
| `company_id` | `filters.company_id` | `number \| null` | `null` |
| `project_id` | `filters.project_id` | `number \| null` | `null` |
| `task_type_id` | `filters.task_type_id` | `number \| null` | `null` |
| `status` | `filters.status` | `string` | `''` |
| `remind_today` | `filters.remind_today` | `boolean` | 见下 |

消费时机（**两处都要**）：

1. **`onMounted` 时**：组件挂载完成后立即读取 `route.query` 全量写回 store，然后 `fetchList()`；
2. **`watch(() => route.query)`**：当 query 变化（包括 user 在 filter UI 中触发的路由跳转、或外部 dashboard 钻取），再次把 query 写回 store 后 `fetchList()`。

行为约束：

- **query 全量接管**：从 query 写回的字段视为本次会话的初始 filters；用户后续手动修改下拉框时**不再回写 URL**（v0.1 故意不做双向，避免循环依赖；后续 v0.2 可加）；
- **`remind_today` 由 `meta.remindToday` 与 `query.remind_today` 共同决定**：只要任一为 `true / 'true'` 即视为开启；这是 dashboard summary「合计 → `?remind_today=true`」能正确生效的必要条件；
- **副作用**：当 `query.company_id` 改动时，`query.project_id` 与 `store.filters.project_id` 自动置空（与现有 `onCompanyFilterChange` 同语义），避免旧项目 id 跨公司残留；
- **page 重置**：query 变化时 `filters.page = 1`，避免翻页状态跨场景残留；
- **空值约定**：query 字段缺省 / 为空字符串 / 为 `null` 时视为未传，落到 filter 的默认值（`null` / `''` / `false`）。

> **未实现的边界**（v0.2 再议）：dashboard 钻取时 query 不携带 `due_from` / `due_to` / `keyword` / `page` / `size`；这些仍由用户在 TaskList 内手动控制。

### 2.4 功能点：空态（`summary.total === 0`）

#### 静态展示
- 主区域替换为单卡片，居中显示；
- 主文案：`✨ 今日无事`（emoji 不渲染，使用 `el-icon` 占位或纯文本「今日无事」）；
- 副文案：`当前没有需要处理的任务提醒。`；
- 按钮：`+ 新建任务`，点击 → `router.push('/tasks')`；
- 卡片高度 ≈ 200px，纵向居中。

#### 何时显示
仅当 `store.summary && store.summary.total === 0` 时显示；任一时刻不与 summary 区同时显示。

### 2.5 功能点：加载与错误三态

| 状态 | 条件 | UI 渲染 |
|------|------|--------|
| 加载中（首屏） | `store.loading === true` 且 `!store.companies.length` | 全区 `<el-skeleton :rows="4" />` |
| 加载成功 | `store.error === null` 且 `!loading` | 正常 summary + 公司表（或空态卡片） |
| 加载失败（无旧数据） | `store.error !== null` 且 `!store.companies.length` | error 卡片含「加载失败 [重试]」按钮 |
| 加载失败（有旧数据） | `store.error !== null` 且 `store.companies.length > 0` | 仍渲染上次数据；toast `ElMessage.warning('刷新失败')`；error 区不替换主内容 |

> 「重试」按钮 `@click="refresh"` 等价于页头刷新按钮，逻辑统一走 `store.fetch()`。

---

## 3. 字段契约（与 OpenAPI 对齐）

`useDashboardStore` state 与 OpenAPI schema 字段**完全 snake_case 直存**，中间不转换。

| State 字段 | OpenAPI 字段 | 类型 | 含义 |
|----------|------------|------|------|
| `today` | `today` | `string YYYY-MM-DD` | 服务端今天（来自 `services.scheduler.get_today()`） |
| `summary.urgent` | `summary.urgent` | `int` | 全局紧急任务数 |
| `summary.due_soon` | `summary.due_soon` | `int` | 全局临期任务数 |
| `summary.early` | `summary.early` | `int` | 全局尚早任务数 |
| `summary.total` | `summary.total` | `int` | 三档合计（与 companies[] 求和一致） |
| `companies[i].company_id` | `companies[].company_id` | `int` | 公司主键 |
| `companies[i].company_name` | `companies[].company_name` | `string` | 公司名 |
| `companies[i].urgent` | `companies[].urgent` | `int` | 该公司紧急任务数 |
| `companies[i].due_soon` | `companies[].due_soon` | `int` | 该公司临期任务数 |
| `companies[i].early` | `companies[].early` | `int` | 该公司尚早任务数 |
| `companies[i].total` | `companies[].total` | `int` | 该公司三档合计 |
| `loading` | — | `boolean` | UI 状态字段（不与后端对齐） |
| `error` | — | `string \| null` | UI 状态字段（不与后端对齐） |

> **空响应兜底**：`companies` 缺省写 `[]`；`summary` 缺省写 `{ urgent: 0, due_soon: 0, early: 0, total: 0 }`；写入前对 `res` 做 `|| {}` / `|| []` 防御。

---

## 4. 手动 QA 清单

> 前端 v0.1 不引入 vitest / jest，本模块靠手动 QA 验证。下列为开发自测与产品验收的统一基线。

| # | 场景 | 期望 |
|---|------|------|
| 1 | 数据库为空时访问 `/` | 显示「今日无事」空态卡片 |
| 2 | 数据库只有 `completed` 任务时访问 `/` | 显示「今日无事」（summary.total === 0） |
| 3 | 一家公司有紧急任务时访问 `/` | summary 紧急卡片 N=1；公司表只一行，三档分布正确 |
| 4 | 多家公司混合各档时访问 `/` | summary 各数字加和正确；公司表按后端 `total DESC, urgent DESC, name ASC` 排序展示 |
| 5 | 点击 summary「紧急 5」 | 跳转到 `/tasks?status=pending`；列表区状态选 `pending` |
| 6 | 点击 summary「合计 12」 | 跳转到 `/tasks?remind_today=true`；列表区显示提醒区间内任务 |
| 7 | 点击公司名「ACME」/ 点击公司行任意位置 | 跳转到 `/tasks?company_id=2`；整行 hover 高亮；**列表区筛选该公司的任务**（公司下拉值 = 「ACME」） |
| 8 | 点击公司行不同位置（公司名格、紧急格、数字=0格） | 均触发同一跳转 `/tasks?company_id=2`（row-click 统一）；列表只显示该公司任务 |
| 9 | 公司行 hover | 整行染 `--el-fill-color-light`；cursor: pointer |
| 9a | dashboard 行点击 → /tasks?company_id=N 后 URL 与列表筛选**强一致** | Network 请求含 `?company_id=N`；公司下拉回显选项；列表只显示该公司任务 |
| 9b | dashboard summary「紧急」点击 → /tasks?status=pending | Network 请求含 `?status=pending`；状态下拉回显「待办」 |
| 9c | dashboard summary「合计」点击 → /tasks?remind_today=true | Network 请求含 `?remind_today=true` |
| 9d | 用户在 /tasks 改了下拉后再次 dashboard 行点击 | **不**保留用户上次设置；按新 URL query 重新覆盖 filters |
| 10 | 在 `/tasks` 创建任务 → 返回 `/` | dashboard 因 `onActivated` 自动刷新；新任务出现在合适档位 |
| 11 | 切到其他标签页 → 切回 | `visibilitychange` 触发刷新 |
| 12 | 点击页头「刷新」 | 按钮短暂 `loading`；`store.fetch()`；再次拿到新数据 |
| 13 | 后端停掉，访问 `/` | error 卡片显示「加载失败 [重试]」；点击重试再次请求 |
| 14 | 后端 502 且已有 summary 渲染 | `ElMessage.warning('刷新失败')`；旧数据继续展示；error 区不替换主内容 |
| 15 | 侧边栏切换到「任务管理」 | 路由 `/tasks`；激活项切换；Dashboard 不重渲染（仍在 keep-alive 缓存中） |
| 16 | 浏览器后退从 `/tasks` 返回 `/` | `onActivated` 触发；新数据可见 |
| 17 | 浏览器宽度 < 1280px | 按 [README §3.6](./README.md#36-兼容要求) 给提示（既有逻辑不动） |
| 18 | 旧链接 `#/tasks/today`（hash 直访） | 仍可达旧 TaskList 路由；侧边栏无激活项；本模块不保证视觉效果一致 |

---

## 5. 范围声明

### 在范围内（本模块实现）
- 新建 `views/Dashboard.vue`（主页）；
- 路由迁移：`/` 切到 Dashboard；新增 `/tasks` 用 TaskList；
- 侧边栏 `navItems` 顺序与 to 路径调整（精简到 2 项）；
- `useDashboardStore` / `api/dashboard.js` 新建；
- drill-down 到 `/tasks`（coarse-grained）；
- 3 种刷新策略：`onMounted` / `onActivated` / `visibilitychange`；
- 「今日无事」空态；
- 加载中 / 加载失败（重试）三态；
- 手动 QA 清单（§4）。

### 不在本模块范围（与本次 dashboard 同步声明）
- **不**删除任何既有路由（`/tasks/today` / `/settings` 保留可达）；
- **不**改后端 `remind_today` API（`GET /api/tasks?remind_today=true` 仍可用；本模块 dashboard 钻取会用其 coarse-grained 形式）；
- **不**改 `TaskList.vue` 内 remind_today 业务逻辑；仅在 `onRemindTodayChange` 函数体里把 `router.push('/')` 替换为 `router.push('/tasks')`，让原 `remind_today` 开关仍能跳到一个合法页面；
- **不**做后端 `remind_today` 参数语义清理（属其他专项）。

### v0.2+ 演进项（不在本轮）
- 三档严格钻取：需后端在 `/api/tasks` 加 `bucket=urgent|due_soon|early` 参数；
- WebSocket 推送 / 定时轮询 / `setInterval` 自动刷新；
- 「昨天 vs 今天」「任意日期范围」对比视图；
- 「点击公司名进入公司详情」专页（用新 CompanyCRUD 表替代）；
- 国际化（仍仅中文）；
- 移动端适配（v0.1 桌面 ≥ 1280px）。

---

## 6. 关联文档

| 文档 | 位置 |
|------|------|
| 前端全局规则 | [./README.md](./README.md) |
| 后端模块 spec | [../../backend/spec/dashboard.md](../../backend/spec/dashboard.md) |
| OpenAPI 接口契约 | [../../backend/openapi/dashboard.json](../../backend/openapi/dashboard.json) |
