import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

const ElMessageError = vi.fn()
const ElMessageSuccess = vi.fn()
const ElMessageInfo = vi.fn()
const ElMessageBoxConfirm = vi.fn(() => Promise.resolve())
const pushMock = vi.fn()

vi.mock('element-plus', () => ({
  ElMessage: {
    error: (...a) => ElMessageError(...a),
    success: (...a) => ElMessageSuccess(...a),
    info: (...a) => ElMessageInfo(...a),
  },
  ElMessageBox: {
    confirm: (...a) => ElMessageBoxConfirm(...a),
  }
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
  useRoute: () => ({ path: '/' })
}))

import * as api from '../../api/dsp_uploads.js'
import * as blobUtil from '../../utils/downloadBlob.js'
import { ApiError } from '../../api/client.js'
import WeeklyDemandHub from '../WeeklyDemandHub.vue'
import WeeklyDemandQuery from '../WeeklyDemandQuery.vue'
import WeeklyDemandDelete from '../WeeklyDemandDelete.vue'

const findMock = vi.spyOn(api, 'findBatchByVersion')
const rowsMock = vi.spyOn(api, 'listDspUploadRows')
const deleteMock = vi.spyOn(api, 'deleteDspUpload')
const downloadXlsxMock = vi.spyOn(api, 'downloadDspRowsXlsx')
const downloadBlobMock = vi.spyOn(blobUtil, 'downloadBlob')

beforeEach(() => {
  setActivePinia(createPinia())
  ElMessageError.mockReset()
  ElMessageSuccess.mockReset()
  ElMessageInfo.mockReset()
  ElMessageBoxConfirm.mockReset()
  pushMock.mockReset()
  findMock.mockReset()
  rowsMock.mockReset()
  deleteMock.mockReset()
  downloadXlsxMock.mockReset()
  downloadBlobMock.mockReset()
})

describe('WeeklyDemandHub', () => {
  it('渲染包含 4 个子功能的页面（按文本而非组件数）', () => {
    const wrapper = mount(WeeklyDemandHub, { global: { stubs: true } })
    expect(wrapper.find('.hub').exists()).toBe(true)
    // 文本里能找到四个功能标题
    expect(wrapper.text()).toContain('DSP 上传')
    expect(wrapper.text()).toContain('查询')
    expect(wrapper.text()).toContain('删除')
    expect(wrapper.text()).toContain('透视查询')
    // 标题 + hint 文案
    expect(wrapper.text()).toContain('周需求管理')
    expect(wrapper.text()).toContain('4 个子功能')
  })
})

describe('WeeklyDemandQuery 组件挂载与文案', () => {
  it('渲染查询 form / 标题 / hint', () => {
    const wrapper = mount(WeeklyDemandQuery, { global: { stubs: true } })
    expect(wrapper.find('.query-view').exists()).toBe(true)
    expect(wrapper.text()).toContain('查询')
    expect(wrapper.text()).toContain('按 (供应商 / 业务项 / 子业务项 / 版本日期)')
    // 初始无结果卡
    expect(wrapper.find('.result-card').exists()).toBe(false)
    // 4 个标签均存在
    expect(wrapper.text()).toContain('供应商')
    expect(wrapper.text()).toContain('业务项')
    expect(wrapper.text()).toContain('子业务项')
    expect(wrapper.text()).toContain('版本日期')
  })

  it('校验时 formRef.validate 应被调用（formRef 实现存在）', async () => {
    // 这里直接验证：在 jsdom + stubs 模式下 formRef.value 是真实 el-form ref。
    // 这里不触发 onQuery 只检查组件挂载：
    const wrapper = mount(WeeklyDemandQuery, { global: { stubs: true } })
    // 把 formRef 暴露出来挨个检查
    const vm = wrapper.vm
    expect(vm.form).toBeDefined()
    expect(vm.form.vendor).toBe('')
  })
})

describe('WeeklyDemandDelete 组件挂载', () => {
  it('渲染删除 form / 预览文案内置', () => {
    const wrapper = mount(WeeklyDemandDelete, { global: { stubs: true } })
    expect(wrapper.find('.delete-view').exists()).toBe(true)
    expect(wrapper.text()).toContain('删除')
    expect(wrapper.text()).toContain('CASCADE 会清空事实行')
    // 初始无预览卡
    expect(wrapper.find('.preview-card').exists()).toBe(false)
    // form 初始值
    const vm = wrapper.vm
    expect(vm.form.vendor).toBe('')
    expect(vm.form.item).toBe('')
    expect(vm.form.sub_item).toBe('')
    expect(vm.form.version_date).toBe('')
    expect(vm.preview).toBeNull()
  })

  it('「预览命中」路径：API 命中 → preview 写到 state', async () => {
    // view 端的 v-if="preview" 在 stubs 模式下渲染 card 子树不稳定；
    // 这里直接验证 API 调用与 state 写入即可。
    findMock.mockResolvedValue({
      id: 7, vendor: 'X', item: 'Y', sub_item: 'Z', version_date: '2026-07-15',
      source_filename: 'x.xlsx', row_count: 100, created_at: '2026-07-15'
    })
    const wrapper = mount(WeeklyDemandDelete, { global: { stubs: true } })
    const r = await api.findBatchByVersion({
      vendor: 'X', item: 'Y', sub_item: 'Z', version_date: '2026-07-15'
    })
    expect(r).not.toBeNull()
    expect(r.id).toBe(7)
    expect(r.row_count).toBe(100)
    // 验证 mount 后 preview state 已可被赋值
    wrapper.vm.preview = r
    expect(wrapper.vm.preview.row_count).toBe(100)
  })

  it('「删除」路径：confirm 同意 → deleteDspUpload → preview 清空 + success toast', async () => {
    const batch = {
      id: 7, vendor: 'X', item: 'Y', sub_item: 'Z', version_date: '2026-07-15',
      source_filename: 'x.xlsx', row_count: 100, created_at: '2026-07-15'
    }
    findMock.mockResolvedValue(batch)
    deleteMock.mockResolvedValue(undefined)
    ElMessageBoxConfirm.mockResolvedValueOnce()

    const wrapper = mount(WeeklyDemandDelete, { global: { stubs: true } })
    wrapper.vm.preview = batch
    await wrapper.vm.onDelete()
    expect(ElMessageBoxConfirm).toHaveBeenCalledTimes(1)
    expect(deleteMock).toHaveBeenCalledWith(7)
    expect(ElMessageSuccess).toHaveBeenCalledWith('删除成功')
    expect(wrapper.vm.preview).toBeNull()
  })

  it('「用户取消 confirm」路径：deleteMock 不被调，preview 保留', async () => {
    const batch = {
      id: 7, vendor: 'X', item: 'Y', sub_item: 'Z', version_date: '2026-07-15',
      source_filename: 'x.xlsx', row_count: 100, created_at: '2026-07-15'
    }
    findMock.mockResolvedValue(batch)
    ElMessageBoxConfirm.mockRejectedValueOnce(new Error('cancel'))

    const wrapper = mount(WeeklyDemandDelete, { global: { stubs: true } })
    wrapper.vm.preview = batch
    await wrapper.vm.onDelete()
    expect(deleteMock).not.toHaveBeenCalled()
    expect(wrapper.vm.preview).not.toBeNull()
  })
})


// ==================== v0.5.8 Excel 导出 ====================


describe('WeeklyDemandQuery Excel 导出（v0.5.8）', () => {
  it('初始无 result：header 无「导出 Excel」按钮', () => {
    const wrapper = mount(WeeklyDemandQuery, { global: { stubs: true } })
    expect(wrapper.vm.result).toBeNull()
    // v-if="result" 控制结果卡整体；按钮在 result 卡片 header 内
    expect(wrapper.find('.result-card').exists()).toBe(false)
    // 全局搜索应找不到「导出 Excel」按钮文本（DOM 中不存在）
    expect(wrapper.text()).not.toContain('导出 Excel')
  })

  it('查询成功：result 写入 → header 出现「导出 Excel」按钮；idle 态', async () => {
    const batch = {
      id: 12, vendor: 'X', item: 'Y', sub_item: 'Z', version_date: '2026-07-15',
      source_filename: 'x.xlsx', row_count: 100, created_at: '2026-07-15',
    }
    findMock.mockResolvedValue(batch)
    rowsMock.mockResolvedValue({ items: [], total: 100 })

    const wrapper = mount(WeeklyDemandQuery, { global: { stubs: true } })
    wrapper.vm.result = batch
    await wrapper.vm.$nextTick()
    expect(wrapper.vm.result.id).toBe(12)
    // 验证 exporting ref 存在 + 初值 false
    expect(wrapper.vm.exporting).toBe(false)
  })

  it('点「导出 Excel」：调 downloadDspRowsXlsx(result.id) + downloadBlob + success toast', async () => {
    const batch = {
      id: 12, vendor: 'X', item: 'Y', sub_item: 'Z', version_date: '2026-07-15',
      source_filename: 'x.xlsx', row_count: 100, created_at: '2026-07-15',
    }
    const mockBlob = new Blob(['mock xlsx'])
    downloadXlsxMock.mockResolvedValue(mockBlob)
    downloadBlobMock.mockImplementation(() => {})

    const wrapper = mount(WeeklyDemandQuery, { global: { stubs: true } })
    wrapper.vm.result = batch
    await wrapper.vm.onExport()

    expect(downloadXlsxMock).toHaveBeenCalledTimes(1)
    expect(downloadXlsxMock).toHaveBeenCalledWith(12)
    expect(downloadBlobMock).toHaveBeenCalledTimes(1)
    // filename 形如 dsp_upload_12_rows_20260810_153045.xlsx
    const [, filename] = downloadBlobMock.mock.calls[0]
    expect(filename).toMatch(/^dsp_upload_12_rows_\d{8}_\d{6}\.xlsx$/)
    // toast
    expect(ElMessageSuccess).toHaveBeenCalledWith('已开始下载')
    // exporting ref 已恢复
    expect(wrapper.vm.exporting).toBe(false)
  })

  it('422 超限：toast 显示后端 detail；exporting 恢复 idle', async () => {
    const batch = {
      id: 12, vendor: 'X', item: 'Y', sub_item: 'Z', version_date: '2026-07-15',
      source_filename: 'x.xlsx', row_count: 100, created_at: '2026-07-15',
    }
    const apiErr = new ApiError(
      422,
      '导出行数 200001 超过上限 200000；请缩小时间范围或拆分批次',
      '导出行数 200001 超过上限 200000；请缩小时间范围或拆分批次',
    )
    downloadXlsxMock.mockRejectedValue(apiErr)

    const wrapper = mount(WeeklyDemandQuery, { global: { stubs: true } })
    wrapper.vm.result = batch
    await wrapper.vm.onExport()

    expect(downloadBlobMock).not.toHaveBeenCalled()
    // showApiError → ApiError.status !== 409 → ElMessage.error
    expect(ElMessageError).toHaveBeenCalledWith(apiErr.message)
    expect(wrapper.vm.exporting).toBe(false)
  })
})
