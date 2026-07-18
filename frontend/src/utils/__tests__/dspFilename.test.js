import { describe, it, expect } from 'vitest'
import { parseFilename } from '../dspFilename.js'

describe('parseFilename', () => {
  it('解析真实样本 4 段文件名（取前 3 段）', () => {
    expect(parseFilename('Arista-网络设备DSP横版-机箱-061626.xlsx'))
      .toEqual({ vendor: 'Arista', item: '网络设备DSP横版', sub_item: '机箱' })
  })

  it('3 段文件名直接返回', () => {
    expect(parseFilename('a-b-c.xlsx'))
      .toEqual({ vendor: 'a', item: 'b', sub_item: 'c' })
  })

  it('4 段文件名前 3 段，第 4 段丢弃', () => {
    expect(parseFilename('a-b-c-d.xlsx'))
      .toEqual({ vendor: 'a', item: 'b', sub_item: 'c' })
  })

  it('2 段（<3）抛错', () => {
    expect(() => parseFilename('foo-bar.xlsx')).toThrow(/at least 3 segments/)
  })

  it('空字符串抛错', () => {
    expect(() => parseFilename('')).toThrow(/filename is required/)
  })

  it('无扩展名 + 2 段仍抛错（split 按整串）', () => {
    expect(() => parseFilename('foo-bar')).toThrow(/at least 3 segments/)
  })
})
