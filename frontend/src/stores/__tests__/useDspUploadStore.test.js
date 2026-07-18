import { describe, it, expect, beforeEach, vi } from 'vitest'

const uploadMock = vi.fn()
const listRowsMock = vi.fn()
const deleteMock = vi.fn()

vi.mock('../../api/dsp_uploads.js', () => ({
  uploadDspFile: (...a) => uploadMock(...a),
  listDspUploadRows: (...a) => listRowsMock(...a),
  deleteDspUpload: (...a) => deleteMock(...a)
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
  deleteMock.mockReset()
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

  // ===== v0.5.2 新增 =====

  it('selectFile 在 hasResult=true 时自动重置 uploadResult/rows/version_date，再解析新文件名', () => {
    const store = useDspUploadStore()
    // 模拟已有上传结果
    uploadMock.mockResolvedValue({ id: 100, row_count: 5, vendor: 'Old', item: 'a', sub_item: 'b' })
    listRowsMock.mockResolvedValue({ items: [], total: 0 })
    store.selectFile(makeFile('Old-a-b.xlsx'))
    store.form.version_date = '2026-07-15'
    return store.submitUpload().then(() => {
      expect(store.hasResult).toBe(true)
      expect(store.uploadResult.id).toBe(100)
      expect(store.form.version_date).toBe('2026-07-15')

      // 用户重新选新文件
      const ok = store.selectFile(makeFile('VendorX-Network-Chassis-061626.xlsx'))
      expect(ok.ok).toBe(true)
      // 自动重置
      expect(store.uploadResult).toBeNull()
      expect(store.rows).toEqual([])
      expect(store.rowsTotal).toBe(0)
      expect(store.rowsPage).toBe(1)
      expect(store.form.version_date).toBe('')
      // 3 段由新文件名解析填入
      expect(store.form.vendor).toBe('VendorX')
      expect(store.form.item).toBe('Network')
      expect(store.form.sub_item).toBe('Chassis')
    })
  })

  it('selectFile(hasResult=true 且解析失败) → 旧结果仍清空、3 段保持空', () => {
    const store = useDspUploadStore()
    uploadMock.mockResolvedValue({ id: 1, row_count: 1 })
    listRowsMock.mockResolvedValue({ items: [], total: 0 })
    store.selectFile(makeFile())
    store.form.version_date = '2026-07-15'
    return store.submitUpload().then(() => {
      expect(store.hasResult).toBe(true)
      // 选 < 3 段文件
      const ok = store.selectFile(makeFile('bad-name.xlsx'))
      expect(ok.ok).toBe(false)
      // 旧结果仍清空（隐式 reset 那部分）
      expect(store.uploadResult).toBeNull()
      expect(store.rows).toEqual([])
      expect(store.form.version_date).toBe('')
      // 3 段保持空（不写 initialParsed）
      expect(store.form.vendor).toBe('')
      expect(store.form.item).toBe('')
      expect(store.form.sub_item).toBe('')
      expect(store.selectedFile).toBeNull()
    })
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

// ===== v0.5.2 新增：replaceAndUpload =====
describe('useDspUploadStore - replaceAndUpload', () => {
  it('成功路径：DELETE 调一次 + 内部 POST 成功', async () => {
    deleteMock.mockResolvedValue(null)
    uploadMock.mockResolvedValue({ id: 99, row_count: 50, vendor: 'Arista' })
    listRowsMock.mockResolvedValue({ items: [], total: 0 })

    const store = useDspUploadStore()
    store.selectFile(makeFile())
    store.form.version_date = '2026-07-15'

    // replaceAndUpload 内部只调用 1 次 POST（之前的 409 由 view 层调用 submitUpload 触发，与本方法无关）
    const r = await store.replaceAndUpload(7)
    expect(r.ok).toBe(true)
    expect(r.response.id).toBe(99)
    // DELETE 调一次
    expect(deleteMock).toHaveBeenCalledTimes(1)
    expect(deleteMock.mock.calls[0][0]).toBe(7)
    // POST 调一次（成功路径）
    expect(uploadMock).toHaveBeenCalledTimes(1)
    // uploadResult 更新为新的
    expect(store.uploadResult.id).toBe(99)
  })

  it('DELETE 失败：不重发 POST，错误透传', async () => {
    const eDelete = new Error('delete failed')
    eDelete.name = 'ApiError'
    eDelete.status = 500
    deleteMock.mockRejectedValue(eDelete)

    const store = useDspUploadStore()
    store.selectFile(makeFile())
    store.form.version_date = '2026-07-15'

    const r = await store.replaceAndUpload(7)
    expect(r.ok).toBe(false)
    expect(uploadMock).not.toHaveBeenCalled()
    expect(store.error).toBe('delete failed')
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

// ===== v0.5.2 删除：formDisabled getter 不应存在 =====
describe('useDspUploadStore - formDisabled 已删除 (v0.5.2)', () => {
  it('store.formDisabled 为 undefined', () => {
    const store = useDspUploadStore()
    expect(store.formDisabled).toBeUndefined()
  })
})
