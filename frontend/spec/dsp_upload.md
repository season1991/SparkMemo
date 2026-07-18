# DSP 上传模块规格（前端）

> 适配 OpenAPI：[../../backend/openapi/dsp_uploads.json](../../backend/openapi/dsp_uploads.json)（`info.version = 0.5.1`，路径 `/api/dsp-uploads`；schema `DspUploadRead` / `DspUploadRowRead`）
> 适配后端 spec：[../../backend/spec/dsp_upload.md](../../backend/spec/dsp_upload.md)（v0.5.1）
> 前端实现版本：v0.5.1（POST API 升级：4 个必填 Form 字段 `vendor / item / sub_item / version_date`）
> 页面入口：`views/DspUpload.vue`（路由 `/dsp-uploads`）
> 全局规则遵循 [./README.md](./README.md)；本文档只描述本模块特有的页面拆解、功能点交互与测试案例。

---

## 1. 整体页面结构拆解

### 1.1 路由与视图

| 路径 | 视图 | 侧边栏激活项 | `meta.title` | 说明 |
|------|------|------------|--------------|------|
| `/dsp-uploads` | `views/DspUpload.vue` | DSP 上传 | DSP 上传 | 单页向导：选文件 → 自动解析 + 编辑 4 字段 → 载入 → 下方结果卡预览前 50 条 |

### 1.2 侧边栏（v0.5.1 在「任务管理」与「邮箱配置」之间插入「DSP 上传」）

| 顺序 | 名称 | icon | to |
|------|------|------|----|
| 1 | 今日概述 | `DataAnalysis` | `/` |
| 2 | 任务管理 | `List` | `/tasks` |
| 3 | **DSP 上传**（v0.5.1 新增） | `Upload` | `/dsp-uploads` |
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
      <DspUploadView>   ← max-width 720px
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
        │     … 9 列：country / category / config_code / data_type /  │
        │       ttl / ym / week / date / quantity                    │
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

### 1.4 模块涉及组件与 store

| 类型 | 名称 | 职责 |
|------|------|------|
| Layout | `layouts/AppLayout.vue` | 整体布局：Sidebar + Page |
| Layout | `layouts/AppSidebar.vue` | 左导航；**v0.5.1 追加第 3 项「DSP 上传」** |
| View | `views/DspUpload.vue` | 单页向导；上半 el-form + 下半结果 el-card |
| Store | `stores/useDspUploadStore.js` | state（selectedFile / form / initialParsed / uploading / uploadResult / rows / rowsTotal / rowsPage / rowsSize / error）+ actions（selectFile / updateMeta / submitUpload / loadResultRows / reset）+ getters（hasFile / hasResult / hasEditedMeta / canSubmit） |
| API | `api/dsp_uploads.js` | `uploadDspFile / listDspUploads / getDspUpload / listDspUploadRows / deleteDspUpload` |
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
| 操作前 | 3 段输入框 disabled；按钮「载入」disabled |
| 触发动作 | input.change 事件 |
| 校验 | `.xlsx` 后缀（前端短路）；非 `.xlsx` → toast「仅支持 .xlsx 文件」并保持现有状态 |
| 解析 | 调 `store.selectFile(file)` → 内部 `parseFilename(file.name)` |
| 解析成功 | store 写入：`selectedFile = file`、`form.vendor/item/sub_item = parsed.*`、`initialParsed = {…}` |
| 解析失败（< 3 段） | toast「文件名解析失败，请确保文件名 ≥ 3 段（按 - 分隔）」；`selectedFile = null`；3 段 form 清空 |
| 校验副作用 | 3 段输入框由 disabled 变为 enabled；按钮「载入」仍 disabled（缺 version_date） |

### 2.3 功能点：编辑 4 个 Form 字段

| 字段 | 必填 | 校验 | 触发 | disabled 条件 |
|------|------|------|------|----------------|
| vendor | 是 | 1-64 字符（maxlength 控制 + blur 校验消息）| `blur` + `submit` | !hasFile \|\| formDisabled |
| item | 是 | 1-128 字符 | `blur` + `submit` | 同上 |
| sub_item | 是 | 1-128 字符 | `blur` + `submit` | 同上 |
| version_date | 是 | YYYY-MM-DD；≤ 今天（含）| `change` + `submit` | 同上 |

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
| 接口请求 | `POST /api/dsp-uploads` FormData：`file` + `vendor` + `item` + `sub_item` + `version_date` |
| 成功逻辑（201） | toast「载入成功，共 N 条数据」；上半 form 全部 disabled；下方结果卡片 fade-in；store 自动触发 `loadResultRows(1, 50)` 拉预览 |
| 失败（400 / 413 / 415 / 422 / 5xx） | `ElMessage.error(detail)`（detail 由 axios 拦截器 humanize 为字符串） |
| 失败（409） | `ElMessageBox.alert(detail, '无法操作', { type: 'warning' })`（沿用 `client.showApiError`） |
| 失败（网络 / timeout） | `ElMessage.error('网络异常，请稍后重试')` |

#### 按钮状态
| 场景 | 「载入」 | 「重置」 |
|------|---------|---------|
| 初始（无文件） | disabled | 可点 |
| 已选文件，未填 version_date | disabled | 可点 |
| 4 字段齐全 | 可点 | 可点 |
| 提交中 | loading + disabled | disabled |
| 上传成功 | disabled（formDisabled=true）| 可点 |
| 重置后 | 回初始 | 初始状态 |

### 2.5 功能点：结果区预览（v0.5.1 新增）

| 阶段 | 内容 |
|------|------|
| 触发动作 | 上传成功自动触发 `loadResultRows(1, 50)` |
| 接口请求 | `GET /api/dsp-uploads/{id}/rows?page=1&size=50` |
| 成功渲染 | `<el-table>` 9 列（country / category / config_code / data_type / ttl / ym / week / date / quantity）+ 顶部「✓ 已载入 N 条」+ 元信息 tag 4 个 |
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
| 触发动作 | 点击侧边栏「DSP 上传」|
| 路由跳转 | `router.push('/dsp-uploads')` |
| 组件行为 | 路由切换 → `DspUpload.vue` mount → 状态由 store 全局持久（刷新组件不丢；路由切走不主动 reset） |
| 失败逻辑 | — |

> 注：因为本模块无 `onMounted` 拉取，组件级别的 state reset 是由用户在「重置」按钮主动触发；如未来需要「离开即清」，可在 `onBeforeUnmount` 调 `store.reset()`。

---

## 3. 错误码 → UI 文案（沿用 global §3.5.4 + 本模块定制）

| HTTP | 来源 | UI 展示 |
|------|------|----------|
| 400 | 后端 detail（如「version_date must be YYYY-MM-DD」、quantity 非数字）| `ElMessage.error` |
| 409 | 后端 detail 含 `upload_id=N` | `ElMessageBox.alert`（沿用 `client.showApiError`） |
| 413 | 后端 detail「file exceeds 20 MB limit」| `ElMessage.error` |
| 415 | 后端 detail「file must be .xlsx MIME type」| `ElMessage.error` |
| 422 | 后端 detail「sheet 'DSP' not found」/ 必填字段缺失 | `ElMessage.error` |
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
| 重置 | 「重置」 |
| 重置二次确认 | 「重置会清空已载入的 N 条数据，确定吗？」 |
| 结果区顶部 | 「✓ 已载入 {N} 条数据」 |
| 预览表空数据 | 「该批次无事实行（所有数据均被规则跳过）」 |
| 文件名解析失败 | 「文件名解析失败，请确保文件名 ≥ 3 段（按 - 分隔）」 |
| 文件类型错 | 「仅支持 .xlsx 文件」 |

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
| `selectFile(valid)` | 自动填 form；snapshot initialParsed |
| `selectFile(<3 段)` | selectedFile = null；form 清空；error 写入 |
| `selectFile(null)` | 清空 |
| `canSubmit` getter | 4 字段齐全 → true；任一缺 / version_date 格式错 → false |
| `submitUpload` 201 | uploadResult 写入；rows 自动拉取 |
| `submitUpload` 409 | error 写入；不抛 |
| `submitUpload` 未选文件 | ok=false；不上传 |
| `reset` | 全清回初态 |
| `hasEditedMeta` | 与 initialParsed 不一致 → true |

### 5.4 View `views/DspUpload.vue`

| 用例 | 期望 |
|------|------|
| DOM 烟雾渲染 | `.dsp-upload-view` / `.upload-card` 存在；未上传时 `.result-card` 不存在 |
| 初始 canSubmit | false |
| 选文件 + version_date → canSubmit | true |
| 上传成功 → 结果卡 | .result-card 出现；el-table 有数据 |
| 409 错误 → 状态 | store.error 写入；view 不崩 |
| 全清 → reset | selectedFile / form / uploadResult 全 null/empty |

---

## 6. 不实现的组件（明确范围）

- 不实现批次列表 / 历史导入页面（本模块入口仅 `/dsp-uploads`）；
- 不实现事实行编辑（按后端 spec §不实现的组件「只能整批删除后重传」）；
- 不在路由切换时自动 `store.reset()`（用户决定何时清）；
- el-upload 组件**没有采用** Element Plus 的 `<el-upload>` —— 直接用原生隐藏 `<input type="file">`，简化文件名校验与 store 联动；
- 不引入拖拽上传（v0.5.1 仅点击触发）。

---

## 7. 验证清单（每 PR）

- [x] `npm test` 全绿（vitest 32 测）
- [x] 后端 `pytest backend/tests` 全绿（193+ / 含 v0.5.1 新增 1 测）
- [x] `frontend/src/views/DspUpload.vue` / `stores/useDspUploadStore.js` / `utils/dspFilename.js` 全部有 docstring（JSDoc 中文）
- [x] 侧边栏第 3 项 `DSP 上传` 显示并跳 `/dsp-uploads`
- [x] 上传成功后页面下方出现 el-table 预览
- [x] 上传成功后改任一字段不再触发新上传（formDisabled）
- [x] 点重置时 store.hasResult 状态下走二次确认
- [x] 缺任一必填字段被 el-form validate 拦下，不发请求

---

## 8. 修订记录

| 版本 | 章节 | 修订 |
|------|------|------|
| **v0.5.1** | §1.2 | 侧边栏第 3 项「DSP 上传」新增 |
| v0.5.1 | §1.3 | 上半 form 4 字段全部必填；下半结果卡片为新增 |
| v0.5.1 | §2.2 | 自动解析 `/ 字段可编辑` 联动 |
| v0.5.1 | §2.4 | 「载入」成功后整个上半 form disabled |
| v0.5.1 | §2.5 | 结果预览 50 条 + 分页（**新增**） |
| v0.5.1 | §2.6 | 重置：hasResult 时二次确认 |
| v0.5.1 | §5 | 测试计划引入 vitest 框架 |
