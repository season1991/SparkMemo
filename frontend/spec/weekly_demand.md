# 周需求管理模块规格（前端，v0.5.7 — 透视查询激活 `demand_plus_supply` + 视觉分组）

> 适配 OpenAPI：
> - [../../backend/openapi/dsp_uploads.json](../../backend/openapi/dsp_uploads.json)（`info.version = 0.5.7`，路径 `/api/dsp-uploads`；schema `DspUploadRead` / `DspUploadRowRead` / `DspUploadListResponse`）
> - [../../backend/openapi/pivot_query.json](../../backend/openapi/pivot_query.json)（`info.version = 0.5.7`，路径 `/api/pivot-query`；schema `PivotQueryRequest` / `PivotQueryResponse` / `PivotRow` / `WeekInfo`）
> 适配后端 spec：[../../backend/spec/weekly_demand.md](../../backend/spec/weekly_demand.md)（v0.5.7，含 §11 Demand+Supply 计算规则）
> 前端实现版本：v0.5.7
> 页面入口：
> - Hub：`views/WeeklyDemandHub.vue`（路由 `/dsp-uploads`；含 4 张功能卡片）
> - 上传：`views/DspUpload.vue`（路由 `/dsp-uploads/upload`）
> - 查询：`views/WeeklyDemandQuery.vue`（路由 `/dsp-uploads/query`）
> - 删除：`views/WeeklyDemandDelete.vue`（路由 `/dsp-uploads/delete`）
> - 透视查询：`views/PivotQuery.vue`（路由 `/pivot-query`，v0.5.6 新增；v0.5.7 启用 `demand_plus_supply` + 行级视觉分组）
> 全局规则遵循 [./README.md](./README.md)；本文档只描述本模块特有的页面拆解、功能点交互与测试案例。

> **v0.5.7 前端侧变更**（摘要）：
>
> 1. **`pivot_type` 启用 `demand_plus_supply`**：透视查询页单选框移除 `:disabled`；选择后 `version_dates` 自动改为单选。
> 2. **视觉分组（行级底色）**：1 组业务维度产出 4 行（Demand / Supply / TTL_GAP / Rolling_TTLGAP）；用三种 Element Plus 浅色 token 区分：
>    - `Demand` + `Supply` → `#ecf5ff`（primary-light-9，原始数据组）
>    - `TTL_GAP` → `#fdf6ec`（warning-light-9，单期派生）
>    - `Rolling_TTLGAP` → `#fef0f0`（danger-light-9，累计派生）
> 3. **负数 quantity 视觉强调**：仅 `TTL_GAP` / `Rolling_TTLGAP` 行单元格 `< 0` 时使用 `cell-negative`（加粗 + 红色 `#f56c6c`），其余 `data_type` 与 `Demand` 行为完全一致（零值灰、非零加粗深色）。
> 4. **整行底色压制**：`el-table` hover 高亮需被 `:row-class-name` 注入的 css `!important` 压住。
> 5. 测试计划 / 验证清单 / 修订记录同步更新（详见各章节）。
>
> **v0.5.6 前端侧变更**（摘要）：
>
> 1. **新增透视查询子模块**：独立路由 `/pivot-query`，对应 `views/PivotQuery.vue`。
> 2. **Hub 页扩展**：`WeeklyDemandHub.vue` 从 3 张卡片扩展为 4 张（新增「透视查询」卡片，icon `DataLine`，跳 `/pivot-query`）。
> 3. **API 层新增**：`api/pivot_query.js`（`queryPivot` + 4 个 lookup 函数）。
> 4. **透视查询页面**：三组筛选（必填定位 + 业务行级联 + 时间维度）+ 一张 OLAP 风格透视表。
> 5. 其余 v0.5.5 行为保持不变。

> **v0.5.5 前端侧变更**（摘要）：
>
> 1. **Config Name 字段入库**：表格列从 9 列增加到 10 列（新增 `config_name` 列）。
> 2. 其余 v0.5.4 行为保持不变。

> **v0.5.4 前端侧变更**（摘要）：
>
> 1. **模块重命名**：`DSP 上传` → `周需求管理`；侧边栏第 3 项改名 + icon 维持 `Upload`。
> 2. **路由层级**：`/dsp-uploads` 变成 hub 页（3 张卡片导航），子路由 `/dsp-uploads/{upload,query,delete}`。
> 3. **查询**：新增 `WeeklyDemandQuery.vue`；4 字段 form + 查询按钮 + 元数据 + 前 50 条事实行预览。
> 4. **删除**：新增 `WeeklyDemandDelete.vue`；4 字段 form + 查询预览按钮 + 删除按钮（带 `ElMessageBox.confirm` 二次确认）。
> 5. API 层扩展：`api/dsp_uploads.js` 加 `findBatchByVersion(meta)` 帮助函数；走既有 `GET /api/dsp-uploads?vendor=&item=&sub_item=&version_date=`（v0.5.4 新增的 4 个可选 query 参数）。

---

## 1. 整体页面结构拆解

### 1.1 路由与视图（v0.5.6）

| 路径 | 视图 | 侧边栏激活项 | `meta.title` | 说明 |
|------|------|------------|--------------|------|
| `/dsp-uploads` | `views/WeeklyDemandHub.vue` | 周需求管理 | 周需求管理 | Hub 页：4 张功能卡片导航到子页面（v0.5.6 新增透视查询卡片） |
| `/dsp-uploads/upload` | `views/DspUpload.vue` | 周需求管理 | DSP 上传 | 上传文件（v0.5.3 行为沿用） |
| `/dsp-uploads/query` | `views/WeeklyDemandQuery.vue` | 周需求管理 | 查询 | 按 4 字段精确查找已存在批次 + 事实行预览 |
| `/dsp-uploads/delete` | `views/WeeklyDemandDelete.vue` | 周需求管理 | 删除 | 按 4 字段定位 → 预览 → 确认删除 |
| `/pivot-query` | `views/PivotQuery.vue` | 周需求管理 | 透视查询 | v0.5.6 新增；v0.5.7 启用 `demand_plus_supply` + 行级视觉分组（详情见 §2.11.x）|

### 1.2 侧边栏（v0.5.1 在「任务管理」与「邮箱配置」之间插入「DSP 上传」）

| 顺序 | 名称 | icon | to |
|------|------|------|----|
| 1 | 今日概述 | `DataAnalysis` | `/` |
| 2 | 任务管理 | `List` | `/tasks` |
| 3 | **周需求管理**（v0.5.4 重命名；v0.5.1 起原名「DSP 上传」） | `Upload` | `/dsp-uploads`（hub 页） |
| 4 | 邮箱配置 | `Message` | `/email-config` |

> 图标 `Upload` 来自 `@element-plus/icons-vue`，按需 import。

### 1.3 主页 DOM 结构（v0.5.1）

布局遵循 [README §5.2](./README.md#52-布局)：左 220px 导航 + 右侧 56px 页面页头 + 主内容区。

```
<AppLayout>
  <AppSidebar>          ← 220px（第 3 项：DSP 上传）
  <AppPage>
    <AppHeader>
      └─ 左：<h1>{{ route.meta.title }}</h1>  ← "DSP 上传"
    </AppHeader>
    <AppMain>
      <DspUploadView>   ← max-width 960px (v0.5.2 起 720→960)
        <h2 class="page-title">DSP 上传</h2>
        <p class="page-hint">…</p>
        ┌─ 上传卡片 ──────────────────────────────────────────────────┐
        │ <el-card shadow="never" class="upload-card">              │
        │   <el-form :model="store.form" :rules="META_RULES">        │
        │     <el-form-item label="Excel 文件">                      │
        │       <el-button @click="triggerPick">选择 Excel 文件</el-button> │
        │       <span v-if="store.selectedFile">{{ name }}</span>    │
        │       <input ref="fileInputRef" type="file" hidden />     │
        │     </el-form-item>                                       │
        │     <el-form-item label="供应商（vendor）">                │
        │       <el-input v-model="store.form.vendor"                │
        │                :disabled="!store.hasFile || formDisabled"/> │
        │     </el-form-item>                                       │
        │     <el-form-item label="业务项（item）"> …                │
        │     <el-form-item label="子业务项（sub_item）"> …          │
        │     <el-form-item label="版本日期（version_date）">        │
        │       <el-date-picker v-model="store.form.version_date"    │
        │                       value-format="YYYY-MM-DD" />         │
        │     </el-form-item>                                       │
        │     <div class="form-actions">                             │
        │       <el-button @click="onReset">重置</el-button>         │
        │       <el-button type="primary"                            │
        │                   :loading="store.uploading"               │
        │                   :disabled="!store.canSubmit"             │
        │                   @click="onSubmit">载入</el-button>        │
        │     </div>                                                │
        │   </el-form>                                              │
        │ </el-card>                                                │
        └────────────────────────────────────────────────────────────┘
        ┌─ 结果卡片（v-if="store.hasResult"）─────────────────────────┐
        │ <el-card shadow="never" class="result-card">              │
        │   <template #header>                                      │
        │     <div class="result-header">                            │
        │       ✓ 已载入 <strong>{{ row_count }}</strong> 条数据      │
        │       <el-tag size="small">{{ vendor }}</el-tag>          │
        │       <el-tag size="small">{{ item }}</el-tag>            │
        │       <el-tag size="small">{{ sub_item }}</el-tag>        │
        │       <el-tag size="small">{{ version_date }}</el-tag>    │
        │     </div>                                                │
        │   </template>                                             │
        │   <el-table :data="store.rows" stripe>                    │
│     … 10 列：country / category / config_code / config_name /  │
│       data_type / ttl / ym / week / date / quantity            │
        │   </el-table>                                             │
        │   <el-pagination v-if="total > size" :total="..."         │
        │                   :page-sizes="[20, 50, 100]"              │
        │                   @current-change="onPageChange" />        │
        │ </el-card>                                                │
        └────────────────────────────────────────────────────────────┘
      </DspUploadView>
    </AppMain>
  </AppPage>
</AppLayout>
```

### 1.4 模块涉及组件与 store（v0.5.4）

| 类型 | 名称 | 职责 |
|------|------|------|
| Layout | `layouts/AppLayout.vue` | 整体布局：Sidebar + Page |
| Layout | `layouts/AppSidebar.vue` | 左导航；**v0.5.4 第 3 项改名「DSP 上传」→「周需求管理」**，to 仍指向 `/dsp-uploads` |
| View | `views/WeeklyDemandHub.vue` | **v0.5.4 新增** Hub 页：3 张卡片导航到 3 个子功能视图 |
| View | `views/DspUpload.vue` | DSP 上传子功能（v0.5.3 行为沿用；路由迁到 `/dsp-uploads/upload`） |
| View | `views/WeeklyDemandQuery.vue` | **v0.5.4 新增** 查询子功能：4 字段 form + 查询按钮 + 元数据 + 前 50 条事实行预览 |
| View | `views/WeeklyDemandDelete.vue` | **v0.5.4 新增** 删除子功能：4 字段 form + 「查询预览」按钮 + 「删除」按钮（带 `ElMessageBox.confirm`） |
| View | `views/PivotQuery.vue` | v0.5.6 新增 / v0.5.7 视觉分组：透视查询（三组筛选 + 一张 OLAP 透视表；启用 `demand_plus_supply` 后按 4 行/组 + 三色行级底色 + 负数 cell 红色突出）|
| Store（共享） | `stores/useDspUploadStore.js` | state（selectedFile / form / initialParsed / uploading / uploadResult / rows / rowsTotal / rowsPage / rowsSize / error）+ actions（**v0.5.2** `selectFile / updateMeta / submitUpload / loadResultRows / reset / replaceAndUpload` + **v0.5.4** `queryBatch / deleteBatch`）+ getters（hasFile / hasResult / hasEditedMeta / canSubmit） |
| Store（新增 query-only） | `stores/useDspQueryStore.js` | **v0.5.4 新增** 仅管查询：state（form / queriedBatch / queryRows / querying / error）+ action `runQuery(form)` |
| Store（新增 delete-only） | `stores/useDspDeleteStore.js` | **v0.5.4 新增** 仅管删除：state（form / preview / deleting / error）+ actions `loadPreview(form)` / `confirmDelete(preview)` |
| API | `api/dsp_uploads.js` | v0.5.3：`uploadDspFile / listDspUploads / getDspUpload / listDspUploadRows / deleteDspUpload` <br> **v0.5.4 新增**：`findBatchByVersion(meta)` —— 内部走 `listDspUploads({...meta, page:1, size:1})` |
| API | `api/pivot_query.js` | **v0.5.6 新增**：`queryPivot(req)` + `lookupCountries / lookupCategories / lookupConfigNames / lookupWeeksOfMonth` |
| Util | `utils/dspFilename.js` | 纯函数 `parseFilename(filename)` —— 与后端 `services/dsp_parser.py:parse_filename` 规则一致 |

### 1.5 新增前端工具链

| 项 | 用途 |
|------|------|
| `vitest@^2` | 测试 runner |
| `@vue/test-utils@^2` | Vue 组件测试 |
| `jsdom@^25` | 提供 DOM 环境 |
| `vitest.config.js` | 配置文件（jsdom env、`@` → `src` 别名） |
| `package.json` `scripts.test` | `vitest run` |

---

## 2. 页面的功能点

### 2.1 功能点：进入上传页

#### 入口
- 浏览器访问 `#/dsp-uploads`；
- 左侧导航条点击「DSP 上传」→ `router.push('/dsp-uploads')`。

#### 静态展示规则
- 侧边栏第 3 项激活（上传图标 `Upload`）；
- 页面页头：左侧 `meta.title` = `DSP 上传`；
- 主区：标题 + 灰色 hint + 上传卡片（结果卡片不渲染，因 `store.hasResult === false`）。

#### 进入初始态
- `store.selectedFile = null`
- `store.form = { vendor: '', item: '', sub_item: '', version_date: '' }`
- `store.uploadResult = null`
- `store.canSubmit === false`（4 个字段都为空）

### 2.2 功能点：选择 Excel 文件

#### 交互逻辑
- 用户点击「选择 Excel 文件」按钮 → 触发隐藏的 `<input type="file">` 原生选择器；
- 选中 `.xlsx` 文件：

| 阶段 | 内容 |
|------|------|
| 操作前 | 3 段输入框 disabled（未选文件）；按钮「载入」disabled（缺 version_date）|
| 触发动作 | input.change 事件 |
| 校验 | `.xlsx` 后缀（前端短路）；非 `.xlsx` → toast「仅支持 .xlsx 文件」并保持现有状态 |
| 解析 | 调 `store.selectFile(file)` → 内部 `parseFilename(file.name)` |
| **v0.5.2 新**：hasResult=true 状态 | `selectFile` 入口先清空 `uploadResult / rows / rowsTotal / rowsPage / rowsSize / rowsLoading / form.version_date / error`，再走解析路径 → 结果卡消失，进入新一轮 |
| 解析成功 | store 写入：`selectedFile = file`、`form.vendor/item/sub_item = parsed.*`、`initialParsed = {…}` |
| 解析失败（< 3 段） | toast「文件名解析失败，请确保文件名 ≥ 3 段（按 - 分隔）」；`selectedFile = null`；3 段 form 清空 |
| 校验副作用 | 3 段输入框由 disabled 变为 enabled（**只要选过文件就一直 enabled；上传成功也不会再被锁**）；按钮「载入」按 canSubmit 控制 |

### 2.3 功能点：编辑 4 个 Form 字段

**v0.5.2 修订**：4 字段在「载入」成功后**保持 enabled**（不再被 `store.hasResult` 锁死）。`disabled` 条件仅「未选文件」一项。这样用户可以在看到上一批结果时立即开始编辑下一批参数，不必先点「重置」。

| 字段 | 必填 | 校验 | 触发 | disabled 条件 |
|------|------|------|------|----------------|
| vendor | 是 | 1-64 字符（maxlength 控制 + blur 校验消息）| `blur` + `submit` | !hasFile |
| item | 是 | 1-128 字符 | `blur` + `submit` | !hasFile |
| sub_item | 是 | 1-128 字符 | `blur` + `submit` | !hasFile |
| version_date | 是 | YYYY-MM-DD；≤ 今天（含）| `change` + `submit` | !hasFile |

`formDisabled = uploading || hasResult` —— 一旦「载入」成功，整个上半 form 不可改。

#### 用户修改 3 段后
- `form.xxx` 实时更新（`store.updateMeta` 在 `blur` 触发更新快照与 form 一致性）；
- 暂不主动判定「用户编辑过」，因为「重置」二次确认基于 `hasResult` 而非「未保存修改」。

#### 用户移除文件
- 「移除」按钮（在文件名右侧，hasResult 后不显示）；
- 仅清 `store.selectedFile` 与 `store.initialParsed`，不动 form —— 用户编辑过的值保留，避免误触丢失。

### 2.4 功能点：载入（提交上传）

| 阶段 | 内容 |
|------|------|
| 操作前 | 表单 4 字段已填，文件已选 |
| 触发动作 | 点击「载入」|
| 前端校验 | `el-form.validate()`：任一必填字段失败 → 字段红字 + 按钮恢复可用（不弹 toast） |
| 接口请求（v0.5.2 主路径） | `POST /api/dsp-uploads` FormData：`file` + `vendor` + `item` + `sub_item` + `version_date` |
| 成功逻辑（201） | toast「载入成功，共 N 条数据」；上方 form 保持 enabled；下方结果卡片 fade-in；store 自动触发 `loadResultRows(1, 50)` 拉预览 |
| 失败（400 / 413 / 415 / 422 / 5xx） | `ElMessage.error(detail)`（detail 由 axios 拦截器 humanize 为字符串） |
| 失败（404 / 其它业务码） | 同上 |
| 失败（网络 / timeout） | `ElMessage.error('网络异常，请稍后重试')` |

#### 409「版本已存在」分支（v0.5.2 新增）

| 阶段 | 内容 |
|------|------|
| 操作前 | 首次 POST 命中唯一键约束 |
| 接口响应 | 409 + detail `"version (vendor=A, item=B, sub_item=C, version_date=YYYY-MM-DD) already uploaded (upload_id=N)"` |
| 解析 detail | 正则 `/upload_id=(\d+)/` 取出 `N`；取不到时降级 `ElMessageBox.alert` 路径（同 v0.5.1 行为） |
| 用户弹窗 | `ElMessageBox.confirm('该版本（vendor / item / sub_item / version_date）已存在。\n是否替换？替换将先清空当前批次的全部事实行再重新导入。', '数据已存在', { type: 'warning', confirmButtonText: '替换', cancelButtonText: '取消' })` |
| 用户选「替换」 | 调 `store.replaceAndUpload(oldId)` → DELETE `/api/dsp-uploads/{id}`（CASCADE 清事实行）→ 重发 POST |
| 替换成功 | toast「替换成功，共 N 条数据」；store.uploadResult 更新；下方结果卡刷新 |
| 替换过程中 DELETE 失败 | `ElMessage.error(detail)`；表单保留原值，用户可手动再次尝试或先选新文件 |
| 用户选「取消」 | 表单状态保留；4 字段保留当前值；结果不动；可在 UI 内修改后再「载入」（重试会再次 409） |

#### 按钮状态（v0.5.2）
| 场景 | 「载入」 | 「重置」 |
|------|---------|---------|
| 初始（无文件） | disabled | 可点 |
| 已选文件，未填 version_date | disabled | 可点 |
| 4 字段齐全 | 可点 | 可点 |
| 提交中（含替换 retry）| loading + disabled | disabled |
| 上传成功 | 可点（4 字段 enabled，可继续编辑或再选文件 → 替换 / 新批次） | 可点 |
| 替换确认弹窗中 | disabled | disabled |
| 重置后 | 回初始 | 初始状态 |

### 2.5 功能点：结果区预览（v0.5.1 新增）

| 阶段 | 内容 |
|------|------|
| 触发动作 | 上传成功自动触发 `loadResultRows(1, 50)` |
| 接口请求 | `GET /api/dsp-uploads/{id}/rows?page=1&size=50` |
| 成功渲染 | `<el-table>` 10 列（country / category / config_code / config_name / data_type / ttl / ym / week / date / quantity）+ 顶部「✓ 已载入 N 条」+ 元信息 tag 4 个 |
| 数据为空 | `el-table.empty-text`：「该批次无事实行（所有数据均被规则跳过）」 |
| rowsLoading | 表格 `v-loading="store.rowsLoading"`，期间表格区显示骨架 |
| 分页 | 仅 `store.rowsTotal > store.rowsSize`（>50）时显示；支持切换 size 20/50/100；最大页码取决于 total |
| 用户翻页 | 触发 `onPageChange / onSizeChange` → `store.loadResultRows(page, size)` |

### 2.6 功能点：重置

#### 入口
- 表单卡片底部「重置」按钮（任何状态下都可点）。

#### 行为

| `store.hasResult` | 行为 |
|--------|--------|
| `false` | 直接 `store.reset()`，无确认 |
| `true`  | 弹 `ElMessageBox.confirm('重置会清空已载入的 N 条数据，确定吗？', '重置', { type: 'warning' })`；确定 → `store.reset()`；取消 → 不动 |

`store.reset()` 全清：file / form / initialParsed / uploading / uploadResult / rows / rowsTotal 等。

### 2.7 功能点：侧边栏导航切换

| 阶段 | 内容 |
|------|------|
| 操作前 | 任意路由 |
| 触发动作 | 点击侧边栏「周需求管理」|
| 路由跳转 | `router.push('/dsp-uploads')` |
| 组件行为 | 路由切换 → `WeeklyDemandHub.vue` mount（显示 3 张子功能卡片导航） |
| 失败逻辑 | — |

### 2.8 功能点：进入 Hub 页（v0.5.4 新增）

| 阶段 | 内容 |
|------|------|
| 入口 | 侧边栏第 3 项「周需求管理」 → `router.push('/dsp-uploads')`；或直接 `#/dsp-uploads` URL |
| 静态展示 | 页面页头 `meta.title = 周需求管理`；主区显示 3 张 `<el-card>`（横向网格或纵向栈） |
| 卡片 1 | 标题「DSP 上传」+ 描述「上传 DSP 周预测 Excel 文件并入库」+ 跳转图标 → 点进 `/dsp-uploads/upload` |
| 卡片 2 | 标题「查询」+ 描述「按 (供应商 / 业务项 / 子业务项 / 版本日期) 查找已入库批次及事实行」 → `/dsp-uploads/query` |
| 卡片 3 | 标题「删除」+ 描述「按 4 字段定位批次并删除其全部事实行」 → `/dsp-uploads/delete` |
| 卡片交互 | hover 高亮 + 主色边框；点击整卡触发 `router.push` |
| 失败逻辑 | — |

### 2.9 功能点：查询（v0.5.4 新增）

| 阶段 | 内容 |
|------|------|
| 入口 | 路由 `/dsp-uploads/query` 或从 Hub 卡片 2 进入 |
| 初始态 | 4 个级联下拉框（`vendor → item → sub_item → version_date`），全部空；「查询」按钮 disabled |
| 页面加载 | `onMounted` → 调 `getDistinctVendors()` → 填充供应商下拉框 |
| 用户选择供应商 | 清空后续 3 个下拉框 + 已有查询结果；调 `getDistinctItems(vendor)` → 填充业务项下拉框 |
| 用户选择业务项 | 清空后续 2 个下拉框；调 `getDistinctSubItems(vendor, item)` → 填充子业务项下拉框 |
| 用户选择子业务项 | 清空版本日期下拉框；调 `getDistinctVersionDates(vendor, item, sub_item)` → 填充版本日期下拉框 |
| 用户选择版本日期 | 4 字段就绪；「查询」按钮 enabled |
| 点「查询」| 调 `findBatchByVersion(form)` → `GET /api/dsp-uploads?vendor=&item=&sub_item=&version_date=&page=1&size=1` |
| 命中（`items.length === 1`） | 弹出结果卡：批次元数据 (`vendor / item / sub_item / version_date / source_filename / row_count / created_at`) + `el-table` 10 列事实行前 50 条（与上传页结果卡同模板）；如果 `row_count > 50` 显示分页 |
| 未命中（`items.length === 0`） | toast「未找到该版本」；不弹结果卡；form 保留 |
| 网络 / 5xx | 沿用 `client.showApiError(err)` |
| 状态文案 | 「✓ 已找到 1 个批次，共 N 条事实行」/「未找到该版本」/「查询中…」 |
| 错误约定 | 沿用 §3 |

### 2.10 功能点：删除（v0.5.4 新增）

| 阶段 | 内容 |
|------|------|
| 入口 | 路由 `/dsp-uploads/delete` 或从 Hub 卡片 3 进入 |
| 初始态 | 4 个级联下拉框（同 §2.9）；「查询预览」+「删除」按钮 disabled |
| 页面加载 | `onMounted` → 调 `getDistinctVendors()` → 填充供应商下拉框 |
| 级联选择 | 同 §2.9 的级联逻辑：选 vendor → 拉 items；选 item → 拉 sub_items；选 sub_item → 拉 version_dates |
| 点「查询预览」| 调 `findBatchByVersion(form)`（即 `GET /api/dsp-uploads?...&size=1`） |
| 命中 | 预览卡显示：vendor / item / sub_item / version_date / source_filename / row_count / created_at + 「⚠ 删除将清空该批次的 N 条事实行（CASCADE）；删除后不可恢复」警告文案 + 「删除」按钮 enable |
| 未命中 | toast「该版本不存在」；预览卡不显；form 保留 |
| 点「删除」| 弹 `ElMessageBox.confirm("确定删除 vendor=… / item=… / sub_item=… / version_date=… 的 N 条事实行？删除后不可恢复", "删除确认", { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })` |
| 用户确认 | 调 `DELETE /api/dsp-uploads/{preview.id}` |
| 204 成功 | toast「删除成功」；清空预览卡；form 保留 |
| 网络 / 5xx / 404（已被前端 GC）| 沿用 `client.showApiError(err)` |
| 状态文案 | 「⚠ 即将删除 N 条事实行」/「该版本不存在」/「删除中…」/「删除成功」 |
| 错误约定 | 沿用 §3 |

> 注：`useDspUploadStore`（既有）保留 upload 子功能的全部状态；查询和删除页面各自内部管理级联下拉状态（无独立 store），通过 API 直接调用。每个页面独立、页面销毁时不相互影响。

### 2.11 功能点：透视查询（v0.5.6 新增）

#### 入口
- 路由 `/pivot-query` 或从 Hub 第 4 张卡片「透视查询」进入（icon `DataLine`）。

#### 页面结构

页面分两部分：**筛选区**（`el-card`）+ **结果区**（`el-card`，查询后显示）。

筛选区共 4 行：
1. **必填定位行**：vendor → item → sub_item 三级级联下拉（复用 `dsp_uploads.js` 的 `getDistinctVendors / getDistinctItems / getDistinctSubItems`）；选中后联动加载后续下拉。
2. **版本日期 + 透视类型 + 日期粒度行**：version_dates 多选（复用 `getDistinctVersionDates`）；pivot_type 单选（v0.5.7 起支持 `demand` 与 `demand_plus_supply` 两个选项；`demand_plus_supply` 模式下 version_dates 联动改为单选，详见 §2.11.2）；日期粒度单选（按周 / 按日）。
3. **业务行筛选行**（`el-collapse` 折叠，可选）：countries → categories → config_names 三级级联多选（调 `lookupCountries / lookupCategories / lookupConfigNames`）。
4. **时间维度行**：years（`el-date-picker type="year"` 单选，返回字符串如 `"2026"`，`form.years` 类型为 `string`，默认值为系统当前年份 `String(new Date().getFullYear())`）→ months（1-12 下拉多选）→ weeks（联动 years+months，调 `lookupWeeksOfMonth`）；至少选一个时间维度。

> **v0.5.7 视觉分组总览**：详情见 §2.11.3 / §2.11.4。本节只声明需求，下文子章节展开。
>
> 1 组业务维度 → 4 行（Demand / Supply / TTL_GAP / Rolling_TTLGAP）；多组业务维度 → 连续 4 行一组。
> - 行底色：`Demand + Supply` 用 `#ecf5ff`；`TTL_GAP` 用 `#fdf6ec`；`Rolling_TTLGAP` 用 `#fef0f0`。
> - cell 字体：负数仅 `TTL_GAP` / `Rolling_TTLGAP` 行触发（加粗 + 红色 `#f56c6c`）。
>
> 实现位于 `views/PivotQuery.vue`：`getRowClass(row)` 返回 `row--ds-base` / `row--ttl-gap` / `row--rolling`；`getCellClass(row, pd)` 命中负数返回 `cell-negative`。

#### 交互逻辑

| 阶段 | 内容 |
|------|------|
| 页面加载 | `onMounted` → 调 `getDistinctVendors()` 填充供应商下拉框 |
| 选 vendor | 清空后续所有下拉 + 结果；调 `getDistinctItems(vendor)` |
| 选 item | 清空后续下拉；调 `getDistinctSubItems(vendor, item)` |
| 选 sub_item | 清空版本日期 + 业务行筛选；调 `getDistinctVersionDates(vendor, item, sub_item)` |
| 选 version_dates | 清空业务行筛选；调 `lookupCountries({vendor, item, sub_item, version_dates})` |
| 选 countries | 清空下级；调 `lookupCategories({..., countries})` |
| 选 categories | 清空下级；调 `lookupConfigNames({..., countries, categories})` |
| 选 years | 清空 weeks；调 `lookupWeeksOfMonth`（单个 year，直接用 `Number(form.years)` 作为参数）|
| 选 months | 清空 weeks；调 `lookupWeeksOfMonth` |
| 点「查询」| 校验 canQuery（4 必填 + 至少一个时间维度）；调 `queryPivot(buildRequest())` |
| buildRequest 类型注意 | `form.years` 是单个字符串（如 `"2026"`），后端 `years: list[int]` 要求数组。`buildRequest` 中 `[Number(form.years)]` 包为单元素数组；`months` / `weeks` 来自 `el-select` 的 `:value` 数字，无需转换。 |
| 查询成功 | 渲染透视表；toast `查询完成：N 行 · M 个日期列` |
| 查询失败 422 | `showApiError(err)`（Pydantic 级联校验失败 / 笛卡尔积超限） |
| 查询失败 500 | `showApiError(err)`（week_dt 表不存在 / DB 不可达） |
| 点「重置」| 全部清空 + 重新加载 vendors |

#### 级联校验提示

前端在筛选区底部展示 `el-alert` 级联提示（`cascadeHint` 计算属性）：
- `config_names` 已选但 `categories` 未选 → 提示「已选择 config_names，请同时选择 categories 与 countries」
- `categories` 已选但 `countries` 未选 → 提示
- `weeks` 已选但 `months` 未选 → 提示
- 三个时间维度都未选 → 提示「请至少选择一个时间维度（years / months / weeks）」（注：`years` 有默认值恒不为空，此分支仅在极端情况下触发）

> 提示仅做 UI 引导，不阻断操作；后端 Pydantic 级联校验是最终守门人。

#### 透视表渲染

| 元素 | 说明 |
|------|------|
| 固定列（左侧） | 7 列，顺序：`version_date` / country / category / config_code / config_name / data_type / ttl；**列宽详见下表** |
| 冻结列 | `version_date` 列 `fixed="left"` 首位冻结（横向滚动时版本日期始终可见） |
| 动态列（右侧） | `result.period_columns` 中每个日期一列（按周为周起始日 YYYY-MM-DD，按日为每天 YYYY-MM-DD） |
| 交叉点 — 非 0 | `quantity > 0` → 加粗（`font-weight: 600`）+ 深色（`#303133`），class `nonzero-cell` |
| 交叉点 — 0 | `quantity === 0` 或缺失 → 灰色 `#c0c4cc`，class `zero-cell` |
| 表头 | 结果卡 header 显示：`✓ 查询结果` + tag（N 行 / M 个日期列 / K 个版本 / 按周/按日） |
| 空数据 | `total_rows === 0` → 居中提示「该筛选条件下无匹配数据。请缩小筛选范围或选择其他时间维度。」 |
| 滚动 | `el-table` 固定 `height="600"`，水平溢出 `overflow-x: auto` |

**固定列列宽**（v0.5.7.3 起维护）：

| 列 prop | label | 列宽 (px) | 备注 |
|---|---|---|---|
| `version_date` | 版本日期 | 110 | v0.5.6 沿用 |
| `country` | Country | 110 | v0.5.6 沿用 |
| `category` | Category | 110 | v0.5.6 沿用 |
| `config_code` | Config Code | 140 | v0.5.6 沿用 |
| `config_name` | Config Name | 160 | v0.5.6 沿用 |
| `data_type` | Data Type | **140**（v0.5.7.3 修订：原 90 太窄，`Rolling_TTLGAP` 13 字符无法完整显示，被截为 `...`） | 重点列 |
| `ttl` | TTL | 60 | v0.5.6 沿用（3 字符够用）|

**列宽计算原则**（v0.5.7.3 新增）：
- 公式：`列宽 ≥ header label 字符数 × 8px + padding 16px`
- 修订后 7 列总宽 = 110+110+110+140+160+140+60 = **830px**；窄屏（< 1280px 宽）情况下可横滚出现滚动条
- 后续如新增 `data_type` 衍生类型（如 `Rolling_TTLGAP_N`）需重新计算 `data_type` 列宽
| **v0.5.7 新**：行级底色 / 行级 class | 详见 §2.11.3 |
| **v0.5.7 新**：cell 字体规则（含负数突出） | 详见 §2.11.4 |

#### 2.11.1 pivot_type 选项启用（v0.5.7 新）

| 阶段 | 内容 |
|------|------|
| 选项卡 | `<el-radio-group v-model="form.pivot_type">` 内含两个 `<el-radio-button>`：<br>• `value="demand"` 标签「Demand」<br>• `value="demand_plus_supply"` 标签「Demand+Supply」（v0.5.7 起**可点击**，移除 `:disabled="true"`） |
| watch pivot_type 切换 | 通过 `@change` 或 `watch(form, 'pivot_type')` 处理：<br>1) 清空 `result.value = null`<br>2) 切到 `demand_plus_supply` 时执行 §2.11.2 的 version_dates 单选联动<br>3) 切回 `demand` 时恢复多选（已选中的版本日期保留） |
| Toast（运行中选项切换） | 「已切换到 Demand+Supply 模式」/「已切换到 Demand 模式」（仅当已成功查询过 result 后切换）|
| 失败逻辑 | — |

> 注意：v0.5.7 之前 `el-radio-button value="demand_plus_supply" :disabled="true"`；本版本起无条件启用。

#### 2.11.2 version_dates 单选联动（v0.5.7.1 修订）

后端 spec §11.1 约束 `pivot_type='demand_plus_supply'` 时 `version_dates` 仅允许 1 个。前端采用**双字段互斥**模型，彻底避免 v-model / :multiple 类型不匹配导致的"控件显示 1 个但底层数组 length > 1"bug。

**数据模型**：

```js
const form = reactive({
  // demand 模式专用：数组（多选）
  version_dates: [],
  // demand_plus_supply 模式专用：单值（string）
  version_date_single: '',
  pivot_type: 'demand',
})

// 受控 v-model：computed setter 按 pivot_type 写到不同字段
const versionDateVModel = computed({
  get() {
    return form.pivot_type === 'demand' ? form.version_dates : form.version_date_single
  },
  set(v) {
    if (form.pivot_type === 'demand') {
      form.version_dates = Array.isArray(v) ? v : []
    } else {
      form.version_date_single = typeof v === 'string' ? v : ''
    }
  },
})
```

模板：

```vue
<el-select
  v-model="versionDateVModel"
  :multiple="form.pivot_type === 'demand'"
  :collapse-tags="form.pivot_type === 'demand'"
  ...
>
```

**切换模式同步规则**（`onPivotTypeChange(newType, oldType)`）：

| 切换方向 | 同步动作 | 备注 |
|---|---|---|
| demand → `demand_plus_supply` | `version_date_single = version_dates[0] \|\| ''`；`version_dates = []` | 数组多余项丢弃，最多保留 1 个 |
| `demand_plus_supply` → demand | `version_dates = version_date_single ? [version_date_single] : []`；`version_date_single = ''` | 单值塞入数组，保证多选模式至少 1 个 |
| 任何切换 | `result = null` | 避免展示过期透视表 |
| 任何切换（`oldType` 非空）| `ElMessage.success('已切换到 X 模式')` | 用户感知模式变更 |

**校验**：`canQuery` 按 pivot_type 检查不同字段：

```js
const hasVersion =
  form.pivot_type === 'demand'
    ? form.version_dates.length >= 1
    : form.version_date_single !== ''
```

**buildRequest** 同步规则：dps 模式 → `version_dates = [version_date_single]`；demand 模式 → `version_dates = form.version_dates.slice()`。

> v0.5.7 早期版本曾尝试"同一数组字段 + 切换 :multiple + 检测 length>1 警告"，导致 Element Plus 单选模式下回显与数据不一致，已修复。详见 §8 v0.5.7.1 修订记录。

#### 2.11.3 视觉分组规范 — 行级底色（v0.5.7 新）

**目的**：让用户扫一眼透视表就能识别 4 行属于哪一类：

| `row.data_type` | 行级 class | 颜色（Element Plus token） | 含义 |
|---|---|---|---|
| `'Demand'` | `row--ds-base` | `#ecf5ff`（`--el-color-primary-light-9`） | 原始数据组 |
| `'Supply'` | `row--ds-base` | `#ecf5ff` | 原始数据组（与 Demand 同色，强调"配对"语义）|
| `'TTL_GAP'` | `row--ttl-gap` | `#fdf6ec`（`--el-color-warning-light-9`） | 单期派生指标 |
| `'Rolling_TTLGAP'` | `row--rolling` | `#fef0f0`（`--el-color-danger-light-9`） | 累计派生指标 |

实现：

```js
// PivotQuery.vue script setup
function getRowClass({ row }) {
  if (row.data_type === 'TTL_GAP') return 'row--ttl-gap'
  if (row.data_type === 'Rolling_TTLGAP') return 'row--rolling'
  return 'row--ds-base'  // Demand / Supply
}
```

```vue
<el-table
  :data="result.row_groups"
  :row-class-name="getRowClass"
  stripe   ← v0.5.7: stripe 与 row-class-name 互不冲突；保留 stripe 提供浅灰行间分隔
  ...
>
```

```css
/* PivotQuery.vue <style scoped> — v0.5.7.2 修订 */

/* 【v0.5.7.2 关键约束】
 * Vue <style scoped> 会给每个选择器末尾追加 [data-v-XXX] 属性。
 * el-table / tr / td 都是 Element Plus 子组件渲染出来的 DOM，不带本组件的 data-v-XXX，
 * 写 .pivot-view .el-table__body tr.row--xxx > td { ... } 会因末尾 [data-v-XXX] 匹配不上而整条规则失效。
 * 必须用 :deep() 把穿透部分包裹起来，让 [data-v-XXX] 只挂在最外层本组件选择器上。
 * 参考：本项目 Dashboard.vue:319 已用 :deep() 写同类行级样式。
 */
.pivot-view :deep(.el-table__body tr.row--ds-base > td)   { background-color: #ecf5ff !important; }
.pivot-view :deep(.el-table__body tr.row--ttl-gap > td)   { background-color: #fdf6ec !important; }
.pivot-view :deep(.el-table__body tr.row--rolling > td)   { background-color: #fef0f0 !important; }

/* 行底色不覆盖 cell 文本颜色（cell 文本仍按 zero-cell / nonzero-cell / cell-negative 决定）*/
.pivot-view :deep(.el-table__body tr.row--ttl-gap > td.zero-cell),
.pivot-view :deep(.el-table__body tr.row--rolling > td.zero-cell),
.pivot-view :deep(.el-table__body tr.row--ttl-gap > td.cell-negative),
.pivot-view :deep(.el-table__body tr.row--rolling > td.cell-negative) { color: inherit; }
```

> **悬停降级**：因底色已用 `!important`，鼠标 hover 时元素颜色保持不变（避免视觉跳动）。如未来需要 hover 信息，可在 `<tr>` 上加 `title` 属性。
>
> **v0.5.7 漏写 `:deep()` 的回退**：v0.5.7 原写法（无 `:deep()`）在编译后整条规则被 Element Plus 子组件 DOM 过滤掉，导致三个底色完全不生效，肉眼只剩 `stripe` 默认浅灰交替；spec §2.11.3 v0.5.7 章节内容已在 v0.5.7.2 修正，详见 §8 修订记录。

#### 2.11.4 cell 字体规则（v0.5.7 新）

按 `data_type` × `quantity 符号` 决定 cell class：

| `row.data_type` | `qty === 0` 或缺失 | `qty > 0` | `qty < 0` |
|---|---|---|---|
| Demand | `zero-cell`（灰 `#c0c4cc`）| `nonzero-cell`（加粗 `#303133`）| 不可能（Demand 行无负数）|
| Supply | `zero-cell` | `nonzero-cell` | 不可能（Supply 行无负数）|
| **TTL_GAP** | `zero-cell` | `nonzero-cell` | **`cell-negative`（加粗 `#f56c6c`）** ← 显眼 |
| **Rolling_TTLGAP** | `zero-cell` | `nonzero-cell` | **`cell-negative`（加粗 `#f56c6c`）** ← 显眼 |

实现：

```js
function getCellClass(row, periodDate) {
  const v = cellQty(row, periodDate)  // 现有 helper
  if (
    v < 0 &&
    (row.data_type === 'TTL_GAP' || row.data_type === 'Rolling_TTLGAP')
  ) {
    return 'cell-negative'
  }
  return v === 0 ? 'zero-cell' : 'nonzero-cell'
}
```

```vue
<template #default="slotProps">
  <span :class="getCellClass(slotProps.row, pd)">
    {{ cellQty(slotProps.row, pd) }}
  </span>
</template>
```

```css
/* 保留 v0.5.6 原样式 */
.zero-cell    { color: #c0c4cc; }
.nonzero-cell { font-weight: 600; color: #303133; }

/* v0.5.7 新增：负数强烈突出，仅 TTL_GAP / Rolling 命中 */
.cell-negative { font-weight: 700; color: #f56c6c; }
```

> **Demand/Supply 与 TTL_GAP/Rolling 的非负值显示完全一致**（即沿用原 `nonzero-cell` / `zero-cell` 风格），保证视觉一致性与原 spec §5.4 颜色 token 不冲突。

#### 按钮状态

| 场景 | 「查询」 | 「重置」 |
|------|---------|---------|
| 初始 | disabled（4 必填不全） | 可点 |
| 必填项不完整 | disabled | 可点 |
| 4 必填齐全（years 有默认值） | 可点 | 可点 |
| 查询中 | loading + disabled | disabled |
| 查询成功 | 可点 | 可点 |
| 重置后 | 回初始 | 初始状态 |

---

## 3. 错误码 → UI 文案（沿用 global §3.5.4 + 本模块定制）

| HTTP | 来源 | UI 展示 |
|------|------|----------|
| 400 | 后端 detail（如「version_date must be YYYY-MM-DD」、quantity 非数字）| `ElMessage.error` |
| 409 | 后端 detail 含 `upload_id=N` | `ElMessageBox.alert`（沿用 `client.showApiError`） |
| 413 | 后端 detail「file exceeds 20 MB limit」| `ElMessage.error` |
| 415 | 后端 detail「file must be .xlsx MIME type」| `ElMessage.error` |
| 422 | 后端 detail「sheet 'DSP' not found」/ 必填字段缺失 | `ElMessage.error` |
| 422 | 透视查询：Pydantic 级联校验失败 / 笛卡尔积预检超出 MAX_CARTESIAN(50000) | `showApiError(err)` → `ElMessage.error(detail)` |
| 422 | **v0.5.7 透视查询**：`pivot_type='demand_plus_supply'` 时 `version_dates` 超过 1 个 | `showApiError(err)` 沿用；前端用 §2.11.2 预先 UI 引导避免触发 |
| 500 | 透视查询：SQLAlchemy 异常（如 week_dt 表不存在） | `showApiError(err)` → `ElMessage.error(detail)` |
| 5xx | 拦截器兜底 | `ElMessage.error('服务异常，请稍后重试')` |
| 网络 | 拦截器兜底 | `ElMessage.error('网络异常，请稍后重试')` |

---

## 4. 状态文案（本模块新增补充 README §3.5.2）

| 场景 | 文案 |
|------|------|
| 选文件按钮触发器 | 「选择 Excel 文件」 |
| 移除文件 | 「移除」 |
| 提交 | 「载入」 |
| 提交成功 | 「载入成功，共 N 条数据」 |
| 替换成功（v0.5.2） | 「替换成功，共 N 条数据」 |
| 409 替换确认弹窗标题 | 「数据已存在」 |
| 409 替换确认弹窗内容 | 「该版本（vendor / item / sub_item / version_date）已存在。\n是否替换？替换将先清空当前批次的全部事实行再重新导入。」 |
| 409 替换确认弹窗按钮 | confirmButtonText=「替换」 / cancelButtonText=「取消」 |
| 重置 | 「重置」 |
| 重置二次确认 | 「重置会清空已载入的 N 条数据，确定吗？」 |
| 结果区顶部 | 「✓ 已载入 {N} 条数据」 |
| 预览表空数据 | 「该批次无事实行（所有数据均被规则跳过）」 |
| 文件名解析失败 | 「文件名解析失败，请确保文件名 ≥ 3 段（按 - 分隔）」 |
| 文件类型错 | 「仅支持 .xlsx 文件」 |
| 透视查询 — 查询成功 | 「查询完成：{N} 行 · {M} 个日期列」 |
| 透视查询 — 无数据 | 「该筛选条件下无匹配数据。请缩小筛选范围或选择其他时间维度。」 |
| 透视查询 — 必填项不完整 | 「请先完成必填项：供应商 / 业务项 / 子业务项 / 版本日期，且至少选择一个时间维度」 |
| 透视查询 — 级联提示（config_names 缺 categories） | 「已选择 config_names，请同时选择 categories 与 countries」 |
| 透视查询 — 级联提示（categories 缺 countries） | 「已选择 categories，请同时选择 countries」 |
| 透视查询 — 级联提示（weeks 缺 years+months） | 「已选择 weeks，请同时选择 years 与 months」 |
| 透视查询 — 级联提示（months 缺 years） | 「已选择 months，请同时选择 years」 |
| 透视查询 — 级联提示（无时间维度） | 「请至少选择一个时间维度（years / months / weeks）」 |
| **v0.5.7 透视查询** — 切换到 Demand+Supply 模式 | 「已切换到 Demand+Supply 模式」 |
| **v0.5.7 透视查询** — 切换回 Demand 模式 | 「已切换到 Demand 模式」 |

---

## 5. 测试计划

> 测试框架：vitest + @vue/test-utils + jsdom（首次引入，已加 devDeps）。
> 运行命令：`npm test`（`vitest run`）。
> 测试文件位于 `src/**/__tests__/*.test.js` 与 `src/views/__tests__/*.test.js`。

### 5.1 纯函数 `utils/dspFilename.js`

| 用例 | 期望 |
|------|------|
| `Arista-网络设备DSP横版-机箱-061626.xlsx` | `{vendor:'Arista', item:'网络设备DSP横版', sub_item:'机箱'}` |
| `a-b-c.xlsx` | 3 段返回 |
| `a-b-c-d.xlsx` | 取前 3 段（第 4 段丢弃）|
| `foo-bar.xlsx` | 抛 Error（at least 3 segments）|
| `''` | 抛 Error（filename is required）|
| `foo-bar`（无扩展名 + 2 段）| 抛 Error |

### 5.2 API 层 `api/dsp_uploads.js`

| 用例 | 期望 |
|------|------|
| `uploadDspFile(file, meta)` | 走 POST /dsp-uploads；FormData keys 含 file/vendor/item/sub_item/version_date；Content-Type multipart/form-data；timeout ≥ 10s |
| `listDspUploads` | GET 带 page/size params |
| `getDspUpload` | GET /dsp-uploads/{id} |
| `listDspUploadRows` | GET /dsp-uploads/{id}/rows |
| `deleteDspUpload` | DELETE /dsp-uploads/{id} |

### 5.3 Store `stores/useDspUploadStore.js`

| 用例 | 期望 |
|------|------|
| `selectFile(valid)`（无 uploadResult）| 自动填 form；snapshot initialParsed |
| `selectFile(<3 段)` | selectedFile = null；form 清空 |
| `selectFile(null)` | 清空 |
| **`selectFile(hasResult=true)`（v0.5.2）** | 入口先清 `uploadResult / rows / rowsTotal / rowsPage / rowsSize / rowsLoading / form.version_date / error`；再走解析路径；3 段由新文件解析填入 |
| **`selectFile(hasResult=true 且解析失败)`（v0.5.2）** | 旧 uploadResult 等已清空；新 selectedFile = null；3 段保持空 |
| **`formDisabled` getter 已删除（v0.5.2）** | 不存在；字段 enabled 条件仅看 `hasFile` |
| `canSubmit` getter | 4 字段齐全 → true；任一缺 / version_date 格式错 → false |
| `submitUpload` 201 | uploadResult 写入；rows 自动拉取 |
| `submitUpload` 409 | error 写入；不抛；返回 `{ok:false, error:ApiError(status:409)}` |
| `submitUpload` 未选文件 | ok=false；不上传 |
| **`replaceAndUpload(uploadId)`（v0.5.2）** | DELETE 调 + 清空 uploadResult/rows + 重发 submitUpload；成功 → 新 uploadResult；DELETE 失败 → 不重发 + error 透传 |
| `reset` | 全清回初态 |
| `hasEditedMeta` | 与 initialParsed 不一致 → true |

### 5.4 View `views/DspUpload.vue`

| 用例 | 期望 |
|------|------|
| DOM 烟雾渲染 | `.dsp-upload-view` / `.upload-card` 存在；未上传时 `.result-card` 不存在 |
| 初始 canSubmit | false |
| 选文件 + version_date → canSubmit | true |
| 上传成功 → 结果卡 | .result-card 出现；el-table 有数据 |
| 409 错误：用户选「替换」→ confirm + DELETE + POST + 成功（v0.5.2） | store.uploadResult 更新；store 调用 1 次 delete + 2 次 POST（一次 409、一次 201）；toast「替换成功，共 N 条」 |
| 409 错误：用户选「取消」（v0.5.2） | store.uploadResult 仍为 null；不调 DELETE；表单状态保留 |
| 409 错误：detail 不含 upload_id 退化路径 | 走 `ElMessageBox.alert`（同 v0.5.1 行为） |
| 全清 → reset | selectedFile / form / uploadResult 全 null/empty |

### 5.5 API 层 `api/pivot_query.js`（v0.5.6 新增）

| 用例 | 期望 |
|------|------|
| `queryPivot(req)` | POST `/pivot-query`；请求体 = req；返回 `PivotQueryResponse` |
| `lookupCountries(base)` | GET `/pivot-query/lookups/countries`；params 含 vendor/item/sub_item/version_dates(逗号分隔) |
| `lookupCategories(base)` | GET `/pivot-query/lookups/categories`；params 额外含 countries(逗号分隔) |
| `lookupConfigNames(base)` | GET `/pivot-query/lookups/config-names`；params 额外含 categories(逗号分隔) |
| `lookupWeeksOfMonth(year, month)` | GET `/pivot-query/lookups/weeks-of-month`；params 含 year/month |

### 5.6 View `views/PivotQuery.vue`（v0.5.6 新增）

| 用例 | 期望 |
|------|------|
| DOM 烟雾渲染 | `.pivot-view` 存在；`.form-card` 存在；初始无 `.result-card` |
| 初始 canQuery | false（vendor/item/sub_item/version_dates/时间维度都空） |
| 级联：选 vendor → 拉 items | `getDistinctItems` 被调用；itemOptions 更新 |
| 级联：选 item → 拉 sub_items | `getDistinctSubItems` 被调用 |
| 级联：选 sub_item → 拉 version_dates | `getDistinctVersionDates` 被调用 |
| 级联：选 version_dates → 拉 countries | `lookupCountries` 被调用；countries 清空 |
| 级联：选 countries → 拉 categories | `lookupCategories` 被调用 |
| 级联：选 categories → 拉 config_names | `lookupConfigNames` 被调用 |
| 级联：选 years → 拉 weeks | `lookupWeeksOfMonth` 被调用（遍历 years × months） |
| canQuery 条件 | 4 必填 + 至少一个时间维度 → true |
| buildRequest 构造 | 只包含非空字段；expand_to_daily 由 date_granularity 决定 |
| 查询成功 | `.result-card` 出现；el-table 有 row_groups + 动态 period_columns 列 |
| 查询成功 toast | `查询完成：N 行 · M 个日期列` |
| cellQty 辅助 | `quantities[date]` 存在 → 返回值；不存在 → 0 |
| 无数据 | `total_rows === 0` → 空提示文案 |
| 重置 | 所有 form 字段清空；所有 options 清空；result 清空；重新加载 vendors |
| **v0.5.7 新**：`pivot_type` radio 切换 | `demand_plus_supply` 单选框可点击（去除 `:disabled`）|
| **v0.5.7.1 修订**：表单字段拆分 | `form.version_dates: string[]`（demand 模式）+ `form.version_date_single: string`（dps 模式），两个字段互斥使用 |
| **v0.5.7.1 修订**：受控 v-model 桥接 | `versionDateVModel` computed setter 按 pivot_type 写到正确字段；demand 模式 set 数组 / dps 模式 set string |
| **v0.5.7.1 修订**：受控 v-model 防御 | demand 模式 setter 收到非数组 → 写空数组；dps 模式 setter 收到非字符串 → 写空字符串 |
| **v0.5.7.1 修订**：demand → dps 同步 | onPivotTypeChange 取 `version_dates[0]` 到 `version_date_single`；数组清空 |
| **v0.5.7.1 修订**：dps → demand 同步 | 单值塞入 `version_dates` 数组；`version_date_single` 清空 |
| **v0.5.7.1 修订**：canQuery 按模式 | demand 检查 `version_dates.length >= 1`；dps 检查 `version_date_single !== ''` |
| **v0.5.7.1 修订**：buildRequest 按模式 | demand → version_dates 数组副本；dps → `[version_date_single]` |
| **v0.5.7.1 修订**：versionDatesForLookup helper | demand → 数组副本；dps → `[version_date_single]`（dps 模型仍能为空，lookup 自然短路）|
| **v0.5.7.1 修订**：onReset 同时清空两字段 | `form.version_date_single = ''` |
| **v0.5.7 新**：`getRowClass` 对 Demand / Supply 行返回 `'row--ds-base'` | 行元素 class 含 `row--ds-base` |
| **v0.5.7 新**：`getRowClass` 对 TTL_GAP 行返回 `'row--ttl-gap'` | 行元素 class 含 `row--ttl-gap` |
| **v0.5.7 新**：`getRowClass` 对 Rolling_TTLGAP 行返回 `'row--rolling'` | 行元素 class 含 `row--rolling` |
| **v0.5.7 新**：`getCellClass` 对 TTL_GAP 行的负数量返回 `'cell-negative'` | cell 元素 class 含 `cell-negative` |
| **v0.5.7 新**：`getCellClass` 对 Rolling_TTLGAP 行的负数量返回 `'cell-negative'` | cell 元素 class 含 `cell-negative` |
| **v0.5.7 新**：`getCellClass` 对 Demand / Supply 行的非负数量返回 `zero-cell` / `nonzero-cell`（不返回 `cell-negative`）| 行为完全沿用 v0.5.6 |
| **v0.5.7 新**：行级 css 压制 hover | `.row--ttl-gap > td` 实际渲染背景色为 `#fdf6ec`（用 `getComputedStyle` 校验 `background-color`）|
| **v0.5.7.2 修订**：3 条 `background-color` 规则必须在 `:deep()` 选择器块内（防止 v0.5.7 漏写 `:deep()` 导致 scoped 规则失效的回归）| 静态扫描 `PivotQuery.vue` 源文件：每条 `#fdf6ec / #fef0f0 / #ecf5ff !important` 规则对应的选择器必须以 `:deep(` 包裹子组件部分 |
| **v0.5.7.3 修订**：`data_type` 列宽 = 140（防止回到旧值 90 导致 `Rolling_TTLGAP` 被截断）| 静态扫描 `PivotQuery.vue`：`prop: 'data_type'` 行 80 字符内必须出现 `width: 140`；`data_type` 行不得出现 `width: 90` |

---

## 6. 不实现的组件（明确范围）

- 不实现批次列表 / 历史导入页面（本模块入口仅 `/dsp-uploads`）；
- 不实现事实行编辑（按后端 spec §不实现的组件「只能整批删除后重传」）；
- 不在路由切换时自动 `store.reset()`（用户决定何时清）；
- el-upload 组件**没有采用** Element Plus 的 `<el-upload>` —— 直接用原生隐藏 `<input type="file">`，简化文件名校验与 store 联动；
- 不引入拖拽上传（v0.5.2 仅点击触发）；
- v0.5.2 起「重置」不再强制——选新文件即隐式重置；保留按钮作为手动清理入口；
- **v0.5.6 / v0.5.7**：透视查询不实现结果缓存（每次查询重新请求）；
- **v0.5.6 / v0.5.7**：透视查询不实现自定义排序（默认 `ORDER BY c.dt` 升序）；
- **v0.5.6 / v0.5.7**：透视查询不实现结果分页（单次返回全部数据，硬上限通过笛卡尔积预检保证）；
- **v0.5.6 / v0.5.7**：透视查询不实现跨版本 quantity 合并（每个 version_date 独立成行）；
- **v0.5.7**：透视查询行级底色**不**随主题切换——硬编码 3 个十六进制色（`#ecf5ff` / `#fdf6ec` / `#fef0f0`）而非 `var(--el-color-*)`，避免 Element Plus 主题包变量未公开导致样式漂移；如未来切主题，需在 `<style>` 中改 token。

---

## 7. 验证清单（每 PR）

- [x] `npm test` 全绿（vitest **40**+ 测；v0.5.4 新增 Hub / Query / Delete store + view 单测）
- [x] 后端 `pytest backend/tests` 全绿（**51 + 4** / v0.5.4 新增 list with filter 测试）
- [x] `frontend/src/views/WeeklyDemandHub.vue` / `WeeklyDemandQuery.vue` / `WeeklyDemandDelete.vue` / `DspUpload.vue` / `stores/useDspUploadStore.js` / `useDspQueryStore.js` / `useDspDeleteStore.js` / `utils/dspFilename.js` 全部有 docstring（JSDoc 中文）
- [x] 侧边栏第 3 项 `周需求管理` 显示并跳 `/dsp-uploads`（Hub）
- [x] 4 路由都可达：`/dsp-uploads`（Hub）、`/dsp-uploads/upload`、`/dsp-uploads/query`、`/dsp-uploads/delete`
- [x] Hub 3 张卡片各跳转正确子页面
- [x] 查询页：4 字段必填 + 「查询」按钮 enable/disable 切换 + 命中显示预览 + 未命中 toast
- [x] 删除页：4 字段必填 + 「查询预览」显示元数据与警告文案 + 二次确认弹窗 + 「删除」按钮触发 DELETE 并清空预览
- [x] 上传成功后页面下方出现 el-table 预览（v0.5.3 行为）
- [x] 上传成功后 4 字段保持 enabled（不再 formDisabled，v0.5.2 行为）
- [x] 点重置时 store.hasResult 状态下走二次确认
- [x] 缺任一必填字段被 el-form validate 拦下，不发请求
- [x] 409 + 用户选「替换」→ DELETE + POST 完成，结果卡刷新
- [x] 409 + 用户选「取消」→ 表单保留，不调 DELETE
- [x] 文件名 `dsp_upload.md` → `weekly_demand.md`（spec 文件名同步重命名）
- [x] `frontend/src/views/PivotQuery.vue` / `api/pivot_query.js` 有 docstring（JSDoc 中文）
- [x] Hub 第 4 张卡片「透视查询」显示并跳 `/pivot-query`
- [x] 透视查询页：4 必填 + 至少一个时间维度 + 「查询」按钮 enable/disable 切换
- [x] 透视查询页：业务行级联（countries → categories → config_names）联动正确
- [x] 透视查询页：时间维度级联（years → months → weeks）联动正确
- [x] 透视查询页：查询成功 → 透视表渲染（固定列 + 动态 period_columns + 交叉点 quantity）
- [x] 透视查询页：无数据 → 空提示文案
- [x] 透视查询页：重置全清 + 重新加载 vendors
- [x] 透视查询页：422 笛卡尔积超限 / 级联校验失败 → showApiError
- [x] 透视查询页：cascadeHint 级联提示正确显示
- [x] **v0.5.7**：透视查询页 `pivot_type` 单选可点击 `demand_plus_supply`（去除 `:disabled`）
- [x] **v0.5.7**：切到 `demand_plus_supply` 后 `version_dates` 控件改为单选
- [x] **v0.5.7.1 修订**：受控 v-model 按 pivot_type 把数据写入 `version_dates` / `version_date_single` 互斥字段（不再"同一数组字段切换 :multiple"，彻底消除"UI 看着 1 个但底层 length > 1"bug）
- [x] **v0.5.7.1 修订**：demand → dps 时 `version_date_single = version_dates[0]`；dps → demand 时 `version_dates = [version_date_single]`
- [x] **v0.5.7.1 修订**：`canQuery` / `buildRequest` 按 pivot_type 检查 / 构造对应字段
- [x] **v0.5.7.1 修订**：删除 `versionDatesExceedsOne` computed 与 `<el-alert>` 提示（v0.5.7 旧版残留，已不再需要）
- [x] **v0.5.7.2 修订**：npm run dev → 打开 `/pivot-query` → 切到 `pivot_type='demand_plus_supply'` → 选版本 → 查 → 肉眼确认 TTL_GAP / Rolling_TTLGAP 两行底色分别为 `#fdf6ec` / `#fef0f0`（jsdom 不能验真实渲染，需手动烟雾测试）
- [x] **v0.5.7**：Demand / Supply 行 `getComputedStyle().backgroundColor === 'rgb(236, 245, 255)'`（即 `#ecf5ff`）
- [x] **v0.5.7**：TTL_GAP 行 `backgroundColor === 'rgb(253, 246, 236)'`（即 `#fdf6ec`）
- [x] **v0.5.7**：Rolling_TTLGAP 行 `backgroundColor === 'rgb(254, 240, 240)'`（即 `#fef0f0`）
- [x] **v0.5.7**：TTL_GAP 负数量 cell class 含 `cell-negative`，computed `color === 'rgb(245, 108, 108)'` + `fontWeight === '700'`
- [x] **v0.5.7**：Rolling_TTLGAP 负数量 cell class 含 `cell-negative`
- [x] **v0.5.7**：Demand / Supply 行非负 cell class 仅 `zero-cell` / `nonzero-cell`（无 `cell-negative`）
- [x] **v0.5.7.3 修订**：npm run dev → 打开 `/pivot-query` → 切到 `pivot_type='demand_plus_supply'` → 查 → 肉眼确认 `Data Type` 列中 `Rolling_TTLGAP` header 与 cell 完整显示（不被 `...` 截断，需手动烟雾测试）

---

## 8. 修订记录

| 版本 | 章节 | 修订 |
|------|------|------|
| **v0.5.7** | 头部 / §1.1 / §1.4 / §2.11 / §3 / §4 / §5.6 / §6 / §7 / §8 | **透视查询激活 `demand_plus_supply` + 行级视觉分组**：启用 `demand_plus_supply` 单选；version_dates 联动单选 + 顶端 `<el-alert>` 引导；4 行/组（Demand+Supply / TTL_GAP / Rolling_TTLGAP）行级底色（Element Plus 浅 token 3 色）；仅 TTL_GAP/Rolling 负数量 cell 加粗红色 `#f56c6c`；测试 / 验证清单同步更新；OpenAPI / 后端无改动 |
| v0.5.7 | §2.11.1 | pivot_type radio 启用 demand_plus_supply 与切模式行为 |
| v0.5.7 | §2.11.2 | version_dates 单选联动 + versionDatesExceedsOne 校验 |
| v0.5.7 | §2.11.3 | 行级底色规范（`row--ds-base` / `row--ttl-gap` / `row--rolling`）+ css 压制 hover |
| v0.5.7 | §2.11.4 | cell 字体规则（`cell-negative` 红色加粗）+ getCellClass 实现 |
| v0.5.7 | §4 | 新增 3 条状态文案（切模式 toast + Demand+Supply 多版本提示）|
| v0.5.7 | §5.6 | 新增 11 个测试用例（含 pivot_type radio / version_dates 单选 / getRowClass / getCellClass / css 渲染）|
| v0.5.7 | §6 | 删除原 "demand_plus_supply UI 上 disabled" 一项；新增"行级底色不随主题切换"明确说明 |
| v0.5.7 | §7 | 追加 9 条视觉验证项（含 3 色 hex 与 `cell-negative` rgb + fontWeight）|
| **v0.5.7.1** | §2.11.2 / §4 / §5.6 / §7 / §8 | **fix `version_date_single` 表单字段拆分 + 受控 v-model 桥接**：v0.5.7 旧版"同一数组字段 + 切换 :multiple + length 检测"在 Element Plus 单选模式下出现"UI 看着选了 1 个但底层数组 length > 1"bug，用户报"明明选了 1 个版本日期仍提示多版本"。修复：`form.version_dates: string[]`（demand 模式）+ `form.version_date_single: string`（dps 模式）双字段互斥；`versionDateVModel` computed setter 按 pivot_type 写入正确字段；`onPivotTypeChange` 同步两个字段；删除 `versionDatesExceedsOne` 与 `<el-alert>`；OpenAPI / 后端无改动 |
| **v0.5.7.2** | §2.11.3 / §5.6 / §7 | **fix 行级底色 `:deep()` 缺失**：v0.5.7 实施时复制 spec §2.11.3 原 CSS 片段，但 spec 该片段未加 `:deep()`，Vue scoped 编译后末尾 `[data-v-XXX]` 选择器无法命中 Element Plus 子组件的 `<td>`，导致 `#fdf5ec / #fef0f0 / #ecf5ff` 三色全部失效（用户报告"TTL_GAP 和 Rolling_TTLGAP 底色没变"）。修复：spec §2.11.3 重写实现片段，加 `:deep()` 穿透 + 注明「scoped 与子组件 DOM」约束；`PivotQuery.vue` 同步改造；新增一条静态源文件检查 + 一条手动烟雾测试项（jsdom 无法验真实渲染）|
| **v0.5.7.3** | §2.11 / §5.6 / §7 | **fix `data_type` 列宽 90 → 140**：v0.5.7 实施时 `fixedColumns` 中 `data_type` width 设为 90，无 spec 依据；实测 `Rolling_TTLGAP` 13 字符在 90px 列宽下被截为 `...`。修复：spec §2.11 新加「固定列列宽」表 + 「列宽计算原则」公式（`列宽 ≥ label 字符数 × 8px + padding 16px`）；`PivotQuery.vue` data_type width 90 改 140；新增 1 条静态源文件检查 + 1 条手动烟雾测试项 |
| **v0.5.6** | 头部 / §1.1 / §1.4 / §2.11 / §3 / §4 / §5 / §6 / §7 / §8 | **新增透视查询子模块**：路由 `/pivot-query`；`PivotQuery.vue` + `api/pivot_query.js`；Hub 卡片从 3→4 张；错误码/状态文案/测试计划/不实现组件/验证清单同步更新 |
| v0.5.6 | §2.11 | 透视查询完整功能点：三组筛选（必填定位 + 业务行级联 + 时间维度）+ 透视表渲染 + 级联提示 + 重置 |
| v0.5.6 | §5.5 / §5.6 | 新增 API 层 + View 层测试计划（覆盖级联、buildRequest、cellQty、onQuery、onReset、loadWeeks） |
| **v0.5.4** | 头部 / §1.1 / §1.2 / §1.4 / §2 / §3 / §5 / §6 / §7 / §8 | **模块重命名**：DSP 上传 → 周需求管理；新增 Hub + 查询 + 删除子功能；spec 文件 `dsp_upload.md` → `weekly_demand.md` |
| v0.5.4 | §2.8 | Hub 页功能点（3 张卡片导航） |
| v0.5.4 | §2.9 | 查询页功能点（4 字段 form + 查询按钮 + 元数据 + 前 50 条事实行预览） |
| v0.5.4 | §2.10 | 删除页功能点（4 字段 form + 预览 + 二次确认 + DELETE） |
| v0.5.4 | §1.4 | store 拆分为 3 个（既有 useDspUploadStore + 新增 useDspQueryStore + useDspDeleteStore） |
| v0.5.4 | §1.4 | api/dsp_uploads.js 新增 `findBatchByVersion(meta)` 帮助函数 |
| **v0.5.3** | 头部 v0.5.3 段 | 后端解析层 v0.5.3 升级为列头文本匹配；前端 **0 改动**，仅在 spec 中声明版本向后对齐 |
| v0.5.3 | §3 错误码表 | 加一行 422 列缺失场景（detail `"Excel header missing required column '<name>'"`）；沿用 `ElMessage.error` 展示 |
| **v0.5.2** | §1.3 | 宽度 720 → 960（页面更宽以容纳预览区） |
| v0.5.2 | §2.2 | `selectFile` 在 `hasResult=true` 时自动清 uploadResult/rows/version_date（隐式重置）|
| v0.5.2 | §2.3 | 4 字段 disabled 条件由 `!hasFile \|\| formDisabled` 简化为 `!hasFile`；`formDisabled` 概念删除 |
| v0.5.2 | §2.4 | 新增 409 分支：解析 detail → ElMessageBox.confirm → replaceAndUpload（DELETE + 重发 POST）/ 取消 |
| v0.5.2 | §2.4 | 「载入」成功后 4 字段保持 enabled |
| v0.5.2 | §2.6 | 「重置」语义不变；与隐式重置（选新文件）并存 |
| v0.5.2 | §4 | 新增「替换成功」/「数据已存在」/「替换」相关 toast & confirm 文案 |
| v0.5.2 | §5.3 / §5.4 | 测试计划追加 store / view 各 2 个 case |
| v0.5.2 | §6 | 明确「重置不再强制」 |
| v0.5.2 | §7 | 删除 formDisabled 验证项；新增 960 / 隐式重置 / 409 替换 / 409 取消 4 个验证项 |
| **v0.5.1** | §1.2 | 侧边栏第 3 项「DSP 上传」新增（原「周需求管理」前身） |
| v0.5.1 | §1.3 | 上半 form 4 字段全部必填；下半结果卡片为新增 |
| v0.5.1 | §2.2 | 自动解析 `/ 字段可编辑` 联动 |
| v0.5.1 | §2.4 | 「载入」成功后整个上半 form disabled（v0.5.2 撤回）|
| v0.5.1 | §2.5 | 结果预览 50 条 + 分页（**新增**） |
| v0.5.1 | §2.6 | 重置：hasResult 时二次确认 |
| v0.5.1 | §5 | 测试计划引入 vitest 框架 |
