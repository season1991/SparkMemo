/**
 * 跨表数据填充 API（v0.6.0）：对接后端 /api/cross-table-fill 路由。
 *
 * 错误约定沿用 client.js 拦截器抛出 ApiError；调用方按 status 决定 toast / ElMessageBox.alert。
 * 文件上传走 multipart/form-data（content-type 由 axios 自动设置 + boundary）。
 */

import client from './client.js'

/**
 * 上传两张表（multipart）。
 *
 * @param {{ target: File, base: File, expires_in_hours?: number }} input
 * @returns {Promise<{
 *   job_id: number,
 *   target_filename: string, base_filename: string,
 *   target_headers: string[], base_headers: string[],
 *   target_row_count: number, base_row_count: number,
 *   status: 'pending',
 *   expires_at: string
 * }>}
 */
export function uploadCrossTable({ target, base, expires_in_hours }) {
  const form = new FormData()
  form.append('target_file', target)
  form.append('base_file', base)
  if (expires_in_hours !== undefined && expires_in_hours !== null) {
    form.append('expires_in_hours', String(expires_in_hours))
  }
  return client.post('/cross-table-fill/jobs', form, {
    timeout: 60000,
  })
}

/**
 * 单查 job（状态/执行摘要）。
 *
 * @param {number} jobId
 * @returns {Promise<{
 *   id: number, target_filename: string, base_filename: string,
 *   target_headers: string[], base_headers: string[],
 *   target_row_count: number, base_row_count: number,
 *   status: string, result_row_count: number|null,
 *   filled_count: number|null, unmatched_count: number|null,
 *   multi_match_count: number|null,
 *   created_at: string, updated_at: string, expires_at: string
 * }>}
 */
export function getCrossTableJob(jobId) {
  return client.get(`/cross-table-fill/jobs/${jobId}`)
}

/**
 * 列表（默认按 id 倒序；可选 status filter + page + size）。
 *
 * @param {{ page?: number, size?: number, status?: string }} [opts]
 */
export function listCrossTableJobs(opts = {}) {
  return client.get('/cross-table-fill/jobs', { params: opts })
}

/**
 * PATCH /config：主键 + 映射 + 高级选项。
 *
 * @param {number} jobId
 * @param {{
 *   target_keys: string[],
 *   base_keys: string[],
 *   mappings: Array<{ base_field: string, target_field: string, mode: 'overwrite' | 'new_column' }>,
 *   join_mode?: 'left' | 'inner',
 *   match_mode?: 'merge_multi' | 'first' | 'last',
 *   case_sensitive?: boolean,
 *   trim_strings?: boolean,
 *   confirm_token?: string | null,
 * }} payload
 * @returns {Promise<{
 *   job_id: number, status: string, config_digest: object, warnings: string[]
 * }>}
 */
export function patchCrossTableConfig(jobId, payload) {
  return client.patch(`/cross-table-fill/jobs/${jobId}/config`, payload)
}

/**
 * 执行匹配；返回前 1000 行预览 + 5 min 内有效的 download_token。
 *
 * @param {number} jobId
 * @returns {Promise<{
 *   job_id: number, status: 'executed',
 *   summary: { target_row_count, result_row_count, filled_count, unmatched_count, multi_match_count },
 *   preview_headers: string[], preview: Array<Record<string, unknown>>,
 *   download_token: string, download_url: string
 * }>}
 */
export function executeCrossTable(jobId) {
  return client.post(`/cross-table-fill/jobs/${jobId}/execute`)
}

/**
 * 下载填充结果 xlsx（流式；responseType='blob'）。
 *
 * @param {number} jobId
 * @param {string} token 来自 executeResponse.download_token（5 min TTL）
 * @returns {Promise<Blob>}
 */
export function downloadCrossTableResult(jobId, token) {
  return client.get(`/cross-table-fill/jobs/${jobId}/download`, {
    params: { token },
    responseType: 'blob',
    timeout: 60000,
  })
}

/**
 * 删除 job（级联清 rows / configs）。
 *
 * @returns {Promise<void>}
 */
export function deleteCrossTableJob(jobId) {
  return client.delete(`/cross-table-fill/jobs/${jobId}`)
}
