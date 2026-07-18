import { describe, it, expect, vi, beforeEach } from 'vitest'

// axios 客户端的可控 mock：拦截 POST/GET/DELETE 并记录调用。
const post = vi.fn()
const get = vi.fn()
const del = vi.fn()

vi.mock('../client.js', () => ({
  default: {
    post: (...args) => post(...args),
    get: (...args) => get(...args),
    delete: (...args) => del(...args)
  }
}))

import {
  uploadDspFile,
  listDspUploads,
  findBatchByVersion,
  getDspUpload,
  listDspUploadRows,
  deleteDspUpload
} from '../dsp_uploads.js'

beforeEach(() => {
  post.mockReset()
  get.mockReset()
  del.mockReset()
})

function makeFile(name = 'foo.xlsx', content = 'xlsx-bytes') {
  return new File([content], name, { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
}

describe('uploadDspFile', () => {
  it('走 POST /dsp-uploads，4 form fields + file 都带上', async () => {
    post.mockResolvedValue({ id: 1, row_count: 10, vendor: 'Arista' })
    const file = makeFile('Arista-X-Y-061626.xlsx')
    const meta = { vendor: 'Arista', item: 'X', sub_item: 'Y', version_date: '2026-07-15' }
    const result = await uploadDspFile(file, meta)
    expect(post).toHaveBeenCalledTimes(1)
    const [url, form, cfg] = post.mock.calls[0]
    expect(url).toBe('/dsp-uploads')
    // FormData iteration order matters; check keys by name
    const keys = []
    for (const k of form.keys()) keys.push(k)
    expect(keys).toEqual(expect.arrayContaining(['file', 'vendor', 'item', 'sub_item', 'version_date']))
    expect(form.get('vendor')).toBe('Arista')
    expect(form.get('item')).toBe('X')
    expect(form.get('sub_item')).toBe('Y')
    expect(form.get('version_date')).toBe('2026-07-15')
    expect(cfg.headers['Content-Type']).toBe('multipart/form-data')
    expect(result.id).toBe(1)
  })

  it('使用更长 timeout（≥10s 默认）', async () => {
    post.mockResolvedValue({})
    await uploadDspFile(makeFile(), { vendor: 'A', item: 'B', sub_item: 'C', version_date: '2026-01-01' })
    const cfg = post.mock.calls[0][2]
    expect(cfg.timeout).toBeGreaterThanOrEqual(10000)
  })
})

describe('listDspUploads / getDspUpload / listDspUploadRows / deleteDspUpload', () => {
  it('listDspUploads 走 GET 带分页参数', async () => {
    get.mockResolvedValue({ items: [], total: 0, page: 2, size: 50 })
    await listDspUploads({ page: 2, size: 50 })
    expect(get).toHaveBeenCalledWith('/dsp-uploads', { params: { page: 2, size: 50 } })
  })

  it('listDspUploads 4 个可选 filter 参数都附加到 query', async () => {
    get.mockResolvedValue({ items: [], total: 0 })
    await listDspUploads({
      vendor: 'Arista', item: 'X', sub_item: 'Y', version_date: '2026-07-15',
      page: 1, size: 1,
    })
    expect(get).toHaveBeenCalledWith('/dsp-uploads', {
      params: {
        page: 1, size: 1,
        vendor: 'Arista', item: 'X', sub_item: 'Y', version_date: '2026-07-15',
      }
    })
  })

  it('listDspUploads filter 部分提供 → 只把非空那几条附加', async () => {
    get.mockResolvedValue({ items: [], total: 0 })
    await listDspUploads({ vendor: 'Arista', page: 1, size: 20 })
    expect(get).toHaveBeenCalledWith('/dsp-uploads', {
      params: { page: 1, size: 20, vendor: 'Arista' }
    })
  })

  it('listDspUploads filter 空字符串与 0 字段 → 不附加', async () => {
    get.mockResolvedValue({ items: [], total: 0 })
    await listDspUploads({ vendor: '', item: '', sub_item: '', version_date: '', page: 1, size: 20 })
    expect(get).toHaveBeenCalledWith('/dsp-uploads', {
      params: { page: 1, size: 20 }
    })
  })

  it('getDspUpload 走 GET /dsp-uploads/{id}', async () => {
    get.mockResolvedValue({ id: 7 })
    await getDspUpload(7)
    expect(get).toHaveBeenCalledWith('/dsp-uploads/7')
  })

  it('listDspUploadRows 走 GET /dsp-uploads/{id}/rows', async () => {
    get.mockResolvedValue({ items: [], total: 0 })
    await listDspUploadRows(7, { page: 1, size: 50 })
    expect(get).toHaveBeenCalledWith('/dsp-uploads/7/rows', { params: { page: 1, size: 50 } })
  })

  it('deleteDspUpload 走 DELETE', async () => {
    del.mockResolvedValue(null)
    await deleteDspUpload(7)
    expect(del).toHaveBeenCalledWith('/dsp-uploads/7')
  })
})

describe('findBatchByVersion (v0.5.4)', () => {
  it('命中（items.length=1）→ 返回 items[0]', async () => {
    get.mockResolvedValue({
      items: [{ id: 12, vendor: 'A', item: 'X', sub_item: 'Y', version_date: '2026-07-15', row_count: 100, source_filename: 'f.xlsx', created_at: '2026-07-15' }],
      total: 1,
    })
    const r = await findBatchByVersion({ vendor: 'A', item: 'X', sub_item: 'Y', version_date: '2026-07-15' })
    expect(r).not.toBeNull()
    expect(r.id).toBe(12)
    // 内部应调用 GET 带 4 filter + page=1 + size=1
    expect(get).toHaveBeenCalledWith('/dsp-uploads', {
      params: { page: 1, size: 1, vendor: 'A', item: 'X', sub_item: 'Y', version_date: '2026-07-15' }
    })
  })

  it('未命中（items=[]）→ 返回 null', async () => {
    get.mockResolvedValue({ items: [], total: 0, page: 1, size: 1 })
    const r = await findBatchByVersion({ vendor: 'A', item: 'X', sub_item: 'Y', version_date: '2026-07-15' })
    expect(r).toBeNull()
  })

  it('API 出错时抛 ApiError（沿用 axios 拦截器 → 不做特殊处理）', async () => {
    const e = new Error('boom')
    e.name = 'ApiError'
    e.status = 500
    get.mockRejectedValue(e)
    await expect(findBatchByVersion({ vendor: 'A', item: 'X', sub_item: 'Y', version_date: '2026-07-15' }))
      .rejects.toThrow('boom')
  })
})
