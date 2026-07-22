/**
 * HTML → Excel 模块 API 客户端（v0.2.0）。
 *
 * 对接后端 `/api/html-to-excel/*` 路由：
 * - POST /inspect             — inspectHtmlControls(file)             【v0.2.0 新增主路径】
 * - POST /extract-by-index    — extractHtmlToExcelByIndex(file, idx)  【v0.2.0 新增主路径】
 * - POST /extract             — extractHtmlToExcel(file, title, opts) 【v0.1.0 高级模式保留】
 * - GET  /download/{filename} — downloadHtmlToExcelXlsx(filename)     【v0.1.0 保留】
 *
 * 文件上传走 FormData + multipart/form-data；timeout 60s（参考 backend spec §9）。
 *
 * 错误处理：抛出 ApiError；调用方按 err.status + err.detail.error 决定 UI：
 *   413 → 文件过大（前端也会拦截一次）
 *   422 html_unparseable / empty_html → 解析失败 / 空 HTML
 *   422 index_out_of_range → 索引越界（响应的 detail.candidates 列出全部 suggested_title）
 *   404 title_not_found → 高级模式：未找到标题（detail.candidates 列出近似建议）
 *   409 multiple_matches → 高级模式：多匹配（detail.candidates 待用户二选一）
 *   5xx → 后端服务异常
 */
import client from './client.js'

// ────────────────────────────── v0.2.0 主路径：inspect + extract-by-index ──────────────────────────────

/**
 * 上传 HTML → 后端枚举所有可下载控件（带 index + preview + 行/列数）。
 *
 * 成功响应（参考 SPEC §2.1）：
 * ```js
 * {
 *   ok: true,
 *   html_size_kb: 3058,
 *   controls: [
 *     { index: 0, control_type: 'table', suggested_title: 'Item',
 *       title_source: 'thead-th', row_count: 23, column_count: 107,
 *       preview: { headers: [...], first_rows: [[...], [...]] } }
 *   ]
 * }
 * ```
 *
 * `controls: []` 是合法响应。
 *
 * @param {File} file 用户选择的 HTML 文件。
 * @returns {Promise<{ ok: boolean, html_size_kb: number, controls: ControlSummary[] }>}
 */
export function inspectHtmlControls(file) {
  const form = new FormData()
  form.append('html_file', file)
  return client.post('/html-to-excel/inspect', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
}

/**
 * 按 index 直接抽控件 → 生成 xlsx → 返回下载信息。
 *
 * 与 `/extract` 同 schema 输出（见 `extractHtmlToExcel` 注释）。
 *
 * @param {File} file HTML 文件（同一上传；不必再走一遍 inspect）
 * @param {number} index 0-based，来自 `inspectHtmlControls(file).controls[i].index`
 * @param {object} [opts]
 * @param {string|null} [opts.filename_hint] 下载文件名提示
 * @returns {Promise<{
 *   ok: boolean, control_type: string, matched_title: string,
 *   xlsx_path: string, download_filename: string,
 *   rows: number, columns: number, warnings: string[],
 * }>}
 */
export function extractHtmlToExcelByIndex(file, index, opts = {}) {
  const { filename_hint = null } = opts
  const form = new FormData()
  form.append('html_file', file)
  form.append('index', String(index))
  if (filename_hint) {
    form.append('filename_hint', filename_hint)
  }
  return client.post('/html-to-excel/extract-by-index', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
}

// ────────────────────────────── v0.1.0 高级模式：title-based extract + download ──────────────────────────────

/**
 * 上传 HTML + 标题 → 后端精确匹配标题抽控件 → 写 xlsx → 返回下载信息。
 *
 * v0.1.0 引入；v0.2.0 保留作为高级 / 手动模式入口。普通用户推荐 v0.2.0 inspect 路径。
 *
 * @param {File} file HTML 文件
 * @param {string} title 控件标题（中/英文），后端做大小写不敏感归一后完全相等匹配
 * @param {object} [opts]
 * @param {string|null} [opts.filename_hint] 下载文件名提示
 * @param {boolean}   [opts.auto_select_first=true] 多匹配时是否自动选第一个
 * @returns {Promise<{
 *   ok: boolean, control_type: string, matched_title: string,
 *   xlsx_path: string, download_filename: string,
 *   rows: number, columns: number, warnings: string[],
 * }>}
 */
export function extractHtmlToExcel(file, title, opts = {}) {
  const { filename_hint = null, auto_select_first = true } = opts
  const form = new FormData()
  form.append('html_file', file)
  form.append('title', title)
  if (filename_hint) form.append('filename_hint', filename_hint)
  form.append('auto_select_first', String(auto_select_first))

  return client.post('/html-to-excel/extract', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
}

/**
 * 下载已生成的 xlsx 二进制。
 *
 * 浏览器侧配合 `utils/downloadBlob.js` 触发下载：
 * ```js
 * const blob = await downloadHtmlToExcelXlsx(filename)
 * downloadBlob(blob, filename)
 * ```
 *
 * @param {string} filename 后端返回的 `download_filename`（如 `Item_20260721_112510.xlsx`）。
 *   路径里的 / 与空格由 encodeURIComponent 处理。
 * @returns {Promise<Blob>}
 */
export function downloadHtmlToExcelXlsx(filename) {
  return client.get(
    `/html-to-excel/download/${encodeURIComponent(filename)}`,
    {
      responseType: 'blob',
      timeout: 60000,
    }
  )
}
