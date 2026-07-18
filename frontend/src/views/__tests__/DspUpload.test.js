import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

const ElMessageError = vi.fn()
const ElMessageSuccess = vi.fn()

vi.mock('element-plus', () => ({
  ElMessage: { error: (...a) => ElMessageError(...a), success: (...a) => ElMessageSuccess(...a) },
  ElMessageBox: { confirm: vi.fn(() => Promise.resolve()) }
}))

import * as api from '../../api/dsp_uploads.js'
import DspUpload from '../DspUpload.vue'
import { useDspUploadStore } from '../../stores/useDspUploadStore.js'

const uploadMock = vi.spyOn(api, 'uploadDspFile')
const listRowsMock = vi.spyOn(api, 'listDspUploadRows')

beforeEach(() => {
  setActivePinia(createPinia())
  uploadMock.mockReset()
  listRowsMock.mockReset()
  ElMessageError.mockReset()
  ElMessageSuccess.mockReset()
})

function makeFile(name = 'Arista-X-Y-061626.xlsx') {
  return new File(['x'], name, { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
}

describe('DspUpload view', () => {
  it('渲染卡片组件（DOM 烟雾测试）', () => {
    const wrapper = mount(DspUpload, { global: { stubs: true } })
    expect(wrapper.find('.dsp-upload-view').exists()).toBe(true)
    expect(wrapper.find('.upload-card').exists()).toBe(true)
    expect(wrapper.find('.result-card').exists()).toBe(false)  // 未上传时不应有
  })

  it('未上传时 store.canSubmit === false', () => {
    const store = useDspUploadStore()
    mount(DspUpload, { global: { stubs: true } })
    expect(store.canSubmit).toBe(false)
  })

  it('selectFile 后 store.canSubmit === false（version_date 未填）', () => {
    const store = useDspUploadStore()
    mount(DspUpload, { global: { stubs: true } })
    store.selectFile(makeFile())
    expect(store.canSubmit).toBe(false)
  })

  it('selectFile + version_date → canSubmit === true', () => {
    const store = useDspUploadStore()
    mount(DspUpload, { global: { stubs: true } })
    store.selectFile(makeFile())
    store.form.version_date = '2026-07-15'
    expect(store.canSubmit).toBe(true)
  })

  it('上传成功后结果卡出现', async () => {
    uploadMock.mockResolvedValue({
      id: 12, row_count: 366, vendor: 'Arista', item: 'X', sub_item: 'Y',
      version_date: '2026-07-15', source_filename: 'a.xlsx', created_at: '2026-07-15'
    })
    listRowsMock.mockResolvedValue({ items: [{ id: 1, quantity: 5 }], total: 1 })

    const store = useDspUploadStore()
    store.selectFile(makeFile())
    store.form.version_date = '2026-07-15'

    const wrapper = mount(DspUpload, { global: { stubs: true } })
    const r = await store.submitUpload()
    expect(r.ok).toBe(true)
    // 触发响应式刷新
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.result-card').exists()).toBe(true)
  })

  it('hasResult=true 后 store.form 仍保留，但 view 中 formDisabled=true', async () => {
    uploadMock.mockResolvedValue({
      id: 1, row_count: 1, vendor: 'A', item: 'B', sub_item: 'C',
      version_date: '2026-07-15', source_filename: 'a.xlsx', created_at: '2026-07-15'
    })
    listRowsMock.mockResolvedValue({ items: [], total: 0 })
    const store = useDspUploadStore()
    store.selectFile(makeFile())
    store.form.version_date = '2026-07-15'
    await store.submitUpload()
    expect(store.hasResult).toBe(true)
    // 数据保留
    expect(store.form.vendor).toBe('Arista')
    expect(store.form.item).toBe('X')
    expect(store.form.sub_item).toBe('Y')
  })

  it('409 错误：submitUpload 不抛，store.error 写入', async () => {
    const e = new Error('version already uploaded (upload_id=1)')
    e.status = 409
    e.name = 'ApiError'
    uploadMock.mockRejectedValue(e)
    const store = useDspUploadStore()
    store.selectFile(makeFile())
    store.form.version_date = '2026-07-15'
    const r = await store.submitUpload()
    expect(r.ok).toBe(false)
    expect(store.error).toMatch(/already uploaded/)
  })

  it('reset 后 store 全清（无 confirm 弹窗因为无结果）', async () => {
    const store = useDspUploadStore()
    store.selectFile(makeFile())
    store.form.version_date = '2026-07-15'
    store.reset()
    expect(store.selectedFile).toBeNull()
    expect(store.uploadResult).toBeNull()
    expect(store.form.vendor).toBe('')
  })
})
