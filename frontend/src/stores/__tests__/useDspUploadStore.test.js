import { describe, it, expect, beforeEach, vi } from 'vitest'

const uploadMock = vi.fn()
const listRowsMock = vi.fn()

vi.mock('../../api/dsp_uploads.js', () => ({
  uploadDspFile: (...a) => uploadMock(...a),
  listDspUploadRows: (...a) => listRowsMock(...a)
}))

vi.mock('../../api/client.js', () => ({
  ApiError: class ApiError extends Error {
    constructor(status, detail, message) {
      super(message)
      this.name = 'ApiError'
      this.status = status
      this.detail = detail
    }
  }
}))

import { setActivePinia, createPinia } from 'pinia'
import { useDspUploadStore } from '../useDspUploadStore.js'

function makeFile(name = 'Arista-X-Y-061626.xlsx') {
  return new File(['x'], name, { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
}

beforeEach(() => {
  setActivePinia(createPinia())
  uploadMock.mockReset()
  listRowsMock.mockReset()
})

describe('useDspUploadStore - selectFile', () => {
  it('解析成功自动填充 form', () => {
    const store = useDspUploadStore()
    const ok = store.selectFile(makeFile('Arista-X-Y-061626.xlsx'))
    expect(ok.ok).toBe(true)
    expect(store.selectedFile.name).toBe('Arista-X-Y-061626.xlsx')
    expect(store.form.vendor).toBe('Arista')
    expect(store.form.item).toBe('X')
    expect(store.form.sub_item).toBe('Y')
    expect(store.initialParsed).toEqual({ vendor: 'Arista', item: 'X', sub_item: 'Y' })
  })

  it('< 3 段抛错时清空 selectedFile 与 3 段 form', () => {
    const store = useDspUploadStore()
    const ok = store.selectFile(makeFile('foo-bar.xlsx'))
    expect(ok.ok).toBe(false)
    expect(store.selectedFile).toBeNull()
    expect(store.form.vendor).toBe('')
    expect(store.form.item).toBe('')
    expect(store.form.sub_item).toBe('')
    expect(store.error).toMatch(/at least 3 segments/)
  })

  it('selectFile(null) 直接清空', () => {
    const store = useDspUploadStore()
    store.selectFile(makeFile())  // 先选
    const ok = store.selectFile(null)
    expect(ok.ok).toBe(false)
    expect(store.selectedFile).toBeNull()
  })
})

describe('useDspUploadStore - canSubmit', () => {
  it('4 字段齐全 + 文件已选 + version_date 合规 → true', () => {
    const store = useDspUploadStore()
    store.selectFile(makeFile())
    store.form.version_date = '2026-07-15'
    expect(store.canSubmit).toBe(true)
  })

  it('version_date 为空 → false', () => {
    const store = useDspUploadStore()
    store.selectFile(makeFile())
    expect(store.canSubmit).toBe(false)
  })

  it('version_date 格式错误 → false', () => {
    const store = useDspUploadStore()
    store.selectFile(makeFile())
    store.form.version_date = '2026/07/15'
    expect(store.canSubmit).toBe(false)
  })

  it('未选文件 → false', () => {
    const store = useDspUploadStore()
    store.form.version_date = '2026-07-15'
    expect(store.canSubmit).toBe(false)
  })
})

describe('useDspUploadStore - submitUpload', () => {
  it('201 → uploadResult 写入，rows 预拉', async () => {
    uploadMock.mockResolvedValue({ id: 12, row_count: 366, vendor: 'Arista' })
    listRowsMock.mockResolvedValue({ items: [{ id: 1, quantity: 5 }], total: 1 })

    const store = useDspUploadStore()
    store.selectFile(makeFile())
    store.form.version_date = '2026-07-15'
    const r = await store.submitUpload()
    expect(r.ok).toBe(true)
    expect(store.uploadResult.id).toBe(12)
    expect(store.hasResult).toBe(true)
    expect(store.rows.length).toBe(1)
    expect(store.rowsTotal).toBe(1)
    expect(uploadMock).toHaveBeenCalledTimes(1)
    const [file, meta] = uploadMock.mock.calls[0]
    expect(meta.vendor).toBe('Arista')
    expect(meta.item).toBe('X')
    expect(meta.sub_item).toBe('Y')
    expect(meta.version_date).toBe('2026-07-15')
    expect(file).toBe(store.selectedFile)
  })

  it('未选文件直接返回 ok=false', async () => {
    const store = useDspUploadStore()
    const r = await store.submitUpload()
    expect(r.ok).toBe(false)
    expect(uploadMock).not.toHaveBeenCalled()
  })

  it('409 → store.error 写入消息', async () => {
    const e409 = new Error('version already uploaded (upload_id=1)')
    e409.name = 'ApiError'
    e409.status = 409
    uploadMock.mockRejectedValue(e409)
    const store = useDspUploadStore()
    store.selectFile(makeFile())
    store.form.version_date = '2026-07-15'
    const r = await store.submitUpload()
    expect(r.ok).toBe(false)
    expect(store.error).toMatch(/already uploaded/)
    expect(store.uploadResult).toBeNull()
  })
})

describe('useDspUploadStore - reset', () => {
  it('有结果时 reset 全清', async () => {
    uploadMock.mockResolvedValue({ id: 1, row_count: 1 })
    listRowsMock.mockResolvedValue({ items: [], total: 0 })
    const store = useDspUploadStore()
    store.selectFile(makeFile())
    store.form.version_date = '2026-07-15'
    await store.submitUpload()
    expect(store.hasResult).toBe(true)
    store.reset()
    expect(store.selectedFile).toBeNull()
    expect(store.form.vendor).toBe('')
    expect(store.uploadResult).toBeNull()
    expect(store.rows).toEqual([])
  })
})

describe('useDspUploadStore - hasEditedMeta', () => {
  it('用户编辑 3 段后与 initialParsed 不同 → true', () => {
    const store = useDspUploadStore()
    store.selectFile(makeFile('Arista-X-Y-061626.xlsx'))
    expect(store.hasEditedMeta).toBe(false)
    store.form.sub_item = 'Z'
    expect(store.hasEditedMeta).toBe(true)
  })
})
