<script setup>
/**
 * DSP 上传主页（路由 /dsp-uploads）。
 *
 * 数据流（v0.5.1）：
 *   1. 用户选 .xlsx 文件 → onFileChange → store.selectFile(file)
 *      自动调 parseFilename 解析 → 自动填充 form.vendor / item / sub_item 并 snapshot 到 initialParsed
 *   2. 用户可修改 3 段输入（store.updateMeta）；选 version_date
 *   3. 点「载入」→ store.submitUpload() → POST /api/dsp-uploads (multipart, 4 form fields)
 *   4. 成功后页面下方出现结果卡：el-table 预览前 50 条 + 分页器（仅 total>50 时显示）
 *
 * 错误码 → UI 文案遵循 frontend/spec/README.md §3.5.4 + 后端 spec §错误约定：
 *   400 → ElMessage.error(detail)
 *   409 → ElMessageBox.alert（沿用 showApiError）
 *   413/415/422/5xx → ElMessage.error
 *
 * 「重置」二次确认：当 store.hasResult === true，弹 ElMessageBox.confirm。
 *
 * 全局规则遵循 frontend/spec/README.md。
 */
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ApiError, showApiError } from '../api/client.js'
import { useDspUploadStore } from '../stores/useDspUploadStore.js'

const store = useDspUploadStore()

const XLSX_EXT = '.xlsx'

const formRef = ref(null)

const META_RULES = {
  vendor: [
    { required: true, message: '供应商不能为空', trigger: 'blur' },
    { min: 1, max: 64, message: '1-64 字符', trigger: 'blur' }
  ],
  item: [
    { required: true, message: '业务项不能为空', trigger: 'blur' },
    { min: 1, max: 128, message: '1-128 字符', trigger: 'blur' }
  ],
  sub_item: [
    { required: true, message: '子业务项不能为空', trigger: 'blur' },
    { min: 1, max: 128, message: '1-128 字符', trigger: 'blur' }
  ],
  version_date: [
    { required: true, message: '版本日期不能为空', trigger: 'change' }
  ]
}

// el-date-picker 已强制 value-format="YYYY-MM-DD"，不用再写 pattern 校验
// 仅需校验后端对接：YYYY-MM-DD / 必须 ≤ 今天 + 不晚于今天一年（防止手滑）
function validateVersionDate(rule, value, callback) {
  if (!value) return callback(new Error('版本日期不能为空'))
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return callback(new Error('版本日期必须为 YYYY-MM-DD'))
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return callback(new Error('版本日期非法'))
  const today = new Date()
  today.setHours(23, 59, 59, 999)
  if (d.getTime() > today.getTime()) {
    return callback(new Error('版本日期不能晚于今天'))
  }
  callback()
}
META_RULES.version_date = [{ validator: validateVersionDate, trigger: 'change' }]

// 表格列定义在 template 内联声明（<el-table-column>），便于 el-table-column 内部 slot 控制。

// 文件 input ref，用于点击「选择 Excel 文件」时触发原生文件选择器
const fileInputRef = ref(null)

function triggerPick() {
  fileInputRef.value?.click()
}

function onFileChange(ev) {
  const f = ev.target.files && ev.target.files[0]
  // 重置 value，否则同文件名二次选择不会触发 change
  ev.target.value = ''
  if (!f) return
  if (!f.name.toLowerCase().endsWith(XLSX_EXT)) {
    ElMessage.error('仅支持 .xlsx 文件')
    return
  }
  const r = store.selectFile(f)
  if (!r.ok) {
    ElMessage.error(r.error || '文件名解析失败，请确保文件名 ≥ 3 段（按 - 分隔）')
  }
}

function onFileRemove() {
  store.selectedFile = null
  store.initialParsed = null
  // 不动 form.vendor/item/sub_item，让用户保留已编辑值（万一误点）
}

// 提交
async function onSubmit() {
  if (!formRef.value) return
  // el-form validate
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  if (!store.selectedFile) {
    ElMessage.error('请先选择 Excel 文件')
    return
  }
  const r = await store.submitUpload()
  if (r.ok) {
    ElMessage.success(`载入成功，共 ${r.response.row_count} 条数据`)
  } else if (r.error instanceof ApiError) {
    showApiError(r.error)
  }
}

// 重置
async function onReset() {
  if (store.hasResult) {
    try {
      await ElMessageBox.confirm(
        `重置会清空已载入的 ${store.uploadResult.row_count} 条数据，确定吗？`,
        '重置',
        { type: 'warning', confirmButtonText: '确定重置', cancelButtonText: '取消' }
      )
    } catch {
      return  // 用户取消
    }
  }
  store.reset()
}

// 结果区分页
const PREVIEW_PAGE_SIZES = [20, 50, 100]
async function onPageChange(page) {
  await store.loadResultRows(page, store.rowsSize)
}
async function onSizeChange(size) {
  await store.loadResultRows(1, size)
}

// 「载入后」disabled 上半段表单（用户想再传需要先「重置」）
const formDisabled = computed(() => store.uploading || store.hasResult)
</script>

<template>
  <div class="dsp-upload-view">
    <h2 class="page-title">DSP 上传</h2>
    <p class="page-hint">
      选择 DSP 周预测 Excel 文件，自动解析文件名得到「供应商 / 业务项 / 子业务项」，可手动修改后选择版本日期载入。
      仅入库 Data Type 为 <code>Demand</code> / <code>Supply</code> 的事实行（按 spec §跳过规则 R2）。
    </p>

    <el-card shadow="never" class="upload-card">
      <el-form
        ref="formRef"
        :model="store.form"
        :rules="META_RULES"
        label-position="top"
      >
        <el-form-item label="Excel 文件" prop="file_display">
          <div class="file-row">
            <el-button type="primary" plain @click="triggerPick">
              选择 Excel 文件
            </el-button>
            <span v-if="store.selectedFile" class="file-name">
              {{ store.selectedFile.name }}
              <el-button
                v-if="!store.hasResult"
                link
                type="danger"
                size="small"
                @click="onFileRemove"
              >移除</el-button>
            </span>
            <span v-else class="file-placeholder">尚未选择文件</span>
          </div>
          <input
            ref="fileInputRef"
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            style="display: none"
            @change="onFileChange"
          />
        </el-form-item>

        <el-form-item label="供应商（vendor）" prop="vendor">
          <el-input
            v-model="store.form.vendor"
            :disabled="!store.hasFile || formDisabled"
            placeholder="自动从文件名解析，可修改"
            maxlength="64"
            show-word-limit
            @blur="store.updateMeta('vendor', store.form.vendor)"
          />
        </el-form-item>

        <el-form-item label="业务项（item）" prop="item">
          <el-input
            v-model="store.form.item"
            :disabled="!store.hasFile || formDisabled"
            placeholder="自动从文件名解析，可修改"
            maxlength="128"
            show-word-limit
            @blur="store.updateMeta('item', store.form.item)"
          />
        </el-form-item>

        <el-form-item label="子业务项（sub_item）" prop="sub_item">
          <el-input
            v-model="store.form.sub_item"
            :disabled="!store.hasFile || formDisabled"
            placeholder="自动从文件名解析，可修改"
            maxlength="128"
            show-word-limit
            @blur="store.updateMeta('sub_item', store.form.sub_item)"
          />
        </el-form-item>

        <el-form-item label="版本日期（version_date）" prop="version_date">
          <el-date-picker
            v-model="store.form.version_date"
            :disabled="!store.hasFile || formDisabled"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择版本日期（不晚于今天）"
            style="width: 240px"
          />
        </el-form-item>

        <div class="form-actions">
          <el-button @click="onReset">重置</el-button>
          <el-button
            type="primary"
            :loading="store.uploading"
            :disabled="!store.canSubmit"
            @click="onSubmit"
          >
            载入
          </el-button>
        </div>
      </el-form>
    </el-card>

    <el-card
      v-if="store.hasResult"
      shadow="never"
      class="result-card"
    >
      <template #header>
        <div class="result-header">
          <span class="result-title">
            ✓ 已载入 <strong>{{ store.uploadResult.row_count }}</strong> 条数据
            <small v-if="store.uploadResult.source_filename" class="result-meta">
              {{ store.uploadResult.source_filename }}
            </small>
          </span>
          <span class="result-meta">
            <el-tag size="small" type="info">{{ store.uploadResult.vendor }}</el-tag>
            <el-tag size="small" type="info">{{ store.uploadResult.item }}</el-tag>
            <el-tag size="small" type="info">{{ store.uploadResult.sub_item }}</el-tag>
            <el-tag size="small" type="success">{{ store.uploadResult.version_date }}</el-tag>
          </span>
        </div>
      </template>

      <el-table
        v-loading="store.rowsLoading"
        :data="store.rows"
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
        v-if="store.rowsTotal > store.rowsSize"
        :current-page="store.rowsPage"
        :page-size="store.rowsSize"
        :page-sizes="PREVIEW_PAGE_SIZES"
        :total="store.rowsTotal"
        layout="total, sizes, prev, pager, next"
        class="result-pagination"
        @current-change="onPageChange"
        @size-change="onSizeChange"
      />
    </el-card>
  </div>
</template>

<style scoped>
.dsp-upload-view {
  max-width: 720px;
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
.page-hint code {
  font-family: SFMono-Regular, Consolas, monospace;
  background: #f5f7fa;
  padding: 1px 6px;
  border-radius: 3px;
}
.upload-card,
.result-card {
  margin-top: 16px;
  border-radius: 4px;
}
.file-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.file-name {
  font-size: 13px;
  color: #606266;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.file-placeholder {
  font-size: 13px;
  color: #c0c4cc;
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
  margin: 0 2px;
}
.result-meta {
  font-size: 12px;
  color: #909399;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.result-pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
