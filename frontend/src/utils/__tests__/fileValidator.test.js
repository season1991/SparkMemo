/**
 * utils/fileValidator 单测（v0.6.0.1 新增）。
 *
 * 核心覆盖：
 * - el-upload wrapper 解包（raw 字段）
 * - 非 wrapper 裸 File 降级
 * - null / 类型错误降级
 * - 后缀 .xlsx 校验（不区分大小写）
 * - 大小上限校验
 * - 完整 validateElUploadFile 函数
 */
import { describe, it, expect } from 'vitest'
import {
  isWithinSize,
  isXlsxFile,
  unwrapElUploadFile,
  validateElUploadFile,
} from '../fileValidator.js'

function makeFile(name = 'test.xlsx', size = 1024, type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') {
  return new File([new Uint8Array(size)], name, { type })
}

function makeWrapper(file, extras = {}) {
  return {
    name: file.name,
    size: file.size,
    status: 'ready',
    uid: 1,
    percentage: 0,
    raw: file,
    ...extras,
  }
}

describe('unwrapElUploadFile', () => {
  it('el-upload wrapper 形态：解出 raw', () => {
    const f = makeFile()
    const wrapper = makeWrapper(f)
    const result = unwrapElUploadFile(wrapper)
    expect(result).toBe(f)
    expect(result instanceof File).toBe(true)
  })

  it('裸 File（直接传 File 而非 wrapper）：降级用 file 本身', () => {
    const f = makeFile()
    const result = unwrapElUploadFile(f)
    expect(result).toBe(f)
  })

  it('null：返回 null', () => {
    expect(unwrapElUploadFile(null)).toBeNull()
    expect(unwrapElUploadFile(undefined)).toBeNull()
  })

  it('普通对象（既非 wrapper 也非 File）：返回 null', () => {
    expect(unwrapElUploadFile({ name: 'X', size: 10 })).toBeNull()
    expect(unwrapElUploadFile('string')).toBeNull()
    expect(unwrapElUploadFile(123)).toBeNull()
  })

  it('wrapper 但 raw 不是 File：返回 null', () => {
    expect(unwrapElUploadFile({ name: 'X', raw: 'not-a-file' })).toBeNull()
    expect(unwrapElUploadFile({ name: 'X', raw: { blob: 1 } })).toBeNull()
    expect(unwrapElUploadFile({ name: 'X' })).toBeNull()
  })

  it('wrapper 但 raw 缺失：返回 null（不是降级到 wrapper）', () => {
    expect(unwrapElUploadFile({ name: 'X', size: 10, uid: 1 })).toBeNull()
  })
})

describe('isXlsxFile', () => {
  it('大写 .XLSX：通过', () => {
    expect(isXlsxFile(makeFile('T.XLSX'))).toBe(true)
  })

  it('小写 .xlsx：通过', () => {
    expect(isXlsxFile(makeFile('t.xlsx'))).toBe(true)
  })

  it('大小写混合 .Xlsx：通过', () => {
    expect(isXlsxFile(makeFile('My.File.Xlsx'))).toBe(true)
  })

  it('非 .xlsx：拒绝', () => {
    expect(isXlsxFile(makeFile('t.csv'))).toBe(false)
    expect(isXlsxFile(makeFile('t.xls'))).toBe(false)
    expect(isXlsxFile(makeFile('t.xlsx.txt'))).toBe(false)
  })

  it('null / 没名字：拒绝', () => {
    expect(isXlsxFile(null)).toBe(false)
    expect(isXlsxFile({})).toBe(false)
  })
})

describe('isWithinSize', () => {
  it('小于上限：通过', () => {
    expect(isWithinSize(makeFile('t.xlsx', 1024))).toBe(true)
  })

  it('等于上限：通过', () => {
    expect(isWithinSize(makeFile('t.xlsx', 20 * 1024 * 1024))).toBe(true)
  })

  it('超过上限：拒绝', () => {
    expect(isWithinSize(makeFile('t.xlsx', 20 * 1024 * 1024 + 1))).toBe(false)
  })

  it('自定义 limit', () => {
    expect(isWithinSize(makeFile('t.xlsx', 2048), 1024)).toBe(false)
    expect(isWithinSize(makeFile('t.xlsx', 512), 1024)).toBe(true)
  })

  it('null：拒绝', () => {
    expect(isWithinSize(null)).toBe(false)
  })
})

describe('validateElUploadFile（组合校验）', () => {
  it('wrapper + .xlsx + 正常大小：ok + file', () => {
    const f = makeFile('t.xlsx', 2048)
    const wrapper = makeWrapper(f)
    const result = validateElUploadFile(wrapper)
    expect(result.ok).toBe(true)
    expect(result.file).toBe(f)
  })

  it('裸 File + .xlsx：ok（验证兼容降级）', () => {
    const f = makeFile('t.xlsx', 2048)
    const result = validateElUploadFile(f)
    expect(result.ok).toBe(true)
    expect(result.file).toBe(f)
  })

  it('null：reason=empty', () => {
    expect(validateElUploadFile(null)).toEqual({ ok: false, reason: 'empty' })
  })

  it('非 File 普通对象：reason=wrong_type', () => {
    expect(validateElUploadFile({ name: 'X', size: 10 })).toEqual({
      ok: false,
      reason: 'wrong_type',
    })
  })

  it('wrapper 但 raw 不存在：reason=wrong_type', () => {
    const result = validateElUploadFile({ name: 't.xlsx', size: 10, uid: 1 })
    expect(result).toEqual({ ok: false, reason: 'wrong_type' })
  })

  it('.xlsx 大写 + 正常大小：ok', () => {
    const f = makeFile('T.XLSX', 1024)
    expect(validateElUploadFile(makeWrapper(f)).ok).toBe(true)
  })

  it('.csv 后缀：reason=wrong_ext', () => {
    const f = makeFile('t.csv', 1024)
    expect(validateElUploadFile(makeWrapper(f))).toEqual({
      ok: false,
      reason: 'wrong_ext',
    })
  })

  it('.xlsx 但 21 MB：reason=too_large', () => {
    const f = makeFile('t.xlsx', 21 * 1024 * 1024)
    expect(validateElUploadFile(makeWrapper(f))).toEqual({
      ok: false,
      reason: 'too_large',
    })
  })

  it('顺序优先级：先 wrong_type 后 wrong_ext（避免「wrapper 但后缀是 csv」穿透）', () => {
    // 这是 wrapper 解包路径走通后再判后缀的逻辑；验证 not-callable wrapper 时先挡住
    const result = validateElUploadFile('plain-string')
    expect(result).toEqual({ ok: false, reason: 'wrong_type' })
  })
})
