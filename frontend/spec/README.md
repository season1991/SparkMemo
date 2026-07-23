# SparkMemo 前端规格

> 适配规格：SparkMemo 任务提醒系统 v0.1
> 适用范围：单用户本地版，无登录。
> **日期约定**：所有日期字段全程作为 10 字符字符串 `YYYY-MM-DD` 处理；`el-date-picker` 必须 `value-format="YYYY-MM-DD"`，不做 `Date` 对象转换与时区偏移。
> **不引入 TypeScript**；类型以 JSDoc 注释 + 模块规格文档为准。

---

## 1. 需求的概述

### 1.1 项目背景

SparkMemo 是单用户的本地化任务提醒 Web 应用。用户管理多家公司下的多个项目，并为每个项目维护任务（含自定义类型、提前提醒规则）。到截止日期前由系统每天提醒一次，逾期 3 天的任务自动标记为完成。前端是对接 FastAPI 后端的单页应用，承载所有 UI 交互，不持有持久化数据，不做业务计算（提醒计划生成、逾期判断等均由后端完成）。

### 1.2 目标用户

- 单用户本地使用；
- 关心「截止前还能看见」「逾期不被遗忘」两类信号；
- 操作频次低，每次操作希望步骤少、反馈清晰。

### 1.3 核心价值

- 一个页面完成「浏览 / 筛选 / 新建 / 编辑 / 删除 / 标记完成」全流程；
- 抽屉与弹窗承载表单，不打断列表浏览；
- 「今日待提醒」独立视图，避免被大量历史任务淹没；
- 所有日期在前端始终是 `YYYY-MM-DD` 字符串，杜绝时区 / 序列化问题。

### 1.4 技术栈

| 技术 | 用途 |
|------|------|
| Vue 3 | 框架（Composition API + `<script setup>`） |
| Vite 5 | 构建工具 |
| Vue Router 4 | 路由（hash 模式） |
| Pinia | 状态管理（按域拆 store） |
| Element Plus | UI 组件库（中文友好） |
| Axios | HTTP 客户端（单实例 + 拦截器） |

### 1.5 范围声明

| 在范围内 | 不在范围内 |
|---------|----------|
| 公司 / 项目 / 任务类型 / 任务四域 CRUD | 登录 / 多用户 / 权限 |
| 列表筛选、分页、今日待提醒 | 移动端响应式（v0.1 仅桌面 ≥ 1280px） |
| 表单提交、422 字段级错误展示 | WebSocket 推送 |
| 抽屉 / 弹窗交互 | 系统级通知 |
| 任务状态展示（pending / completed / overdue_done） | i18n（仅中文） |

### 1.6 项目结构

```
frontend/
├── public/
├── src/
│   ├── api/          # axios 实例 + 按域拆分的请求函数
│   ├── components/   # 公共组件
│   ├── views/        # 页面组件
│   ├── stores/       # Pinia store
│   ├── router/       # Vue Router 配置
│   ├── App.vue
│   └── main.js
├── spec/             # 规格文档
│   ├── README.md     # 本文件
│   └── *.md          # 模块规格
├── index.html
├── vite.config.js
└── package.json
```

---

## 2. 功能点介绍与索引

| 功能点 | 阅读文件 |
|--------|---------|
| 今日概述模块 | [./dashboard.md](./dashboard.md) |
| 任务管理模块 | [./task_management.md](./task_management.md) |
| 公司 / 项目管理模块 | [./company_project.md](./company_project.md) |
| 周需求管理模块（v0.5.4：DSP 上传 / 查询 / 删除） | [./weekly_demand.md](./weekly_demand.md) |
| 跨表数据填充模块（v0.6.0：4 步向导式单页 ETL） | [./cross_table_fill.md](./cross_table_fill.md) |

---

## 3. 全局通用规则

本节列出所有页面 / 组件都必须遵守的横向规则。各模块规格文档（`task_management.md` 等）若与本节冲突，以本节为准。

### 3.1 分页通用规范

| 项 | 规范 |
|----|------|
| 数据格式 | 后端返回 `{ items: T[], total: number }`；前端不缓存跨页数据 |
| 默认参数 | `page=1`、`size=20` |
| 每页条数选项 | `10` / `20` / `50`（与后端 `size` 上限 100 对齐） |
| 分页器位置 | 列表底部，与列表共享滚动容器外层 |
| 分页器组件 | `el-pagination`，`layout="total, sizes, prev, pager, next, jumper"` |
| 加载状态 | 请求中分页器禁用所有按钮，列表区显示 `el-skeleton` 或骨架屏 |
| 空状态 | `total === 0` 时列表区显示「暂无数据」占位（按当前筛选条件给出友好文案） |
| 筛选条件变化 | 强制重置 `page=1` 后再发请求 |
| 路由切换 | 不保留分页状态（每次进入页面从 page=1 起） |
| 总数展示 | 始终显示 `共 N 条`，N 由后端 `total` 字段提供 |

### 3.2 搜索 / 筛选通用规则

| 项 | 规范 |
|----|------|
| 触发方式 | 筛选条件变化自动触发；关键词搜索需 `debounce 300ms` 后触发 |
| 重置 | 顶部「重置」按钮一键清空所有筛选条件，强制 page=1 后重新请求 |
| URL 同步 | 筛选条件不写入 URL query（hash 路由 + 单页面应用，避免刷新错位）；如需深链，v0.2 再议 |
| 关键词搜索 | 后端用 `keyword` 参数做 LIKE 模糊匹配（标题 / 描述）；前端不限制长度 |
| 日期筛选 | `due_from` / `due_to` 必须合法 `YYYY-MM-DD`，且 `due_from <= due_to`（前端预校验，后端 400 兜底） |
| 公司 → 项目联动 | 切换公司时项目下拉清空并按新公司重新拉取 |
| 多选筛选 | 任务类型、状态目前为单选；如需多选，须后端先升级接口 |
| 筛选结果为空 | 列表区显示「无匹配任务，建议调整筛选条件」+ 「重置筛选」快捷按钮 |
| 筛选状态可视化 | 已生效的筛选条件在筛选条上方用 `el-tag` 列出，可单独删除某个条件 |

### 3.3 表单通用校验规则

| 项 | 规范 |
|----|------|
| 必填标识 | 必填字段 label 前红色 `*` |
| 校验时机 | 失焦（`blur`）+ 提交（`submit`）；输入中不打断 |
| 错误展示 | 字段下方红色文案（`el-form-item` 的 `error`）；非字段错误用 `ElMessage` |
| 422 回显 | axios 拦截器解析 `detail: ValidationError[]`，按 `loc` 数组映射到对应字段红字 |
| 400 / 409 | `ElMessage.error(detail)` 展示后端文案 |
| 字段级硬约束 | 「特定」模式下 `custom_remind_start_at <= due_at`；「提前提醒」必填；`company_id` / `project_id` 必填且对应记录存在 |
| 外键校验 | 后端负责存在性校验（422）；前端不预先全量校验 |
| 提交按钮 | 请求中禁用 + loading 态；提交成功后关闭表单 |
| 取消 / 关闭 | 表单 dirty 时关闭需 `ElMessageBox.confirm` 二次确认 |
| 重置 | 「重置」按钮恢复初始值；新建模式初始值 = 空 / 默认；编辑模式初始值 = 当前实体 |
| 字段长度 | 标题 ≤ 200 字符；描述 ≤ 4000 字符；名称 ≤ 128 字符（与后端模型对齐） |
| 日期控件 | `el-date-picker` 统一 `value-format="YYYY-MM-DD"`；禁止 `datetime` 类型（仅需日期） |

### 3.4 弹窗通用行为

| 弹窗类型 | 用途 | 默认尺寸 | 出现位置 |
|---------|------|---------|---------|
| 抽屉（`el-drawer`） | 任务新建 / 编辑 | `width=560px` | 右侧 |
| 对话框（`el-dialog`） | 任务类型管理、删除确认 | `width=800px` / `420px` | 居中 |
| 消息框（`ElMessageBox`） | 危险操作二次确认 | 系统默认 | 居中 |

| 项 | 规范 |
|----|------|
| 同时只能打开 | 同一时间最多 1 个弹窗；打开新弹窗前关闭已有弹窗 |
| ESC 关闭 | 抽屉、对话框默认开启 ESC 关闭；表单 dirty 时关闭需二次确认 |
| 点击遮罩关闭 | 默认关闭；表单 dirty 时需二次确认 |
| 提交反馈 | 成功后：关闭弹窗 + toast「xxx 成功」+ 列表自动刷新；失败时：弹窗不关闭 + 字段红字 / 顶部 toast |
| 删除提示文案 | 危险操作前必须 `ElMessageBox.confirm`，文案示例：「确定删除「任务标题」？删除后不可恢复。」 |
| 409 / 业务冲突 | `ElMessageBox.alert(detail, '无法操作', { type: 'warning' })` |
| 动画 | 使用 Element Plus 默认动画，不自定义 |

### 3.5 全局状态文案

#### 3.5.1 任务状态展示

| 值 | 中文 | 标签颜色（`el-tag` `type`） | UI 行为 |
|----|------|---------------------------|--------|
| `pending` | 待办 | `warning` | 可编辑 / 完成 / 删除 |
| `completed` | 已完成 | `success` | 可删除；编辑置灰 |
| `overdue_done` | 逾期自动完成 | `info` | 可删除；编辑置灰 |

#### 3.5.2 操作按钮文案

| 场景 | 文案 |
|------|------|
| 新建 | 「+ 新建任务」 |
| 编辑 | 「编辑」 |
| 删除 | 「删除」 |
| 完成 | 「完成」 |
| 保存 | 「保存」 |
| 取消 | 「取消」 |
| 重置 | 「重置」 |
| 确认 | 「确定」 |
| 关闭 | 「关闭」 |
| 搜索 / 查询 | 「搜索」（按钮场景），筛选条场景不设按钮 |

#### 3.5.3 确认 / 提示文案

| 场景 | 文案 |
|------|------|
| 删除任务 | 「确定删除「{title}」？删除后不可恢复。」 |
| 删除类型被引用 | 后端 detail 直接展示（`ElMessageBox.alert`），如「该类型被 3 个任务引用，无法删除」 |
| 表单 dirty 关闭 | 「当前修改尚未保存，确定离开？」 |
| 提交成功 | 「创建成功」/「更新成功」/「删除成功」/「已完成」 |

#### 3.5.4 错误文案

| 场景 | 文案 |
|------|------|
| 网络错误 / timeout | 「网络异常，请稍后重试」 |
| 404 | 「资源不存在」 |
| 409 | 后端 detail 文案 |
| 422 字段错误 | 后端 `msg` 文案（直接展示） |
| 422 非字段错误 | 「请求参数有误，请检查后重试」 |
| 5xx | 「服务异常，请稍后重试」 |
| 非 pending 标记完成 | 「当前状态不允许此操作」 |

### 3.6 FormData 上传规则（v0.6.0 新增）

> **背景（v0.6.0 修复）**：早期模块（如 `api/dsp_uploads.js`）在 multipart 上传时手动设置了 `headers: { 'Content-Type': 'multipart/form-data' }`，**但未带 `boundary=...` 参数**。axios 检测到用户手动设置 Content-Type 后，**不再自动补 boundary**，导致请求头是 `multipart/form-data`（无 boundary），服务端 multipart 解析器把文件字段识别为普通 form 字段读为字符串，最终 `Value error, Expected UploadFile, received: <class 'str'>` 报错。

**全局规则**：

1. **不要在 API 调用处手动设置 `Content-Type` 头**（`api/*.js`）—— 凡上传 `FormData` 时，绝不在 `client.post(...)` 的 `config.headers` 里写 `'Content-Type': 'multipart/form-data'`，**让 axios 自动追加 boundary**。
2. **`api/client.js` 提供 request interceptor 兜底**：拦截 `cfg.data instanceof FormData` 的请求，自动 `delete cfg.headers['Content-Type']`（兼容任何模块旧代码错误地手动设置了 Content-Type 的情形）。**任何新增上传 API 自动受保护**。
3. **后端 multipart 解析依赖 boundary**：浏览器 / axios / node-form-data 任意一处丢了 boundary，都会触发 Pydantic 「Expected UploadFile, received str」错误。开发排查时第一步必看 Network tab 的 Request Headers。

| 调用方式 | 期望行为 |
|---------|---------|
| `client.post(url, formData)` | axios 自动设置 `multipart/form-data; boundary=...` |
| `client.post(url, formData, { headers: { 'X-Custom': 'foo' } })` | 同上（只要不写 Content-Type） |
| `client.post(url, formData, { headers: { 'Content-Type': 'multipart/form-data' } })` | **禁止** —— 触发 bug；interceptor 会自动 delete 该 header 防爆 |

**§3.6 历史**：v0.5.x 时 `api/dsp_uploads.js` 即埋下此 bug，v0.6.0 引入 interceptor 一并根治，无需逐文件改 API 模块。

**相关 spec**：[`./weekly_demand.md`](./weekly_demand.md) §5.1、[`./cross_table_fill.md`](./cross_table_fill.md) §4.1 均仅调 `client.post(url, formData)`，依赖本节全局规则 + interceptor 兜底。

### 3.7 兼容要求

| 项 | 要求 |
|----|------|
| 浏览器 | Chrome ≥ 100、Edge ≥ 100、Firefox ≥ 100、Safari ≥ 15 |
| 最低分辨率 | 1280 × 720 |
| 响应式 | v0.1 不适配移动端；< 1280px 宽度给出提示「请使用 ≥ 1280px 宽度的桌面浏览器」 |
| Node | ≥ 18（开发环境） |
| 包管理 | `npm`（与 `package.json` scripts 一致） |
| 后端协议 | HTTP / JSON |
| 时区 | 不依赖时区；所有日期字段为 `YYYY-MM-DD` 字符串 |
| 国际化 | 仅中文；不引入 i18n 库 |
| 持久化 | 前端不持有任何持久化数据（刷新即重新拉取） |

---

## 4. 关联文档

| 文档 | 位置 |
|------|------|
| 后端总览 spec | [../backend/spec/README.md](../backend/spec/README.md) |
| 任务管理后端 spec | [../backend/spec/task_management.md](../backend/spec/task_management.md) |
| OpenAPI 接口契约 | [../backend/openapi/task_management.json](../backend/openapi/task_management.json) |
| 前端任务管理模块规格 | [./task_management.md](./task_management.md) |
| 前端周需求管理模块规格（含 DSP 上传） | [./weekly_demand.md](./weekly_demand.md) |
| 前端跨表数据填充模块规格（含 multipart 上传） | [./cross_table_fill.md](./cross_table_fill.md) |

---

## 5. 前台样式设计

参考 [`../index.html`](../index.html) 的基底（`lang="zh-CN"` / `UTF-8` / 标准 viewport / `<title>SparkMemo</title>`），样式层全部走 **Element Plus + 局部 `<style scoped>`** 路线，不引入 Tailwind / UI Kit 之外的额外框架。

### 5.1 设计原则

- **克制**：以 Element Plus 默认视觉为基线，仅在确有必要时覆盖；不引入多余的设计 token。
- **一致**：同类组件（按钮 / 标签 / 间距 / 圆角）使用同一组变量，避免一页面一样。
- **可读**：中文优先，字号、行高、对比度以「长时间浏览不疲劳」为目标。
- **桌面优先**：v0.1 仅保证 ≥ 1280px 桌面端可用；不做响应式。

### 5.2 布局

```
┌──────────┬────────────────────────────────────────────────────────────┐
│          │  页面页头（56px）                                          │
│   ⚡     │   - 左侧：页面标题（route.meta.title）                      │
│ SparkMemo│   - 右侧：信息展示位（v0.1 留空）                          │
│          ├────────────────────────────────────────────────────────────┤
│  任务管理│                                                            │
│          │  主内容区 Main                                             │
│  （预留）│   - 最大宽 1440px，居中                                    │
│          │   - padding 16px 24px                                     │
└──────────┴────────────────────────────────────────────────────────────┘
   220px
```

| 项 | 规范 |
|----|------|
| 左侧导航条宽度 | 220px，固定 |
| 导航条背景 | `#fff`；右侧 1px 边框 `--el-border-color-lighter` |
| Logo 区高度 | 64px；左 padding 20px；图标 22px + 文字 18px / 600 |
| 导航项高度 | 44px；左 padding 20px；图标 18px + 文字 14px / 400；图标与文字间距 10px |
| 导航项间距 | 4px |
| 导航项激活态 | 左 3px 主色竖条 + 浅主色背景 `#ecf5ff` + 文字主色 `#409eff` |
| 导航项 hover | 背景 `#f5f7fa` |
| 导航项圆角 | 0（贴合整条带状视觉） |
| 页面页头高度 | 56px，固定；背景 `#fff`；下方 1px 边框 `--el-border-color-lighter` |
| 页面标题 | 18px / 600；颜色 `#303133`；左 padding 24px |
| 页面信息展示位 | 右 padding 24px；右对齐；字号 14px / 颜色 `#909399` |
| 主内容区最大宽度 | 1440px；超过居中 |
| 主内容区内边距 | 左右 24px，上下 16px |
| 区块间距 | 16px |
| 卡片 / 筛选条 / 表格 | 圆角 4px；背景 `#fff`；1px 边框 `#ebeef5` |

### 5.3 排版

| 项 | 规范 |
|----|------|
| 主字体 | `-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif`（跟随系统中文栈） |
| 等宽字体 | `SFMono-Regular, Consolas, "Liberation Mono", monospace`（仅日期字符串、代码片段用） |
| 基础字号 | 14px（与 Element Plus 一致） |
| 标题层级 | H1 20px / H2 18px / H3 16px / 正文 14px / 辅助 12px |
| 行高 | 正文 1.5；表格行 1.4；标题 1.3 |
| 字重 | 正文 400；强调 500；标题 600 |
| 颜色 | 主文本 `#303133`；次要文本 `#606266`；辅助文本 `#909399`；占位 `#c0c4cc` |

### 5.4 颜色

继承 Element Plus 主题色，不再额外引入品牌色：

| 用途 | 颜色变量 | 备注 |
|------|---------|------|
| 主色（Primary） | `--el-color-primary` | 默认 `#409eff`；按钮、链接、激活态 |
| 成功 | `--el-color-success` | `#67c23a`；`completed` 状态 tag |
| 警告 | `--el-color-warning` | `#e6a23c`；`pending` 状态 tag、`due_at` 高亮 |
| 危险 | `--el-color-danger` | `#f56c6c`；删除按钮、错误提示 |
| 信息 | `--el-color-info` | `#909399`；`overdue_done` 状态 tag |
| 边框 | `--el-border-color-lighter` | `#ebeef5` |
| 背景 | `--el-bg-color` | `#ffffff` |
| 页面底色 | `#f5f7fa` | 表格区外层 |

> 状态 tag 配色与 [§3.5.1 任务状态展示](#35-任务状态展示) 一致：`pending` 警告、`completed` 成功、`overdue_done` 信息。

### 5.5 间距

基于 4px 网格：

| 场景 | 值 |
|------|---|
| 表单字段间距 | 16px（`el-form` 默认） |
| 筛选条元素间距 | 12px |
| 表格行内边距 | 上下 8px，左右 0（由 `el-table` 控制） |
| 弹窗内边距 | 20px |
| 抽屉内边距 | 20px |

### 5.6 圆角与阴影

| 项 | 值 |
|----|---|
| 按钮 / 输入 / 选择 | 4px（`--el-border-radius-base`） |
| 卡片 | 4px |
| 弹窗 | 4px |
| 抽屉 | 0（左对齐右侧抽屉） |
| 阴影层级 | 弹窗 `0 8px 24px rgba(0,0,0,.12)`；浮层 `0 2px 12px rgba(0,0,0,.08)` |

### 5.7 图标

- 使用 **Element Plus Icons**（`@element-plus/icons-vue`），按需注册；
- 不引入第三方图标库（Font Awesome / Material Icons）；
- 操作按钮文字 + 图标组合：图标在前，文字在后；纯图标按钮仅在表格行内操作使用，必须配 `title` 属性。

### 5.8 动画

- 直接使用 Element Plus 内置过渡（抽屉、弹窗、消息）；
- 列表筛选切换不强制动画（避免误以为加载中）；
- 骨架屏（`el-skeleton`）用于列表加载态，时长与请求一致。

### 5.9 暂不实现

| 项 | 原因 |
|----|------|
| 暗色模式 | v0.1 不引入；如需规划，覆盖 Element Plus `--el-color-*` 与背景色变量即可 |
| 移动端响应式 | v0.1 仅桌面；< 1280px 给提示 |
| 自定义主题色切换 | 用户无需切换，保持 Element Plus 默认 |
| 自定义字体加载 | 跟随系统字体栈，避免引入字体文件 |