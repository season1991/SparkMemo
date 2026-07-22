/**
 * v0.2.0 HTML → Excel 模块 API 单测（SPEC §7.1）。
 *
 * 覆盖：
 * - extractHtmlToExcel（v0.1.0 保留）：POST /extract，4 form fields，timeout ≥ 10000
 * - downloadHtmlToExcelXlsx（v0.1.0 保留）：GET /download/{filename}，responseType=blob
 * - inspectHtmlControls（v0.2.0 新增）：POST /inspect，Content-Type multipart
 * - extractHtmlToExcelByIndex（v0.2.0 新增）：POST /extract-by-index，3 form fields
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// axios 客户端的可控 mock
const post = vi.fn()
const get = vi.fn()

vi.mock('../client.js', () => ({
  default: {
    post: (...args) => post(...args),
    get: (...args) => get(...args)
  }
}))

import {
  extractHtmlToExcel,
  downloadHtmlToExcelXlsx,
  inspectHtmlControls,
  extractHtmlToExcelByIndex
} from '../htmlToExcel.js'

beforeEach(() => {
  post.mockReset()
  get.mockReset()
})

function makeFile(name = 'page.html', content = '<html></html>') {
  return new File([content], name, { type: 'text/html' })
}

// ────────────────────────────── v0.1.0（保留测试） ──────────────────────────────

describe('extractHtmlToExcel（v0.1.0 保留）', () => {
  it('走 POST /html-to-excel/extract，4 form fields，Content-Type multipart，timeout ≥ 10000', async () => {
    post.mockResolvedValue({
      ok: true,
      control_type: 'table',
      matched_title: 'Item',
      xlsx_path: 'C:/x.xlsx',
      download_filename: 'Item_xxx.xlsx',
      rows: 23,
      columns: 107,
      warnings: [],
    })
    const file = makeFile()
    const result = await extractHtmlToExcel(file, 'Item')
    expect(post).toHaveBeenCalledTimes(1)
    const [url, form, cfg] = post.mock.calls[0]
    expect(url).toBe('/html-to-excel/extract')
    const keys = []
    for (const k of form.keys()) keys.push(k)
    expect(keys).toEqual(
      expect.arrayContaining(['html_file', 'title', 'auto_select_first'])
    )
    expect(form.get('title')).toBe('Item')
    expect(form.get('auto_select_first')).toBe('true')
    expect(cfg.headers['Content-Type']).toBe('multipart/form-data')
    expect(cfg.timeout).toBeGreaterThanOrEqual(10000)
    expect(result.rows).toBe(23)
  })

  it('缺省时不附加 filename_hint；显式传入则附加', async () => {
    post.mockResolvedValue({ ok: true, rows: 0, columns: 0, warnings: [] })
    const file = makeFile()
    await extractHtmlToExcel(file, 'Title1')
    expect(post.mock.calls[0][1].get('filename_hint')).toBeNull()
    await extractHtmlToExcel(file, 'Title2', { filename_hint: 'MyOutput' })
    expect(post.mock.calls[1][1].get('filename_hint')).toBe('MyOutput')
  })

  it('4xx 错误 → 抛 ApiError', async () => {
    const e = new Error('not found')
    e.name = 'ApiError'
    e.status = 404
    e.detail = { ok: false, error: 'title_not_found', candidates: ['Item'] }
    post.mockRejectedValue(e)
    await expect(extractHtmlToExcel(makeFile(), 'X')).rejects.toThrow('not found')
  })
})

describe('downloadHtmlToExcelXlsx（v0.1.0 保留）', () => {
  it('走 GET /html-to-excel/download/{filename}，responseType=blob，timeout ≥ 10000', async () => {
    get.mockResolvedValue(new Blob(['x']))
    const filename = 'Item_20260721_112510.xlsx'
    const blob = await downloadHtmlToExcelXlsx(filename)
    const [url, cfg] = get.mock.calls[0]
    expect(url).toBe(`/html-to-excel/download/${encodeURIComponent(filename)}`)
    expect(cfg.responseType).toBe('blob')
    expect(cfg.timeout).toBeGreaterThanOrEqual(10000)
    expect(blob).toBeInstanceOf(Blob)
  })

  it('文件名含中文/空格 → encodeURIComponent 编码', async () => {
    get.mockResolvedValue(new Blob())
    await downloadHtmlToExcelXlsx('SO3000273 items.xlsx')
    const [url] = get.mock.calls[0]
    expect(url).toBe('/html-to-excel/download/SO3000273%20items.xlsx')
  })
})

// ────────────────────────────── v0.2.0 新增 ──────────────────────────────

describe('inspectHtmlControls（v0.2.0）', () => {
  it('走 POST /html-to-excel/inspect，Content-Type multipart，timeout ≥ 10000', async () => {
    post.mockResolvedValue({
      ok: true,
      html_size_kb: 12,
      controls: [
        { index: 0, control_type: 'table', suggested_title: 'Items',
          title_source: 'thead-th', row_count: 23, column_count: 107,
          preview: { headers: ['Line Number'], first_rows: [['1']] } }
      ]
    })
    const file = makeFile()
    const result = await inspectHtmlControls(file)
    expect(post).toHaveBeenCalledTimes(1)
    const [url, form, cfg] = post.mock.calls[0]
    expect(url).toBe('/html-to-excel/inspect')
    const keys = [...form.keys()]
    expect(keys).toEqual(['html_file'])
    expect(form.get('html_file')).toBe(file)
    expect(cfg.headers['Content-Type']).toBe('multipart/form-data')
    expect(cfg.timeout).toBeGreaterThanOrEqual(10000)
    expect(result.controls.length).toBe(1)
    expect(result.controls[0].row_count).toBe(23)
  })

  it('4xx 错误 → 抛 ApiError（不重试）', async () => {
    const e = new Error('parse fail')
    e.name = 'ApiError'
    e.status = 422
    e.detail = { ok: false, error: 'html_unparseable' }
    post.mockRejectedValue(e)
    await expect(inspectHtmlControls(makeFile())).rejects.toThrow('parse fail')
  })
})

describe('extractHtmlToExcelByIndex（v0.2.0）', () => {
  it('走 POST /html-to-excel/extract-by-index，form 含 html_file + index；可选 filename_hint', async () => {
    post.mockResolvedValue({
      ok: true, control_type: 'table', matched_title: 'Items',
      xlsx_path: 'C:/y.xlsx', download_filename: 'Items_idx.xlsx',
      rows: 23, columns: 107, warnings: []
    })
    const file = makeFile()
    const result = await extractHtmlToExcelByIndex(file, 0, { filename_hint: 'custom.xlsx' })
    const [url, form, cfg] = post.mock.calls[0]
    expect(url).toBe('/html-to-excel/extract-by-index')
    const keys = [...form.keys()]
    expect(keys).toEqual(['html_file', 'index', 'filename_hint'])
    expect(form.get('index')).toBe('0')
    expect(form.get('filename_hint')).toBe('custom.xlsx')
    expect(form.get('html_file')).toBe(file)
    expect(cfg.headers['Content-Type']).toBe('multipart/form-data')
    expect(result.download_filename).toBe('Items_idx.xlsx')
  })

  it('filename_hint 缺省 → 不附加', async () => {
    post.mockResolvedValue({ ok: true, rows: 0, columns: 0, warnings: [] })
    await extractHtmlToExcelByIndex(makeFile(), 5)
    const [, form] = post.mock.calls[0]
    expect(form.get('filename_hint')).toBeNull()
    expect(form.get('index')).toBe('5')
  })

  it('index_out_of_range 422 → 抛 ApiError，detail 含 candidates', async () => {
    const e = new Error('out of range')
    e.name = 'ApiError'
    e.status = 422
    e.detail = { ok: false, error: 'index_out_of_range', candidates: ['A', 'B'] }
    post.mockRejectedValue(e)
    let captured = null
    try {
      await extractHtmlToExcelByIndex(makeFile(), 99)
    } catch (caught) {
      captured = caught
    }
    expect(captured).not.toBeNull()
    expect(captured.status).toBe(422)
    expect(captured.detail.error).toBe('index_out_of_range')
    expect(captured.detail.candidates).toEqual(['A', 'B'])
  })

  it('index 始终以字符串附加（数字 0、负数、超大值）', async () => {
    post.mockResolvedValue({ ok: true, rows: 0, columns: 0, warnings: [] })
    await extractHtmlToExcelByIndex(makeFile(), 0)
    await extractHtmlToExcelByIndex(makeFile(), 42)
    await extractHtmlToExcelByIndex(makeFile(), 999999)
    expect(post.mock.calls[0][1].get('index')).toBe('0')
    expect(post.mock.calls[1][1].get('index')).toBe('42')
    expect(post.mock.calls[2][1].get('index')).toBe('999999')
  })
})
