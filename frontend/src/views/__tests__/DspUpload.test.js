import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

const ElMessageError = vi.fn()
const ElMessageSuccess = vi.fn()
const ElMessageBoxConfirm = vi.fn(() => Promise.resolve())
const ElMessageBoxAlert = vi.fn(() => Promise.resolve())

vi.mock('element-plus', () => ({
  ElMessage: {
    error: (...a) => ElMessageError(...a),
    success: (...a) => ElMessageSuccess(...a)
  },
  ElMessageBox: {
    confirm: (...a) => ElMessageBoxConfirm(...a),
    alert: (...a) => ElMessageBoxAlert(...a)
  }
}))

import * as api from '../../api/dsp_uploads.js'
import DspUpload from '../DspUpload.vue'
import { useDspUploadStore } from '../../stores/useDspUploadStore.js'

const uploadMock = vi.spyOn(api, 'uploadDspFile')
const listRowsMock = vi.spyOn(api, 'listDspUploadRows')
const deleteMock = vi.spyOn(api, 'deleteDspUpload')

beforeEach(() => {
  setActivePinia(createPinia())
  uploadMock.mockReset()
  listRowsMock.mockReset()
  deleteMock.mockReset()
  ElMessageError.mockReset()
  ElMessageSuccess.mockReset()
  ElMessageBoxConfirm.mockReset()
  ElMessageBoxAlert.mockReset()
})

function makeFile(name = 'Arista-X-Y-061626.xlsx') {
  return new File(['x'], name, { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
}

/**
 * 本测试文件聚焦视图层对 store 状态的反应（DOM 烟雾、hasResult → result-card，
 * canSubmit 派生、隐式重置可见性）；onSubmit 中的 409 替换编排由 store 层
 * tests/useDspUploadStore.test.js 覆盖（store 是 PUT/DELETE 的编排者），
 * 视图层只做"调 store + 弹 confirm 框"。本文件不再重复覆盖 409 E2E 流程。
 */
describe('DspUpload view - DOM 烟雾', () => {
  it('渲染 upload-card；未上传时 result-card 不存在', () => {
    const wrapper = mount(DspUpload, { global: { stubs: true } })
    expect(wrapper.find('.dsp-upload-view').exists()).toBe(true)
    expect(wrapper.find('.upload-card').exists()).toBe(true)
    expect(wrapper.find('.result-card').exists()).toBe(false)
  })

  it('上传成功后 result-card 出现', async () => {
    uploadMock.mockResolvedValue({
      id: 12, row_count: 366, vendor: 'Arista', item: 'X', sub_item: 'Y',
      version_date: '2026-07-15', source_filename: 'a.xlsx', created_at: '2026-07-15'
    })
    listRowsMock.mockResolvedValue({ items: [{ id: 1, quantity: 5 }], total: 1 })

    const store = useDspUploadStore()
    store.selectFile(makeFile())
    store.form.version_date = '2026-07-15'

    const wrapper = mount(DspUpload, { global: { stubs: true } })
    await store.submitUpload()
    await wrapper.vm.$nextTick()

    expect(store.hasResult).toBe(true)
    expect(wrapper.find('.result-card').exists()).toBe(true)
  })

  it('v0.5.2：上传成功后 4 字段仍 enabled（hasResult 不再锁定 form）', async () => {
    uploadMock.mockResolvedValue({
      id: 1, row_count: 1, vendor: 'A', item: 'B', sub_item: 'C',
      version_date: '2026-07-15', source_filename: 'a.xlsx', created_at: '2026-07-15'
    })
    listRowsMock.mockResolvedValue({ items: [], total: 0 })
    const store = useDspUploadStore()
    store.selectFile(makeFile())
    store.form.version_date = '2026-07-15'
    await store.submitUpload()
    // store 上传后 form 数据保留：v0.5.2 后视图仍能编辑
    expect(store.form.vendor).toBe('Arista')
    expect(store.form.item).toBe('X')
    expect(store.form.sub_item).toBe('Y')
    // store.canSubmit 仅看字段齐全 + 文件 + version_date 合规
    expect(store.canSubmit).toBe(true)
    // formDisabled 在 v0.5.2 中已删除
    expect(store.formDisabled).toBeUndefined()
  })

  it('v0.5.2：hasResult=true 时重新选文件 → store.uploadResult 被清空且 version_date 清空（隐式 reset）', async () => {
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

    // 选新文件
    const ok = store.selectFile(makeFile('VendorX-Network-Chassis-061626.xlsx'))
    expect(ok.ok).toBe(true)

    // 自动重置
    expect(store.uploadResult).toBeNull()
    expect(store.form.version_date).toBe('')
    // 3 段由新文件名覆盖
    expect(store.form.vendor).toBe('VendorX')
    expect(store.form.item).toBe('Network')
    expect(store.form.sub_item).toBe('Chassis')
  })
})

describe('DspUpload view - canSubmit', () => {
  it('未上传时 canSubmit === false', () => {
    useDspUploadStore()
    mount(DspUpload, { global: { stubs: true } })
    expect(useDspUploadStore().canSubmit).toBe(false)
  })

  it('选文件 + version_date → canSubmit === true', () => {
    const store = useDspUploadStore()
    mount(DspUpload, { global: { stubs: true } })
    store.selectFile(makeFile())
    store.form.version_date = '2026-07-15'
    expect(store.canSubmit).toBe(true)
  })
})

describe('DspUpload view - replaceAndUpload 编排（间接）', () => {
  it('409 + 确认 → store.replaceAndUpload 路径：DELETE 1 次 + 内部 POST 1 次成功', async () => {
    deleteMock.mockResolvedValue(null)
    uploadMock.mockResolvedValue({ id: 99, row_count: 50, vendor: 'Arista' })
    listRowsMock.mockResolvedValue({ items: [], total: 0 })

    const store = useDspUploadStore()
    store.selectFile(makeFile())
    store.form.version_date = '2026-07-15'

    // 用户确认 → store.replaceAndUpload(7)
    ElMessageBoxConfirm.mockResolvedValueOnce()
    const r = await store.replaceAndUpload(7)
    expect(r.ok).toBe(true)
    expect(deleteMock).toHaveBeenCalledTimes(1)
    expect(deleteMock.mock.calls[0][0]).toBe(7)
    expect(uploadMock).toHaveBeenCalledTimes(1)
    expect(store.uploadResult.id).toBe(99)
  })

  it('409 + 取消 → store.replaceAndUpload 不被调，DELETE 不调', async () => {
    deleteMock.mockReset()
    uploadMock.mockReset()
    listRowsMock.mockReset()
    const e409 = (() => {
      const e = new Error('version already uploaded (upload_id=7)')
      e.name = 'ApiError'
      e.status = 409
      e.detail = e.message
      return e
    })()
    uploadMock.mockRejectedValue(e409)
    listRowsMock.mockResolvedValue({ items: [], total: 0 })

    const store = useDspUploadStore()
    store.selectFile(makeFile())
    store.form.version_date = '2026-07-15'

    const r = await store.submitUpload()
    expect(r.ok).toBe(false)
    expect(r.error.status).toBe(409)
    // 取消：不调 replaceAndUpload
    expect(deleteMock).not.toHaveBeenCalled()
    expect(store.uploadResult).toBeNull()
    // 表单保留（cancel 不动 store）
    expect(store.form.version_date).toBe('2026-07-15')
  })
})

describe('DspUpload view - 退化路径', () => {
  it('409 但 detail 不含 upload_id：调用方走 alert 路径（退化）', async () => {
    const e409 = (() => {
      const e = new Error('version already uploaded')
      e.name = 'ApiError'
      e.status = 409
      e.detail = null
      return e
    })()
    uploadMock.mockRejectedValue(e409)
    listRowsMock.mockResolvedValue({ items: [], total: 0 })

    const store = useDspUploadStore()
    store.selectFile(makeFile())
    store.form.version_date = '2026-07-15'
    const r = await store.submitUpload()
    expect(r.ok).toBe(false)
    expect(r.error.status).toBe(409)
    expect(r.error.detail).toBeNull()
    // 退化：调用方走 ElMessageBox.alert 路径（沿用 client.showApiError 的 409 alert 分支）
    // 这里 store 不调 alert；由 view 层 onSubmit 接到 409+null detail 后调用 showApiError
  })
})

describe('DspUpload view - 重置', () => {
  it('reset → 全清', () => {
    const store = useDspUploadStore()
    store.selectFile(makeFile())
    store.form.version_date = '2026-07-15'
    store.reset()
    expect(store.selectedFile).toBeNull()
    expect(store.uploadResult).toBeNull()
    expect(store.form.vendor).toBe('')
  })
})
