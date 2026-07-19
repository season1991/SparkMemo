import { describe, it, expect, vi, beforeEach } from 'vitest'
import { downloadBlob } from '../downloadBlob.js'

describe('downloadBlob', () => {
  let createObjectURLSpy
  let revokeObjectURLSpy
  let createdElements
  let originalCreateElement

  beforeEach(() => {
    createdElements = []
    // spy URL.createObjectURL / revokeObjectURL
    createObjectURLSpy = vi.fn(() => 'blob:mock-url-1')
    revokeObjectURLSpy = vi.fn()
    globalThis.URL.createObjectURL = createObjectURLSpy
    globalThis.URL.revokeObjectURL = revokeObjectURLSpy

    // spy document.createElement('a') to capture attributes
    originalCreateElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag) => {
      const el = originalCreateElement(tag)
      if (tag === 'a') {
        const clickSpy = vi.fn()
        Object.defineProperty(el, 'click', { value: clickSpy, configurable: true })
        el._clickSpy = clickSpy
        createdElements.push(el)
      }
      return el
    })
  })

  it('触发完整下载流程：createObjectURL → <a download> → click → revokeObjectURL', () => {
    const blob = new Blob(['mock xlsx data'], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })

    downloadBlob(blob, 'test.xlsx')

    // createObjectURL 被调用 1 次
    expect(createObjectURLSpy).toHaveBeenCalledTimes(1)
    expect(createObjectURLSpy).toHaveBeenCalledWith(blob)

    // <a> 元素被创建且 download 属性 = 'test.xlsx'，href = 'blob:mock-url-1'
    expect(createdElements.length).toBe(1)
    const a = createdElements[0]
    expect(a.download).toBe('test.xlsx')
    expect(a.href).toBe('blob:mock-url-1')

    // click() 被调用 1 次
    expect(a._clickSpy).toHaveBeenCalledTimes(1)

    // revokeObjectURL 被调用 1 次（参数 = createObjectURL 返回的 url）
    expect(revokeObjectURLSpy).toHaveBeenCalledTimes(1)
    expect(revokeObjectURLSpy).toHaveBeenCalledWith('blob:mock-url-1')
  })
})