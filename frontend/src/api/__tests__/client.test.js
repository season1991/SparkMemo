/**
 * api/client.js 单测（v0.6.0 新增）。
 *
 * 主要验证 formDataRequestInterceptor 的行为：
 * - FormData 请求：自动 delete cfg.headers['Content-Type']
 * - 非 FormData 请求：不影响 headers
 * - 兜底兼容：用户手动设置 'Content-Type': 'multipart/form-data'（无 boundary）也会被清掉
 * - 不抛异常
 *
 * 详见 frontend/spec/README.md §3.6 FormData 上传规则。
 */
import { describe, it, expect } from 'vitest'
import { formDataRequestInterceptor } from '../client.js'

function makeFormData() {
  return new FormData()
}

describe('formDataRequestInterceptor', () => {
  it('FormData 请求：删除 Content-Type 头', () => {
    const cfg = {
      url: '/api/cross-table-fill/jobs',
      data: makeFormData(),
      headers: { 'Content-Type': 'multipart/form-data' },
    }
    const result = formDataRequestInterceptor(cfg)
    expect(result).toBe(cfg)
    expect(cfg.headers['Content-Type']).toBeUndefined()
  })

  it('FormData 请求：无 Content-Type 头时不报错', () => {
    const cfg = {
      url: '/api/cross-table-fill/jobs',
      data: makeFormData(),
      headers: { 'X-Custom': 'foo' },
    }
    expect(() => formDataRequestInterceptor(cfg)).not.toThrow()
    expect(cfg.headers['X-Custom']).toBe('foo')
    expect(cfg.headers['Content-Type']).toBeUndefined()
  })

  it('FormData 请求：boundary=xxx 也一并清掉（兜底）', () => {
    // 即便用户已经手写了正确的 multipart/form-data; boundary=...
    // 也走删除路径 —— axios 会重新计算并注入新 boundary（基于当前 FormData 实例）
    const cfg = {
      url: '/api/dsp-uploads',
      data: makeFormData(),
      headers: { 'Content-Type': 'multipart/form-data; boundary=----foo' },
    }
    formDataRequestInterceptor(cfg)
    expect(cfg.headers['Content-Type']).toBeUndefined()
  })

  it('小写 content-type 也清掉（兼容用户写法）', () => {
    const cfg = {
      url: '/api/cross-table-fill/jobs',
      data: makeFormData(),
      headers: { 'content-type': 'multipart/form-data' },
    }
    formDataRequestInterceptor(cfg)
    expect(cfg.headers['content-type']).toBeUndefined()
  })

  it('非 FormData 请求：不修改 headers', () => {
    const cfg = {
      url: '/api/tasks',
      data: { foo: 'bar' },
      headers: {
        'Content-Type': 'application/json',
        'X-Custom': 'keep-me',
      },
    }
    const before = { ...cfg.headers }
    formDataRequestInterceptor(cfg)
    expect(cfg.headers).toEqual(before)
  })

  it('JSON 字符串 body + Content-Type=application/json：不修改', () => {
    const cfg = {
      url: '/api/tasks',
      data: JSON.stringify({ foo: 'bar' }),
      headers: { 'Content-Type': 'application/json' },
    }
    formDataRequestInterceptor(cfg)
    expect(cfg.headers['Content-Type']).toBe('application/json')
  })

  it('URLSearchParams body + Content-Type=application/x-www-form-urlencoded：不修改', () => {
    const cfg = {
      url: '/api/foo',
      data: new URLSearchParams('a=1&b=2'),
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    }
    formDataRequestInterceptor(cfg)
    expect(cfg.headers['Content-Type']).toBe('application/x-www-form-urlencoded')
  })

  it('Blob body（不是 FormData）下不修改', () => {
    const cfg = {
      url: '/api/foo',
      data: new Blob(['hello']),
      headers: { 'Content-Type': 'text/plain' },
    }
    formDataRequestInterceptor(cfg)
    expect(cfg.headers['Content-Type']).toBe('text/plain')
  })

  it('headers 为 undefined 时不报错（防御性）', () => {
    const cfg = {
      url: '/api/foo',
      data: makeFormData(),
      // headers 缺失
    }
    expect(() => formDataRequestInterceptor(cfg)).not.toThrow()
  })

  it('cfg 为 null 时不报错（防御性）', () => {
    expect(() => formDataRequestInterceptor(null)).not.toThrow()
    expect(() => formDataRequestInterceptor(undefined)).not.toThrow()
  })

  it('返回值必须是 cfg（axios 拦截器契约）', () => {
    const cfg = { data: { foo: 'bar' }, headers: {} }
    const ret = formDataRequestInterceptor(cfg)
    expect(ret).toBe(cfg) // 同一引用；axios 拦截器链依赖返回值
  })

  it('FormData + 自定义其它请求头：只清 Content-Type，其它保留', () => {
    const cfg = {
      data: makeFormData(),
      headers: {
        'Content-Type': 'multipart/form-data',
        'X-Request-Id': 'req-123',
        'X-Trace-Id': 'trace-abc',
      },
    }
    formDataRequestInterceptor(cfg)
    expect(cfg.headers['Content-Type']).toBeUndefined()
    expect(cfg.headers['X-Request-Id']).toBe('req-123')
    expect(cfg.headers['X-Trace-Id']).toBe('trace-abc')
  })
})
