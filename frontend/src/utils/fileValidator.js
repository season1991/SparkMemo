/**
 * el-upload 文件校验工具（v0.6.0.1 新增）。
 *
 * 关键问题：el-upload 的 @change 回调入参是 Element Plus 的 wrapper
 * `{ name, size, uid, status, percentage, raw: File, ... }`，**不是浏览器原生
 * `File`**。直接把 wrapper 塞给 `form.append(name, wrapper)`，浏览器会把它
 * String() 序列化为 `"[object Object]"` 当普通字段提交，后端 Pydantic 抛
 * `Value error, Expected UploadFile, received: <class 'str'>` → 422。
 *
 * 本工具负责把 wrapper 解出真正的 `File`，并做：
 * 1. 后缀 `.xlsx` 校验（前后）
 * 2. 大小上限校验（默认 20 MB）
 * 3. 类型守卫（兜底非 File 时返回 reason）
 *
 * 详见 frontend/spec/cross_table_fill.md §2.2 / §11 v0.6.0.1。
 */

const MAX_BYTES = 20 * 1024 * 1024

/**
 * 解 el-upload wrapper 出真 File。
 *
 * @param {any} fileOrWrapper el-upload @change 入参，或测试场景下的裸 File
 * @returns {File|null} 真 File；非 File 时返回 null
 */
export function unwrapElUploadFile(fileOrWrapper) {
  if (!fileOrWrapper) return null
  if (fileOrWrapper instanceof File) return fileOrWrapper
  if (fileOrWrapper.raw instanceof File) return fileOrWrapper.raw
  return null
}

/**
 * 校验文件后缀（不区分大小写）。
 *
 * @param {File|null} rawFile
 * @returns {boolean} 是否 .xlsx
 */
export function isXlsxFile(rawFile) {
  if (!rawFile || !rawFile.name) return false
  return rawFile.name.toLowerCase().endsWith('.xlsx')
}

/**
 * 校验文件大小上限。
 *
 * @param {File|null} rawFile
 * @param {number} [limit=MAX_BYTES]
 * @returns {boolean} true 表示在上限内
 */
export function isWithinSize(rawFile, limit = MAX_BYTES) {
  if (!rawFile) return false
  return rawFile.size <= limit
}

/**
 * 完整校验 el-upload 选中的「文件元数据」。
 *
 * @param {any} fileOrWrapper el-upload @change 入参
 * @param {object} [opts]
 * @param {number} [opts.maxBytes=MAX_BYTES]
 * @returns {{ ok: true, file: File } | { ok: false, reason: 'empty' | 'wrong_type' | 'wrong_ext' | 'too_large' }}
 */
export function validateElUploadFile(fileOrWrapper, opts = {}) {
  const maxBytes = opts.maxBytes ?? MAX_BYTES
  if (!fileOrWrapper) return { ok: false, reason: 'empty' }
  const rawFile = unwrapElUploadFile(fileOrWrapper)
  if (!rawFile) return { ok: false, reason: 'wrong_type' }
  if (!isXlsxFile(rawFile)) return { ok: false, reason: 'wrong_ext' }
  if (!isWithinSize(rawFile, maxBytes)) return { ok: false, reason: 'too_large' }
  return { ok: true, file: rawFile }
}
