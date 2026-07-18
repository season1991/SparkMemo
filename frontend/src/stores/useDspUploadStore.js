/**
 * DSP 上传 store（v0.5.1）。
 *
 * state 字段（用户表单 → 提交 → 预览 三段式）：
 * - selectedFile        : File | null  用户在 UI 内选中的 .xlsx
 * - form                : { vendor, item, sub_item, version_date } 4 个 form 字段
 * - initialParsed       : { vendor, item, sub_item } | null  解析初值（用于"重置到解析值"对比）
 * - uploading           : bool  上传中
 * - uploadResult        : DspUploadRead | null  后端响应
 * - rows                : DspUploadRow[]  当前预览分页的行
 * - rowsTotal           : number
 * - rowsPage / rowsSize : 当前预览的分页
 * - rowsLoading         : bool
 * - error               : string | null  上一次错误提示
 *
 * action 约定：
 * - selectFile(file)：调 parseFilename 解析；成功 → 自动填 form.vendor/item/sub_item，
 *                     并 snapshot 到 initialParsed；失败 → 清空 selectedFile，error 写消息
 * - submitUpload()：POST，成功 → 设置 uploadResult + 自动 loadResultRows(1, 50)，
 *                  失败 → 错误由 caller 接收；store 不抛
 * - loadResultRows(page, size)：GET .../rows；成功写 rows/rowsTotal
 * - reset()：有 uploadResult 时由 view 二次确认后调用；全部清空到初态
 */
import { defineStore } from 'pinia'
import { ApiError } from '../api/client.js'
import {
  listDspUploadRows,
  uploadDspFile
} from '../api/dsp_uploads.js'
import { parseFilename } from '../utils/dspFilename.js'

const EMPTY_FORM = Object.freeze({
  vendor: '',
  item: '',
  sub_item: '',
  version_date: ''
})

function emptyForm() {
  return { ...EMPTY_FORM }
}

export const useDspUploadStore = defineStore('dspUpload', {
  state: () => ({
    selectedFile: null,
    form: emptyForm(),
    initialParsed: null,
    uploading: false,
    uploadResult: null,
    rows: [],
    rowsTotal: 0,
    rowsPage: 1,
    rowsSize: 50,
    rowsLoading: false,
    error: null
  }),
  getters: {
    /** 是否已选择文件（让 3 段输入框启用）。 */
    hasFile: (state) => state.selectedFile !== null,
    /** 上传成功后显示结果区。 */
    hasResult: (state) => state.uploadResult !== null,
    /** 用户是否编辑过 3 段（与 initialParsed 不一致）。 */
    hasEditedMeta: (state) => {
      const { initialParsed } = state
      if (!initialParsed) return false
      return (
        state.form.vendor !== initialParsed.vendor ||
        state.form.item !== initialParsed.item ||
        state.form.sub_item !== initialParsed.sub_item
      )
    },
    /** 4 个必填字段是否都非空。 */
    canSubmit: (state) =>
      Boolean(state.selectedFile) &&
      state.form.vendor.trim() !== '' &&
      state.form.item.trim() !== '' &&
      state.form.sub_item.trim() !== '' &&
      /^\d{4}-\d{2}-\d{2}$/.test(state.form.version_date)
  },
  actions: {
    /**
     * 用户在 UI 内选中一个 .xlsx 文件：
     * 1. 调 parseFilename 自动解析 vendor/item/sub_item；
     * 2. 解析成功 → form 自动填，initialParsed snapshot；
     * 3. 解析失败（< 3 段等）→ 清空 selectedFile，error 写消息，调用方处理 toast。
     *
     * @param {File} file
     * @returns {{ ok: boolean, error?: string }}
     */
    selectFile(file) {
      this.error = null
      if (!file) {
        this.selectedFile = null
        this.initialParsed = null
        this.form.vendor = ''
        this.form.item = ''
        this.form.sub_item = ''
        return { ok: false, error: 'no file selected' }
      }
      try {
        const parsed = parseFilename(file.name)
        this.selectedFile = file
        this.initialParsed = { ...parsed }
        this.form.vendor = parsed.vendor
        this.form.item = parsed.item
        this.form.sub_item = parsed.sub_item
        return { ok: true }
      } catch (err) {
        this.selectedFile = null
        this.initialParsed = null
        this.form.vendor = ''
        this.form.item = ''
        this.form.sub_item = ''
        const msg = err && err.message ? err.message : 'filename parse failed'
        this.error = msg
        return { ok: false, error: msg }
      }
    },

    /** 用户在 UI 内编辑某个 form 字段；key ∈ {vendor, item, sub_item, version_date}。 */
    updateMeta(key, value) {
      if (!(key in this.form)) return
      this.form[key] = value
    },

    /**
     * 提交上传。
     * @returns {Promise<{ ok: boolean, response?: object, error?: ApiError }>}
     */
    async submitUpload() {
      if (!this.selectedFile) {
        return { ok: false, error: new Error('no file') }
      }
      this.uploading = true
      this.error = null
      try {
        const res = await uploadDspFile(this.selectedFile, {
          vendor: this.form.vendor,
          item: this.form.item,
          sub_item: this.form.sub_item,
          version_date: this.form.version_date
        })
        this.uploadResult = res
        // 自动加载首 50 条预览
        this.rowsPage = 1
        this.rowsSize = 50
        await this.loadResultRows(1, 50)
        return { ok: true, response: res }
      } catch (err) {
        if (err instanceof ApiError) {
          this.error = err.message
        } else {
          this.error = (err && err.message) || '上传失败'
        }
        return { ok: false, error: err }
      } finally {
        this.uploading = false
      }
    },

    /**
     * 加载结果区当前批次的事实行分页。
     * @param {number} page
     * @param {number} size
     */
    async loadResultRows(page, size) {
      if (!this.uploadResult) return
      this.rowsLoading = true
      try {
        const res = await listDspUploadRows(this.uploadResult.id, { page, size })
        this.rows = res.items || []
        this.rowsTotal = res.total || 0
        this.rowsPage = page
        this.rowsSize = size
      } catch (err) {
        if (err instanceof ApiError) {
          this.error = err.message
        } else {
          this.error = (err && err.message) || '加载预览失败'
        }
      } finally {
        this.rowsLoading = false
      }
    },

    /** 全部清空回初态（由 view 在「重置」二次确认后调用）。 */
    reset() {
      this.selectedFile = null
      this.form = emptyForm()
      this.initialParsed = null
      this.uploading = false
      this.uploadResult = null
      this.rows = []
      this.rowsTotal = 0
      this.rowsPage = 1
      this.rowsSize = 50
      this.rowsLoading = false
      this.error = null
    }
  }
})
