# DSP 上传前端模块 Todo List

> 适配规格：`frontend/spec/dsp_upload.md`（SparkMemo v0.5.1）
> 测试策略：vitest + @vue/test-utils + jsdom（首次引入）；`npm test` 期望全绿。
> 测试组织：按层分文件（`utils/__tests__/dspFilename.test.js` / `api/__tests__/dsp_uploads.test.js` / `stores/__tests__/useDspUploadStore.test.js` / `views/__tests__/DspUpload.test.js`）。

## 总体阶段

- [x] **Phase 0**  规格定稿（`frontend/spec/dsp_upload.md` 与更新 `backend/spec/dsp_upload.md`）
- [x] **Phase 1**  生成 Todo List（本文件）
- [x] **Phase 2**  测试驱动 - 全红后全绿（vitest 单测按层实现）
- [x] **Phase 3**  前端实现 - 全绿（`src/` 代码让 vitest 全过）
- [x] **Phase 4**  生成 OpenAPI 已重导（由后端负责，与前端 Module 共用）
- [x] **Phase 6**  收尾（README / 全量回归）

---

## Phase 2 — 测试驱动（已落地，32 条）

### 2.0 测试基础设施
- [x] **2.0.1** 安装 `vitest@^2` + `@vue/test-utils@^2` + `jsdom@^25`（devDeps）
- [x] **2.0.2** 新建 `frontend/vitest.config.js`（jsdom env、`@` → `src` 别名、`<rootDir>=frontend`）
- [x] **2.0.3** `frontend/package.json` 加 `"test": "vitest run"`
- [x] **2.0.4** 测试文件统一放 `src/**/__tests__/*.test.js`

### 2.1 纯函数（spec §5.1）→ `utils/__tests__/dspFilename.test.js`
- [x] **2.1.1** 真实样本文件名解析 → Arista / 网络设备DSP横版 / 机箱
- [x] **2.1.2** 三段直接返回
- [x] **2.1.3** 四段取前三
- [x] **2.1.4** 两段抛错
- [x] **2.1.5** 空串抛错
- [x] **2.1.6** 无扩展名 + 两段仍抛错

### 2.2 API 层（spec §5.2）→ `api/__tests__/dsp_uploads.test.js`
- [x] **2.2.1** `uploadDspFile` 走 POST + 4 FormData keys + multipart Content-Type
- [x] **2.2.2** `uploadDspFile` timeout ≥ 10s
- [x] **2.2.3** `listDspUploads` 带分页 params
- [x] **2.2.4** `getDspUpload` 路径含 id
- [x] **2.2.5** `listDspUploadRows` 路径含 id + 分页
- [x] **2.2.6** `deleteDspUpload` 走 DELETE

### 2.3 Store（spec §5.3）→ `stores/__tests__/useDspUploadStore.test.js`
- [x] **2.3.1** `selectFile(valid)` 自动填 + snapshot initialParsed
- [x] **2.3.2** `selectFile(<3 段)` 清空 + error
- [x] **2.3.3** `selectFile(null)` 清空
- [x] **2.3.4** `canSubmit` 全填 → true
- [x] **2.3.5** `canSubmit` version_date 空 → false
- [x] **2.3.6** `canSubmit` version_date 格式错 → false
- [x] **2.3.7** `canSubmit` 未选文件 → false
- [x] **2.3.8** `submitUpload` 201 → 自动 loadResultRows
- [x] **2.3.9** `submitUpload` 未选文件 → 早返回
- [x] **2.3.10** `submitUpload` 409 → error 写入
- [x] **2.3.11** `reset` 全清
- [x] **2.3.12** `hasEditedMeta` 区分编辑与否

### 2.4 View（spec §5.4）→ `views/__tests__/DspUpload.test.js`
- [x] **2.4.1** DOM 烟雾渲染：.dsp-upload-view / .upload-card 存在；.result-card 不存在
- [x] **2.4.2** 未上传时 canSubmit === false
- [x] **2.4.3** 选文件未填 version_date → canSubmit === false
- [x] **2.4.4** 选文件 + version_date → canSubmit === true
- [x] **2.4.5** 上传成功 → .result-card 出现
- [x] **2.4.6** 上传成功后 form 数据保留
- [x] **2.4.7** 409 错误 → store.error 写入，不抛
- [x] **2.4.8** reset → 全清

---

## Phase 3 — 前端实现（已落地）

### 3.1 路由 / 导航
- [x] **3.1.1** `src/router/index.js` 注册 `/dsp-uploads`（`meta.title='DSP 上传'`）+ import `DspUpload` 视图
- [x] **3.1.2** `src/layouts/AppSidebar.vue` 第 3 项插入「DSP 上传」，icon = `Upload`

### 3.2 纯函数
- [x] **3.2.1** `src/utils/dspFilename.js` —— 与后端 `services/dsp_parser.py:parse_filename` 规则一致（含 v0.5.1 状态说明）

### 3.3 API 层
- [x] **3.3.1** `src/api/dsp_uploads.js` 五个函数：`uploadDspFile` 走 multipart FormData + 4 form fields；`listDspUploads` / `getDspUpload` / `listDspUploadRows` / `deleteDspUpload`

### 3.4 Store
- [x] **3.4.1** `src/stores/useDspUploadStore.js` 完整实现：state + getters（hasFile / hasResult / hasEditedMeta / canSubmit） + actions（selectFile / updateMeta / submitUpload / loadResultRows / reset）
- [x] **3.4.2** 4 字段必填规则校验：`/^\d{4}-\d{2}-\d{2}$/` + ≤ 今天
- [x] **3.4.3** 错误不抛：`submitUpload` 返回 `{ok, response?, error?}`；调用方按 status 路由 toast

### 3.5 View
- [x] **3.5.1** `src/views/DspUpload.vue` 单页实现：
  - 上半部分 el-form（4 字段；3 段 + 文件 disabled until selectedFile）
  - 下半部分 el-card（v-if="store.hasResult"）：el-tag 元信息 + el-table 9 列 + el-pagination（>50 时）
  - 「载入」按钮：canSubmit 控制 disabled + uploading 时 loading
  - 「重置」按钮：hasResult 时 ElMessageBox.confirm
  - 错误处理沿用 `client.showApiError`
  - **v0.5.2**：onSubmit 多级 409 处理—— 解析 detail → ElMessageBox.confirm → 用户选「替换」→ `store.replaceAndUpload(uploadId)`；选「取消」→ 表单保留
  - **v0.5.2**：4 字段 disabled 仅看 `!store.hasFile`，不锁；CSS `max-width: 960px`
- [x] **3.5.2** `el-upload` 不引入，直接用隐藏 `<input type="file">` 触发
- [x] **3.5.3** **v0.5.2**：store 新增 `replaceAndUpload(uploadId)`（DELETE + 清空 + submitUpload）；`selectFile` 在 hasResult=true 时自动重置；`formDisabled` getter 删除

### 3.6 工具链
- [x] **3.6.1** `frontend/vitest.config.js`
- [x] **3.6.2** `frontend/package.json` 加 `"test": "vitest run"`
- [x] **3.6.3** devDeps 加 `@vue/test-utils` / `jsdom` / `vitest`

---

## Phase 4 — OpenAPI

- [x] **4.1** 后端 `python -c "from app.main import app; ..."` 重导 `backend/openapi/dsp_uploads.json`（含 4 form fields 必填、6 API）
- [x] **4.2** `info.version` 升 `0.5.1`（v0.5.2 未变更）

---

## Phase 5 — v0.5.2 增量

- [x] **5.1** store: `selectFile` 自动隐式 reset
- [x] **5.2** store: 新增 `replaceAndUpload(uploadId)` action
- [x] **5.3** view: `onSubmit` 多级 409 处理（confirm + retry）
- [x] **5.4** view: CSS `max-width: 720 → 960`
- [x] **5.5** view: 删除 `formDisabled` 概念；4 字段 disabled 仅看 `!store.hasFile`
- [x] **5.6** 测试: store +4 / -1 case；view +2 / -1 case
- [x] **5.7** spec: `frontend/spec/dsp_upload.md` §1.3/§2.2/§2.3/§2.4/§3/§5/§6/§7/§8 全量更新
- [x] **5.8** spec: `backend/spec/dsp_upload.md` §重传策略 + 修订记录
- [x] **5.9** 验证: `npm test` 全绿（39 / 39）；`pytest -q` 仍 194/194（无后端改动）

---

## Phase 6 — 收尾

- [x] **6.1** 后端 `backend/spec/dsp_upload.md` 同步 v0.5.1 + v0.5.2
- [x] **6.2** 后端 `requirements.txt` 已含 `openpyxl>=3.1`
- [x] **6.3** 前端 `frontend/spec/dsp_upload.md` 同步 v0.5.2
- [x] **6.4** 前端 `.todo/dsp_upload.md`（本文件）Phase 1~6 全部 `[x]`
- [x] **6.5** 全量回归：`pytest -q` 194/194；`npm test` 39/39
- [x] **6.6** `backend/openapi/dsp_uploads.json` 含 4 form fields

---

## 验证清单（每 PR）

- [x] `pytest -q` 全绿（194 / 194；后端无改动）
- [x] `npm test` 全绿（39 / 39，含 v0.5.2 新增 7 测）
- [x] `frontend/src/views/DspUpload.vue` / `stores/useDspUploadStore.js` / `utils/dspFilename.js` 全有 JSDoc 中文
- [x] 页面 max-width = 960px（720 → 960 v0.5.2）
- [x] 上传成功后页面下方出现 el-table 预览
- [x] 上传成功后 4 字段保持 enabled（不再 formDisabled）
- [x] 选新文件 → 自动隐式 reset（hasResult → null）
- [x] 409 + 用户选「替换」→ DELETE + POST 完成，结果卡刷新
- [x] 409 + 用户选「取消」→ 表单保留，不调 DELETE
- [x] 点重置时 store.hasResult 状态下走二次确认
- [x] `backend/spec/dsp_upload.md` §修订记录 含 v0.5.2
- [x] `backend/openapi/dsp_uploads.json` 字段 = `ym`（非 `year_month`）+ 4 form fields
