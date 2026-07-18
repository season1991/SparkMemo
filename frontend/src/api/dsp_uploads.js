/**
 * DSP 上传 API：对接后端 /api/dsp-uploads 路由（v0.5.1）。
 *
 * 文件上传走 axios 原始客户端（不走拦截器中的 json-encoder）：
 * axios 会自动把 FormData 编码为 multipart/form-data 并附 Content-Type + boundary。
 *
 * 错误处理约定：抛出 ApiError（来自 ./client.js）；上层 store / view 捕获后
 * 根据 status 决定 toast / ElMessageBox.alert。
 */

import client from './client.js'

/**
 * 上传 DSP Excel 文件。
 *
 * @param {File} file 用户选择的 .xlsx File 对象
 * @param {{ vendor: string, item: string, sub_item: string, version_date: string }} meta
 *        4 个必填字段；与后端 Form(...) 参数一一对应
 * @returns {Promise<{ id: number, vendor: string, item: string, sub_item: string,
 *                     version_date: string, source_filename: string,
 *                     row_count: number, created_at: string }>}
 */
export function uploadDspFile(file, meta) {
  const form = new FormData()
  form.append('file', file)
  form.append('vendor', meta.vendor)
  form.append('item', meta.item)
  form.append('sub_item', meta.sub_item)
  form.append('version_date', meta.version_date)
  return client.post('/dsp-uploads', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000  // Excel 解析可能慢于 10s 默认 timeout
  })
}

/**
 * 批次列表（按 id 倒序）。
 * @param {{ page?: number, size?: number }} [opts]
 */
export function listDspUploads({ page = 1, size = 20 } = {}) {
  return client.get('/dsp-uploads', { params: { page, size } })
}

/** 单个批次详情。 */
export function getDspUpload(id) {
  return client.get(`/dsp-uploads/${id}`)
}

/** 单个批次的事实行分页。 */
export function listDspUploadRows(id, { page = 1, size = 50 } = {}) {
  return client.get(`/dsp-uploads/${id}/rows`, { params: { page, size } })
}

/** 整批删除。 */
export function deleteDspUpload(id) {
  return client.delete(`/dsp-uploads/${id}`)
}
