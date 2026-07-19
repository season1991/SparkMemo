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
import * as blobUtil from '../../utils/downloadBlob.js'
import { ApiError } from '../../api/client.js'
import PivotQuery from '../PivotQuery.vue'

const queryPivotMock = vi.spyOn(pivotApi, 'queryPivot')
const exportPivotMock = vi.spyOn(pivotApi, 'exportPivot')
const lookupCountriesMock = vi.spyOn(pivotApi, 'lookupCountries')
const lookupCategoriesMock = vi.spyOn(pivotApi, 'lookupCategories')
const lookupConfigNamesMock = vi.spyOn(pivotApi, 'lookupConfigNames')
const lookupWeeksMock = vi.spyOn(pivotApi, 'lookupWeeksOfMonth')
const getDistinctVendorsMock = vi.spyOn(dspApi, 'getDistinctVendors')
const getDistinctItemsMock = vi.spyOn(dspApi, 'getDistinctItems')
const getDistinctSubItemsMock = vi.spyOn(dspApi, 'getDistinctSubItems')
const getDistinctVersionDatesMock = vi.spyOn(dspApi, 'getDistinctVersionDates')
const downloadBlobMock = vi.spyOn(blobUtil, 'downloadBlob')

const CURRENT_YEAR = String(new Date().getFullYear())

beforeEach(() => {
  setActivePinia(createPinia())
  ElMessageSuccess.mockReset()
  ElMessageWarning.mockReset()
  ElMessageError.mockReset()
  queryPivotMock.mockReset()
  exportPivotMock.mockReset()
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

// ==================== v0.5.7 新增 ====================

describe('v0.5.7 PivotQuery getRowClass 行级底色', () => {
  it('Demand 行 → row--ds-base', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const cls = wrapper.vm.getRowClass({ row: { data_type: 'Demand' } })
    expect(cls).toBe('row--ds-base')
  })

  it('Supply 行 → row--ds-base（与 Demand 同色，强调"配对"语义）', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const cls = wrapper.vm.getRowClass({ row: { data_type: 'Supply' } })
    expect(cls).toBe('row--ds-base')
  })

  it('TTL_GAP 行 → row--ttl-gap（单期派生）', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const cls = wrapper.vm.getRowClass({ row: { data_type: 'TTL_GAP' } })
    expect(cls).toBe('row--ttl-gap')
  })

  it('Rolling_TTLGAP 行 → row--rolling（累计派生）', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const cls = wrapper.vm.getRowClass({ row: { data_type: 'Rolling_TTLGAP' } })
    expect(cls).toBe('row--rolling')
  })

  it('data_type 缺失 → 空字符串', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    expect(wrapper.vm.getRowClass({ row: {} })).toBe('')
    expect(wrapper.vm.getRowClass({ row: null })).toBe('')
  })
})

// v0.5.7.2 新增：静态源文件检查 — 防止 v0.5.7 的「scoped + 子组件缺 :deep()」回归
// jsdom 不能验证 <style scoped> 编译后选择器是否真实命中 Element Plus 子组件 DOM，
// 但能扫描源码确保每条 background-color 规则都在 :deep() 块内，从而保证编译产物可匹配
const fs = require('node:fs')
const path = require('node:path')
const sourcePath = path.resolve(__dirname, '..', 'PivotQuery.vue')
const sourceCode = fs.readFileSync(sourcePath, 'utf-8')

describe('v0.5.7.2 PivotQuery 行级底色 :deep() 源文件检查', () => {
  it('源码包含 #fdf6ec 颜色值（TTL_GAP 行底色）', () => {
    expect(sourceCode).toContain('#fdf6ec')
  })

  it('源码包含 #fef0f0 颜色值（Rolling_TTLGAP 行底色）', () => {
    expect(sourceCode).toContain('#fef0f0')
  })

  it('源码包含 #ecf5ff 颜色值（Demand+Supply 行底色）', () => {
    expect(sourceCode).toContain('#ecf5ff')
  })

  it('3 条 background-color !important 规则都在 :deep() 选择器内', () => {
    // 实现思路：从 `background-color: <color> !important` 反向找到本规则所在选择器区段
    // （前一个 `}` 到规则内容），该区段必须含 `:deep(`。
    const colors = ['#fdf6ec', '#fef0f0', '#ecf5ff']
    for (const color of colors) {
      const idx = sourceCode.indexOf(`background-color: ${color} !important`)
      expect(idx, `${color} 规则须存在`).toBeGreaterThan(-1)
      // 向前找最近的 `}` 或文件头；从那里开始到 idx 是选择器区段（含 `:deep(...)`）
      const prevBrace = sourceCode.lastIndexOf('}', idx)
      const searchStart = prevBrace === -1 ? 0 : prevBrace + 1
      const selectorRegion = sourceCode.slice(searchStart, idx)
      expect(
        selectorRegion.includes(':deep('),
        `${color} 规则前的选择器区段必须包含 :deep()（v0.5.7.2 修复）`
      ).toBe(true)
    }
  })
})

// v0.5.7.3 新增：data_type 列宽 90 → 140，防止回到旧值导致 Rolling_TTLGAP 被截断
// jsdom 同样不能验证实际 UI 列宽渲染（同 v0.5.7.2 视觉分组同源问题）
describe('v0.5.7.3 PivotQuery data_type 列宽 90 → 140 源文件检查', () => {
  const dataTypeLine = sourceCode
    .split('\n')
    .find((l) => l.includes("prop: 'data_type'"))

  it('fixedColumns 中包含 prop: \'data_type\' 行', () => {
    expect(dataTypeLine, "data_type 行须存在").toBeDefined()
  })

  it("data_type 行 width = 140（防止回到旧值 90）", () => {
    expect(dataTypeLine).toBeDefined()
    // 同行 80 字符内必须出现 width: 140
    expect(dataTypeLine).toMatch(/width:\s*140/)
  })

  it("data_type 行 width 不再为 90", () => {
    expect(dataTypeLine).toBeDefined()
    expect(dataTypeLine).not.toMatch(/width:\s*90\b/)
  })
})

describe('v0.5.7 PivotQuery getCellClass cell 字体规则', () => {
  it('TTL_GAP 行的负数量 → cell-negative', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const row = { data_type: 'TTL_GAP', quantities: { '2026-07-06': -10 } }
    expect(wrapper.vm.getCellClass(row, '2026-07-06')).toBe('cell-negative')
  })

  it('Rolling_TTLGAP 行的负数量 → cell-negative', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const row = { data_type: 'Rolling_TTLGAP', quantities: { '2026-07-06': -25 } }
    expect(wrapper.vm.getCellClass(row, '2026-07-06')).toBe('cell-negative')
  })

  it('TTL_GAP 行的零数量 → zero-cell（不加红）', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const row = { data_type: 'TTL_GAP', quantities: { '2026-07-06': 0 } }
    expect(wrapper.vm.getCellClass(row, '2026-07-06')).toBe('zero-cell')
  })

  it('TTL_GAP 行的正数量 → nonzero-cell（不加红）', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const row = { data_type: 'TTL_GAP', quantities: { '2026-07-06': 20 } }
    expect(wrapper.vm.getCellClass(row, '2026-07-06')).toBe('nonzero-cell')
  })

  it('Demand / Supply 行的任意数量（即使是负）→ 不返回 cell-negative', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    // 业务上 Demand / Supply 不会出现负数；负数时也按 zero/nonzero 处理（不触发红）
    const demandNeg = { data_type: 'Demand', quantities: { '2026-07-06': -5 } }
    const supplyPos = { data_type: 'Supply', quantities: { '2026-07-06': 100 } }
    expect(wrapper.vm.getCellClass(demandNeg, '2026-07-06')).toBe('nonzero-cell')
    expect(wrapper.vm.getCellClass(supplyPos, '2026-07-06')).toBe('nonzero-cell')
  })
})

describe('v0.5.7 PivotQuery version_dates / version_date_single 字段拆分', () => {
  it('初始 form 包含两个版本日期字段：version_dates（数组）+ version_date_single（空字符串）', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    expect(vm.form.version_dates).toEqual([])
    expect(vm.form.version_date_single).toBe('')
  })
})

describe('v0.5.7 PivotQuery versionDateVModel 受控 v-model', () => {
  it('demand 模式 getter 返回数组', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.pivot_type = 'demand'
    vm.form.version_dates = ['v1', 'v2']
    expect(vm.versionDateVModel).toEqual(['v1', 'v2'])
  })

  it('dps 模式 getter 返回字符串', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.pivot_type = 'demand_plus_supply'
    vm.form.version_date_single = 'v1'
    expect(vm.versionDateVModel).toBe('v1')
  })

  it('demand 模式 setter 写入数组', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.pivot_type = 'demand'
    vm.versionDateVModel = ['v1', 'v2']
    expect(vm.form.version_dates).toEqual(['v1', 'v2'])
  })

  it('dps 模式 setter 写入字符串', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.pivot_type = 'demand_plus_supply'
    vm.versionDateVModel = 'v1'
    expect(vm.form.version_date_single).toBe('v1')
  })

  it('demand 模式 setter 非数组 → 写为空数组（防御）', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.pivot_type = 'demand'
    vm.versionDateVModel = 'v1'
    expect(vm.form.version_dates).toEqual([])
  })

  it('dps 模式 setter 非字符串 → 写为空字符串（防御）', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.pivot_type = 'demand_plus_supply'
    vm.versionDateVModel = ['v1', 'v2']
    expect(vm.form.version_date_single).toBe('')
  })
})

describe('v0.5.7 PivotQuery canQuery 按模式判定版本日期', () => {
  it('demand 模式 + version_dates 1 个 → canQuery true', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.vendor = 'A'
    vm.form.item = 'X'
    vm.form.sub_item = 'Y'
    vm.form.version_dates = ['2026-06-29']
    vm.form.years = '2026'
    expect(vm.canQuery).toBe(true)
  })

  it('dps 模式 + version_date_single 设置 → canQuery true', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.vendor = 'A'
    vm.form.item = 'X'
    vm.form.sub_item = 'Y'
    vm.form.version_date_single = '2026-06-29'
    vm.form.pivot_type = 'demand_plus_supply'
    vm.form.years = '2026'
    expect(vm.canQuery).toBe(true)
  })

  it('dps 模式 + version_date_single 为空 → canQuery false', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.vendor = 'A'
    vm.form.item = 'X'
    vm.form.sub_item = 'Y'
    vm.form.version_date_single = ''
    vm.form.pivot_type = 'demand_plus_supply'
    vm.form.years = '2026'
    expect(vm.canQuery).toBe(false)
  })
})

describe('v0.5.7 PivotQuery onPivotTypeChange 同步两个字段', () => {
  it('demand → dps：取 version_dates[0] 到 version_date_single；array 清空', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.version_dates = ['2026-06-29', '2026-07-15']
    vm.onPivotTypeChange('demand_plus_supply', 'demand')
    expect(vm.form.version_date_single).toBe('2026-06-29')
    expect(vm.form.version_dates).toEqual([])
  })

  it('demand → dps：version_dates 为空时 version_date_single = ""', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.version_dates = []
    vm.onPivotTypeChange('demand_plus_supply', 'demand')
    expect(vm.form.version_date_single).toBe('')
  })

  it('dps → demand：单值塞入数组；version_date_single 清空', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.version_date_single = '2026-06-29'
    vm.onPivotTypeChange('demand', 'demand_plus_supply')
    expect(vm.form.version_dates).toEqual(['2026-06-29'])
    expect(vm.form.version_date_single).toBe('')
  })

  it('dps → demand：单值为空时数组也为空', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.version_date_single = ''
    vm.onPivotTypeChange('demand', 'demand_plus_supply')
    expect(vm.form.version_dates).toEqual([])
  })

  it('任何 pivot_type 切换都清空 result', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.result = { total_rows: 1 }
    vm.onPivotTypeChange('demand_plus_supply', 'demand')
    expect(vm.result).toBeNull()
  })
})

describe('v0.5.7 PivotQuery buildRequest 按模式返回 version_dates', () => {
  it('demand 模式 → version_dates = form.version_dates 数组', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.vendor = 'A'
    vm.form.item = 'X'
    vm.form.sub_item = 'Y'
    vm.form.version_dates = ['2026-06-29', '2026-07-15']
    vm.form.years = '2026'
    const req = vm.buildRequest()
    expect(req.version_dates).toEqual(['2026-06-29', '2026-07-15'])
    expect(req.pivot_type).toBe('demand')
  })

  it('dps 模式 → version_dates = [version_date_single]', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.vendor = 'A'
    vm.form.item = 'X'
    vm.form.sub_item = 'Y'
    vm.form.version_date_single = '2026-06-29'
    vm.form.pivot_type = 'demand_plus_supply'
    vm.form.years = '2026'
    const req = vm.buildRequest()
    expect(req.version_dates).toEqual(['2026-06-29'])
    expect(req.pivot_type).toBe('demand_plus_supply')
  })

  it('dps 模式 + version_date_single 空 → version_dates = []', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.vendor = 'A'
    vm.form.item = 'X'
    vm.form.sub_item = 'Y'
    vm.form.version_date_single = ''
    vm.form.pivot_type = 'demand_plus_supply'
    vm.form.years = '2026'
    // canQuery 应为 false，buildRequest 仍能调用，但返回空数组（不阻断）
    const req = vm.buildRequest()
    expect(req.version_dates).toEqual([])
  })
})

describe('v0.5.7 PivotQuery versionDatesForLookup helper', () => {
  it('demand 模式 → 数组副本', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.pivot_type = 'demand'
    vm.form.version_dates = ['v1', 'v2']
    expect(vm.versionDatesForLookup()).toEqual(['v1', 'v2'])
  })

  it('dps 模式 + version_date_single 设置 → 单元素数组', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.pivot_type = 'demand_plus_supply'
    vm.form.version_date_single = 'v1'
    expect(vm.versionDatesForLookup()).toEqual(['v1'])
  })

  it('dps 模式 + version_date_single 空 → 空数组', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.pivot_type = 'demand_plus_supply'
    vm.form.version_date_single = ''
    expect(vm.versionDatesForLookup()).toEqual([])
  })
})

describe('v0.5.7 PivotQuery onReset 同步清空两个字段', () => {
  it('重置 version_date_single 清空', () => {
    getDistinctVendorsMock.mockResolvedValue([])
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.form.version_date_single = '2026-06-29'
    vm.onReset()
    expect(vm.form.version_date_single).toBe('')
  })
})


// ==================== v0.5.8 Excel 导出 ====================


describe('PivotQuery Excel 导出（v0.5.8）', () => {
  it('初始无 result：lastQueryRequest 为 null', () => {
    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    expect(vm.result).toBeNull()
    expect(vm.lastQueryRequest).toBeNull()
    expect(vm.exporting).toBe(false)
  })

  it('查询成功：lastQueryRequest 写入快照', async () => {
    const resp = {
      period_columns: ['2026-07-06'],
      row_groups: [],
      total_rows: 0,
      version_dates: ['2026-06-29'],
      date_granularity: 'week',
    }
    queryPivotMock.mockResolvedValue(resp)

    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    // 走 canQuery 路径
    vm.form.vendor = 'X'
    vm.form.item = 'Y'
    vm.form.sub_item = 'Z'
    vm.form.version_dates = ['2026-06-29']
    vm.form.years = CURRENT_YEAR
    vm.form.months = []

    await vm.onQuery()

    expect(queryPivotMock).toHaveBeenCalledTimes(1)
    // vm.result 是 Vue 响应式代理，用 toEqual 比对值
    expect(vm.result).toEqual(resp)
    expect(vm.lastQueryRequest).not.toBeNull()
    expect(vm.lastQueryRequest.pivot_type).toBe('demand')
    expect(vm.lastQueryRequest.vendor).toBe('X')
  })

  it('点「导出 Excel」：exportPivot(lastQueryRequest) + downloadBlob + success toast', async () => {
    const snapshot = {
      pivot_type: 'demand',
      vendor: 'X', item: 'Y', sub_item: 'Z',
      version_dates: ['2026-06-29'],
      years: [2026],
    }
    const mockBlob = new Blob(['mock xlsx'])
    exportPivotMock.mockResolvedValue(mockBlob)
    downloadBlobMock.mockImplementation(() => {})

    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.lastQueryRequest = snapshot
    vm.result = { period_columns: [], row_groups: [], total_rows: 0, version_dates: [], date_granularity: 'week' }

    await vm.onExport()

    expect(exportPivotMock).toHaveBeenCalledTimes(1)
    expect(exportPivotMock).toHaveBeenCalledWith(snapshot)
    expect(downloadBlobMock).toHaveBeenCalledTimes(1)
    // filename: pivot_demand_{YYYYMMDD_HHMMSS}.xlsx
    const [, filename] = downloadBlobMock.mock.calls[0]
    expect(filename).toMatch(/^pivot_demand_\d{8}_\d{6}\.xlsx$/)
    expect(ElMessageSuccess).toHaveBeenCalledWith('已开始下载')
    expect(vm.exporting).toBe(false)
  })

  it('「lastQueryRequest 隔离」：用户改 countries 后点导出 → 仍用旧 snapshot', async () => {
    const oldSnapshot = {
      pivot_type: 'demand',
      vendor: 'X', item: 'Y', sub_item: 'Z',
      version_dates: ['2026-06-29'],
      countries: ['爱尔兰'],
      years: [2026],
    }
    exportPivotMock.mockResolvedValue(new Blob(['mock']))
    downloadBlobMock.mockImplementation(() => {})

    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.lastQueryRequest = oldSnapshot
    vm.result = { period_columns: [], row_groups: [], total_rows: 0, version_dates: [], date_granularity: 'week' }
    // 用户改了 form.countries（不会影响 lastQueryRequest）
    vm.form.countries = ['日本', '马来西亚']

    await vm.onExport()

    expect(exportPivotMock).toHaveBeenCalledTimes(1)
    // 关键断言：调用参数仍是 oldSnapshot，不是当前 form
    expect(exportPivotMock).toHaveBeenCalledWith(oldSnapshot)
    expect(exportPivotMock.mock.calls[0][0].countries).toEqual(['爱尔兰'])
    expect(exportPivotMock.mock.calls[0][0].countries).not.toEqual(['日本', '马来西亚'])
  })

  it('onReset 后：lastQueryRequest 清空；onExport 无响应', async () => {
    exportPivotMock.mockResolvedValue(new Blob(['mock']))

    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.lastQueryRequest = {
      pivot_type: 'demand', vendor: 'X', item: 'Y', sub_item: 'Z',
      version_dates: ['2026-06-29'], years: [2026],
    }
    getDistinctVendorsMock.mockResolvedValue([])
    vm.onReset()
    expect(vm.lastQueryRequest).toBeNull()

    await vm.onExport()
    expect(exportPivotMock).not.toHaveBeenCalled()
  })

  it('422 笛卡尔积超限：showApiError 走 422 → ElMessage.error', async () => {
    const apiErr = new ApiError(
      422,
      'cartesian product estimated 60000 rows exceeds limit 50000',
      'cartesian product estimated 60000 rows exceeds limit 50000',
    )
    exportPivotMock.mockRejectedValue(apiErr)
    downloadBlobMock.mockImplementation(() => {})

    const wrapper = mount(PivotQuery, { global: { stubs: true } })
    const vm = wrapper.vm
    vm.lastQueryRequest = {
      pivot_type: 'demand', vendor: 'X', item: 'Y', sub_item: 'Z',
      version_dates: ['2026-06-29'], years: [2026],
    }

    const beforeCalls = downloadBlobMock.mock.calls.length
    await vm.onExport()
    const afterCalls = downloadBlobMock.mock.calls.length
    // 422 错误路径下不应触发下载（calls 不增）
    expect(afterCalls).toBe(beforeCalls)
    expect(ElMessageError).toHaveBeenCalledWith(expect.stringContaining('cartesian product'))
    expect(vm.exporting).toBe(false)
  })
})
