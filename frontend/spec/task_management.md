# 任务管理模块规格

> 适配 OpenAPI：[../../backend/openapi/task_management.json](../../backend/openapi/task_management.json)
> 适配后端 spec：[../../backend/spec/task_management.md](../../backend/spec/task_management.md)
> 页面入口：`views/TaskList.vue`
> 全局规则遵循 [./README.md](./README.md)，本文档只描述本模块特有的页面拆解、功能点交互与测试案例。

---

## 1. 整体页面结构拆解

### 1.1 路由与视图

| 路径 | 视图 | 说明 |
|------|------|------|
| `/` | `views/TaskList.vue` | 任务列表（默认全部状态） |
| `/tasks/today` | `views/TaskList.vue` | 任务列表（仅今日待提醒） |
| `/settings` | `views/Settings.vue` | 占位页，不在本规格范围 |

> 两个路由共用同一视图，靠路由 meta 决定初始 filters（`remind_today` / `status`）。

### 1.2 主页 DOM 结构

```
<el-container>
  <el-header />                 ← App.vue 顶部 Header
  <el-main>
    <TaskListView>
      ┌─ 筛选条 ─────────────────────────────────────┐
      │ [公司] [项目] [类型] [状态] [关键词] [今日开关]│
      │ [重置]                          [+ 新建任务]  │
      │                                            [管理类型] │
      └────────────────────────────────────────────┘
      ┌─ 列表区 ─────────────────────────────────────┐
      │ <el-table>                                  │
      │   列：title / type / company / project /     │
      │        due_at / remind_start_at / status /   │
      │        操作（编辑 / 完成 / 删除）            │
      └────────────────────────────────────────────┘
      ┌─ 分页器 ─────────────────────────────────────┐
      │ <el-pagination total / sizes / pager />      │
      └────────────────────────────────────────────┘
    </TaskListView>
  </el-main>
</el-container>

<!-- 浮层（按需挂载，单实例） -->
<el-drawer>      ← TaskForm（新建 / 编辑）
<el-dialog>      ← TypeManager（任务类型管理）
<ElMessageBox>   ← 危险操作二次确认
```

### 1.3 模块涉及组件与 store

| 类型 | 名称 | 职责 |
|------|------|------|
| View | `views/TaskList.vue` | 主页骨架，组合筛选条 / 列表 / 分页器，承载浮层 |
| Component | `components/TaskForm.vue` | 任务新建 / 编辑表单（抽屉承载） |
| Component | `components/TaskItem.vue` | 行内展示（实际由 `<el-table>` 列模板承担；保留作可复用行组件） |
| Component | `components/ReminderChips.vue` | 编辑模式下展示 `task.reminders` |
| Component | `components/TypeManager.vue` | 任务类型 CRUD（弹窗承载） |
| Store | `stores/useTaskStore.js` | 任务列表 / 详情 / 筛选状态 |
| Store | `stores/useTypeStore.js` | 任务类型全量字典 |
| Store | `stores/useCompanyStore.js` | 公司全量字典（供下拉） |
| Store | `stores/useProjectStore.js` | 项目列表 + 按公司分组 |
| API | `api/tasks.js` / `api/taskTypes.js` / `api/companies.js` / `api/projects.js` / `api/client.js` | axios 实例与按域函数 |

### 1.4 状态机

```
         用户点击「完成」POST /api/tasks/{id}/complete
pending ─────────────────────────────────────────►  completed
   │
   │  截止日 ≤ 今天 - 3 天（后端 APScheduler 自动）
   ▼
overdue_done
```

- `pending → completed`：用户主动；
- `pending → overdue_done`：后端 Job 自动，前端只读；
- `completed` 与 `overdue_done` 之间不互通；不提供 reopen。

UI 操作可见性：

| 当前状态 | 编辑 | 完成 | 删除 |
|---------|-----|-----|-----|
| `pending` | ✓ | ✓ | ✓ |
| `completed` | 灰 | — | ✓ |
| `overdue_done` | 灰 | — | ✓ |

---

## 2. 页面的功能点

### 2.1 功能点：进入主页（任务列表）

#### 入口
- 浏览器访问 `/` 或 `/tasks/today`；
- 顶部 Header 中部 tab 切换：「全部 / 今日待提醒」。

#### 静态展示规则
- 标题：左侧「SparkMemo」Logo，右侧「设置」入口（占位）；
- 筛选条：默认全部为空；「今日待提醒」开关默认关（`/`）或开（`/tasks/today`）；
- 列表列：`title / 类型 / 公司 / 项目 / 截止日 / 提醒起 / 状态 / 操作`；
- 状态列：按 [README §3.5.1](./README.md) 颜色映射；
- 分页器：每页条数默认 20；无数据时显示「暂无数据」占位；
- 操作列：编辑 / 完成 / 删除按钮按状态可见性规则显示。

#### 交互逻辑：首次加载

| 阶段 | 内容 |
|------|------|
| 操作前 | 路由切换完成，组件已 mount |
| 触发动作 | `App.vue` 的 `onMounted` 并行触发 3 个字典加载 + `useTaskStore.fetchList()` |
| 接口请求 | `GET /api/task-types`<br>`GET /api/companies`<br>`GET /api/projects`<br>`GET /api/tasks?page=1&size=20`（`/tasks/today` 时附加 `&remind_today=true&status=pending`） |
| 成功逻辑 | store 写入 `types / companies / projects / tasks / total`；列表与分页器渲染；筛选条下拉数据源就绪 |
| 失败逻辑 | 字典加载失败 → toast + 筛选条下拉为空（仍可提交，等用户手动触发）；列表加载失败 → toast + 列表区显示「加载失败，点此重试」 |

---

### 2.2 功能点：筛选条件变化

#### 入口
- 筛选条中任一控件：`<el-select>` 公司 / 项目 / 类型 / 状态、`<el-input>` 关键词、`<el-switch>` 今日待提醒。

#### 静态展示规则
- 关键词输入框宽度 200px，含清空按钮；
- 公司 → 项目下拉联动：公司变化后项目下拉清空并按新公司重新拉取；
- 「今日待提醒」开关打开时自动锁定 `status=pending` 并禁用状态下拉。

#### 交互逻辑：单个筛选条件变化

| 阶段 | 内容 |
|------|------|
| 操作前 | 当前筛选条件已生效，列表已渲染 |
| 触发动作 | 修改任一筛选字段 |
| 接口请求 | 关键词：`debounce 300ms` 后；其余立即：`GET /api/tasks?{filters}&page=1&size=20` |
| 成功逻辑 | `useTaskStore.tasks` 与 `total` 替换；分页器回到第 1 页 |
| 失败逻辑 | toast「加载失败」+ 保留旧列表与旧筛选条件 |

#### 交互逻辑：「今日待提醒」开关

| 阶段 | 内容 |
|------|------|
| 操作前 | 开关任意状态 |
| 触发动作 | 切换开关 |
| 接口请求 | 开 → `GET /api/tasks?remind_today=true&status=pending&page=1&size=20`<br>关 → `GET /api/tasks?remind_today=false&{其它筛选}&page=1&size=20`（`status` 恢复用户先前选择） |
| 成功逻辑 | 列表更新；URL hash 不变（hash 路由不持久化查询参数） |
| 失败逻辑 | 开关回弹 + toast |

---

### 2.3 功能点：翻页 / 改每页条数

#### 入口
- 列表底部 `<el-pagination>`。

#### 静态展示规则
- `layout="total, sizes, prev, pager, next, jumper"`；
- 每页条数选项 `[10, 20, 50]`；
- 总数显示「共 N 条」。

#### 交互逻辑：翻页

| 阶段 | 内容 |
|------|------|
| 操作前 | 当前页已加载 |
| 触发动作 | 点击页码 / next / prev / jumper |
| 接口请求 | `GET /api/tasks?{filters}&page={newPage}&size={size}` |
| 成功逻辑 | `tasks` 替换；分页器 current 更新；列表滚动到顶部 |
| 失败逻辑 | 分页器 current 回滚到点击前的值 + toast |

#### 交互逻辑：改每页条数

| 阶段 | 内容 |
|------|------|
| 操作前 | 当前 size |
| 触发动作 | 选择新 size |
| 接口请求 | `GET /api/tasks?{filters}&page=1&size={newSize}` |
| 成功逻辑 | 列表更新，分页回到第 1 页 |
| 失败逻辑 | 分页器 size 回滚 + toast |

---

### 2.4 功能点：新建任务

#### 入口
- 主页顶部右侧 `+ 新建任务` 按钮。

#### 静态展示规则
- 抽屉（`<el-drawer>`）从右侧滑入，宽度 560px；
- 标题：「新建任务」；
- 表单字段：

| 字段 | 控件 | 必填 | 默认值 |
|------|------|------|--------|
| 标题 | `<el-input>` | ✓ | 空 |
| 描述 | `<el-input type=textarea>` | — | 空 |
| 任务类型 | `<el-select>` | — | 空 |
| 公司 | `<el-select>` | ✓ | 空 |
| 项目 | `<el-select>`（按公司联动） | ✓ | 空 |
| 截止日 | `<el-date-picker value-format="YYYY-MM-DD">` | ✓ | 今天 |
| 提醒起 | `<el-date-picker>` | — | `due_at - 1 天`，可改 |

- 底部按钮：「取消」「保存」；
- 保存中：按钮 loading，按钮禁用。

#### 交互逻辑：打开抽屉

| 阶段 | 内容 |
|------|------|
| 操作前 | 主页正常展示 |
| 触发动作 | 点击 `+ 新建任务` |
| 接口请求 | 无 |
| 成功逻辑 | 抽屉打开，焦点落到「标题」输入框 |
| 失败逻辑 | — |

#### 交互逻辑：选择公司 → 项目联动

| 阶段 | 内容 |
|------|------|
| 操作前 | 公司未选 / 已选 |
| 触发动作 | 选中某公司 |
| 接口请求 | 若该公司的项目未缓存：`GET /api/projects?company_id={id}` |
| 成功逻辑 | 项目下拉数据源刷新；若之前已选项目，清空项目值 |
| 失败逻辑 | 项目下拉显示「加载失败」+ 空列表（允许用户先保存公司，下次再补项目——但保存时会校验必填） |

#### 交互逻辑：截止日变化 → 提醒起默认

| 阶段 | 内容 |
|------|------|
| 操作前 | `due_at` 已填，提醒起可能已填 |
| 触发动作 | 修改 `due_at` |
| 接口请求 | 无 |
| 成功逻辑 | 提醒起若为空或等于上一次 `due_at - 1 天`，自动设为 `new_due_at - 1 天` |
| 失败逻辑 | — |

#### 交互逻辑：保存

| 阶段 | 内容 |
|------|------|
| 操作前 | 表单字段已填写 |
| 触发动作 | 点击「保存」 |
| 接口请求 | `POST /api/tasks` body（snake_case）：<br>`{ title, description?, task_type_id?, company_id, project_id, due_at, remind_start_at? }` |
| 成功逻辑 | 抽屉关闭；列表首行插入新任务；`total += 1`；`ElMessage.success('创建成功')` |
| 失败逻辑 | 抽屉不关闭；<br>400 → 顶部 toast（`ElMessage.error(detail)`）；<br>422 → 解析 `detail[].loc` 映射回表单字段红字；<br>5xx → 顶部 toast |

---

### 2.5 功能点：编辑任务

#### 入口
- 列表行内 `编辑` 按钮（仅 `pending` 状态可见）。

#### 静态展示规则
- 抽屉标题：「编辑任务」；
- 抽屉顶部紧贴「提醒计划」区域：渲染 `<ReminderChips :reminders="current.reminders" :due-at="current.due_at" />`；
- 字段预填当前任务值；
- 底部按钮：「取消」「保存」。

#### 交互逻辑：打开编辑抽屉

| 阶段 | 内容 |
|------|------|
| 操作前 | 列表已渲染，目标行可见 |
| 触发动作 | 点击行内 `编辑` |
| 接口请求 | `GET /api/tasks/{id}` |
| 成功逻辑 | `useTaskStore.current` 写入；抽屉打开；表单预填；ReminderChips 渲染 |
| 失败逻辑 | toast「加载失败」+ 抽屉不打开 |

#### 交互逻辑：保存编辑

| 阶段 | 内容 |
|------|------|
| 操作前 | 抽屉打开，表单已修改 |
| 触发动作 | 点击「保存」 |
| 接口请求 | `PUT /api/tasks/{id}` body：<br>`{ title, description?, task_type_id?, company_id, project_id, due_at, remind_start_at }` |
| 成功逻辑 | 抽屉关闭；列表对应行内容替换；`current` 清空；`ElMessage.success('更新成功')` |
| 失败逻辑 | 抽屉不关闭；422 字段红字；其他 toast |

---

### 2.6 功能点：标记完成

#### 入口
- 列表行内 `完成` 按钮（仅 `pending` 状态可见）。

#### 静态展示规则
- 按钮文字「完成」，无二次确认弹窗。

#### 交互逻辑

| 阶段 | 内容 |
|------|------|
| 操作前 | 目标行 `status='pending'` |
| 触发动作 | 点击 `完成` |
| 接口请求 | `POST /api/tasks/{id}/complete`（无 body） |
| 成功逻辑 | 列表行 `status` 变为 `completed`，tag 颜色变更；`ElMessage.success('已完成')` |
| 失败逻辑 | 422 → toast「当前状态不允许此操作」；列表状态不变 |

---

### 2.7 功能点：删除任务

#### 入口
- 列表行内 `删除` 按钮（任意状态可见）。

#### 静态展示规则
- 无独立按钮态样式，hover 显示危险色；
- 点击后立即触发 `ElMessageBox.confirm`。

#### 交互逻辑

| 阶段 | 内容 |
|------|------|
| 操作前 | 目标行存在 |
| 触发动作 | 点击 `删除` |
| 接口请求 | 无（仅弹窗） |
| 成功逻辑 | 弹窗打开，文案「确定删除「{title}」？删除后不可恢复。」；等待用户确认 |
| 失败逻辑 | 用户点取消 → 关闭弹窗，无操作 |

#### 交互逻辑：用户确认删除

| 阶段 | 内容 |
|------|------|
| 操作前 | 确认弹窗已打开 |
| 触发动作 | 点击「确定」 |
| 接口请求 | `DELETE /api/tasks/{id}` |
| 成功逻辑 | 弹窗关闭；列表行移除；`total -= 1`；`ElMessage.success('删除成功')` |
| 失败逻辑 | 弹窗关闭 + toast |

---

### 2.8 功能点：管理任务类型（弹窗）

#### 入口
- 主页顶部 `管理类型` 按钮。

#### 静态展示规则
- 对话框（`<el-dialog>`）宽度 800px，居中；
- 标题：「任务类型管理」；
- 内容：顶部「+ 新建」输入区 + 列表区；
- 列表行：name 输入框 + 「保存」+ 「删除」+ 「取消」按钮组；
- 列表为空时显示「暂无任务类型」占位。

#### 交互逻辑：打开弹窗

| 阶段 | 内容 |
|------|------|
| 操作前 | 主页加载 |
| 触发动作 | 点击 `管理类型` |
| 接口请求 | `GET /api/task-types` |
| 成功逻辑 | 弹窗打开，列表渲染 |
| 失败逻辑 | 弹窗不打开 + toast |

#### 交互逻辑：新建类型

| 阶段 | 内容 |
|------|------|
| 操作前 | 顶部输入框有值 |
| 触发动作 | 点击「+ 新建」 |
| 接口请求 | `POST /api/task-types` body：`{ name }` |
| 成功逻辑 | 列表追加新行；输入框清空；`ElMessage.success('创建成功')` |
| 失败逻辑 | 422 → 输入框红字；409 → toast「该名称已存在」 |

#### 交互逻辑：编辑类型

| 阶段 | 内容 |
|------|------|
| 操作前 | 列表中某行处于编辑态（点击行内编辑按钮进入） |
| 触发动作 | 修改 name，点击「保存」 |
| 接口请求 | `PUT /api/task-types/{id}` body：`{ name }` |
| 成功逻辑 | 行退出编辑态，新值生效 |
| 失败逻辑 | 422 → 红字；409 → toast |

#### 交互逻辑：删除类型

| 阶段 | 内容 |
|------|------|
| 操作前 | 目标行存在 |
| 触发动作 | 点击行内 `删除` |
| 接口请求 | `DELETE /api/task-types/{id}` |
| 成功逻辑 | 行移除；`ElMessage.success('删除成功')` |
| 失败逻辑 | 409 → `ElMessageBox.alert(detail, '无法删除', { type: 'warning' })`；行保留 |

---

### 2.9 功能点：公司 / 项目数据源（下拉）

#### 入口
- 仅在任务表单（TaskForm）的公司 / 项目下拉中触发。

#### 静态展示规则
- 公司下拉数据源 = `useCompanyStore.companies`（启动时全量拉取一次）；
- 项目下拉数据源 = `useProjectStore.byCompany[company_id]`（按公司懒加载）。

#### 交互逻辑：首次进入主页

| 阶段 | 内容 |
|------|------|
| 操作前 | 主页未加载 |
| 触发动作 | `App.vue` mount |
| 接口请求 | `GET /api/companies`<br>`GET /api/projects`（全量） |
| 成功逻辑 | store 写入 |
| 失败逻辑 | toast「字典加载失败」+ 下拉为空 |

#### 交互逻辑：切换公司触发项目联动

| 阶段 | 内容 |
|------|------|
| 操作前 | 已选公司 A |
| 触发动作 | 选中公司 B |
| 接口请求 | 若 B 的项目未缓存：`GET /api/projects?company_id={B}` |
| 成功逻辑 | 项目下拉数据源替换 |
| 失败逻辑 | toast + 项目下拉空 |

> 本版本不提供公司 / 项目独立管理页；CRUD 通过后端 API 支撑，可由后端工具或后续 Settings 页补充。

---

## 3. 测试案例（Playwright + Chrome）

### 3.1 测试环境

| 项 | 值 |
|----|---|
| 浏览器 | Chrome ≥ 100（Chromium） |
| 测试框架 | Playwright（`@playwright/test`） |
| 前端地址 | `http://localhost:5173` |
| 后端地址 | `http://localhost:8000`（由 Vite 代理转发 `/api`） |
| 测试库 | 测试数据库，隔离数据；每个 case 前后清理 |
| 启动方式 | `npx playwright test --project=chromium` |

### 3.2 用例编号约定

`TC<模块编号><序号>`：`TC-TM-01` … `TC-TM-NN`

### 3.3 用例清单

#### TC-TM-01 主页加载（空数据）
- **前置**：后端清空 tasks / types / companies / projects；
- **步骤**：
  1. `page.goto('http://localhost:5173/')`；
  2. 等待 `el-table` 出现；
  3. 断言：标题「SparkMemo」可见；
  4. 断言：列表区显示「暂无数据」；
  5. 断言：分页器显示「共 0 条」；
  6. 断言：`+ 新建任务`、`管理类型` 按钮可见。
- **预期**：页面正常渲染，无错误弹窗。

#### TC-TM-02 筛选公司下拉
- **前置**：后端存在公司 A / B；
- **步骤**：
  1. 进入主页；
  2. 等待公司下拉可见；
  3. 点击公司下拉，断言出现 A、B 选项；
  4. 选择 A；
  5. 等待列表刷新；
  6. 断言网络收到 `GET /api/tasks?company_id={A}&page=1&size=20`。
- **预期**：列表只显示 A 公司的任务。

#### TC-TM-03 新建任务（正常）
- **前置**：后端存在公司 A、项目 P、类型 T；
- **步骤**：
  1. 点击 `+ 新建任务`；
  2. 断言抽屉标题「新建任务」；
  3. 填写标题「TC 新建 1」；
  4. 选择公司 A；
  5. 等待项目下拉刷新后选择 P；
  6. 选择类型 T；
  7. 截止日选择今天；
  8. 点击「保存」；
  9. 断言网络收到 `POST /api/tasks` 且 body 含 `title="TC 新建 1"`；
  10. 断言抽屉关闭，列表首行出现「TC 新建 1」；
  11. 断言 toast「创建成功」出现。
- **预期**：任务创建成功。

#### TC-TM-04 新建任务（422 字段错误）
- **前置**：同 TC-TM-03；
- **步骤**：
  1. 打开抽屉；
  2. 截止日 `2026-08-10`、提醒起手动改为 `2026-08-15`（大于截止日）；
  3. 点击「保存」；
  4. 断言网络收到 `POST /api/tasks` 响应 400 或 422（后端 400）；
  5. 断言抽屉未关闭；
  6. 断言后端 detail 文案展示（`ElMessage.error` 或字段红字）。
- **预期**：表单不提交，提示错误。

#### TC-TM-05 编辑任务
- **前置**：已存在 pending 任务 X；
- **步骤**：
  1. 在 X 行点击 `编辑`；
  2. 断言网络收到 `GET /api/tasks/{X}`；
  3. 断言抽屉标题「编辑任务」；
  4. 断言表单标题字段等于 X.title；
  5. 断言「提醒计划」区域可见并显示 reminders；
  6. 修改标题为「TC 编辑 X」；
  7. 点击「保存」；
  8. 断言网络收到 `PUT /api/tasks/{X}`；
  9. 断言列表中 X 行标题变为「TC 编辑 X」；
  10. 断言 toast「更新成功」。
- **预期**：编辑成功。

#### TC-TM-06 标记完成
- **前置**：存在 pending 任务 Y；
- **步骤**：
  1. 在 Y 行点击 `完成`；
  2. 断言网络收到 `POST /api/tasks/{Y}/complete`；
  3. 断言 Y 行状态 tag 文本变为「已完成」；
  4. 断言 Y 行 `编辑` 按钮置灰；
  5. 断言 toast「已完成」。
- **预期**：标记成功。

#### TC-TM-07 删除任务（确认）
- **前置**：存在任意状态任务 Z；
- **步骤**：
  1. 在 Z 行点击 `删除`；
  2. 断言 `ElMessageBox.confirm` 出现，文案含 Z.title；
  3. 点击「确定」；
  4. 断言网络收到 `DELETE /api/tasks/{Z}`；
  5. 断言列表中 Z 行消失；
  6. 断言 toast「删除成功」。
- **预期**：删除成功。

#### TC-TM-08 删除任务（取消）
- **前置**：存在任务 Z；
- **步骤**：
  1. 点击 Z 行 `删除`；
  2. 在确认弹窗中点击「取消」；
  3. 断言未发出 `DELETE` 请求；
  4. 断言 Z 仍在列表中。
- **预期**：删除取消。

#### TC-TM-09 翻页
- **前置**：存在 ≥ 25 条 pending 任务；
- **步骤**：
  1. 进入主页；
  2. 断言分页器显示「共 N 条（N ≥ 25）」；
  3. 点击 next 页；
  4. 断言网络收到 `GET /api/tasks?...&page=2&size=20`；
  5. 断言列表内容更新；
  6. 切换 size 至 50；
  7. 断言网络收到 `GET /api/tasks?...&page=1&size=50`。
- **预期**：分页正常。

#### TC-TM-10 今日待提醒
- **前置**：存在 3 条任务，1 条 `remind_start_at ≤ today ≤ due_at`、1 条尚未到提醒起、1 条已逾期；
- **步骤**：
  1. 进入主页（默认全部）；
  2. 断言列表显示 3 条；
  3. 切换 tab 至「今日待提醒」；
  4. 断言网络收到 `GET /api/tasks?remind_today=true&status=pending&page=1&size=20`；
  5. 断言列表仅显示 1 条（提醒区间含今天）；
  6. 切换回「全部」；
  7. 断言列表恢复 3 条。
- **预期**：今日筛选生效。

#### TC-TM-11 任务类型管理 - 新建
- **前置**：无特殊前置；
- **步骤**：
  1. 点击 `管理类型`；
  2. 断言网络收到 `GET /api/task-types`；
  3. 在顶部输入框输入「TC 类型 1」；
  4. 点击「+ 新建」；
  5. 断言网络收到 `POST /api/task-types` body `{ name: "TC 类型 1" }`；
  6. 断言列表出现「TC 类型 1」；
  7. 断言输入框清空。
- **预期**：新建成功。

#### TC-TM-12 任务类型管理 - 删除（被引用 409）
- **前置**：存在类型 T 且被至少一个任务引用；
- **步骤**：
  1. 打开 `管理类型` 弹窗；
  2. 在 T 行点击 `删除`；
  3. 断言网络收到 `DELETE /api/task-types/{T}` 响应 409；
  4. 断言 `ElMessageBox.alert` 出现，type='warning'，文案含后端 detail；
  5. 断言 T 仍在列表中。
- **预期**：删除被阻断，提示明确。

#### TC-TM-13 关键词搜索
- **前置**：存在任务 K1（标题含「Alpha」）与 K2（标题含「Beta」）；
- **步骤**：
  1. 进入主页；
  2. 在关键词框输入「Alpha」；
  3. 等待 300ms + 网络请求完成；
  4. 断言网络收到 `GET /api/tasks?keyword=Alpha&page=1&size=20`；
  5. 断言列表仅出现 K1；
  6. 清空关键词，断言列表恢复。
- **预期**：搜索生效且有 debounce。

#### TC-TM-14 抽屉 ESC 关闭 + dirty 二次确认
- **前置**：—
- **步骤**：
  1. 点击 `+ 新建任务`；
  2. 在标题框输入「dirty」；
  3. 按 ESC；
  4. 断言 `ElMessageBox.confirm` 出现，文案「当前修改尚未保存，确定离开？」；
  5. 点击「确定」；
  6. 断言抽屉关闭。
- **预期**：dirty 状态有保护。

#### TC-TM-15 网络错误提示
- **前置**：通过 `page.route` 拦截 `GET /api/tasks` 返回 500；
- **步骤**：
  1. 进入主页；
  2. 断言列表区显示「加载失败，点此重试」；
  3. 断言出现 `ElMessage.error('服务异常，请稍后重试')`；
  4. 点击「重试」；
  5. 断言再次发出 `GET /api/tasks`。
- **预期**：5xx 走全局错误文案 + 列表区可重试。

### 3.4 Playwright 代码示例（节选 TC-TM-03）

```js
// e2e/tc-tm-03.spec.js
import { test, expect } from '@playwright/test'

test('TC-TM-03 新建任务（正常）', async ({ page }) => {
  // 监听网络请求
  const postTask = page.waitForRequest(
    (req) => req.method() === 'POST' && req.url().includes('/api/tasks')
  )

  await page.goto('http://localhost:5173/')

  // 打开抽屉
  await page.getByRole('button', { name: '+ 新建任务' }).click()
  await expect(page.getByText('新建任务')).toBeVisible()

  // 填写表单
  await page.getByLabel('标题').fill('TC 新建 1')
  await page.getByLabel('公司').click()
  await page.getByRole('option', { name: 'A 公司' }).click()
  // 等待项目下拉刷新
  await page.waitForResponse(
    (res) => res.url().includes('/api/projects?company_id=')
  )
  await page.getByLabel('项目').click()
  await page.getByRole('option', { name: 'P 项目' }).click()
  await page.getByLabel('类型').click()
  await page.getByRole('option', { name: 'T 类型' }).click()
  // 截止日默认今天，不动

  // 提交
  await page.getByRole('button', { name: '保存' }).click()

  // 断言请求
  const req = await postTask
  const body = req.postDataJSON()
  expect(body.title).toBe('TC 新建 1')
  expect(body.company_id).toBeGreaterThan(0)
  expect(body.project_id).toBeGreaterThan(0)

  // 断言 UI
  await expect(page.getByText('新建任务')).not.toBeVisible()
  await expect(page.getByRole('cell', { name: 'TC 新建 1' })).toBeVisible()
  await expect(page.getByText('创建成功')).toBeVisible()
})
```

### 3.5 测试数据管理

- **隔离**：每个 `test` 用唯一后缀（如 `Date.now()`）避免冲突；
- **清理**：在 `globalTeardown` 中调用后端 `DELETE` 或重置测试库；
- **夹具（fixture）**：常用字典（公司 / 项目 / 类型）放在 `e2e/fixtures/seed.js`，通过 `test.beforeAll` 调用后端 API 灌入；
- **不依赖顺序**：每个用例独立前置条件，不假定前置 case 已跑过。

### 3.6 运行命令

```bash
# 安装 Playwright（一次性）
npx playwright install chromium

# 运行所有任务管理用例
npx playwright test e2e/tc-tm-*.spec.js --project=chromium

# 调试单个用例
npx playwright test e2e/tc-tm-03.spec.js --project=chromium --debug
```