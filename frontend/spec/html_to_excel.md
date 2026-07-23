# HTML 转 Excel 模块规格（前端，v0.2.1 patch）

> 适配 OpenAPI：[../../backend/docs/openapi_snapshot.json](../../backend/docs/openapi_snapshot.json)（`info.version = 0.4.0`，含 4 个端点）
> - `POST /api/html-to-excel/extract`     — v0.1.0，按 title 抽
> - `POST /api/html-to-excel/inspect`     — **v0.2.0 新增**，列出所有可下载控件
> - `POST /api/html-to-excel/extract-by-index` — **v0.2.0 新增**，按 index 抽
> - `GET  /api/html-to-excel/download/{filename}` — 下载
> 适配后端 spec：[../../backend/docs/SPEC_html_to_excel.md](../../backend/docs/SPEC_html_to_excel.md)（v0.2.0）
> 前端实现版本：v0.2.1 patch
> 页面入口：`views/HtmlToExcel.vue`（路由 `/html-to-excel`）
> 全局规则遵循 [./README.md](./README.md)；本文档只描述本模块特有的页面拆解、功能点交互与测试案例。

> **v0.2.1 patch 前端侧变更**（摘要）：
>
> 1. **关键修复**：v0.2.0 把"按标题查找"埋在底部 `<el-collapse>`、命名"高级 / 手动模式（兼容 v0.1.0）"，普通用户找不到。**v0.2.1 升级为顶部 `<el-tabs>`，两个 tab 同级**：自动检测 + 按标题查找。
> 2. 默认激活 `auto` tab；用户可切到 `title` tab 输入精确 title 走 `/extract`。
> 3. 状态机作用域：`autoState` / `inspection` / `controls` / `downloadingIdx` / `topAlert` 给 auto tab 用；`titleState` / `titleForm` / `titleResult` / `titleSuggestions` / `titleCandidates` / `titlePickedCandidate` 给 title tab 用。**两 tab 互不重置**。
> 4. `form.file` 共享：顶部同一文件 picker，自动模式下上传后跑 `/inspect`；切到 title tab 直接复用。
> 5. 错误码 → UI 文案不变（遵循后端 spec §8：404/409/422/413）。

> **v0.2.0 前端侧变更**（摘要）：
>
> 1. 主流程升级为「上传 → 卡片列表 → 一键下载」（v0.2.1 已沉淀）。
> 2. 上传文件后自动调 `/inspect`；卡片网格展示。
> 3. 点卡片 → `/extract-by-index` + 浏览器下载。
>
> **v0.1.0 前端侧变更**（仅历史）：
>
> 1. 视图：上传 + title 输入 → 「下载 xlsx」按钮 + 「重置」。
> 2. 错误码：404 title_not_found / 409 multiple_matches / 422。
> 3. API：extractHtmlToExcel + downloadHtmlToExcelXlsx。

---

## 1. 整体页面结构拆解

### 1.1 路由与视图

| 路径 | 视图 | 侧边栏激活项 | `meta.title` | 说明 |
|------|------|--------------|--------------|------|
| `/html-to-excel` | `views/HtmlToExcel.vue` | HTML 转 Excel | HTML 转 Excel | 单页面：上传文件 → 卡片网格 → 点击下载；底部"高级"折叠区提供手动模式（输入 title） |

### 1.2 侧边栏

| 顺序 | 名称 | icon | to |
|------|------|------|----|
| 1 | 今日概述 | `DataAnalysis` | `/` |
| 2 | 任务管理 | `List` | `/tasks` |
| 3 | 周需求管理 | `Upload` | `/dsp-uploads` |
| 4 | 邮箱配置 | `Message` | `/email-config` |
| 5 | **HTML 转 Excel**（v0.2.0 升级） | `Document` | `/html-to-excel` |

> icon `Document` 沿用 v0.1.0。

---

## 2. 端点契约（来自 OpenAPI 快照 + backend spec）

### 2.1 `POST /api/html-to-excel/inspect`（v0.2.0 新增 / 主路径）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `html_file` | `UploadFile` (multipart) | ✅ | ≤20 MB |

**200 响应**：
```json
{
  "ok": true,
  "html_size_kb": 3058,
  "controls": [
    {
      "index": 0,
      "control_type": "table",
      "suggested_title": "Item",
      "title_source": "thead-th",
      "row_count": 23,
      "column_count": 107,
      "preview": {
        "headers": ["Line Number", "Item Status", "..."],
        "first_rows": [["1", "OK", "..."], ["2", "Alert", ""]]
      }
    }
  ]
}
```

字段约束（来自后端 spec §4.6.1/§5.8）：
- `index`：0-based stable（同次响应内）。
- `preview.headers / preview.first_rows`：限前 3 行 × 前 5 列。
- `suggested_title`：可能为空（fallback）。

**错误响应**（HTTPException 全部走 SPEC §8）：
| HTTP | error | UI 行为 |
|------|-------|---------|
| 413 | （detail 字符串） | `ElMessage.error`：文件过大 |
| 422 | `html_unparseable` / `empty_html` | `ElMessage.error`：解析失败 |
| 200, `controls: []` | （合法） | 卡片网格显示空态「未发现表格」 |

### 2.2 `POST /api/html-to-excel/extract-by-index`（v0.2.0 新增 / 主路径）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `html_file` | `UploadFile` (multipart) | ✅ | 同 §2.1 |
| `index` | `int` (form) | ✅ | 来自 `/inspect` 响应的 `controls[i].index` |
| `filename_hint` | `string` (form) | ❌ | 可选下载文件名提示 |

**200 响应**（与 `/extract` 同 schema）：
```json
{
  "ok": true,
  "control_type": "table",
  "matched_title": "Item",
  "xlsx_path": "D:\\\\...\\\\Item_20260721_112510.xlsx",
  "download_filename": "Item_20260721_112510.xlsx",
  "rows": 23,
  "columns": 107,
  "warnings": []
}
```

**错误响应**：
| HTTP | error | UI 行为 |
|------|-------|---------|
| 413 | （detail 字符串） | `ElMessage.error`：文件过大 |
| 422 | `index_out_of_range` | 弹 `el-alert`「索引越界，可选以下控件」+ 候选 `candidates` 列表（如旧 v0.1.0 的 404 建议），不重置已有卡片 |
| 422 | `html_unparseable` / `empty_html` | `ElMessage.error`：解析失败 |
| 5xx | （detail 字符串） | `ElMessage.error`：服务异常 |

### 2.3 `POST /api/html-to-excel/extract`（v0.1.0 兼容 / 高级模式）

完整保留 v0.1.0 行为，供手动输入标题路径使用。

### 2.4 `GET /api/html-to-excel/download/{filename}`

不变。浏览器侧用 `<a download>` 触发。

---

## 3. 页面拆解（`views/HtmlToExcel.vue`）

### 3.1 状态机（v0.2.0 重写）

```
IDLE
  ↓ onFileChange（自动触发）
UPLOADING_INSPECT   (loading=true, file=selected)
  ↓ 200 OK → controls[]
INSPECTED            (卡片网格渲染)
  ↓ 用户点击卡片 → onDownloadByIndex(card.index)
DOWNLOADING          (loading=true, single-card)
  ↓ 200 OK → xlsx
INSPECTED            (回到网格态，结果 toast 提示)

UPLOADING_INSPECT 失败：
  - 422 (文件超大 / 解析失败) → state=IDLE + ElMessage.error
INSPECTED 中按卡片下载失败：
  - 422 index_out_of_range → state=INSPECTED，渲染一个 transient el-alert
  - 5xx → state=INSPECTED + ElMessage.error
```

### 3.2 UI 结构（v0.2.0 重写）

| 区块 | 组件 | 行为 |
|------|------|------|
| 页头 | `<h2>HTML 转 Excel</h2>` + 提示语 | 静态 |
| 主输入卡 | `<el-card>` 内：文件 input（点选 / 拖拽） | 文件变化即触发 `/inspect` |
| 进度指示 | `<el-progress v-if="state==='UPLOADING_INSPECT'">` | inspect 期间 |
| 卡片网格 | `<div class="card-grid">` 每条 control = `<el-card class="control-card">` | 见 §3.3 |
| 空态 | 0 controls 时：`<el-empty>` + 「未发现表格」 | |
| 错误 Alert | 卡片网格上方：`<el-alert v-if="errorMessage">` | 越界 / 索引失败 / 服务错误 |
| 重置按钮 | 右上角「重新选择文件」 | 清空 file + state=IDLE |
| 高级 / 手动模式 | `<el-collapse>` 折叠面板 | 见 §3.4 |
| 全局 Toast | 任何 throw → `ElMessage.error/warning` | 复用 `showApiError` |

### 3.3.x 卡片内容（卡片网格内每张 card）

```
┌─ Card ────────────────────────────────────┐
│ 序号：#0                           type：table │
│ Title: Item   (源：thead-th)               │
│ 行数：23   列数：107    [⬇ 下载]            │
│                                           │
│ Preview：                                 │
│   Headers: Line Number | Item Status | ...│
│   Row 1:  1       | OK         | ...       │
│   Row 2:  2       | Alert      | ...       │
│   Row 3:  3       | OK         | ...       │
└───────────────────────────────────────────┘
```

- `type` 用 `<el-tag size="small">` 着色（table → primary、div_grid → success、field_group → warning、list_block → info）。
- 「下载」按钮：onClick → `onDownloadByIndex(card.index)`。

### 3.4 Tab B · 按标题查找（v0.1.0 兼容）

```vue
<el-collapse>
  <el-collapse-item title="高级 / 手动模式（按 title 抽取，与 v0.1.0 一致）">
    <el-form>
      <el-form-item label="控件标题">
        <el-input v-model="manualTitle" />
      </el-form-item>
      <el-form-item label="文件名提示">
        <el-input v-model="manualFilenameHint" />
      </el-form-item>
      <el-button @click="onManualExtract">抽取 xlsx</el-button>
    </el-form>
  </el-collapse-item>
</el-collapse>
```

独立子状态机（与主流程互不干扰）：
- 状态：`manualState ∈ {'IDLE', 'EXTRACTING', 'OK', 'ERROR'}`。
- 「抽取 xlsx」 → `extractHtmlToExcel(file, manualTitle, ...)` → 成功 toast + 自动下载。
- 文件变化 → 自动重置 manualState=IDLE。

### 3.5 文件选择交互

| 行为 | UI |
|------|----|
| 点击「选择 HTML 文件」 | 触发 `<input type="file">` click |
| 文件选择后 | 立即调 `/inspect`，结果显示 |
| 切换文件 | state 重置 → 重新调 `/inspect` |
| 文件 > 20 MB | 前端拦截 + ElMessage.error，不调 API |

---

## 4. 关键交互细节

### 4.1 卡片下载（主流程）

```js
async function onDownloadByIndex(idx) {
  if (!form.file || state.value !== 'INSPECTED') return
  const card = inspection.value.controls.find(c => c.index === idx)
  if (!card) return
  downloadingIdx.value = idx
  state.value = 'DOWNLOADING'
  try {
    const res = await extractHtmlToExcelByIndex(form.file, idx, {
      filename_hint: card.suggested_title || `control_${idx}`,
    })
    const blob = await downloadHtmlToExcelXlsx(res.download_filename)
    downloadBlob(blob, res.download_filename)
    ElMessage.success(`已下载「${res.matched_title}」${res.rows} 行 × ${res.columns} 列`)
  } catch (err) {
    handleDownloadError(err)
  } finally {
    downloadingIdx.value = null
    state.value = 'INSPECTED'
  }
}
```

`handleDownloadError`：
- ApiError.status === 422 且 `detail.error === 'index_out_of_range'`：渲染 `el-alert` + 列出 `detail.candidates` 作提示（不重置卡片）。
- ApiError.status === 422 且 `detail.error === 'html_unparseable'` 或 `empty_html`：state=IDLE。
- 其它走 `showApiError(err)`。

### 4.2 高级模式（v0.1.0 行为完整保留）

```js
async function onManualExtract() {
  if (!form.file || !manualTitle.value) return
  manualState.value = 'EXTRACTING'
  try {
    const res = await extractHtmlToExcel(form.file, manualTitle.value, {
      filename_hint: manualFilenameHint.value || null,
      auto_select_first: true,
    })
    const blob = await downloadHtmlToExcelXlsx(res.download_filename)
    downloadBlob(blob, res.download_filename)
    manualState.value = 'OK'
    ElMessage.success(`已抽取「${res.matched_title}」`)
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      // 渲染 el-alert：未找到 + suggestions 回填
      manualState.value = 'NOT_FOUND'
    } else if (err instanceof ApiError && err.status === 409) {
      manualState.value = 'AMBIGUOUS'
    } else {
      showApiError(err)
      manualState.value = 'IDLE'
    }
  } finally {
    // ...
  }
}
```

### 4.3 索引越界处理

`onDownloadByIndex` 失败 422 + `index_out_of_range`：

```js
function handleDownloadError(err) {
  if (err instanceof ApiError && err.status === 422 && err.detail?.error === 'index_out_of_range') {
    errorMessage.value = {
      type: 'warning',
      title: `索引 ${err.detail.message?.match(/index (\d+)/)?.[1] ?? '?'} 越界`,
      candidates: err.detail.candidates || [],
    }
    return
  }
  // ...
}
```

UI 渲染一个顶部 `el-alert` 列出 candidates 为可点击 tag（点一下不会回到指定 index，只是提示）。

---

## 5. API 客户端（`src/api/htmlToExcel.js`）

> **v0.6.0 multipart 上传约定**：依 [./README.md §3.6](./README.md#36-formdata-上传规则v060-新增) 全局规则，**不要显式设 `Content-Type`**，让 axios 自动追加 `boundary=...`；`api/client.js` request interceptor 已对历史代码兜底。

```js
import client from './client.js'

export function inspectHtmlControls(file) {
  const form = new FormData()
  form.append('html_file', file)
  return client.post('/html-to-excel/inspect', form, {
    timeout: 60000,
  })
}

export function extractHtmlToExcelByIndex(file, index, opts = {}) {
  const { filename_hint = null } = opts
  const form = new FormData()
  form.append('html_file', file)
  form.append('index', String(index))
  if (filename_hint) form.append('filename_hint', filename_hint)
  return client.post('/html-to-excel/extract-by-index', form, {
    timeout: 60000,
  })
}

export function extractHtmlToExcel(file, title, opts = {}) { /* v0.1.0 保留 */ }
export function downloadHtmlToExcelXlsx(filename) { /* v0.1.0 保留 */ }
```

---

## 6. 文件清单

### 6.1 新增

| 路径 | 用途 |
|------|------|
| 现有 `frontend/spec/html_to_excel.md` | **本文档升级到 v0.2.0**（覆盖 v0.1.0 内容） |

### 6.2 修改

| 路径 | 变更 |
|------|------|
| `frontend/src/api/htmlToExcel.js` | 新增 `inspectHtmlControls()` + `extractHtmlToExcelByIndex()` |
| `frontend/src/views/HtmlToExcel.vue` | **重写**：主流程改 inspect + 卡片网格；高级模式折叠面板 |
| `frontend/src/api/__tests__/htmlToExcel.test.js` | 新增 4 用例（inspect 走 POST + 大文件 + ApiError；extract-by-index 走 POST + form fields） |
| `frontend/src/views/__tests__/HtmlToExcel.test.js` | 重写为新状态机测试：自动 inspect 卡片渲染、按 idx 下载、index_out_of_range、empty controls、手动模式 |

---

## 7. 测试计划

### 7.1 API 单测（`__tests__/htmlToExcel.test.js`）

| # | 用例 | 期望 |
|---|------|------|
| 1 | `inspectHtmlControls(file)` 走 POST `/html-to-excel/inspect`，Content-Type multipart，timeout ≥ 10000 | ok |
| 2 | `inspectHtmlControls` 4xx → 抛 ApiError | ok |
| 3 | `extractHtmlToExcelByIndex(file, 0, opts)` 走 POST `/html-to-excel/extract-by-index`，form `html_file` + `index` + (可选 `filename_hint`) | ok |
| 4 | `extractHtmlToExcelByIndex` URL encode / 多种 index 数值 | ok |

> v0.1.0 的 extractHtmlToExcel / downloadHtmlToExcelXlsx 测试保留。

### 7.2 视图单测（`__tests__/HtmlToExcel.test.js` 重写）

| # | 用例 | 期望 |
|---|------|------|
| 1 | 初始 state=IDLE，卡片网格不渲染，文件输入按钮可见 | ok |
| 2 | 文件变化 → 自动调 `/inspect`，200 OK → 渲染卡片网格（每张卡片含 type / title / rows / cols / 下载按钮） | ok |
| 3 | inspect 返空 controls → 显示空态「未发现表格」 | ok |
| 4 | 点击卡片下载按钮 → 调 `/extract-by-index` + `downloadHtmlToExcelXlsx` + `downloadBlob` | ok |
| 5 | 卡片下载失败 422 + index_out_of_range → 顶部展示 el-alert + candidates | ok |
| 6 | 文件 > 20 MB → ElMessage.error，不调 API | ok |
| 7 | 高级模式：手动 mode 走 `/extract` + 下载 | ok |
| 8 | 高级模式：404 title_not_found → 渲染 suggestions + 回填到 manualTitle | ok |
| 9 | 切换文件 → 清空状态 → 重新调 `/inspect` | ok |

### 7.3 端到端验证（手测）

| # | 步骤 |
|---|------|
| 1 | 上传 `table.txt`（3MB NetSuite 销售订单） |
| 2 | 期望：秒级渲染 ~167 个控件卡片 |
| 3 | 找到 items_splits 卡片（行数 23、列数 107）点「下载」 |
| 4 | 期望：浏览器下载 xlsx，openpyxl 重读 24 rows × 107 cols |

---

## 8. 兼容性 / 不做什么

- **不做** 一次性下载多张（v0.1.0 决策过，单次只下载 1 张）。
- **不做** 持久化（刷新即清空）。
- **不做** Pinia store（视图级 ref 足够）。
- **不做** HTML 内容预览 / 解析过程可视化。
- **不做** 多文件批量。

---

## 9. 修订记录

| 日期 | 版本 | 变更人 | 说明 |
|------|------|--------|------|
| 2026-07-21 | v0.1.0 | opencode | 初稿（上传 + title 输入 + 抽 xlsx） |
| 2026-07-21 | v0.2.0 | opencode | 升级：inspect + 卡片网格 + 一键下载；高级模式保留 v0.1.0 行为 |
