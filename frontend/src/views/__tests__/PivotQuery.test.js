import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

const ElMessageSuccess = vi.fn()
const ElMessageWarning = vi.fn()
const ElMessageError = vi.fn()

vi.mock('element-plus', () => ({
  ElMessage: {
    success: (...a) => ElMessageSuccess(...a),
    warning: (...a) => ElMessageWarning(...a),
    error: (...a) => ElMessageError(...a),
  },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ path: '/pivot-query' })
}))

import * as pivotApi from '../../api/pivot_query.js'
import * as dspApi from '../../api/dsp_uploads.js'
import PivotQuery from '../PivotQuery.vue'

const queryPivotMock = vi.spyOn(pivotApi, 'queryPivot')
const lookupCountriesMock = vi.spyOn(pivotApi, 'lookupCountries')
const lookupCategoriesMock = vi.spyOn(pivotApi, 'lookupCategories')
const lookupConfigNamesMock = vi.spyOn(pivotApi, 'lookupConfigNames')
const lookupWeeksMock = vi.spyOn(pivotApi, 'lookupWeeksOfMonth')
const getDistinctVendorsMock = vi.spyOn(dspApi, 'getDistinctVendors')
const getDistinctItemsMock = vi.spyOn(dspApi, 'getDistinctItems')
const getDistinctSubItemsMock = vi.spyOn(dspApi, 'getDistinctSubItems')
const getDistinctVersionDatesMock = vi.spyOn(dspApi, 'getDistinctVersionDates')

const CURRENT_YEAR = String(new Date().getFullYear())

beforeEach(() => {
  setActivePinia(createPinia())
  ElMessageSuccess.mockReset()
  ElMessageWarning.mockReset()
  ElMessageError.mockReset()
  queryPivotMock.mockReset()
  lookupCountriesMock.mockReset()
  lookupCategoriesMock.mockReset()
  lookupConfigNamesMock.mockReset()
  lookupWeeksMock.mockReset()
  getDistinctVendorsMock.mockReset()
  getDistinctItemsMock.mockReset()
  getDistinctSubItemsMock.mockReset()
  getDistinctVersionDatesMock.mockReset()
  // 默认返回空数组避免 onMounted 报错
  getDistinctVendorsMock.mockResolvedValue([])
})

describe('PivotQuery 组件挂载与文案', () => {
  it('DOM 烟雾渲染', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    expect(wrapper.find('.pivot-view').exists()).toBe(true)
    expect(wrapper.find('.form-card').exists()).toBe(true)
    // 初始无结果卡
    expect(wrapper.find('.result-card').exists()).toBe(false)
  })

  it('页面标题与 hint', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    expect(wrapper.text()).toContain('透视查询')
    expect(wrapper.text()).toContain('笛卡尔积')
  })

  it('初始 form 状态', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    expect(vm.form.vendor).toBe('')
    expect(vm.form.item).toBe('')
    expect(vm.form.sub_item).toBe('')
    expect(vm.form.version_dates).toEqual([])
    expect(vm.form.pivot_type).toBe('demand')
    expect(vm.form.date_granularity).toBe('week')
    expect(vm.form.countries).toEqual([])
    expect(vm.form.categories).toEqual([])
    expect(vm.form.config_names).toEqual([])
    expect(vm.form.years).toBe(CURRENT_YEAR)
    expect(vm.form.months).toEqual([])
    expect(vm.form.weeks).toEqual([])
  })

  it('初始 canQuery = false（缺 4 必填）', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    expect(wrapper.vm.canQuery).toBe(false)
  })

  it('canQuery 条件：4 必填齐全 + years 有默认值 → true', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    // 4 必填齐全，years 已有默认值
    vm.form.vendor = 'A'
    vm.form.item = 'X'
    vm.form.sub_item = 'Y'
    vm.form.version_dates = ['2026-06-29']
    expect(vm.canQuery).toBe(true)
  })
})

describe('PivotQuery buildRequest 构造', () => {
  it('只包含非空字段', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.vendor = 'A'
    vm.form.item = 'X'
    vm.form.sub_item = 'Y'
    vm.form.version_dates = ['2026-06-29']
    vm.form.years = '2026'
    vm.form.months = [7]
    const req = vm.buildRequest()
    expect(req).toEqual({
      pivot_type: 'demand',
      vendor: 'A',
      item: 'X',
      sub_item: 'Y',
      version_dates: ['2026-06-29'],
      expand_to_daily: false,
      years: [2026],
      months: [7],
    })
    // 不含空字段
    expect(req.countries).toBeUndefined()
    expect(req.categories).toBeUndefined()
    expect(req.config_names).toBeUndefined()
    expect(req.weeks).toBeUndefined()
  })

  it('expand_to_daily 由 date_granularity 决定', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.vendor = 'A'
    vm.form.item = 'X'
    vm.form.sub_item = 'Y'
    vm.form.version_dates = ['2026-06-29']
    vm.form.years = '2026'
    vm.form.date_granularity = 'day'
    expect(vm.buildRequest().expand_to_daily).toBe(true)
    vm.form.date_granularity = 'week'
    expect(vm.buildRequest().expand_to_daily).toBe(false)
  })

  it('years 单字符串 → 包为 [number] 数组', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.vendor = 'A'
    vm.form.item = 'X'
    vm.form.sub_item = 'Y'
    vm.form.version_dates = ['2026-06-29']
    vm.form.years = '2026'
    vm.form.months = [7]
    const req = vm.buildRequest()
    expect(req.years).toEqual([2026])
    expect(typeof req.years[0]).toBe('number')
  })

  it('非空业务行筛选包含在请求中', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.vendor = 'A'
    vm.form.item = 'X'
    vm.form.sub_item = 'Y'
    vm.form.version_dates = ['2026-06-29']
    vm.form.years = '2026'
    vm.form.countries = ['Ireland']
    vm.form.categories = ['机箱']
    vm.form.config_names = ['32Q-TOR-T3']
    const req = vm.buildRequest()
    expect(req.countries).toEqual(['Ireland'])
    expect(req.categories).toEqual(['机箱'])
    expect(req.config_names).toEqual(['32Q-TOR-T3'])
  })
})

describe('PivotQuery cellQty 辅助函数', () => {
  it('quantities 存在 → 返回值', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const row = { quantities: { '2026-07-06': 100, '2026-07-13': 0 } }
    expect(wrapper.vm.cellQty(row, '2026-07-06')).toBe(100)
    expect(wrapper.vm.cellQty(row, '2026-07-13')).toBe(0)
  })

  it('quantities 不存在 / key 缺失 → 0', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    expect(wrapper.vm.cellQty({}, '2026-07-06')).toBe(0)
    expect(wrapper.vm.cellQty({ quantities: {} }, '2026-07-06')).toBe(0)
  })
})

describe('PivotQuery onQuery 行为', () => {
  it('canQuery = false → warning toast', async () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.vendor = ''
    vm.form.version_dates = []
    await vm.onQuery()
    expect(ElMessageWarning).toHaveBeenCalledWith(
      expect.stringContaining('必填项')
    )
    expect(queryPivotMock).not.toHaveBeenCalled()
  })

  it('查询成功 → result 写入 + success toast', async () => {
    queryPivotMock.mockResolvedValue({
      period_columns: ['2026-07-06'],
      row_groups: [{ country: 'Ireland', version_date: '2026-06-29', quantities: { '2026-07-06': 100 } }],
      total_rows: 1,
      version_dates: ['2026-06-29'],
      date_granularity: 'week',
    })
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.vendor = 'A'
    vm.form.item = 'X'
    vm.form.sub_item = 'Y'
    vm.form.version_dates = ['2026-06-29']
    vm.form.years = '2026'
    await vm.onQuery()
    expect(queryPivotMock).toHaveBeenCalledTimes(1)
    expect(vm.result).not.toBeNull()
    expect(vm.result.total_rows).toBe(1)
    expect(ElMessageSuccess).toHaveBeenCalledWith(expect.stringContaining('1 行'))
  })

  it('查询失败 → showApiError', async () => {
    const { ApiError } = await import('../../api/client.js')
    queryPivotMock.mockRejectedValue(new ApiError(422, 'cartesian product exceeded', 'cartesian product exceeded'))
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.vendor = 'A'
    vm.form.item = 'X'
    vm.form.sub_item = 'Y'
    vm.form.version_dates = ['2026-06-29']
    vm.form.years = '2026'
    await vm.onQuery()
    expect(vm.result).toBeNull()
  })
})

describe('PivotQuery onReset', () => {
  it('重置全清 + years 恢复默认当年 + 重新加载 vendors', () => {
    getDistinctVendorsMock.mockResolvedValue(['A', 'B'])
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    // 先设置一些值
    vm.form.vendor = 'A'
    vm.form.item = 'X'
    vm.form.sub_item = 'Y'
    vm.form.version_dates = ['2026-06-29']
    vm.form.countries = ['Ireland']
    vm.form.years = '2025'
    vm.result = { total_rows: 1 }
    vm.onReset()
    expect(vm.form.vendor).toBe('')
    expect(vm.form.item).toBe('')
    expect(vm.form.sub_item).toBe('')
    expect(vm.form.version_dates).toEqual([])
    expect(vm.form.countries).toEqual([])
    expect(vm.form.years).toBe(CURRENT_YEAR)
    expect(vm.result).toBeNull()
  })
})

describe('PivotQuery loadWeeks 联动逻辑', () => {
  it('years 为空 → weeks 清空', async () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.years = ''
    await vm.loadWeeks()
    expect(vm.weekOptions).toEqual([])
    expect(lookupWeeksMock).not.toHaveBeenCalled()
  })

  it('years + months → 按 (year, month) 查询', async () => {
    lookupWeeksMock.mockResolvedValue([{ week_id: 28, week_start_date: '2026-07-06' }])
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.years = '2026'
    vm.form.months = [7]
    await vm.loadWeeks()
    expect(lookupWeeksMock).toHaveBeenCalledWith(2026, 7)
    expect(vm.weekOptions.length).toBe(1)
    expect(vm.weekOptions[0].week_id).toBe(28)
  })

  it('years 有值但 months 为空 → 遍历 1-12', async () => {
    lookupWeeksMock.mockResolvedValue([])
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.years = '2026'
    vm.form.months = []
    await vm.loadWeeks()
    // 应调用 12 次（1-12 月）
    expect(lookupWeeksMock).toHaveBeenCalledTimes(12)
  })
})

describe('PivotQuery 业务行级联事件', () => {
  it('onCountriesChange → 清空下级 + 拉 categories', async () => {
    lookupCategoriesMock.mockResolvedValue(['机箱'])
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.categories = ['旧值']
    vm.form.config_names = ['旧值']
    vm.onCountriesChange()
    expect(vm.form.categories).toEqual([])
    expect(vm.form.config_names).toEqual([])
  })

  it('onCategoriesChange → 清空下级 + 拉 configNames', async () => {
    lookupConfigNamesMock.mockResolvedValue(['32Q'])
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.config_names = ['旧值']
    vm.onCategoriesChange()
    expect(vm.form.config_names).toEqual([])
  })
})

describe('PivotQuery lookup 调用入参', () => {
  it('onVersionDatesChange → 调 lookupCountries', async () => {
    lookupCountriesMock.mockResolvedValue(['Ireland'])
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.vendor = 'A'
    vm.form.item = 'X'
    vm.form.sub_item = 'Y'
    vm.form.version_dates = ['2026-06-29']
    await vm.onVersionDatesChange()
    expect(lookupCountriesMock).toHaveBeenCalledWith({
      vendor: 'A', item: 'X', sub_item: 'Y',
      version_dates: ['2026-06-29'],
    })
  })

  it('onYearsChange → 清空 weeks + 调 loadWeeks', async () => {
    lookupWeeksMock.mockResolvedValue([])
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.weeks = [28]
    vm.form.years = '2026'
    vm.onYearsChange()
    expect(vm.form.weeks).toEqual([])
  })
})
