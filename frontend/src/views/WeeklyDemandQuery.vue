<script setup>
/**
 * 周需求管理 / 查询子模块（路由 /dsp-uploads/query，v0.5.4）。
 *
 * 数据流（级联下拉）：
 *   1. 页面加载 → 拉 vendors 列表（GET /dsp-uploads/vendors）；
 *   2. 选择 vendor → 拉 items（GET /dsp-uploads/items?vendor=…）→ 清空 item/sub_item/version_date；
 *   3. 选择 item → 拉 sub_items（GET /dsp-uploads/sub-items?vendor=…&item=…）→ 清空 sub_item/version_date；
 *   4. 选择 sub_item → 拉 version_dates（GET /dsp-uploads/version-dates?…）→ 清空 version_date；
 *   5. 选择 version_date → 所有 4 字段就绪 → 「查询」按钮 enabled；
 *   6. 点「查询」→ findBatchByVersion(meta) → 命中：展示元数据 + el-table 前 50 条事实行；
 *      未命中：toast；form 保留。
 *
 * 错误处理沿用 client.showApiError(err)（@/api/client.js）。
 */
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { ApiError, showApiError } from '../api/client.js'
import {
  getDistinctVendors,
  getDistinctItems,
  getDistinctSubItems,
  getDistinctVersionDates,
  findBatchByVersion,
  listDspUploadRows
} from '../api/dsp_uploads.js'

// 下拉选项
const vendorOptions = ref([])
const itemOptions = ref([])
const subItemOptions = ref([])
const versionDateOptions = ref([])

// 加载状态
const loadingVendors = ref(false)
const loadingItems = ref(false)
const loadingSubItems = ref(false)
const loadingVersionDates = ref(false)

// 查询状态
const querying = ref(false)
const result = ref(null)
const rows = ref([])
const rowsTotal = ref(0)
const rowsLoading = ref(false)

const PREVIEW_PAGE_SIZES = [20, 50, 100]

const form = reactive({
  vendor: '',
  item: '',
  sub_item: '',
  version_date: ''
})

const canQuery = computed(() =>
  form.vendor !== '' &&
  form.item !== '' &&
  form.sub_item !== '' &&
  form.version_date !== ''
)

// ==================== 级联加载 ====================

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
    versionDateOptions.value = await getDistinctVersionDates(form.vendor, form.item, form.sub_item)
  } catch (err) {
    showApiError(err)
  } finally {
    loadingVersionDates.value = false
  }
}

// ==================== 级联选择事件 ====================

function onVendorChange() {
  form.item = ''
  form.sub_item = ''
  form.version_date = ''
  itemOptions.value = []
  subItemOptions.value = []
  versionDateOptions.value = []
  loadItems()
  // 清空查询结果
  result.value = null
  rows.value = []
  rowsTotal.value = 0
}

function onItemChange() {
  form.sub_item = ''
  form.version_date = ''
  subItemOptions.value = []
  versionDateOptions.value = []
  loadSubItems()
  result.value = null
  rows.value = []
  rowsTotal.value = 0
}

function onSubItemChange() {
  form.version_date = ''
  versionDateOptions.value = []
  loadVersionDates()
  result.value = null
  rows.value = []
  rowsTotal.value = 0
}

function onVersionDateChange() {
  // 清空查询结果（如果之前有查询过）
  result.value = null
  rows.value = []
  rowsTotal.value = 0
}

// ==================== 查询 ====================

async function onQuery() {
  querying.value = true
  rowsLoading.value = true
  result.value = null
  rows.value = []
  rowsTotal.value = 0
  try {
    const batch = await findBatchByVersion({
      vendor: form.vendor,
      item: form.item,
      sub_item: form.sub_item,
      version_date: form.version_date
    })
    if (!batch) {
      ElMessage.info('未找到该版本')
      return
    }
    result.value = batch
    const rp = await listDspUploadRows(batch.id, { page: 1, size: 50 })
    rows.value = rp.items || []
    rowsTotal.value = rp.total || 0
    ElMessage.success(`✓ 已找到 1 个批次，共 ${batch.row_count} 条事实行`)
  } catch (err) {
    if (err instanceof ApiError) showApiError(err)
    else ElMessage.error(err.message || '查询失败')
  } finally {
    querying.value = false
    rowsLoading.value = false
  }
}

async function onPageChange(page) {
  if (!result.value) return
  rowsLoading.value = true
  try {
    const rp = await listDspUploadRows(result.value.id, { page, size: 50 })
    rows.value = rp.items || []
  } finally {
    rowsLoading.value = false
  }
}

function onReset() {
  form.vendor = ''
  form.item = ''
  form.sub_item = ''
  form.version_date = ''
  vendorOptions.value = []
  itemOptions.value = []
  subItemOptions.value = []
  versionDateOptions.value = []
  result.value = null
  rows.value = []
  rowsTotal.value = 0
  // 重新加载 vendors
  loadVendors()
}

// ==================== 初始化 ====================

onMounted(() => {
  loadVendors()
})
</script>

<template>
  <div class="query-view">
    <h2 class="page-title">查询</h2>
    <p class="page-hint">
      按 (供应商 / 业务项 / 子业务项 / 版本日期) 4 字段级联选择精确查找已入库批次；
      命中展示元数据与前 50 条事实行预览。
    </p>

    <el-card shadow="never" class="form-card">
      <el-form label-position="top">
        <div class="cascade-grid">
          <!-- 供应商 -->
          <el-form-item label="供应商（vendor）">
            <el-select
              v-model="form.vendor"
              placeholder="请选择供应商"
              filterable
              :loading="loadingVendors"
              @change="onVendorChange"
              style="width: 100%"
            >
              <el-option
                v-for="v in vendorOptions"
                :key="v"
                :label="v"
                :value="v"
              />
            </el-select>
          </el-form-item>

          <!-- 业务项 -->
          <el-form-item label="业务项（item）">
            <el-select
              v-model="form.item"
              placeholder="请先选择供应商"
              filterable
              :loading="loadingItems"
              :disabled="!form.vendor"
              @change="onItemChange"
              style="width: 100%"
            >
              <el-option
                v-for="v in itemOptions"
                :key="v"
                :label="v"
                :value="v"
              />
            </el-select>
          </el-form-item>

          <!-- 子业务项 -->
          <el-form-item label="子业务项（sub_item）">
            <el-select
              v-model="form.sub_item"
              placeholder="请先选择业务项"
              filterable
              :loading="loadingSubItems"
              :disabled="!form.item"
              @change="onSubItemChange"
              style="width: 100%"
            >
              <el-option
                v-for="v in subItemOptions"
                :key="v"
                :label="v"
                :value="v"
              />
            </el-select>
          </el-form-item>

          <!-- 版本日期 -->
          <el-form-item label="版本日期（version_date）">
            <el-select
              v-model="form.version_date"
              placeholder="请先选择子业务项"
              :loading="loadingVersionDates"
              :disabled="!form.sub_item"
              @change="onVersionDateChange"
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

    <el-card v-if="result" shadow="never" class="result-card">
      <template #header>
        <div class="result-header">
          <span class="result-title">
            ✓ 已找到 1 个批次，共 <strong>{{ result.row_count }}</strong> 条数据
          </span>
          <span class="result-meta">
            <el-tag size="small" type="info">{{ result.vendor }}</el-tag>
            <el-tag size="small" type="info">{{ result.item }}</el-tag>
            <el-tag size="small" type="info">{{ result.sub_item }}</el-tag>
            <el-tag size="small" type="success">{{ result.version_date }}</el-tag>
          </span>
        </div>
        <div v-if="result.source_filename" class="result-source">
          来源文件：<code>{{ result.source_filename }}</code>
          · 创建于 {{ result.created_at }}
        </div>
      </template>

      <el-table
        v-loading="rowsLoading"
        :data="rows"
        stripe
        size="small"
        empty-text="该批次无事实行（所有数据均被规则跳过）"
      >
        <el-table-column prop="country" label="Country" width="110" />
        <el-table-column prop="category" label="Category" width="100" />
        <el-table-column prop="config_code" label="Config Code" width="140" />
        <el-table-column prop="data_type" label="Data Type" width="100" />
        <el-table-column prop="ttl" label="TTL" width="60" />
        <el-table-column prop="ym" label="年月" width="90" />
        <el-table-column prop="week" label="周" width="80" />
        <el-table-column prop="date" label="日期" width="110" />
        <el-table-column prop="quantity" label="数量" width="80" />
      </el-table>

      <el-pagination
        v-if="rowsTotal > 50"
        :current-page="1"
        :page-size="50"
        :page-sizes="PREVIEW_PAGE_SIZES"
        :total="rowsTotal"
        layout="total, sizes, prev, pager, next"
        class="result-pagination"
        @current-change="onPageChange"
      />
    </el-card>
  </div>
</template>

<style scoped>
.query-view {
  max-width: 1080px;
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
.cascade-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
@media (max-width: 900px) {
  .cascade-grid {
    grid-template-columns: repeat(2, 1fr);
  }
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
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.result-title strong {
  color: #67c23a;
  font-weight: 600;
  font-size: 16px;
}
.result-meta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.result-source {
  font-size: 12px;
  color: #909399;
  margin-top: 6px;
}
.result-source code {
  font-family: SFMono-Regular, Consolas, monospace;
  background: #f5f7fa;
  padding: 1px 6px;
  border-radius: 3px;
}
.result-pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
