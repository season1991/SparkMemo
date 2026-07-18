<script setup>
/**
 * 周需求管理 / 删除子模块（路由 /dsp-uploads/delete，v0.5.4）。
 *
 * 数据流（级联下拉）：
 *   1. 页面加载 → 拉 vendors 列表；
 *   2. 选择 vendor → 拉 items → 清空 item/sub_item/version_date；
 *   3. 选择 item → 拉 sub_items → 清空 sub_item/version_date；
 *   4. 选择 sub_item → 拉 version_dates → 清空 version_date；
 *   5. 选择 version_date → 所有 4 字段就绪 → 「查询预览」按钮 enabled；
 *   6. 点「查询预览」→ findBatchByVersion(meta) → 命中：展示元数据 + 警告文案 + 启用「删除」按钮；
 *   7. 点「删除」→ ElMessageBox.confirm → 确认后 DELETE /api/dsp-uploads/{id}；
 *   8. toast「删除成功」；清空预览。
 */
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ApiError, showApiError } from '../api/client.js'
import {
  getDistinctVendors,
  getDistinctItems,
  getDistinctSubItems,
  getDistinctVersionDates,
  findBatchByVersion,
  deleteDspUpload
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

// 预览/删除状态
const previewing = ref(false)
const deleting = ref(false)
const preview = ref(null)

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
const canDelete = computed(() => !!preview.value && !deleting.value)

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
  preview.value = null
  loadItems()
}

function onItemChange() {
  form.sub_item = ''
  form.version_date = ''
  subItemOptions.value = []
  versionDateOptions.value = []
  preview.value = null
  loadSubItems()
}

function onSubItemChange() {
  form.version_date = ''
  versionDateOptions.value = []
  preview.value = null
  loadVersionDates()
}

function onVersionDateChange() {
  preview.value = null
}

// ==================== 预览 ====================

async function onPreview() {
  previewing.value = true
  try {
    const batch = await findBatchByVersion({
      vendor: form.vendor,
      item: form.item,
      sub_item: form.sub_item,
      version_date: form.version_date
    })
    if (!batch) {
      ElMessage.info('该版本不存在')
      preview.value = null
      return
    }
    preview.value = batch
  } catch (err) {
    if (err instanceof ApiError) showApiError(err)
    else ElMessage.error(err.message || '查询预览失败')
  } finally {
    previewing.value = false
  }
}

// ==================== 删除 ====================

async function onDelete() {
  if (!preview.value) return
  try {
    await ElMessageBox.confirm(
      `确定删除 vendor=${preview.value.vendor} / item=${preview.value.item} / ` +
        `sub_item=${preview.value.sub_item} / version_date=${preview.value.version_date} ` +
        `的 ${preview.value.row_count} 条事实行？删除后不可恢复`,
      '删除确认',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消'
      }
    )
  } catch {
    return  // 用户取消
  }
  deleting.value = true
  try {
    await deleteDspUpload(preview.value.id)
    ElMessage.success('删除成功')
    preview.value = null
  } catch (err) {
    if (err instanceof ApiError) showApiError(err)
    else ElMessage.error(err.message || '删除失败')
  } finally {
    deleting.value = false
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
  preview.value = null
  loadVendors()
}

// ==================== 初始化 ====================

onMounted(() => {
  loadVendors()
})
</script>

<template>
  <div class="delete-view">
    <h2 class="page-title">删除</h2>
    <p class="page-hint">
      按 4 字段级联选择定位批次 → 预览元数据 → 二次确认后整批删除（CASCADE 会清空事实行）。
      删除后不可恢复，请谨慎操作。
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
            type="warning"
            :loading="previewing"
            :disabled="!canQuery"
            @click="onPreview"
          >查询预览</el-button>
        </div>
      </el-form>
    </el-card>

    <el-card v-if="preview" shadow="never" class="preview-card">
      <template #header>
        <div class="preview-header">
          <span class="preview-title">
            找到 1 个匹配批次
            <small class="warn">⚠ 即将删除 {{ preview.row_count }} 条事实行（CASCADE）；删除后不可恢复</small>
          </span>
        </div>
      </template>

      <div class="meta-grid">
        <div class="meta-row"><span class="meta-key">vendor:</span><el-tag size="small">{{ preview.vendor }}</el-tag></div>
        <div class="meta-row"><span class="meta-key">item:</span><el-tag size="small">{{ preview.item }}</el-tag></div>
        <div class="meta-row"><span class="meta-key">sub_item:</span><el-tag size="small">{{ preview.sub_item }}</el-tag></div>
        <div class="meta-row"><span class="meta-key">version_date:</span><el-tag size="small" type="success">{{ preview.version_date }}</el-tag></div>
        <div class="meta-row"><span class="meta-key">source_filename:</span><code>{{ preview.source_filename }}</code></div>
        <div class="meta-row"><span class="meta-key">row_count:</span><strong>{{ preview.row_count }}</strong></div>
        <div class="meta-row"><span class="meta-key">created_at:</span>{{ preview.created_at }}</div>
      </div>

      <div class="delete-actions">
        <el-button
          type="danger"
          :loading="deleting"
          :disabled="!canDelete"
          @click="onDelete"
        >删除该批次</el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.delete-view {
  max-width: 960px;
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
.preview-card {
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
.preview-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.preview-title {
  font-size: 14px;
  color: #303133;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.warn {
  font-size: 13px;
  color: #e6a23c;
  margin-left: 8px;
}
.meta-grid {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 8px 16px;
  align-items: center;
  font-size: 13px;
  color: #303133;
}
.meta-key {
  color: #606266;
  font-weight: 500;
  min-width: 140px;
}
.meta-row {
  display: contents;
}
.meta-row code {
  font-family: SFMono-Regular, Consolas, monospace;
  background: #f5f7fa;
  padding: 1px 6px;
  border-radius: 3px;
}
.delete-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}
</style>
