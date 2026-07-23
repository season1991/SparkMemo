/**
 * 跨表数据填充 store（v0.6.0）。
 *
 * 4 步向导式 state machine：idle → uploaded → configured → executed。
 * 每步由 `stepIndex` 与 `step` 双向绑定驱动 <el-steps>。
 *
 * state 字段：
 * - stepIndex            : 0..3
 * - targetFile           : File | null
 * - baseFile             : File | null
 * - expiresInHours       : number  默认 24
 * - uploading            : bool
 * - uploadResult         : CrossTableFillUploadResponse | null
 * - jobId                : number | null
 * - targetKeys           : string[]
 * - baseKeys             : string[]
 * - mappings             : Array<{ base_field, target_field, mode: 'overwrite'|'new_column' }>
 * - joinMode             : 'left' | 'inner'
 * - matchMode            : 'merge_multi' | 'first' | 'last'
 * - caseSensitive        : bool
 * - trimStrings          : bool
 * - configuring          : bool
 * - configDigest         : object | null
 * - configResponse       : object | null
 * - warnings             : string[]
 * - executing            : bool
 * - executeResponse      : CrossTableFillExecuteResponse | null
 * - downloadToken        : string
 * - downloading          : bool
 *
 * action 抛出 ApiError（client.js 拦截器已统一处理） → 由 caller 决定 toast。
 */

import { defineStore } from 'pinia'
import {
  uploadCrossTable,
  patchCrossTableConfig,
  executeCrossTable,
  downloadCrossTableResult,
  deleteCrossTableJob,
} from '../api/cross_table_fill.js'

export const useCrossTableFillStore = defineStore('crossTableFill', {
  state: () => ({
    stepIndex: 0,
    targetFile: null,
    baseFile: null,
    expiresInHours: 24,
    uploading: false,
    uploadResult: null,
    jobId: null,
    targetKeys: [],
    baseKeys: [],
    mappings: [],
    joinMode: 'left',
    matchMode: 'merge_multi',
    caseSensitive: true,
    trimStrings: true,
    configuring: false,
    configDigest: null,
    configResponse: null,
    warnings: [],
    executing: false,
    executeResponse: null,
    downloadToken: '',
    downloading: false,
  }),

  getters: {
    step: (state) => {
      return ['idle', 'uploaded', 'configured', 'executed'][state.stepIndex] || 'idle'
    },
    canUpload: (state) =>
      state.targetFile !== null && state.baseFile !== null && !state.uploading,
    canConfigure: (state) => {
      if (state.targetKeys.length < 1) return false
      if (state.targetKeys.length !== state.baseKeys.length) return false
      const allKeysFilled = state.targetKeys.every((k, i) =>
        Boolean(k) && Boolean(state.baseKeys[i])
      )
      if (!allKeysFilled) return false
      if (state.mappings.length < 1) return false
      return state.mappings.every(
        (m) =>
          Boolean(m.base_field) &&
          Boolean(m.target_field) &&
          (m.mode === 'overwrite' || m.mode === 'new_column')
      )
    },
    hasOverwriteMapping: (state) =>
      state.mappings.some((m) => m.mode === 'overwrite'),
  },

  actions: {
    setTargetFile(file) {
      this.targetFile = file
    },

    setBaseFile(file) {
      this.baseFile = file
    },

    /**
     * 上传 target + base 两张 xlsx；成功后 → uploaded 态。
     */
    async upload() {
      if (!this.canUpload) return
      this.uploading = true
      try {
        const res = await uploadCrossTable({
          target: this.targetFile,
          base: this.baseFile,
          expires_in_hours: this.expiresInHours,
        })
        this.uploadResult = res
        this.jobId = res.job_id
        this.stepIndex = 1 // uploaded
        return res
      } finally {
        this.uploading = false
      }
    },

    addKeyPair() {
      this.targetKeys.push('')
      this.baseKeys.push('')
    },

    removeKeyPair(idx) {
      if (this.targetKeys.length <= 1) return
      this.targetKeys.splice(idx, 1)
      this.baseKeys.splice(idx, 1)
    },

    addMapping() {
      this.mappings.push({ base_field: '', target_field: '', mode: 'new_column' })
    },

    removeMapping(idx) {
      if (idx < 0 || idx >= this.mappings.length) return
      this.mappings.splice(idx, 1)
    },

    updateMappingAt(idx, patch) {
      if (idx < 0 || idx >= this.mappings.length) return
      this.mappings[idx] = { ...this.mappings[idx], ...patch }
    },

    /**
     * PATCH /config：主键 + 映射 + 高级选项。
     *
     * @param {string|null} confirmToken
     */
    async patchConfig(confirmToken = null) {
      if (!this.canConfigure) return
      this.configuring = true
      try {
        const mappings = this.mappings.map((m) => ({
          base_field: m.base_field,
          target_field: m.target_field,
          mode: m.mode,
        }))
        const payload = {
          target_keys: this.targetKeys.map((k) => k),
          base_keys: this.baseKeys.map((k) => k),
          mappings,
          join_mode: this.joinMode,
          match_mode: this.matchMode,
          case_sensitive: this.caseSensitive,
          trim_strings: this.trimStrings,
          confirm_token: this.hasOverwriteMapping ? confirmToken : null,
        }
        const res = await patchCrossTableConfig(this.jobId, payload)
        this.configDigest = res.config_digest
        this.configResponse = res
        this.warnings = res.warnings || []
        this.stepIndex = 2 // configured
        return res
      } finally {
        this.configuring = false
      }
    },

    async execute() {
      this.executing = true
      try {
        const res = await executeCrossTable(this.jobId)
        this.executeResponse = res
        this.downloadToken = res.download_token || ''
        this.stepIndex = 3 // executed
        return res
      } finally {
        this.executing = false
      }
    },

    /**
     * 调 GET .../download 拿 xlsx blob。
     * @returns {Promise<Blob>}
     */
    async download() {
      this.downloading = true
      try {
        const blob = await downloadCrossTableResult(this.jobId, this.downloadToken)
        return blob
      } finally {
        this.downloading = false
      }
    },

    /**
     * 清理：删 job（级联）+ 重置 state。
     */
    async cleanUp() {
      try {
        if (this.jobId) {
          await deleteCrossTableJob(this.jobId)
        }
      } finally {
        this.reset()
      }
    },

    /**
     * 切 step（仅限上一步），不发请求。
     */
    goToStep(targetStep) {
      const order = ['idle', 'uploaded', 'configured', 'executed']
      const idx = order.indexOf(targetStep)
      if (idx < 0) return
      if (idx >= this.stepIndex) return // 不允许跨步向前
      this.stepIndex = idx
    },

    /**
     * 重置全部 state（不带 DELETE 请求）。
     */
    reset() {
      this.stepIndex = 0
      this.targetFile = null
      this.baseFile = null
      this.uploading = false
      this.uploadResult = null
      this.jobId = null
      this.targetKeys = []
      this.baseKeys = []
      this.mappings = []
      this.joinMode = 'left'
      this.matchMode = 'merge_multi'
      this.caseSensitive = true
      this.trimStrings = true
      this.configuring = false
      this.configDigest = null
      this.configResponse = null
      this.warnings = []
      this.executing = false
      this.executeResponse = null
      this.downloadToken = ''
      this.downloading = false
    },
  },
})
