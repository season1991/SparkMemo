<script setup>
/**
 * 透视查询页（路由 /pivot-query，v0.5.6）。
 *
 * 三组筛选 + 一张透视表：
 * 1. 必填定位：vendor + item + sub_item（级联下拉，复用 dsp_uploads.js）+ version_dates（多选）
 * 2. pivot_type（v0.5.6 固定 demand）+ 日期粒度（按周 / 按日）
 * 3. 业务行筛选：countries / categories / config_names 三级级联（从 lookup API 拉）
 * 4. 时间维度筛选：years（日期控件）+ months（1-12 下拉）+ weeks（根据 years+months 联动）
 *
 * 数据流：
 *   - 选择 vendor/item/sub_item → 复用 dsp_uploads 的 distinct 系列 API 拉下拉
 *   - 选择 country → 重新拉 category（仅显示该 country 下有的）
 *   - 选择 category → 重新拉 config_name（仅显示该 country+category 下有的）
 *   - 选择 years + months → 拉 weeks-of-month 计算可选的 ISO 周编号
 *   - 点击「查询」→ POST /api/pivot-query → 渲染 row_groups × period_columns 透视表
 *
 * 错误沿用 client.showApiError(err)；Pydantic 级联校验失败由 422 错误消息展示给用户。
 */
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { ApiError, showApiError } from '../api/client.js'
import {
  getDistinctVendors,
  getDistinctItems,
  getDistinctSubItems,
  getDistinctVersionDates
} from '../api/dsp_uploads.js'
import {
  queryPivot,
  lookupCountries,
  lookupCategories,
  lookupConfigNames,
  lookupWeeksOfMonth,
  exportPivot
} from '../api/pivot_query.js'
import { downloadBlob } from '../utils/downloadBlob.js'

// ==================== 级联下拉数据 ====================

const vendorOptions = ref([])
const itemOptions = ref([])
const subItemOptions = ref([])
const versionDateOptions = ref([])

// 业务行筛选 options（lookup API 拉取）
const countryOptions = ref([])
const categoryOptions = ref([])
const configNameOptions = ref([])

// 周编号 options（按 (years + months) 联动）
const weekOptions = ref([])

const loadingVendors = ref(false)
const loadingItems = ref(false)
const loadingSubItems = ref(false)
const loadingVersionDates = ref(false)
const loadingCountries = ref(false)
const loadingCategories = ref(false)
const loadingConfigNames = ref(false)
const loadingWeeks = ref(false)

// ==================== 表单状态 ====================

const form = reactive({
  // 必填定位
  vendor: '',
  item: '',
  sub_item: '',
  // v0.5.7 拆分：demand 模式用数组，demand_plus_supply 模式用单值
  version_dates: [],            // demand 模式专用（数组，多选）
  version_date_single: '',      // demand_plus_supply 模式专用（单值）
  // pivot 类型
  pivot_type: 'demand',
  // 日期粒度
  date_granularity: 'week',  // 'week' | 'day'
  // 业务行筛选（多选，三级级联）
  countries: [],
  categories: [],
  config_names: [],
  // 时间维度
  years: String(new Date().getFullYear()),  // ISO 年（string，单选）
  months: [],  // 自然月 1-12（number[]）
  weeks: []    // ISO 周编号（number[]）
})

const querying = ref(false)
const result = ref(null)  // PivotQueryResponse

// v0.5.8 新增：Excel 导出相关状态
const exporting = ref(false)
// 上次成功查询的请求快照；导出始终用此快照，避免「改了筛选但忘了重查」的隐性不一致
const lastQueryRequest = ref(null)

// ==================== 计算属性 ====================

const canQuery = computed(() => {
  // v0.5.7 修订：version_dates / version_date_single 按 pivot_type 互斥生效
  const hasVersion =
    form.pivot_type === 'demand'
      ? form.version_dates.length >= 1
      : form.version_date_single !== ''
  return (
    form.vendor !== '' &&
    form.item !== '' &&
    form.sub_item !== '' &&
    hasVersion &&
    (form.years !== '' || form.months.length >= 1 || form.weeks.length >= 1)
  )
})

// v0.5.7 受控 v-model：el-select v-model 与 :multiple 类型严格匹配
// demand → 数组（多选）；demand_plus_supply → string（单选）；两者通过 setter 写到不同字段
const versionDateVModel = computed({
  get() {
    return form.pivot_type === 'demand' ? form.version_dates : form.version_date_single
  },
  set(v) {
    if (form.pivot_type === 'demand') {
      form.version_dates = Array.isArray(v) ? v : []
    } else {
      form.version_date_single = typeof v === 'string' ? v : ''
    }
  }
})

const cascadeHint = computed(() => {
  // 业务行级联提示
  if (form.config_names.length > 0 && form.categories.length === 0) {
    return '已选择 config_names，请同时选择 categories 与 countries'
  }
  if (form.categories.length > 0 && form.countries.length === 0) {
    return '已选择 categories，请同时选择 countries'
  }
  // 时间维度级联提示（years 有默认值恒不为空）
  if (form.weeks.length > 0 && form.months.length === 0) {
    return '已选择 weeks，请同时选择 months'
  }
  if (form.years === '' && form.months.length === 0 && form.weeks.length === 0) {
    return '请至少选择一个时间维度（years / months / weeks）'
  }
  return ''
})

// 透视表固定列（业务维度 + version_date）
const fixedColumns = [
  { prop: 'version_date', label: '版本日期', width: 110 },
  { prop: 'country', label: 'Country', width: 110 },
  { prop: 'category', label: 'Category', width: 110 },
  { prop: 'config_code', label: 'Config Code', width: 140 },
  { prop: 'config_name', label: 'Config Name', width: 160 },
  { prop: 'data_type', label: 'Data Type', width: 140 },
  { prop: 'ttl', label: 'TTL', width: 60 },
]

const monthOptions = [
  { value: 1, label: '1月' }, { value: 2, label: '2月' }, { value: 3, label: '3月' },
  { value: 4, label: '4月' }, { value: 5, label: '5月' }, { value: 6, label: '6月' },
  { value: 7, label: '7月' }, { value: 8, label: '8月' }, { value: 9, label: '9月' },
  { value: 10, label: '10月' }, { value: 11, label: '11月' }, { value: 12, label: '12月' }
]

// ==================== helper: 判断 (vendor, item, sub_item, version_dates) 是否就绪 ====================

const hasBusinessContext = computed(() => {
  return form.vendor !== '' && form.item !== '' && form.sub_item !== ''
})

// ==================== 4 字段级联加载 ====================

async function loadVendors() {
  loadingVendors.value = true
  try {
    vendorOptions.value = await getDistinctVendors()
  } catch (err) {
    showApiError(err)
  } finally {
    loadingVendors.value = false
  }
}

async function loadItems() {
  if (!form.vendor) {
    itemOptions.value = []
    return
  }
  loadingItems.value = true
  try {
    itemOptions.value = await getDistinctItems(form.vendor)
  } catch (err) {
    showApiError(err)
  } finally {
    loadingItems.value = false
  }
}

async function loadSubItems() {
  if (!form.vendor || !form.item) {
    subItemOptions.value = []
    return
  }
  loadingSubItems.value = true
  try {
    subItemOptions.value = await getDistinctSubItems(form.vendor, form.item)
  } catch (err) {
    showApiError(err)
  } finally {
    loadingSubItems.value = false
  }
}

async function loadVersionDates() {
  if (!form.vendor || !form.item || !form.sub_item) {
    versionDateOptions.value = []
    return
  }
  loadingVersionDates.value = true
  try {
    versionDateOptions.value = await getDistinctVersionDates(
      form.vendor, form.item, form.sub_item
    )
  } catch (err) {
    showApiError(err)
  } finally {
    loadingVersionDates.value = false
  }
}

// v0.5.7 helper：拼装当前 pivot_type 应当使用的 version_dates 数组
// demand → form.version_dates 数组副本；
// demand_plus_supply → 把单值包成单元素数组
function versionDatesForLookup() {
  if (form.pivot_type === 'demand_plus_supply' && form.version_date_single) {
    return [form.version_date_single]
  }
  return form.version_dates.slice()
}

// ==================== 业务行筛选 lookup ====================

async function loadCountries() {
  if (!hasBusinessContext.value) {
    countryOptions.value = []
    return
  }
  loadingCountries.value = true
  try {
    countryOptions.value = await lookupCountries({
      vendor: form.vendor,
      item: form.item,
      sub_item: form.sub_item,
      version_dates: versionDatesForLookup(),
    })
  } catch (err) {
    showApiError(err)
  } finally {
    loadingCountries.value = false
  }
}

async function loadCategories() {
  if (!hasBusinessContext.value) {
    categoryOptions.value = []
    return
  }
  loadingCategories.value = true
  try {
    categoryOptions.value = await lookupCategories({
      vendor: form.vendor,
      item: form.item,
      sub_item: form.sub_item,
      version_dates: versionDatesForLookup(),
      countries: form.countries,
    })
  } catch (err) {
    showApiError(err)
  } finally {
    loadingCategories.value = false
  }
}

async function loadConfigNames() {
  if (!hasBusinessContext.value) {
    configNameOptions.value = []
    return
  }
  loadingConfigNames.value = true
  try {
    configNameOptions.value = await lookupConfigNames({
      vendor: form.vendor,
      item: form.item,
      sub_item: form.sub_item,
      version_dates: versionDatesForLookup(),
      countries: form.countries,
      categories: form.categories,
    })
  } catch (err) {
    showApiError(err)
  } finally {
    loadingConfigNames.value = false
  }
}

// ==================== 周编号 lookup ====================

/**
 * 根据 years + months 计算可选的 ISO 周编号。
 * - 必须先选 years
 * - 如果选了 months，按 (year, month) 组合查询
 * - 如果没选 months，按所有 year 的全部周查询
 */
async function loadWeeks() {
  if (form.years === '') {
    weekOptions.value = []
    return
  }
  loadingWeeks.value = true
  try {
    const seen = new Map()  // week_id → week_start_date（去重）
    const queries = []
    const y = Number(form.years)
    if (form.months.length > 0) {
      for (const m of form.months) {
        queries.push(lookupWeeksOfMonth(y, m))
      }
    } else {
      // 没选 months：遍历 1-12
      for (let m = 1; m <= 12; m++) {
        queries.push(lookupWeeksOfMonth(y, m))
      }
    }
    const results = await Promise.all(queries)
    for (const arr of results) {
      for (const item of arr) {
        if (!seen.has(item.week_id)) {
          seen.set(item.week_id, item.week_start_date)
        }
      }
    }
    // 按 week_id 升序
    weekOptions.value = Array.from(seen.entries())
      .map(([week_id, week_start_date]) => ({ week_id, week_start_date }))
      .sort((a, b) => a.week_id - b.week_id)
  } catch (err) {
    showApiError(err)
  } finally {
    loadingWeeks.value = false
  }
}

// ==================== 4 字段级联选择事件 ====================

function onVendorChange() {
  form.item = ''
  form.sub_item = ''
  form.version_dates = []
  itemOptions.value = []
  subItemOptions.value = []
  versionDateOptions.value = []
  // 业务行筛选清空
  form.countries = []
  form.categories = []
  form.config_names = []
  countryOptions.value = []
  categoryOptions.value = []
  configNameOptions.value = []
  result.value = null
  loadItems()
}

function onItemChange() {
  form.sub_item = ''
  form.version_dates = []
  subItemOptions.value = []
  versionDateOptions.value = []
  form.countries = []
  form.categories = []
  form.config_names = []
  countryOptions.value = []
  categoryOptions.value = []
  configNameOptions.value = []
  result.value = null
  loadSubItems()
}

function onSubItemChange() {
  form.version_dates = []
  versionDateOptions.value = []
  form.countries = []
  form.categories = []
  form.config_names = []
  countryOptions.value = []
  categoryOptions.value = []
  configNameOptions.value = []
  result.value = null
  loadVersionDates()
}

function onVersionDatesChange() {
  // 版本日期变化 → 重新拉业务行 lookup
  form.countries = []
  form.categories = []
  form.config_names = []
  countryOptions.value = []
  categoryOptions.value = []
  configNameOptions.value = []
  result.value = null
  loadCountries()
}

// ==================== 业务行级联事件 ====================

function onCountriesChange() {
  // 选 country → 清空下级 + 重新拉
  form.categories = []
  form.config_names = []
  categoryOptions.value = []
  configNameOptions.value = []
  result.value = null
  loadCategories()
}

function onCategoriesChange() {
  // 选 category → 清空下级 + 重新拉
  form.config_names = []
  configNameOptions.value = []
  result.value = null
  loadConfigNames()
}

function onConfigNamesChange() {
  result.value = null
}

// ==================== 时间维度事件 ====================

function onYearsChange() {
  form.weeks = []
  weekOptions.value = []
  result.value = null
  loadWeeks()
}

function onMonthsChange() {
  form.weeks = []
  weekOptions.value = []
  result.value = null
  loadWeeks()
}

function onWeeksChange() {
  result.value = null
}

function onDateGranularityChange() {
  result.value = null
}

// ==================== 查询 ====================

function buildRequest() {
  // v0.5.7：version_dates 按 pivot_type 从不同字段构造
  const versionDates =
    form.pivot_type === 'demand_plus_supply'
      ? (form.version_date_single ? [form.version_date_single] : [])
      : form.version_dates.slice()
  const req = {
    pivot_type: form.pivot_type,
    vendor: form.vendor,
    item: form.item,
    sub_item: form.sub_item,
    version_dates: versionDates,
    expand_to_daily: form.date_granularity === 'day'
  }
  if (form.countries.length > 0) req.countries = form.countries.slice()
  if (form.categories.length > 0) req.categories = form.categories.slice()
  if (form.config_names.length > 0) req.config_names = form.config_names.slice()
  // form.years 是单个字符串，后端 years: list[int] 要求整数数组
  if (form.years !== '') req.years = [Number(form.years)]
  if (form.months.length > 0) req.months = form.months.slice()
  if (form.weeks.length > 0) req.weeks = form.weeks.slice()
  return req
}

async function onQuery() {
  if (!canQuery.value) {
    ElMessage.warning('请先完成必填项：供应商 / 业务项 / 子业务项 / 版本日期，且至少选择一个时间维度')
    return
  }
  querying.value = true
  result.value = null
  try {
    const req = buildRequest()
    const res = await queryPivot(req)
    result.value = res
    // v0.5.8 新增：快照请求，供「导出 Excel」使用
    lastQueryRequest.value = req
    ElMessage.success(`查询完成：${res.total_rows} 行 · ${res.period_columns.length} 个日期列`)
  } catch (err) {
    if (err instanceof ApiError) showApiError(err)
    else ElMessage.error(err.message || '查询失败')
  } finally {
    querying.value = false
  }
}

// ==================== v0.5.8 Excel 导出 ====================


function timestampForFilename() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}

async function onExport() {
  if (!lastQueryRequest.value) return  // 无成功查询结果 → 不响应
  exporting.value = true
  try {
    const blob = await exportPivot(lastQueryRequest.value)
    const filename = `pivot_${lastQueryRequest.value.pivot_type}_${timestampForFilename()}.xlsx`
    downloadBlob(blob, filename)
    ElMessage.success('已开始下载')
  } catch (err) {
    if (err instanceof ApiError) showApiError(err)
    else ElMessage.error(err.message || '导出失败')
  } finally {
    exporting.value = false
  }
}

function onReset() {
  form.vendor = ''
  form.item = ''
  form.sub_item = ''
  form.version_dates = []
  form.version_date_single = ''
  form.pivot_type = 'demand'
  form.date_granularity = 'week'
  form.countries = []
  form.categories = []
  form.config_names = []
  form.years = String(new Date().getFullYear())
  form.months = []
  form.weeks = []
  itemOptions.value = []
  subItemOptions.value = []
  versionDateOptions.value = []
  countryOptions.value = []
  categoryOptions.value = []
  configNameOptions.value = []
  weekOptions.value = []
  result.value = null
  // v0.5.8 新增：随重置一起清
  lastQueryRequest.value = null
  loadVendors()
}

// ==================== 透视表辅助 ====================

function cellQty(row, periodDate) {
  const v = row.quantities ? row.quantities[periodDate] : undefined
  return typeof v === 'number' ? v : 0
}

// v0.5.7 新增：行级 class — 让用户一眼识别 4 行/组（Demand/Supply / TTL_GAP / Rolling_TTLGAP）
// Demand 与 Supply 共用一类（原始数据组，强调"配对"语义）
function getRowClass({ row }) {
  if (!row || !row.data_type) return ''
  if (row.data_type === 'TTL_GAP') return 'row--ttl-gap'
  if (row.data_type === 'Rolling_TTLGAP') return 'row--rolling'
  return 'row--ds-base'  // 'Demand' / 'Supply'
}

// v0.5.7 新增：cell class — 仅 TTL_GAP / Rolling_TTLGAP 行的负数量触发红色加粗
function getCellClass(row, periodDate) {
  const v = cellQty(row, periodDate)
  if (
    v < 0 &&
    (row.data_type === 'TTL_GAP' || row.data_type === 'Rolling_TTLGAP')
  ) {
    return 'cell-negative'
  }
  return v === 0 ? 'zero-cell' : 'nonzero-cell'
}

// ==================== pivot_type 切换（v0.5.7 新增） ====================

// 当 pivot_type 切换时清理状态；切到 demand_plus_supply 时若已选 ≥ 2 个版本日期，toast 提示
// v0.5.7 pivot_type 切换：互斥同步 version_dates / version_date_single 两个字段
// 同步后 ElMessage 提示；不再使用 versionDatesExceedsOne（v-model 与 :multiple 类型严格匹配，UI 无法选 2 个）
function onPivotTypeChange(newType, oldType) {
  // 任何 pivot_type 切换都清空结果（避免展示过期透视表）
  result.value = null
  // v0.5.8 新增：模式切换隔离 — 同时清空 lastQueryRequest，避免导出旧模式数据
  lastQueryRequest.value = null
  if (newType === 'demand_plus_supply' && oldType === 'demand') {
    // demand → dps：取数组的第一个作为单值；多余项丢弃（保留至多 1 个）
    form.version_date_single = form.version_dates[0] || ''
    form.version_dates = []
  } else if (newType === 'demand' && oldType === 'demand_plus_supply') {
    // dps → demand：单值塞进数组；保证多选模式至少 1 个
    form.version_dates = form.version_date_single ? [form.version_date_single] : []
    form.version_date_single = ''
  }
  // 已查询过 result 后切换，给出切换提示
  if (oldType) {
    ElMessage.success(
      newType === 'demand_plus_supply' ? '已切换到 Demand+Supply 模式' : '已切换到 Demand 模式'
    )
  }
}

watch(() => form.pivot_type, onPivotTypeChange)

// ==================== 初始化 ====================

onMounted(() => {
  loadVendors()
})
</script>

<template>
  <div class="pivot-view">
    <h2 class="page-title">透视查询</h2>
    <p class="page-hint">
      横向业务行 × 纵向日期 × 交叉点 quantity；
      缺失格默认显示 0。最多返回 50000 个笛卡尔积单元格，超出会拒绝执行。
    </p>

    <el-card shadow="never" class="form-card">
      <el-form label-position="top">
        <!-- 第 1 行：必填定位 -->
        <div class="form-row">
          <el-form-item label="供应商（vendor）" class="form-cell">
            <el-select
              v-model="form.vendor"
              placeholder="请选择供应商"
              filterable
              :loading="loadingVendors"
              @change="onVendorChange"
              style="width: 100%"
            >
              <el-option v-for="v in vendorOptions" :key="v" :label="v" :value="v" />
            </el-select>
          </el-form-item>

          <el-form-item label="业务项（item）" class="form-cell">
            <el-select
              v-model="form.item"
              placeholder="请先选择供应商"
              filterable
              :loading="loadingItems"
              :disabled="!form.vendor"
              @change="onItemChange"
              style="width: 100%"
            >
              <el-option v-for="v in itemOptions" :key="v" :label="v" :value="v" />
            </el-select>
          </el-form-item>

          <el-form-item label="子业务项（sub_item）" class="form-cell">
            <el-select
              v-model="form.sub_item"
              placeholder="请先选择业务项"
              filterable
              :loading="loadingSubItems"
              :disabled="!form.item"
              @change="onSubItemChange"
              style="width: 100%"
            >
              <el-option v-for="v in subItemOptions" :key="v" :label="v" :value="v" />
            </el-select>
          </el-form-item>
        </div>

        <!-- 第 2 行：版本日期 + pivot_type + 日期粒度 -->
        <div class="form-row">
          <el-form-item
            :label="form.pivot_type === 'demand'
              ? '版本日期（version_date，可多选）'
              : '版本日期（version_date，单选）'"
            class="form-cell-wide"
          >
            <el-select
              v-model="versionDateVModel"
              :multiple="form.pivot_type === 'demand'"
              :collapse-tags="form.pivot_type === 'demand'"
              :collapse-tags-tooltip="form.pivot_type === 'demand'"
              placeholder="请先选择子业务项"
              :loading="loadingVersionDates"
              :disabled="!form.sub_item"
              @change="onVersionDatesChange"
              style="width: 100%"
            >
              <el-option
                v-for="v in versionDateOptions"
                :key="v"
                :label="v"
                :value="v"
              />
            </el-select>
          </el-form-item>

          <el-form-item label="透视类型" class="form-cell-narrow">
            <el-radio-group v-model="form.pivot_type">
              <el-radio-button value="demand">Demand</el-radio-button>
              <!-- v0.5.7 起启用 demand_plus_supply（去掉 :disabled）-->
              <el-radio-button value="demand_plus_supply">
                Demand+Supply
              </el-radio-button>
            </el-radio-group>
          </el-form-item>

          <el-form-item label="日期粒度" class="form-cell-narrow">
            <el-radio-group v-model="form.date_granularity" @change="onDateGranularityChange">
              <el-radio-button value="week">按周</el-radio-button>
              <el-radio-button value="day">按日</el-radio-button>
            </el-radio-group>
          </el-form-item>
        </div>

        <!-- 第 3 行：业务行筛选（三级级联） -->
        <el-collapse>
          <el-collapse-item title="业务行筛选（三级级联，可选）" name="business">
            <div class="form-row">
              <el-form-item label="国家（country）" class="form-cell">
                <el-select
                  v-model="form.countries"
                  multiple
                  filterable
                  collapse-tags
                  collapse-tags-tooltip
                  placeholder="不选则不限"
                  :loading="loadingCountries"
                  :disabled="!hasBusinessContext"
                  @change="onCountriesChange"
                  style="width: 100%"
                >
                  <el-option v-for="v in countryOptions" :key="v" :label="v" :value="v" />
                </el-select>
              </el-form-item>

              <el-form-item label="类别（category）" class="form-cell">
                <el-select
                  v-model="form.categories"
                  multiple
                  filterable
                  collapse-tags
                  collapse-tags-tooltip
                  placeholder="先选 country（或不选）"
                  :loading="loadingCategories"
                  :disabled="!hasBusinessContext"
                  @change="onCategoriesChange"
                  style="width: 100%"
                >
                  <el-option v-for="v in categoryOptions" :key="v" :label="v" :value="v" />
                </el-select>
              </el-form-item>

              <el-form-item label="配置名称（config_name）" class="form-cell">
                <el-select
                  v-model="form.config_names"
                  multiple
                  filterable
                  collapse-tags
                  collapse-tags-tooltip
                  placeholder="先选 categories（可不选 country）"
                  :loading="loadingConfigNames"
                  :disabled="!hasBusinessContext"
                  @change="onConfigNamesChange"
                  style="width: 100%"
                >
                  <el-option v-for="v in configNameOptions" :key="v" :label="v" :value="v" />
                </el-select>
              </el-form-item>
            </div>
          </el-collapse-item>
        </el-collapse>

        <!-- 第 4 行：时间维度（级联 + 至少一个） -->
        <div class="form-row">
          <el-form-item label="年份（years，日期控件）" class="form-cell">
            <el-date-picker
              v-model="form.years"
              type="year"
              placeholder="选择年份"
              value-format="YYYY"
              format="YYYY"
              style="width: 100%"
              @change="onYearsChange"
            />
          </el-form-item>

          <el-form-item label="月份（months，1-12 下拉）" class="form-cell">
            <el-select
              v-model="form.months"
              multiple
              filterable
              collapse-tags
              collapse-tags-tooltip
              placeholder="选 months 需同时选 years"
              style="width: 100%"
              @change="onMonthsChange"
            >
              <el-option
                v-for="m in monthOptions"
                :key="m.value"
                :label="m.label"
                :value="m.value"
              />
            </el-select>
          </el-form-item>

          <el-form-item label="周编号（weeks，联动 years+months）" class="form-cell">
            <el-select
              v-model="form.weeks"
              multiple
              filterable
              collapse-tags
              collapse-tags-tooltip
              placeholder="先选 years+months"
              :loading="loadingWeeks"
              :disabled="form.years.length === 0"
              style="width: 100%"
              @change="onWeeksChange"
            >
              <el-option
                v-for="w in weekOptions"
                :key="w.week_id"
                :label="`WK${String(w.week_id).padStart(2, '0')}（${w.week_start_date}）`"
                :value="w.week_id"
              />
            </el-select>
          </el-form-item>
        </div>

        <div v-if="cascadeHint" class="cascade-hint">
          <el-alert :title="cascadeHint" type="warning" :closable="false" show-icon />
        </div>

        <div class="form-actions">
          <el-button @click="onReset">重置</el-button>
          <el-button
            type="primary"
            :loading="querying"
            :disabled="!canQuery"
            @click="onQuery"
          >查询</el-button>
        </div>
      </el-form>
    </el-card>

    <!-- 结果卡：透视表 -->
    <el-card v-if="result" shadow="never" class="result-card">
      <template #header>
        <div class="result-header">
          <span class="result-title">
            ✓ 查询结果
          </span>
          <span class="result-meta">
            <el-tag size="small" type="info">{{ result.total_rows }} 行</el-tag>
            <el-tag size="small" type="info">{{ result.period_columns.length }} 个日期列</el-tag>
            <el-tag size="small" type="success">{{ result.version_dates.length }} 个版本</el-tag>
            <el-tag size="small" type="warning">
              {{ result.date_granularity === 'week' ? '按周' : '按日' }}
            </el-tag>
            <!-- v0.5.8 新增：导出 Excel 按钮 -->
            <el-button
              size="small"
              type="success"
              :icon="Download"
              :loading="exporting"
              :disabled="exporting"
              @click="onExport"
            >导出 Excel</el-button>
          </span>
        </div>
      </template>

      <div v-if="result.total_rows === 0" class="empty-hint">
        该筛选条件下无匹配数据。请缩小筛选范围或选择其他时间维度。
      </div>

      <div v-else class="pivot-table-wrapper">
        <el-table
          :data="result.row_groups"
          :row-class-name="getRowClass"
          stripe
          size="small"
          border
          height="600"
        >
          <!-- 固定列：业务维度 -->
          <el-table-column
            v-for="col in fixedColumns"
            :key="col.prop"
            :prop="col.prop"
            :label="col.label"
            :width="col.width"
            :fixed="col.prop === 'version_date'"
          />

          <!-- 动态列：period_date -->
          <el-table-column
            v-for="pd in result.period_columns"
            :key="pd"
            :prop="pd"
            :label="pd"
            width="100"
            align="right"
          >
            <template #default="slotProps">
              <span :class="slotProps ? getCellClass(slotProps.row, pd) : 'zero-cell'">
                {{ slotProps ? cellQty(slotProps.row, pd) : 0 }}
              </span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.pivot-view {
  max-width: 1280px;
  margin: 0 auto;
}
.page-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 4px;
}
.page-hint {
  font-size: 13px;
  color: #909399;
  margin: 0 0 16px;
  line-height: 1.5;
}
.form-card,
.result-card {
  margin-top: 16px;
  border-radius: 4px;
}
.form-row {
  display: flex;
  gap: 12px;
  margin-bottom: 4px;
  align-items: flex-start;
}
.form-cell {
  flex: 1 1 0;
  min-width: 180px;
}
.form-cell-wide {
  flex: 2 1 0;
  min-width: 360px;
}
.form-cell-narrow {
  flex: 0 0 auto;
  min-width: 240px;
}
.cascade-hint {
  margin: 8px 0;
}
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}
.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.result-title {
  font-size: 14px;
  color: #303133;
  font-weight: 600;
}
.result-meta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.empty-hint {
  font-size: 13px;
  color: #909399;
  text-align: center;
  padding: 24px;
}
.pivot-table-wrapper {
  width: 100%;
  overflow-x: auto;
}
.zero-cell {
  color: #c0c4cc;
}
.nonzero-cell {
  font-weight: 600;
  color: #303133;
}

/* v0.5.7.2 修订：行级底色分组（Demand+Supply / TTL_GAP / Rolling_TTLGAP）*/
/* 【v0.5.7.2 关键约束】
 * Vue <style scoped> 会给每个选择器末尾追加 [data-v-XXX] 属性。
 * el-table / tr / td 都是 Element Plus 子组件渲染出来的 DOM，不带本组件的 data-v-XXX，
 * 若不写 :deep()，编译后整条规则被 el-table 子组件 DOM 过滤掉，三色底色全部失效。
 * 对照 Dashboard.vue:319（同项目同类用法）。
 */
/* 用 > td !important 压制 Element Plus 默认行 hover 高亮 */
.pivot-view :deep(.el-table__body tr.row--ds-base > td) {
  background-color: #ecf5ff !important;
}
.pivot-view :deep(.el-table__body tr.row--ttl-gap > td) {
  background-color: #fdf6ec !important;
}
.pivot-view :deep(.el-table__body tr.row--rolling > td) {
  background-color: #fef0f0 !important;
}
/* 行底色不覆盖 cell 文本颜色（cell 文本仍按 zero-cell / nonzero-cell / cell-negative 决定）*/
.pivot-view :deep(.el-table__body tr.row--ttl-gap > td.zero-cell),
.pivot-view :deep(.el-table__body tr.row--rolling > td.zero-cell),
.pivot-view :deep(.el-table__body tr.row--ttl-gap > td.cell-negative),
.pivot-view :deep(.el-table__body tr.row--rolling > td.cell-negative) {
  color: inherit;
}
/* v0.5.7：负数强烈突出，仅 TTL_GAP / Rolling 命中 */
.cell-negative {
  font-weight: 700;
  color: #f56c6c;
}
</style>
