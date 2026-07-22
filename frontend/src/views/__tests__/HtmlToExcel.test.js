/**
 * HtmlToExcel 视图测试（v0.2.1 patch，SPEC §7.2）。
 *
 * 顶部两个 tab：
 *   Tab "auto"  — 自动检测：inspect + 卡片网格 + 一键下载（state = autoState）
 *   Tab "title" — 按标题查找：title 输入 + extract（state = titleState）
 *
 * 切换 tab 互不重置对方 state；共享 form.file。
 *
 * 覆盖：
 *  1. 初始 autoState=IDLE，默认 activeTab='auto'
 *  2. 文件 > 20 MB 拦截
 *  3. 文件变化自动 inspect → cards 渲染
 *  4. inspect 空 → el-empty
 *  5. 卡片下载 → extractByIndex + download
 *  6. 下载失败 422 index_out_of_range → topAlert
 *  7. 切换文件 → 重新 inspect
 *  8. 切到 title tab → onTitleExtract 走 /extract + 下载
 *  9. title 空白 → ElMessage.warning
 * 10. title 404 → suggestions + 回填
 * 11. 切 tab 保留对方 state
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// ────────────────── mock element-plus ──────────────────
const ElMessageError = vi.fn()
const ElMessageSuccess = vi.fn()
const ElMessageWarning = vi.fn()

vi.mock('element-plus', () => ({
  ElMessage: {
    error: (...a) => ElMessageError(...a),
    success: (...a) => ElMessageSuccess(...a),
    warning: (...a) => ElMessageWarning(...a)
  },
  ElMessageBox: { alert: vi.fn(() => Promise.resolve()), confirm: vi.fn(() => Promise.resolve()) },
  ElNotification: vi.fn()
}))

// ────────────────── mock api/htmlToExcel.js ──────────────────
const inspectMock = vi.fn()
const extractByIndexMock = vi.fn()
const extractMock = vi.fn()
const downloadMock = vi.fn()

vi.mock('../../api/htmlToExcel.js', () => ({
  inspectHtmlControls: (...args) => inspectMock(...args),
  extractHtmlToExcelByIndex: (...args) => extractByIndexMock(...args),
  extractHtmlToExcel: (...args) => extractMock(...args),
  downloadHtmlToExcelXlsx: (...args) => downloadMock(...args)
}))

// ────────────────── mock utils/downloadBlob ──────────────────
const downloadBlobMock = vi.fn()

vi.mock('../../utils/downloadBlob.js', () => ({
  downloadBlob: (...args) => downloadBlobMock(...args)
}))

// ────────────────── mock api/client.js ──────────────────
vi.mock('../../api/client.js', () => ({
  default: {},
  ApiError: class ApiError extends Error {
    constructor(status, detail, message) {
      super(message)
      this.status = status
      this.detail = detail
      this.message = message
      this.name = 'ApiError'
    }
  },
  showApiError: vi.fn()
}))

import HtmlToExcel from '../HtmlToExcel.vue'
import { ApiError } from '../../api/client.js'

beforeEach(() => {
  inspectMock.mockReset()
  extractByIndexMock.mockReset()
  extractMock.mockReset()
  downloadMock.mockReset()
  downloadBlobMock.mockReset()
  ElMessageError.mockReset()
  ElMessageSuccess.mockReset()
  ElMessageWarning.mockReset()
})

function makeFile(name = 'page.html', size = 1024) {
  return new File([new Uint8Array(size)], name, { type: 'text/html' })
}

function mountView() {
  return mount(HtmlToExcel, { global: { stubs: true } })
}

function driveFileChange(wrapper, file, size = 1024) {
  const f = file || makeFile('page.html', size)
  wrapper.vm.onFileChange({ target: { files: [f], value: f.name } })
  return f
}

// ============== Tab "auto" 自动检测 ==============

describe('HtmlToExcel view - Tab auto: 初始 / 文件选择', () => {
  it('初始 autoState=IDLE，默认 activeTab="auto"，文件输入可见，无卡片', () => {
    const wrapper = mountView()
    expect(wrapper.vm.autoState).toBe('IDLE')
    expect(wrapper.vm.activeTab).toBe('auto')
    expect(wrapper.find('.html-to-excel-view').exists()).toBe(true)
    expect(wrapper.find('.form-card').exists()).toBe(true)
    expect(wrapper.find('.cards-section').exists()).toBe(false)
  })

  it('文件 > 20 MB → ElMessage.error，不调 /inspect', async () => {
    const wrapper = mountView()
    driveFileChange(wrapper, makeFile('big.html', 21 * 1024 * 1024))
    await flushPromises()
    expect(ElMessageError).toHaveBeenCalledWith(expect.stringContaining('20 MB'))
    expect(inspectMock).not.toHaveBeenCalled()
    expect(wrapper.vm.form.file).toBeNull()
  })
})

describe('HtmlToExcel view - Tab auto: inspect 渲染', () => {
  it('文件变化后自动调 /inspect → autoState=INSPECTED + 卡片列表', async () => {
    inspectMock.mockResolvedValue({
      ok: true,
      html_size_kb: 2,
      controls: [
        { index: 0, control_type: 'table', suggested_title: 'Item',
          title_source: 'thead-th', row_count: 23, column_count: 107,
          preview: { headers: ['Line Number', 'Item Status'],
                    first_rows: [['1', 'OK'], ['2', 'Alert']] } },
        { index: 1, control_type: 'field_group', suggested_title: 'Primary Information',
          title_source: 'legend', row_count: 4, column_count: 2,
          preview: { headers: ['Label', 'Value'],
                    first_rows: [['Document Number', 'SO3000273']] } }
      ]
    })
    const wrapper = mountView()
    driveFileChange(wrapper, makeFile('a.html', 2048))
    await flushPromises()
    expect(inspectMock).toHaveBeenCalledTimes(1)
    expect(wrapper.vm.autoState).toBe('INSPECTED')
    expect(wrapper.vm.controls.length).toBe(2)
    expect(wrapper.find('.cards-section').exists()).toBe(true)
    expect(wrapper.findAll('.control-card').length).toBe(2)
  })

  it('inspect 返回空 controls → 渲染 el-empty', async () => {
    inspectMock.mockResolvedValue({ ok: true, html_size_kb: 1, controls: [] })
    const wrapper = mountView()
    driveFileChange(wrapper)
    await flushPromises()
    expect(wrapper.vm.autoState).toBe('INSPECTED')
    expect(wrapper.vm.controls.length).toBe(0)
  })
})

describe('HtmlToExcel view - Tab auto: 卡片下载', () => {
  it('点下载 → extractByIndex + download + downloadBlob', async () => {
    inspectMock.mockResolvedValue({
      ok: true, html_size_kb: 2,
      controls: [{ index: 0, control_type: 'table', suggested_title: 'Item',
                   title_source: 'thead-th', row_count: 23, column_count: 107,
                   preview: { headers: ['Line Number'], first_rows: [['1']] } }]
    })
    extractByIndexMock.mockResolvedValue({
      ok: true, control_type: 'table', matched_title: 'Item',
      xlsx_path: 'C:/x.xlsx', download_filename: 'Item_xxx.xlsx',
      rows: 23, columns: 107, warnings: []
    })
    downloadMock.mockResolvedValue(new Blob(['x']))
    const wrapper = mountView()
    driveFileChange(wrapper)
    await flushPromises()
    await wrapper.vm.onDownloadByIndex(0)
    await flushPromises()
    expect(extractByIndexMock).toHaveBeenCalledTimes(1)
    expect(extractByIndexMock.mock.calls[0][1]).toBe(0)
    expect(downloadMock).toHaveBeenCalledWith('Item_xxx.xlsx')
    expect(downloadBlobMock).toHaveBeenCalled()
    expect(ElMessageSuccess).toHaveBeenCalled()
    expect(wrapper.vm.autoState).toBe('INSPECTED')
  })

  it('下载失败 422 index_out_of_range → topAlert 含 candidates', async () => {
    inspectMock.mockResolvedValue({
      ok: true, html_size_kb: 1,
      controls: [{ index: 0, control_type: 'table', suggested_title: 'Item',
                   title_source: 'thead-th', row_count: 1, column_count: 1,
                   preview: { headers: ['x'], first_rows: [['y']] } }]
    })
    extractByIndexMock.mockRejectedValue(new ApiError(422,
      { ok: false, error: 'index_out_of_range', candidates: ['Alpha', 'Beta'] },
      'idx oor'
    ))
    const wrapper = mountView()
    driveFileChange(wrapper)
    await flushPromises()
    await wrapper.vm.onDownloadByIndex(0)
    await flushPromises()
    expect(wrapper.vm.topAlert).not.toBeNull()
    expect(wrapper.vm.topAlert.type).toBe('warning')
    expect(wrapper.vm.topAlert.candidates).toEqual(['Alpha', 'Beta'])
    expect(wrapper.vm.autoState).toBe('INSPECTED')  // 不重置网格
  })
})

describe('HtmlToExcel view - Tab auto: 文件切换', () => {
  it('重新选文件 → 重置两 tab → 重新 inspect', async () => {
    inspectMock.mockResolvedValueOnce({ ok: true, html_size_kb: 1, controls: [] })
    inspectMock.mockResolvedValueOnce({ ok: true, html_size_kb: 2,
      controls: [{ index: 0, control_type: 'table', suggested_title: 'New', title_source: 'thead-th',
                   row_count: 1, column_count: 1, preview: { headers: ['x'], first_rows: [] } }] })
    const wrapper = mountView()
    driveFileChange(wrapper, makeFile('a.html', 2048))
    await flushPromises()
    expect(wrapper.vm.autoState).toBe('INSPECTED')
    driveFileChange(wrapper, makeFile('b.html', 4096))
    await flushPromises()
    expect(inspectMock).toHaveBeenCalledTimes(2)
    expect(wrapper.vm.controls.length).toBe(1)
    expect(wrapper.vm.controls[0].suggested_title).toBe('New')
  })
})

// ============== Tab "title" 按标题查找 ==============

describe('HtmlToExcel view - Tab title: 按标题查找', () => {
  beforeEach(() => {
    inspectMock.mockResolvedValue({ ok: true, html_size_kb: 1, controls: [] })
  })

  it('手动 extract 走 /extract + download', async () => {
    extractMock.mockResolvedValue({
      ok: true, control_type: 'table', matched_title: 'ManualItem',
      xlsx_path: 'C:/m.xlsx', download_filename: 'ManualItem_xxx.xlsx',
      rows: 5, columns: 3, warnings: []
    })
    downloadMock.mockResolvedValue(new Blob())
    const wrapper = mountView()
    driveFileChange(wrapper)
    await flushPromises()
    // 切到 title tab
    wrapper.vm.activeTab = 'title'
    wrapper.vm.titleForm.title = 'ManualItem'
    await wrapper.vm.onTitleExtract()
    await flushPromises()
    expect(extractMock).toHaveBeenCalledTimes(1)
    expect(downloadMock).toHaveBeenCalledWith('ManualItem_xxx.xlsx')
    expect(downloadBlobMock).toHaveBeenCalled()
    expect(wrapper.vm.titleState).toBe('OK')
  })

  it('标题空白 → ElMessage.warning，不发请求', async () => {
    const wrapper = mountView()
    driveFileChange(wrapper)
    await flushPromises()
    wrapper.vm.activeTab = 'title'
    await wrapper.vm.onTitleExtract()
    expect(extractMock).not.toHaveBeenCalled()
    expect(ElMessageWarning).toHaveBeenCalled()
  })

  it('404 title_not_found → titleState=NOT_FOUND + suggestions', async () => {
    extractMock.mockRejectedValue(new ApiError(404,
      { ok: false, error: 'title_not_found', candidates: ['Item', 'Items Header'] },
      'not found'
    ))
    const wrapper = mountView()
    driveFileChange(wrapper)
    await flushPromises()
    wrapper.vm.activeTab = 'title'
    wrapper.vm.titleForm.title = 'Itemz'
    await wrapper.vm.onTitleExtract()
    await flushPromises()
    expect(wrapper.vm.titleState).toBe('NOT_FOUND')
    expect(wrapper.vm.titleSuggestions).toEqual(['Item', 'Items Header'])
  })

  it('click suggestion → 回填 titleForm.title + state=IDLE', async () => {
    extractMock.mockRejectedValue(new ApiError(404,
      { ok: false, error: 'title_not_found', candidates: ['Item'] },
      'nf'
    ))
    const wrapper = mountView()
    driveFileChange(wrapper)
    await flushPromises()
    wrapper.vm.activeTab = 'title'
    wrapper.vm.titleForm.title = 'Itemz'
    await wrapper.vm.onTitleExtract()
    await flushPromises()
    wrapper.vm.applyTitleSuggestion('Item')
    await flushPromises()
    expect(wrapper.vm.titleForm.title).toBe('Item')
    expect(wrapper.vm.titleState).toBe('IDLE')
  })
})

// ============== Tab 切换行为 ==============

describe('HtmlToExcel view - Tab 切换：保留对方 state', () => {
  it('inspect 已完成 → 切到 title tab → 切回 auto：cards 仍在', async () => {
    inspectMock.mockResolvedValue({
      ok: true, html_size_kb: 2,
      controls: [{ index: 0, control_type: 'table', suggested_title: 'Item',
                   title_source: 'thead-th', row_count: 23, column_count: 107,
                   preview: { headers: ['Line Number'], first_rows: [['1']] } }]
    })
    const wrapper = mountView()
    driveFileChange(wrapper)
    await flushPromises()
    expect(wrapper.vm.controls.length).toBe(1)
    expect(wrapper.vm.autoState).toBe('INSPECTED')
    // 切到 title tab
    wrapper.vm.activeTab = 'title'
    await flushPromises()
    expect(wrapper.vm.autoState).toBe('INSPECTED')  // 保留
    expect(wrapper.vm.controls.length).toBe(1)
    // 切回 auto
    wrapper.vm.activeTab = 'auto'
    await flushPromises()
    expect(wrapper.vm.autoState).toBe('INSPECTED')
    expect(wrapper.vm.controls.length).toBe(1)
  })

  it('title 成功完成后 → 切到 auto：inspect 状态独立保留', async () => {
    inspectMock.mockResolvedValue({ ok: true, html_size_kb: 1, controls: [] })
    extractMock.mockResolvedValue({
      ok: true, control_type: 'table', matched_title: 'T',
      xlsx_path: 'C:/t.xlsx', download_filename: 'T.xlsx',
      rows: 1, columns: 1, warnings: []
    })
    downloadMock.mockResolvedValue(new Blob())
    const wrapper = mountView()
    driveFileChange(wrapper)
    await flushPromises()
    wrapper.vm.activeTab = 'title'
    wrapper.vm.titleForm.title = 'T'
    await wrapper.vm.onTitleExtract()
    await flushPromises()
    expect(wrapper.vm.titleState).toBe('OK')
    // 切到 auto tab（auto 状态是 INSPECTED，无 cards）
    wrapper.vm.activeTab = 'auto'
    await flushPromises()
    expect(wrapper.vm.titleState).toBe('OK')  // title 状态保留
    expect(wrapper.vm.titleResult.matched_title).toBe('T')
  })
})
