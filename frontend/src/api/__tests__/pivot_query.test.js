import { describe, it, expect, vi, beforeEach } from 'vitest'

// axios 客户端的可控 mock：拦截 POST/GET 并记录调用。
const post = vi.fn()
const get = vi.fn()

vi.mock('../client.js', () => ({
  default: {
    post: (...args) => post(...args),
    get: (...args) => get(...args),
  }
}))

import {
  queryPivot,
  lookupCountries,
  lookupCategories,
  lookupConfigNames,
  lookupWeeksOfMonth,
} from '../pivot_query.js'

beforeEach(() => {
  post.mockReset()
  get.mockReset()
})

describe('queryPivot', () => {
  it('走 POST /pivot-query', async () => {
    const mockResponse = {
      period_columns: ['2026-07-06'],
      row_groups: [],
      total_rows: 0,
      version_dates: ['2026-06-29'],
      date_granularity: 'week',
    }
    post.mockResolvedValue(mockResponse)
    const result = await queryPivot({
      pivot_type: 'demand',
      vendor: 'A',
      item: 'X',
      sub_item: 'Y',
      version_dates: ['2026-06-29'],
      years: [2026],
      months: [7],
    })
    expect(post).toHaveBeenCalledTimes(1)
    expect(post).toHaveBeenCalledWith('/pivot-query', expect.objectContaining({
      pivot_type: 'demand',
    }))
    expect(result).toEqual(mockResponse)
  })

  it('请求体原样透传', async () => {
    post.mockResolvedValue({ period_columns: [], row_groups: [], total_rows: 0, version_dates: [], date_granularity: 'day' })
    const req = {
      pivot_type: 'demand',
      vendor: 'A',
      item: 'X',
      sub_item: 'Y',
      version_dates: ['2026-06-29'],
      countries: ['Ireland'],
      categories: ['机箱'],
      config_names: ['32Q-TOR-T3'],
      years: [2026],
      months: [7],
      weeks: [28],
      expand_to_daily: true,
    }
    await queryPivot(req)
    expect(post).toHaveBeenCalledWith('/pivot-query', req)
  })
})

describe('lookupCountries', () => {
  it('走 GET /pivot-query/lookups/countries，version_dates 逗号分隔', async () => {
    get.mockResolvedValue(['Ireland', 'Japan'])
    const result = await lookupCountries({
      vendor: 'A', item: 'X', sub_item: 'Y',
      version_dates: ['2026-06-29', '2026-07-06'],
    })
    expect(get).toHaveBeenCalledWith('/pivot-query/lookups/countries', {
      params: {
        vendor: 'A', item: 'X', sub_item: 'Y',
        version_dates: '2026-06-29,2026-07-06',
      },
    })
    expect(result).toEqual(['Ireland', 'Japan'])
  })

  it('version_dates 为空数组 → 逗号分隔为空字符串', async () => {
    get.mockResolvedValue([])
    await lookupCountries({ vendor: 'A', item: 'X', sub_item: 'Y', version_dates: [] })
    expect(get).toHaveBeenCalledWith('/pivot-query/lookups/countries', {
      params: { vendor: 'A', item: 'X', sub_item: 'Y', version_dates: '' },
    })
  })
})

describe('lookupCategories', () => {
  it('走 GET /pivot-query/lookups/categories，含 countries 参数', async () => {
    get.mockResolvedValue(['机箱'])
    await lookupCategories({
      vendor: 'A', item: 'X', sub_item: 'Y',
      version_dates: ['2026-06-29'],
      countries: ['Ireland', 'Japan'],
    })
    expect(get).toHaveBeenCalledWith('/pivot-query/lookups/categories', {
      params: {
        vendor: 'A', item: 'X', sub_item: 'Y',
        version_dates: '2026-06-29',
        countries: 'Ireland,Japan',
      },
    })
  })
})

describe('lookupConfigNames', () => {
  it('走 GET /pivot-query/lookups/config-names，含 countries + categories', async () => {
    get.mockResolvedValue(['32Q-TOR-T3'])
    await lookupConfigNames({
      vendor: 'A', item: 'X', sub_item: 'Y',
      version_dates: ['2026-06-29'],
      countries: ['Ireland'],
      categories: ['机箱'],
    })
    expect(get).toHaveBeenCalledWith('/pivot-query/lookups/config-names', {
      params: {
        vendor: 'A', item: 'X', sub_item: 'Y',
        version_dates: '2026-06-29',
        countries: 'Ireland',
        categories: '机箱',
      },
    })
  })
})

describe('lookupWeeksOfMonth', () => {
  it('走 GET /pivot-query/lookups/weeks-of-month', async () => {
    get.mockResolvedValue([{ week_id: 28, week_start_date: '2026-07-06' }])
    const result = await lookupWeeksOfMonth(2026, 7)
    expect(get).toHaveBeenCalledWith('/pivot-query/lookups/weeks-of-month', {
      params: { year: 2026, month: 7 },
    })
    expect(result).toEqual([{ week_id: 28, week_start_date: '2026-07-06' }])
  })
})
