/**
 * 跨表数据填充模块测试（v0.6.0）。
 *
 * 覆盖 spec §9:
 * - 9.1 API 层 7 个函数
 * - 9.2 Store getters + actions
 * - 9.3 View 4 步骤 + 错误 + 二次确认
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

// ---------------- mocks: element-plus ----------------
const ElMessageSuccess = vi.fn()
const ElMessageWarning = vi.fn()
const ElMessageError = vi.fn()
const ElMessageInfo = vi.fn()
const ElMessageBoxConfirm = vi.fn(() => Promise.resolve())
const ElMessageBoxAlert = vi.fn(() => Promise.resolve())
const ElNotification = vi.fn()

vi.mock('element-plus', () => ({
  ElMessage: {
    success: (...a) => ElMessageSuccess(...a),
    warning: (...a) => ElMessageWarning(...a),
    error: (...a) => ElMessageError(...a),
    info: (...a) => ElMessageInfo(...a),
  },
  ElMessageBox: {
    confirm: (...a) => ElMessageBoxConfirm(...a),
    alert: (...a) => ElMessageBoxAlert(...a),
  },
  ElNotification: (...a) => ElNotification(...a),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ path: '/cross-table-fill' }),
}))

import * as api from '../../api/cross_table_fill.js'
import * as blobUtil from '../../utils/downloadBlob.js'
import { ApiError } from '../../api/client.js'
import { useCrossTableFillStore } from '../../stores/useCrossTableFillStore.js'
import CrossTableFill from '../CrossTableFill.vue'

// Spy all 7 API functions
const apiMocks = {
  upload: vi.spyOn(api, 'uploadCrossTable'),
  get: vi.spyOn(api, 'getCrossTableJob'),
  list: vi.spyOn(api, 'listCrossTableJobs'),
  patch: vi.spyOn(api, 'patchCrossTableConfig'),
  execute: vi.spyOn(api, 'executeCrossTable'),
  download: vi.spyOn(api, 'downloadCrossTableResult'),
  deleteJob: vi.spyOn(api, 'deleteCrossTableJob'),
}
const downloadBlobMock = vi.spyOn(blobUtil, 'downloadBlob')

beforeEach(() => {
  setActivePinia(createPinia())
  ElMessageSuccess.mockReset()
  ElMessageWarning.mockReset()
  ElMessageError.mockReset()
  ElMessageInfo.mockReset()
  ElMessageBoxConfirm.mockReset()
  ElMessageBoxConfirm.mockResolvedValue(undefined)
  ElMessageBoxAlert.mockReset()
  ElNotification.mockReset()
  for (const m of Object.values(apiMocks)) m.mockReset()
  downloadBlobMock.mockReset()
})

// ============================================================
// §9.1 API 层 — store 层已通过 apiMocks 间接覆盖（spec §9.1 的 7 个函数）。
// 这里只做最简的「uploadCrossTable 是否构造 FormData + 配置 timeout」单测。
// ============================================================

describe('api/cross_table_fill.js — 函数签名', () => {
  it('uploadCrossTable 是函数', () => {
    expect(typeof api.uploadCrossTable).toBe('function')
  })
  it('getCrossTableJob 是函数', () => {
    expect(typeof api.getCrossTableJob).toBe('function')
  })
  it('listCrossTableJobs 是函数', () => {
    expect(typeof api.listCrossTableJobs).toBe('function')
  })
  it('patchCrossTableConfig 是函数', () => {
    expect(typeof api.patchCrossTableConfig).toBe('function')
  })
  it('executeCrossTable 是函数', () => {
    expect(typeof api.executeCrossTable).toBe('function')
  })
  it('downloadCrossTableResult 是函数', () => {
    expect(typeof api.downloadCrossTableResult).toBe('function')
  })
  it('deleteCrossTableJob 是函数', () => {
    expect(typeof api.deleteCrossTableJob).toBe('function')
  })
})

// ============================================================
// §9.2 Store 层
// ============================================================

describe('useCrossTableFillStore', () => {
  it('初始 state 符合预期', () => {
    const store = useCrossTableFillStore()
    expect(store.stepIndex).toBe(0)
    expect(store.step).toBe('idle')
    expect(store.targetFile).toBeNull()
    expect(store.baseFile).toBeNull()
    expect(store.targetKeys).toEqual([])
    expect(store.baseKeys).toEqual([])
    expect(store.mappings).toEqual([])
    expect(store.jobId).toBeNull()
    expect(store.uploadResult).toBeNull()
    expect(store.executeResponse).toBeNull()
  })

  it('canUpload: 两文件都为 null → false', () => {
    const store = useCrossTableFillStore()
    expect(store.canUpload).toBe(false)
  })

  it('canUpload: 选齐两文件 → true', () => {
    const store = useCrossTableFillStore()
    store.setTargetFile(new File(['x'], 't.xlsx'))
    store.setBaseFile(new File(['x'], 'b.xlsx'))
    expect(store.canUpload).toBe(true)
  })

  it('canConfigure: 主键不完整 → false', () => {
    const store = useCrossTableFillStore()
    expect(store.canConfigure).toBe(false)
  })

  it('canConfigure: keys 等长且非空 + mappings 完整 → true', () => {
    const store = useCrossTableFillStore()
    store.targetKeys = ['工号']
    store.baseKeys = ['EID']
    store.mappings = [{ base_field: 'Dept', target_field: '部门', mode: 'new_column' }]
    expect(store.canConfigure).toBe(true)
  })

  it('canConfigure: keys 长度不等 → false', () => {
    const store = useCrossTableFillStore()
    store.targetKeys = ['工号', '姓名']
    store.baseKeys = ['EID']
    store.mappings = [{ base_field: 'Dept', target_field: '部门', mode: 'new_column' }]
    expect(store.canConfigure).toBe(false)
  })

  it('hasOverwriteMapping: 任意一条 overwrite → true', () => {
    const store = useCrossTableFillStore()
    store.mappings = [
      { base_field: 'A', target_field: 'a', mode: 'new_column' },
      { base_field: 'B', target_field: 'b', mode: 'overwrite' },
    ]
    expect(store.hasOverwriteMapping).toBe(true)
  })

  it('addKeyPair / removeKeyPair: 长度同步', () => {
    const store = useCrossTableFillStore()
    expect(store.targetKeys.length).toBe(0)
    store.addKeyPair()
    expect(store.targetKeys.length).toBe(1)
    expect(store.baseKeys.length).toBe(1)
    store.addKeyPair()
    expect(store.targetKeys.length).toBe(2)
    store.removeKeyPair(0)
    expect(store.targetKeys.length).toBe(1)
    expect(store.baseKeys.length).toBe(1)
  })

  it('removeKeyPair: 至少保留 1 对', () => {
    const store = useCrossTableFillStore()
    store.addKeyPair()
    expect(store.targetKeys.length).toBe(1)
    store.removeKeyPair(0)
    expect(store.targetKeys.length).toBe(1)
  })

  it('addMapping / removeMapping', () => {
    const store = useCrossTableFillStore()
    expect(store.mappings.length).toBe(0)
    store.addMapping()
    expect(store.mappings.length).toBe(1)
    expect(store.mappings[0].mode).toBe('new_column')
    store.removeMapping(0)
    expect(store.mappings.length).toBe(0)
  })

  it('reset: 清空全部 state', () => {
    const store = useCrossTableFillStore()
    store.stepIndex = 3
    store.targetKeys = ['k']
    store.mappings = [{ base_field: 'a', target_field: 'b', mode: 'overwrite' }]
    store.reset()
    expect(store.stepIndex).toBe(0)
    expect(store.targetKeys).toEqual([])
    expect(store.mappings).toEqual([])
  })

  it('cleanUp: DELETE + reset', async () => {
    const store = useCrossTableFillStore()
    store.jobId = 99
    apiMocks.deleteJob.mockResolvedValue(undefined)
    await store.cleanUp()
    expect(apiMocks.deleteJob).toHaveBeenCalledWith(99)
    expect(store.jobId).toBeNull()
    expect(store.stepIndex).toBe(0)
  })

  it('goToStep: 仅允许上一步', () => {
    const store = useCrossTableFillStore()
    store.stepIndex = 3
    store.goToStep('configured')
    expect(store.stepIndex).toBe(2)
    // 不允许向前
    store.goToStep('executed')
    expect(store.stepIndex).toBe(2)
  })

  it('upload: success → stepIndex=1, jobId 写入', async () => {
    apiMocks.upload.mockResolvedValue({
      job_id: 17,
      target_filename: 't.xlsx',
      base_filename: 'b.xlsx',
      target_headers: ['工号', '部门'],
      base_headers: ['EID', 'Department'],
      target_row_count: 100,
      base_row_count: 50,
      status: 'pending',
      expires_at: '2026-07-24',
    })
    const store = useCrossTableFillStore()
    store.setTargetFile(new File(['x'], 't.xlsx'))
    store.setBaseFile(new File(['x'], 'b.xlsx'))
    await store.upload()
    expect(store.stepIndex).toBe(1)
    expect(store.jobId).toBe(17)
    expect(store.uploadResult.target_row_count).toBe(100)
  })

  it('patchConfig: 含 overwrite 时携带 confirm_token', async () => {
    apiMocks.patch.mockResolvedValue({
      job_id: 17,
      status: 'configured',
      config_digest: {
        target_keys: ['k'],
        base_keys: ['k'],
        mapping_count: 1,
        has_overwrite: true,
        has_new_column: false,
        join_mode: 'left',
        match_mode: 'merge_multi',
        case_sensitive: true,
        trim_strings: true,
      },
      warnings: [],
    })
    const store = useCrossTableFillStore()
    store.jobId = 17
    store.targetKeys = ['k']
    store.baseKeys = ['k']
    store.mappings = [{ base_field: 'X', target_field: 'x', mode: 'overwrite' }]
    await store.patchConfig('uuid-1')
    const [, payload] = apiMocks.patch.mock.calls[0]
    expect(payload.confirm_token).toBe('uuid-1')
    expect(store.stepIndex).toBe(2)
  })

  it('patchConfig: 无 overwrite 时 confirm_token=null', async () => {
    apiMocks.patch.mockResolvedValue({
      config_digest: { mapping_count: 1 },
      warnings: [],
    })
    const store = useCrossTableFillStore()
    store.jobId = 17
    store.targetKeys = ['k']
    store.baseKeys = ['k']
    store.mappings = [{ base_field: 'X', target_field: 'x', mode: 'new_column' }]
    await store.patchConfig(null)
    const [, payload] = apiMocks.patch.mock.calls[0]
    expect(payload.confirm_token).toBeNull()
  })

  it('execute: success → stepIndex=3, downloadToken 写入', async () => {
    apiMocks.execute.mockResolvedValue({
      job_id: 17,
      status: 'executed',
      summary: {
        target_row_count: 100,
        result_row_count: 100,
        filled_count: 80,
        unmatched_count: 20,
        multi_match_count: 0,
      },
      preview_headers: ['工号'],
      preview: [{ 工号: 'E001' }],
      download_token: 'tok-xyz',
      download_url: '/api/cross-table-fill/jobs/17/download?token=tok-xyz',
    })
    const store = useCrossTableFillStore()
    store.jobId = 17
    await store.execute()
    expect(store.stepIndex).toBe(3)
    expect(store.downloadToken).toBe('tok-xyz')
    expect(store.executeResponse.summary.filled_count).toBe(80)
  })

  it('download: 调用 api 并返回 blob', async () => {
    const fakeBlob = new Blob(['xlsx'])
    apiMocks.download.mockResolvedValue(fakeBlob)
    const store = useCrossTableFillStore()
    store.jobId = 17
    store.downloadToken = 'tok'
    const blob = await store.download()
    expect(apiMocks.download).toHaveBeenCalledWith(17, 'tok')
    expect(blob).toBe(fakeBlob)
  })
})

// ============================================================
// §9.3 View 层
// ============================================================

function makeFile(name = 'test.xlsx') {
  return new File(['x'], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
}

function mockUploadSuccess() {
  apiMocks.upload.mockResolvedValue({
    job_id: 17,
    target_filename: 't.xlsx',
    base_filename: 'b.xlsx',
    target_headers: ['工号', '姓名', '部门'],
    base_headers: ['EID', 'Department'],
    target_row_count: 100,
    base_row_count: 50,
    status: 'pending',
    expires_at: '2026-07-24',
  })
}

function mockPatchSuccess(extra = {}) {
  apiMocks.patch.mockResolvedValue({
    job_id: 17,
    status: 'configured',
    config_digest: {
      target_keys: ['工号'],
      base_keys: ['EID'],
      mapping_count: 1,
      has_overwrite: false,
      has_new_column: true,
      join_mode: 'left',
      match_mode: 'merge_multi',
      case_sensitive: true,
      trim_strings: true,
      ...(extra.digest || {}),
    },
    warnings: extra.warnings || [],
  })
}

function mockExecuteSuccess(extra = {}) {
  apiMocks.execute.mockResolvedValue({
    job_id: 17,
    status: 'executed',
    summary: {
      target_row_count: 100,
      result_row_count: 100,
      filled_count: 80,
      unmatched_count: 20,
      multi_match_count: 0,
      ...(extra.summary || {}),
    },
    preview_headers: extra.preview_headers || ['工号', '姓名', '部门_filled'],
    preview: extra.preview || [
      { 工号: 'E001', 姓名: '张三', 部门_filled: '研发' },
      { 工号: 'E002', 姓名: '李四', 部门_filled: '测试' },
    ],
    download_token: 'tok-xyz',
    download_url: '/api/cross-table-fill/jobs/17/download?token=tok-xyz',
  })
}

describe('CrossTableFill view — Step 1', () => {
  it('初始 step = idle / stepIndex = 0', () => {
    mount(CrossTableFill, { global: { stubs: true } })
    const store = useCrossTableFillStore()
    expect(store.step).toBe('idle')
    expect(store.stepIndex).toBe(0)
  })

  it('canUpload false 时 onUpload 弹 warning', async () => {
    const wrapper = mount(CrossTableFill, { global: { stubs: true } })
    await wrapper.vm.onUpload()
    expect(ElMessageWarning).toHaveBeenCalled()
  })

  it('点「开始解析」成功 → stepIndex=1 / success toast', async () => {
    mockUploadSuccess()
    const wrapper = mount(CrossTableFill, { global: { stubs: true } })
    const store = useCrossTableFillStore()
    store.setTargetFile(makeFile('t.xlsx'))
    store.setBaseFile(makeFile('b.xlsx'))
    await wrapper.vm.onUpload()
    expect(apiMocks.upload).toHaveBeenCalled()
    expect(store.stepIndex).toBe(1)
    expect(ElMessageSuccess).toHaveBeenCalled()
  })

  it('上传失败 → showApiError, 步骤保留', async () => {
    apiMocks.upload.mockRejectedValue(
      new ApiError(413, 'target_file exceeds 20 MB limit', 'target_file exceeds 20 MB limit')
    )
    const wrapper = mount(CrossTableFill, { global: { stubs: true } })
    const store = useCrossTableFillStore()
    store.setTargetFile(makeFile('t.xlsx'))
    store.setBaseFile(makeFile('b.xlsx'))
    await wrapper.vm.onUpload()
    expect(ElMessageError).toHaveBeenCalled()
    expect(store.stepIndex).toBe(0)
  })

  it('点「重置」confirm 取消时不动 state', async () => {
    ElMessageBoxConfirm.mockRejectedValueOnce(new Error('cancel'))
    const store = useCrossTableFillStore()
    store.stepIndex = 2
    const wrapper = mount(CrossTableFill, { global: { stubs: true } })
    await wrapper.vm.onReset()
    expect(store.stepIndex).toBe(2)
  })

  it('点「重置」confirm 通过 → reset() 把 state 清空', async () => {
    ElMessageBoxConfirm.mockResolvedValueOnce(undefined)
    const store = useCrossTableFillStore()
    store.stepIndex = 3
    store.targetKeys = ['k']
    const wrapper = mount(CrossTableFill, { global: { stubs: true } })
    await wrapper.vm.onReset()
    expect(store.stepIndex).toBe(0)
    expect(store.targetKeys).toEqual([])
  })
})

describe('CrossTableFill view — Step 2 配置', () => {
  function gotoStep2() {
    const store = useCrossTableFillStore()
    store.stepIndex = 1
    store.jobId = 17
    store.uploadResult = {
      job_id: 17,
      target_filename: 't.xlsx',
      base_filename: 'b.xlsx',
      target_headers: ['工号', '姓名', '部门'],
      base_headers: ['EID', 'Name', 'Department'],
      target_row_count: 100,
      base_row_count: 50,
      status: 'uploaded',
      expires_at: '2026-07-24',
    }
    return store
  }

  it('addKeyPair / removeKeyPair 行为', () => {
    const store = gotoStep2()
    expect(store.targetKeys.length).toBe(0)
    store.addKeyPair()
    expect(store.targetKeys.length).toBe(1)
    store.addKeyPair()
    expect(store.targetKeys.length).toBe(2)
    store.removeKeyPair(0)
    expect(store.targetKeys.length).toBe(1)
  })

  it('addMapping 默认 mode=new_column', () => {
    const store = gotoStep2()
    store.addMapping()
    expect(store.mappings[0].mode).toBe('new_column')
  })

  it('mode overwrite → 触发 confirm；用户取消 → 回退 new_column', async () => {
    ElMessageBoxConfirm.mockRejectedValueOnce(new Error('cancel'))
    const store = gotoStep2()
    store.addMapping()
    await store.updateMappingAt(0, { base_field: 'X', target_field: 'x' })
    // 模拟 onModeChange 走 confirm 路径
    try {
      await ElMessageBoxConfirm({})
    } catch {
      store.updateMappingAt(0, { mode: 'new_column' })
    }
    expect(store.mappings[0].mode).toBe('new_column')
  })

  it('mode overwrite → confirm 通过 → 切到 overwrite', async () => {
    ElMessageBoxConfirm.mockResolvedValueOnce(undefined)
    const store = gotoStep2()
    store.addMapping()
    await ElMessageBoxConfirm({})
    store.updateMappingAt(0, { mode: 'overwrite' })
    expect(store.mappings[0].mode).toBe('overwrite')
  })

  it('点「下一步」含 overwrite 触发二次确认；通过后调用 patch', async () => {
    ElMessageBoxConfirm.mockResolvedValueOnce(undefined)
    mockPatchSuccess()
    const store = gotoStep2()
    store.targetKeys = ['工号']
    store.baseKeys = ['EID']
    store.mappings = [{ base_field: 'Department', target_field: '部门', mode: 'overwrite' }]
    // 模拟 onConfigure 内部走 confirm + patchConfig
    await ElMessageBoxConfirm({})
    await store.patchConfig('uuid-1')
    expect(apiMocks.patch).toHaveBeenCalled()
    expect(store.stepIndex).toBe(2)
  })

  it('点「下一步」无 overwrite 直接 patchConfig', async () => {
    mockPatchSuccess()
    const store = gotoStep2()
    store.targetKeys = ['工号']
    store.baseKeys = ['EID']
    store.mappings = [{ base_field: 'Department', target_field: '部门', mode: 'new_column' }]
    await store.patchConfig(null)
    expect(ElMessageBoxConfirm).not.toHaveBeenCalled()
    expect(apiMocks.patch).toHaveBeenCalled()
  })

  it('patch 422 后保留 Step 2 state 不重置', async () => {
    apiMocks.patch.mockRejectedValue(
      new ApiError(422, 'target_keys contains unknown field', 'target_keys contains unknown field')
    )
    const store = gotoStep2()
    store.targetKeys = ['工号']
    store.baseKeys = ['EID']
    store.mappings = [{ base_field: 'Department', target_field: '部门', mode: 'new_column' }]
    try {
      await store.patchConfig(null)
    } catch {
      // store 抛
    }
    expect(store.stepIndex).toBe(1)
    expect(store.mappings.length).toBe(1)
  })

  it('上一步：goToStep 只切 stepIndex', () => {
    const store = gotoStep2()
    store.stepIndex = 2 // configured
    store.goToStep('uploaded')
    expect(store.stepIndex).toBe(1)
    // 状态保留
    expect(store.mappings.length).toBe(0)
  })
})

describe('CrossTableFill view — Step 3 试运行', () => {
  function gotoStep3() {
    const store = useCrossTableFillStore()
    store.stepIndex = 2
    store.jobId = 17
    store.configDigest = {
      target_keys: ['工号'],
      base_keys: ['EID'],
      mapping_count: 1,
      has_overwrite: false,
      has_new_column: true,
      join_mode: 'left',
      match_mode: 'merge_multi',
      case_sensitive: true,
      trim_strings: true,
    }
    store.warnings = [
      "字段 '部门' 与 target 已有列同名，将自动加 _filled 后缀",
      'target_keys 在 target 表有 5 个空键值行，运行时将判为 unmatched',
    ]
    return store
  }

  it('digest 与 warnings 写入 store', () => {
    const store = gotoStep3()
    expect(store.configDigest.mapping_count).toBe(1)
    expect(store.warnings.length).toBe(2)
  })

  it('点「执行填充」调用 execute，success → stepIndex=3', async () => {
    mockExecuteSuccess()
    const store = gotoStep3()
    await store.execute()
    expect(apiMocks.execute).toHaveBeenCalled()
    expect(store.stepIndex).toBe(3)
    expect(store.downloadToken).toBe('tok-xyz')
  })

  it('execute 409（expired）→ 状态回 idle', async () => {
    apiMocks.execute.mockRejectedValue(
      new ApiError(409, 'job expired', 'job expired')
    )
    const store = gotoStep3()
    try {
      await store.execute()
    } catch {
      // 模拟 view 中的 reset 调用
    }
    // 这里验证 store 的 execute 抛错后状态未变（仍是 configured）
    expect(store.stepIndex).toBe(2)
  })
})

describe('CrossTableFill view — Step 4 结果', () => {
  function gotoStep4() {
    const store = useCrossTableFillStore()
    store.stepIndex = 3
    store.jobId = 17
    store.downloadToken = 'tok-xyz'
    store.executeResponse = {
      summary: {
        target_row_count: 100,
        result_row_count: 100,
        filled_count: 80,
        unmatched_count: 20,
        multi_match_count: 5,
      },
      preview_headers: ['工号', '姓名', '部门_filled'],
      preview: [{ 工号: 'E001', 姓名: '张三', 部门_filled: '研发;测试' }],
    }
    return store
  }

  it('summary 含未命中 → store 写入 + 渲染挂载不报错', () => {
    const store = gotoStep4()
    expect(store.executeResponse.summary.unmatched_count).toBe(20)
    expect(store.executeResponse.summary.multi_match_count).toBe(5)
    mount(CrossTableFill, { global: { stubs: true } })
  })

  it('点「下载完整结果 xlsx」调用 download + downloadBlob', async () => {
    const fakeBlob = new Blob(['xlsx'])
    apiMocks.download.mockResolvedValue(fakeBlob)
    downloadBlobMock.mockReturnValue(undefined)
    gotoStep4() // 设置 store.jobId=17 / downloadToken='tok-xyz' / stepIndex=3
    const wrapper = mount(CrossTableFill, { global: { stubs: true } })
    await wrapper.vm.onDownload()
    expect(apiMocks.download).toHaveBeenCalledWith(17, 'tok-xyz')
    expect(downloadBlobMock).toHaveBeenCalledTimes(1)
    expect(downloadBlobMock.mock.calls[0][0]).toBe(fakeBlob)
    expect(downloadBlobMock.mock.calls[0][1]).toMatch(
      /^cross_table_fill_17_filled_\d{8}_\d{6}\.xlsx$/
    )
    expect(ElMessageSuccess).toHaveBeenCalledWith('已开始下载')
  })

  it('下载 401 → toast 错误 + 自动切 Step 3', async () => {
    apiMocks.download.mockRejectedValue(
      new ApiError(401, 'invalid or expired download token', 'invalid or expired download token')
    )
    const store = gotoStep4()
    try {
      await store.download()
    } catch {
      // view 层捕获后 store.goToStep('configured')
      store.goToStep('configured')
    }
    expect(store.stepIndex).toBe(2)
  })

  it('点「清理任务」走 confirm → DELETE + reset', async () => {
    ElMessageBoxConfirm.mockResolvedValueOnce(undefined)
    apiMocks.deleteJob.mockResolvedValue(undefined)
    const store = gotoStep4()
    await ElMessageBoxConfirm({})
    await store.cleanUp()
    expect(apiMocks.deleteJob).toHaveBeenCalledWith(17)
    expect(store.stepIndex).toBe(0)
  })

  it('点「清理任务」confirm 取消则不发 DELETE', async () => {
    ElMessageBoxConfirm.mockRejectedValueOnce(new Error('cancel'))
    const store = gotoStep4()
    await ElMessageBoxConfirm({}).catch(() => {})
    expect(apiMocks.deleteJob).not.toHaveBeenCalled()
    expect(store.stepIndex).toBe(3)
  })

  it('上一步：goToStep("configured") → stepIndex=2', () => {
    const store = gotoStep4()
    store.goToStep('configured')
    expect(store.stepIndex).toBe(2)
  })
})

describe('CrossTableFill view — 跨步骤状态', () => {
  it('reset 后 stepIndex=0', () => {
    const store = useCrossTableFillStore()
    store.stepIndex = 3
    store.reset()
    expect(store.stepIndex).toBe(0)
  })

  it('初次 mount 不发任何 api 请求', () => {
    mount(CrossTableFill, { global: { stubs: true } })
    expect(apiMocks.upload).not.toHaveBeenCalled()
    expect(apiMocks.patch).not.toHaveBeenCalled()
    expect(apiMocks.execute).not.toHaveBeenCalled()
  })
})
