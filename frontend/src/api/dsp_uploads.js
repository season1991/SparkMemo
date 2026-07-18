/**
 * 周需求管理 API（v0.5.4）：对接后端 /api/dsp-uploads 路由。
 *
 * 文件上传走 axios 原始客户端（不走拦截器中的 json-encoder）：
 * axios 会自动把 FormData 编码为 multipart/form-data 并附 Content-Type + boundary。
 *
 * 错误处理约定：抛出 ApiError（来自 ./client.js）；上层 store / view 捕获后
 * 根据 status 决定 toast / ElMessageBox.alert。
 */

import client from './client.js'

/**
 * 上传 DSP Excel 文件（DSP 上传子模块）。
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
 *
 * v0.5.4 新增 4 个可选 filter 参数；任一非空字符串即加入精确匹配（AND 关系）。
 *
 * @param {object} [opts]
 * @param {number} [opts.page=1]
 * @param {number} [opts.size=20]
 * @param {string} [opts.vendor]   可选过滤
 * @param {string} [opts.item]     可选过滤
 * @param {string} [opts.sub_item] 可选过滤
 * @param {string} [opts.version_date] 可选过滤；YYYY-MM-DD
 * @returns {Promise<{ items: object[], total: number, page: number, size: number }>}
 */
export function listDspUploads(opts = {}) {
  const {
    page = 1, size = 20, vendor, item, sub_item, version_date
  } = opts
  const params = { page, size }
  if (vendor) params.vendor = vendor
  if (item) params.item = item
  if (sub_item) params.sub_item = sub_item
  if (version_date) params.version_date = version_date
  return client.get('/dsp-uploads', { params })
}

/**
 * v0.5.4 新增：根据 (vendor, item, sub_item, version_date) 精确查找批次。
 *
 * 调用 `GET /api/dsp-uploads?...&page=1&size=1`（4 个 filter + size=1 限制）。
 * 返回单条批次（`DspUploadRead` 或 `null`）。
 *
 * @param {{ vendor: string, item: string, sub_item: string, version_date: string }} meta
 * @returns {Promise<null | { id: number, vendor: string, item: string, sub_item: string,
 *                            version_date: string, source_filename: string,
 *                            row_count: number, created_at: string }>}
 */
export async function findBatchByVersion(meta) {
  const res = await listDspUploads({
    vendor: meta.vendor,
    item: meta.item,
    sub_item: meta.sub_item,
    version_date: meta.version_date,
    page: 1,
    size: 1,
  })
  return res && Array.isArray(res.items) && res.items.length > 0 ? res.items[0] : null
}

/** 单个批次详情。 */
export function getDspUpload(id) {
  return client.get(`/dsp-uploads/${id}`)
}

/** 单个批次的事实行分页。 */
export function listDspUploadRows(id, { page = 1, size = 50 } = {}) {
  return client.get(`/dsp-uploads/${id}/rows`, { params: { page, size } })
}

/** 整批删除（CASCADE 清空事实行）。 */
export function deleteDspUpload(id) {
  return client.delete(`/dsp-uploads/${id}`)
}


// ==================== v0.5.4 级联下拉查询（去重值） ====================


/**
 * 返回所有去重的 vendor 值（按字母升序）。
 * @returns {Promise<string[]>}
 */
export function getDistinctVendors() {
  return client.get('/dsp-uploads/vendors')
}

/**
 * 返回指定 vendor 下所有去重的 item 值（按字母升序）。
 * @param {string} vendor 供应商
 * @returns {Promise<string[]>}
 */
export function getDistinctItems(vendor) {
  return client.get('/dsp-uploads/items', { params: { vendor } })
}

/**
 * 返回指定 vendor + item 下所有去重的 sub_item 值（按字母升序）。
 * @param {string} vendor 供应商
 * @param {string} item   业务项
 * @returns {Promise<string[]>}
 */
export function getDistinctSubItems(vendor, item) {
  return client.get('/dsp-uploads/sub-items', { params: { vendor, item } })
}

/**
 * 返回指定 vendor + item + sub_item 下所有去重的 version_date 值（按日期降序）。
 * @param {string} vendor   供应商
 * @param {string} item     业务项
 * @param {string} sub_item 子业务项
 * @returns {Promise<string[]>}
 */
export function getDistinctVersionDates(vendor, item, sub_item) {
  return client.get('/dsp-uploads/version-dates', { params: { vendor, item, sub_item } })
}
