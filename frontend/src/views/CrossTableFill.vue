<script setup>
/**
 * 跨表数据填充页（路由 /cross-table-fill，v0.6.0）。
 *
 * 4 步向导式单页 ETL：上传 → 配置 → 试运行 → 查看结果。
 * 每步由 store.stepIndex 驱动 <el-steps>；各步骤对应不同 <el-card>。
 *
 * 全局规则遵循 frontend/spec/README.md（220 导航 + 56 页面页头 + 主内容区 + max-width 960px）。
 */
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Connection,
  Delete,
  Download,
  Minus,
  Plus,
  Promotion,
  Upload,
  VideoPlay,
} from '@element-plus/icons-vue'
import { useCrossTableFillStore } from '../stores/useCrossTableFillStore.js'
import { showApiError } from '../api/client.js'
import { downloadBlob } from '../utils/downloadBlob.js'
import { unwrapElUploadFile } from '../utils/fileValidator.js'

const MAX_BYTES = 20 * 1024 * 1024

const store = useCrossTableFillStore()
const {
  stepIndex,
  step,
  canUpload,
  canConfigure,
  hasOverwriteMapping,
  targetFile,
  baseFile,
  warnings,
} = storeToRefs(store)

// ---------------- file helpers ----------------

/**
 * 构造 el-upload @change 回调。
 *
 * v0.6.0.1 关键修复：el-upload @change 入参是 Element Plus 的 wrapper
 * `{ name, size, uid, status, percentage, raw: File, ... }`，**不是浏览器原生
 * `File`**。若直接把 wrapper 透传给 store，后续 `form.append('target_file',
 * wrapper)` 会被浏览器 `String()` 序列化为 `"[object Object]"`，最终后端
 * Pydantic 抛「Expected UploadFile, received: <class 'str'>」→ 422。
 *
 * 修复路径：先经 `unwrapElUploadFile(...)` 解出真 File，再做后缀 / 大小校验。
 *
 * 详见 spec §2.2 / §11 v0.6.0.1 与 `utils/fileValidator.js`。
 *
 * @param {(rawFile: File) => void} setter 把真 File 写入 store
 * @returns {(file: any) => boolean} 给 el-upload @change 用；返回 false 阻止默认上传
 */
function buildFileValidator(setter) {
  return (file) => {
    if (!file) return false
    const rawFile = unwrapElUploadFile(file)
    if (!rawFile) {
      ElMessage.error('文件类型有误，请重新选择')
      return false
    }
    if (!rawFile.name.toLowerCase().endsWith('.xlsx')) {
      ElMessage.error('仅支持 .xlsx 文件')
      return false
    }
    if (rawFile.size > MAX_BYTES) {
      ElMessage.warning('文件超过 20 MB 上限')
      return false
    }
    setter(rawFile)
    return false // 阻止 el-upload 默认上传
  }
}

const onTargetFileChange = buildFileValidator((f) => store.setTargetFile(f))
const onBaseFileChange = buildFileValidator((f) => store.setBaseFile(f))

// ---------------- step 1 -> 2 ----------------

async function onUpload() {
  if (!canUpload.value) {
    ElMessage.warning('请先选择目标表和基础表')
    return
  }
  try {
    await store.upload()
    ElMessage.success(
      `解析成功：目标表 ${store.uploadResult.target_row_count} 行 · 基础表 ${store.uploadResult.base_row_count} 行`
    )
  } catch (err) {
    showApiError(err)
  }
}

function onReset() {
  ElMessageBox.confirm(
    '重置会清空当前任务、文件选择与所有配置。是否继续？',
    '重置',
    { type: 'warning', confirmButtonText: '重置', cancelButtonText: '取消' }
  )
    .then(() => store.reset())
    .catch(() => {})
}

// ---------------- step 2 config ----------------

function addKeyPair() {
  store.addKeyPair()
}

function removeKeyPair(idx) {
  store.removeKeyPair(idx)
}

function addMapping() {
  store.addMapping()
}

function removeMapping(idx) {
  store.removeMapping(idx)
}

function onMappingFieldChange(idx, key, value) {
  store.updateMappingAt(idx, { [key]: value })
}

function onModeChange(row, val) {
  const idx = row.__idx
  if (val === 'overwrite') {
    // v0.6.0.1.0：先清空 target_field，再弹确认；用户取消 → 还原 mode + target_field
    // 从 store 读取 prev 值（row 是 wrapper 对象，不一定有 mode/target_field 字段）
    const prevMode = store.mappings[idx]?.mode
    const prevTarget = store.mappings[idx]?.target_field
    store.updateMappingAt(idx, { target_field: '' })
    return ElMessageBox.confirm(
      '覆盖模式将覆盖目标表的同名列，确认切换？',
      '提示',
      { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' }
    )
      .then(() => store.updateMappingAt(idx, { mode: 'overwrite' }))
      .catch(() => {
        // 取消：还原原 mode 与 target_field
        store.updateMappingAt(idx, { mode: prevMode, target_field: prevTarget })
      })
  }
  // 切回 new_column：保留 target_field 当前值（用户可继续编辑）；不需要确认
  store.updateMappingAt(idx, { mode: 'new_column' })
}

const targetHeaders = computed(() => store.uploadResult?.target_headers || [])
const baseHeaders = computed(() => store.uploadResult?.base_headers || [])

function targetHeaderOptions() {
  return targetHeaders.value.map((h) => ({ value: h, label: h }))
}

function baseHeaderOptions() {
  return baseHeaders.value.map((h) => ({ value: h, label: h }))
}

// 字段级校验：keys 之间是否重复 / 长度是否对齐
const keysValidationError = computed(() => {
  if (store.targetKeys.length === 0) return ''
  const tk = store.targetKeys.filter(Boolean)
  const bk = store.baseKeys.filter(Boolean)
  if (store.targetKeys.length !== store.baseKeys.length) {
    return 'target_keys 与 base_keys 长度必须一致'
  }
  for (let i = 0; i < tk.length; i++) {
    if (!tk[i] || !bk[i]) return '每对主键都必须填齐 target 与 base'
  }
  const seenT = new Set()
  for (const k of tk) {
    if (seenT.has(k)) return `target_keys 在同一张表内重复：${k}`
    seenT.add(k)
  }
  const seenB = new Set()
  for (const k of bk) {
    if (seenB.has(k)) return `base_keys 在同一张表内重复：${k}`
    seenB.add(k)
  }
  return ''
})

async function onConfigure() {
  if (!canConfigure.value || keysValidationError.value) {
    ElMessage.warning(keysValidationError.value || '请完整填写主键和映射')
    return
  }
  let confirmToken = null
  if (hasOverwriteMapping.value) {
    try {
      await ElMessageBox.confirm(
        '本次配置含「覆盖原列」模式，将覆盖目标表的同名列。如已确认请继续；如需调整请返回修改。',
        '覆盖确认',
        { type: 'warning', confirmButtonText: '已确认，继续', cancelButtonText: '返回修改' }
      )
    } catch {
      return
    }
    confirmToken =
      typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : `tok-${Date.now()}-${Math.random().toString(36).slice(2)}`
  }
  try {
    await store.patchConfig(confirmToken)
  } catch (err) {
    showApiError(err)
  }
}

function onBackToStep1() {
  store.goToStep('idle')
}

function onBackToStep2() {
  store.goToStep('uploaded')
}

function onBackToStep3() {
  store.goToStep('configured')
}

// ---------------- step 3 -> 4 ----------------

async function onExecute() {
  try {
    await store.execute()
  } catch (err) {
    const status = err && err.status
    showApiError(err)
    if (status === 409) {
      // 过期 / 状态不对：自动重置回 Step 1
      const detail = err.detail || '该任务已失效'
      ElMessage.warning(detail + '，请重新上传')
      store.reset()
    }
  }
}

// ---------------- step 4 download / cleanup ----------------

function timestampForFilename() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}

async function onDownload() {
  try {
    const blob = await store.download()
    const filename = `cross_table_fill_${store.jobId}_filled_${timestampForFilename()}.xlsx`
    downloadBlob(blob, filename)
    ElMessage.success('已开始下载')
  } catch (err) {
    if (err && err.status === 401) {
      ElMessage.error('下载链接已失效，请重新执行')
      store.goToStep('configured')
    } else {
      showApiError(err)
    }
  }
}

async function onCleanUp() {
  try {
    await ElMessageBox.confirm(
      '删除该任务将一并清理 rows 与 configs，无法恢复。确认删除？',
      '清理任务',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    await store.cleanUp()
    ElMessage.success('已清理')
  } catch (err) {
    showApiError(err)
  }
}

const summary = computed(() => store.executeResponse?.summary || null)
const previewHeaders = computed(() => store.executeResponse?.preview_headers || [])
const previewRows = computed(() => store.executeResponse?.preview || [])
const digest = computed(() => store.configDigest)
const keyPairsDisplay = computed(() => {
  if (!digest.value) return []
  return digest.value.target_keys.map((tk, i) => ({
    target: tk,
    base: digest.value.base_keys[i],
  }))
})
</script>

<template>
  <div class="cross-table-fill">
    <h2 class="page-title">跨表数据填充</h2>
    <p class="page-hint">
      上传两张 Excel → 选定主键 → 勾选要填充的字段 → 预览并下载结果
    </p>

    <el-steps
      :active="stepIndex"
      finish-status="success"
      class="step-indicator"
    >
      <el-step title="上传两张表" />
      <el-step title="配置主键与映射" />
      <el-step title="试运行" />
      <el-step title="查看结果" />
    </el-steps>

    <!-- ============== Step 1: 上传 ============== -->
    <el-card v-if="step === 'idle'" shadow="never" class="step-card">
      <el-form label-width="160px">
        <el-form-item label="目标表 xlsx（待填充）">
          <el-upload
            :auto-upload="false"
            :on-change="onTargetFileChange"
            :limit="1"
            accept=".xlsx"
            :show-file-list="false"
          >
            <el-button :icon="Upload">选择文件</el-button>
          </el-upload>
          <span v-if="targetFile" class="file-name">{{ targetFile.name }}</span>
        </el-form-item>
        <el-form-item label="基础表 xlsx（数据源）">
          <el-upload
            :auto-upload="false"
            :on-change="onBaseFileChange"
            :limit="1"
            accept=".xlsx"
            :show-file-list="false"
          >
            <el-button :icon="Upload">选择文件</el-button>
          </el-upload>
          <span v-if="baseFile" class="file-name">{{ baseFile.name }}</span>
        </el-form-item>
        <el-form-item label="过期时间（小时）">
          <el-input-number
            v-model="store.expiresInHours"
            :min="1"
            :max="168"
          />
          <span class="form-hint">默认 24 小时，最长 168 小时（7 天）</span>
        </el-form-item>
        <div class="form-actions">
          <el-button @click="onReset">重置</el-button>
          <el-button
            type="primary"
            :icon="Promotion"
            :loading="store.uploading"
            :disabled="!canUpload"
            @click="onUpload"
          >开始解析</el-button>
        </div>
      </el-form>
    </el-card>

    <!-- ============== Step 2: 配置 ============== -->
    <el-card v-else-if="step === 'uploaded'" shadow="never" class="step-card">
      <h3>目标表 <el-tag size="small">{{ store.uploadResult.target_filename }}</el-tag></h3>
      <el-table
        :data="targetHeaders.map((h) => ({ name: h }))"
        stripe
        size="small"
        class="header-table"
        :show-header="false"
      >
        <el-table-column prop="name" label="字段" min-width="120" />
      </el-table>
      <p class="meta-info">共 {{ store.uploadResult.target_row_count }} 行</p>

      <h3>基础表 <el-tag size="small">{{ store.uploadResult.base_filename }}</el-tag></h3>
      <el-table
        :data="baseHeaders.map((h) => ({ name: h }))"
        stripe
        size="small"
        class="header-table"
        :show-header="false"
      >
        <el-table-column prop="name" label="字段" min-width="120" />
      </el-table>
      <p class="meta-info">共 {{ store.uploadResult.base_row_count }} 行</p>

      <el-divider />

      <h3>主键字段</h3>
      <p class="form-hint">target_keys 与 base_keys 按位置一一对应</p>

      <!-- v0.6.0.0.3 hot fix：空态提示 + 「新增一对」按钮外移，避免空态无入口 -->
      <p v-if="store.targetKeys.length === 0" class="empty-hint">
        暂无主键对；点下方「新增一对」添加。
      </p>

      <div
        v-for="(tk, idx) in store.targetKeys"
        :key="`kp-${idx}`"
        class="key-pair-row"
      >
        <el-select
          :model-value="store.targetKeys[idx]"
          :options="targetHeaderOptions()"
          placeholder="目标表字段"
          filterable
          @update:model-value="(v) => (store.targetKeys[idx] = v)"
        />
        <span class="key-separator">⟷</span>
        <el-select
          :model-value="store.baseKeys[idx]"
          :options="baseHeaderOptions()"
          placeholder="基础表字段"
          filterable
          @update:model-value="(v) => (store.baseKeys[idx] = v)"
        />
        <el-button
          v-if="idx === store.targetKeys.length - 1 && store.targetKeys[idx] && store.baseKeys[idx]"
          size="small"
          :icon="Plus"
          @click="addKeyPair"
        >新增一对</el-button>
        <el-button
          v-if="store.targetKeys.length > 1"
          size="small"
          :icon="Minus"
          @click="removeKeyPair(idx)"
        >移除</el-button>
      </div>
      <p v-if="keysValidationError" class="field-error">{{ keysValidationError }}</p>

      <!-- 「新增一对」按钮移出 v-for：永远可见，是空态下加第一对的入口 -->
      <div class="row-actions">
        <el-button :icon="Plus" @click="addKeyPair">新增一对</el-button>
      </div>

      <el-divider />

      <h3>映射规则（基础表 → 目标表）</h3>

      <!-- v0.6.0.0.3：映射区空态提示，与主键对风格一致 -->
      <p v-if="store.mappings.length === 0" class="empty-hint">
        暂无映射行；点下方「新增映射」添加。
      </p>

      <div
        v-for="(m, idx) in store.mappings"
        :key="`m-${idx}`"
        class="mapping-row"
      >
        <span class="mapping-label">基础表字段</span>
        <el-select
          :model-value="m.base_field"
          :options="baseHeaderOptions()"
          placeholder="选择基础表字段"
          filterable
          class="mapping-select"
          @update:model-value="(v) => onMappingFieldChange(idx, 'base_field', v)"
        />
        <span class="mapping-arrow">→</span>
        <span class="mapping-label">目标列</span>
        <!-- v0.6.0.1.0：mode=new_column 时自由输入新列名；mode=overwrite 时下拉选已有列 -->
        <el-input
          v-if="m.mode === 'new_column'"
          :model-value="m.target_field"
          placeholder="输入新列名"
          class="mapping-select"
          @update:model-value="(v) => onMappingFieldChange(idx, 'target_field', v)"
        />
        <el-select
          v-else
          :model-value="m.target_field"
          :options="targetHeaderOptions()"
          placeholder="选择目标列"
          filterable
          class="mapping-select"
          @update:model-value="(v) => onMappingFieldChange(idx, 'target_field', v)"
        />
        <span class="mapping-label">模式</span>
        <el-radio-group
          :model-value="m.mode"
          class="mapping-mode"
          @update:model-value="(v) => onModeChange({ __idx: idx }, v)"
        >
          <el-radio-button value="new_column">新增列</el-radio-button>
          <el-radio-button value="overwrite">覆盖原列</el-radio-button>
        </el-radio-group>
        <el-button
          size="small"
          type="danger"
          :icon="Delete"
          @click="removeMapping(idx)"
        >删除</el-button>
      </div>
      <el-button :icon="Plus" class="add-mapping-btn" @click="addMapping">新增映射</el-button>

      <el-divider />

      <h3>高级选项</h3>
      <el-form label-width="160px">
        <el-form-item label="Join 模式">
          <el-radio-group v-model="store.joinMode">
            <el-radio value="left">left join（VLOOKUP 默认）</el-radio>
            <el-radio value="inner">inner join（只保留命中行）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="多匹配处理">
          <el-radio-group v-model="store.matchMode">
            <el-radio value="merge_multi">合并多值（用 ; 分隔）</el-radio>
            <el-radio value="first">取第一条</el-radio>
            <el-radio value="last">取最后一条</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="归一化">
          <el-checkbox v-model="store.caseSensitive">大小写敏感</el-checkbox>
          <el-checkbox v-model="store.trimStrings">去除两端空格</el-checkbox>
        </el-form-item>
      </el-form>

      <div class="form-actions">
        <el-button @click="onBackToStep1">上一步</el-button>
        <el-button
          type="primary"
          :icon="Promotion"
          :loading="store.configuring"
          :disabled="!canConfigure || !!keysValidationError"
          @click="onConfigure"
        >下一步</el-button>
      </div>
    </el-card>

    <!-- ============== Step 3: 试运行 ============== -->
    <el-card v-else-if="step === 'configured'" shadow="never" class="step-card">
      <h3>配置摘要</h3>
      <el-descriptions v-if="digest" :column="2" border>
        <el-descriptions-item label="主键对">
          <span
            v-for="(kp, i) in keyPairsDisplay"
            :key="i"
            class="key-pair-chip"
          >
            <el-tag size="small">{{ kp.target }} ⟷ {{ kp.base }}</el-tag>
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="映射条数">
          {{ digest.mapping_count }}
        </el-descriptions-item>
        <el-descriptions-item label="含 overwrite">
          {{ digest.has_overwrite ? '是' : '否' }}
        </el-descriptions-item>
        <el-descriptions-item label="含 new_column">
          {{ digest.has_new_column ? '是' : '否' }}
        </el-descriptions-item>
        <el-descriptions-item label="Join 模式">
          {{ digest.join_mode }}
        </el-descriptions-item>
        <el-descriptions-item label="多匹配处理">
          {{ digest.match_mode }}
        </el-descriptions-item>
        <el-descriptions-item label="大小写敏感">
          {{ digest.case_sensitive ? '是' : '否' }}
        </el-descriptions-item>
        <el-descriptions-item label="去两端空格">
          {{ digest.trim_strings ? '是' : '否' }}
        </el-descriptions-item>
      </el-descriptions>

      <div v-if="warnings.length" class="warnings-block">
        <el-alert
          v-for="(w, i) in warnings"
          :key="i"
          :title="w"
          type="warning"
          :closable="false"
          show-icon
          class="warning-item"
        />
      </div>

      <div class="form-actions">
        <el-button @click="onBackToStep2">上一步（修改配置）</el-button>
        <el-button
          type="primary"
          :icon="VideoPlay"
          :loading="store.executing"
          @click="onExecute"
        >执行填充</el-button>
      </div>
    </el-card>

    <!-- ============== Step 4: 结果 ============== -->
    <el-card v-else-if="step === 'executed' && summary" shadow="never" class="step-card">
      <h3>执行摘要</h3>
      <el-descriptions :column="3" border>
        <el-descriptions-item label="target 行数">
          {{ summary.target_row_count }}
        </el-descriptions-item>
        <el-descriptions-item label="结果行数">
          {{ summary.result_row_count }}
        </el-descriptions-item>
        <el-descriptions-item label="填充命中">
          {{ summary.filled_count }}
        </el-descriptions-item>
        <el-descriptions-item label="未命中">
          {{ summary.unmatched_count }}
          <el-tag
            v-if="summary.unmatched_count > 0"
            type="info"
            size="small"
            class="summary-tag"
          >base 表缺失该主键</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="多匹配">
          {{ summary.multi_match_count }}
          <el-tag
            v-if="summary.multi_match_count > 0"
            type="warning"
            size="small"
            class="summary-tag"
          >合并展示</el-tag>
        </el-descriptions-item>
      </el-descriptions>

      <h3>预览（前 1000 行）</h3>
      <el-table
        :data="previewRows"
        stripe
        size="small"
        :max-height="400"
        class="preview-table"
        :empty-text="previewRows.length ? '' : '无匹配数据'"
      >
        <el-table-column
          v-for="col in previewHeaders"
          :key="col"
          :prop="col"
          :label="col"
          min-width="120"
          show-overflow-tooltip
        />
      </el-table>
      <p
        v-if="summary.result_row_count > 1000"
        class="meta-info"
      >仅展示前 1000 行；完整数据请下载 xlsx 文件</p>

      <div class="form-actions">
        <el-button @click="onBackToStep3">上一步</el-button>
        <el-button
          type="success"
          :icon="Download"
          :loading="store.downloading"
          @click="onDownload"
        >下载完整结果 xlsx</el-button>
        <el-button
          type="danger"
          :icon="Delete"
          @click="onCleanUp"
        >清理任务（删除）</el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.cross-table-fill {
  max-width: 960px;
  margin: 0 auto;
}
.page-title {
  margin: 0 0 4px;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}
.page-hint {
  font-size: 13px;
  color: #909399;
  margin: 0 0 20px;
  line-height: 1.5;
}
.step-indicator {
  margin-bottom: 24px;
}
.step-card {
  margin-bottom: 16px;
}
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}
.file-name {
  margin-left: 8px;
  color: #606266;
  font-size: 13px;
}
.form-hint {
  color: #909399;
  font-size: 12px;
  margin-left: 8px;
}
/* v0.6.0.0.3 hot fix：空态提示 / 行动按钮容器 */
.empty-hint {
  color: #909399;
  background: #f5f7fa;
  border: 1px dashed #dcdfe6;
  border-radius: 4px;
  padding: 10px 14px;
  margin: 4px 0 12px;
  font-size: 13px;
  display: block;
}
.row-actions {
  display: flex;
  justify-content: flex-start;
  margin: 8px 0 4px;
}
.meta-info {
  color: #909399;
  font-size: 12px;
  margin: 4px 0 12px;
}
.key-pair-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.key-separator {
  color: #909399;
  font-weight: bold;
}
.key-pair-chip {
  margin-right: 6px;
  display: inline-block;
}
.header-table,
.preview-table {
  margin-bottom: 8px;
}
.mapping-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding: 8px;
  background: #fafbfc;
  border-radius: 4px;
  flex-wrap: wrap;
}
.mapping-label {
  color: #606266;
  font-size: 12px;
  white-space: nowrap;
}
.mapping-arrow {
  color: #909399;
  font-weight: bold;
  font-size: 14px;
}
.mapping-select {
  width: 180px;
  flex-shrink: 0;
}
.mapping-mode {
  flex-shrink: 0;
}
.add-mapping-btn {
  margin-top: 8px;
}
.field-error {
  color: #f56c6c;
  font-size: 12px;
  margin: 4px 0;
}
.warnings-block {
  margin-top: 16px;
}
.warning-item {
  margin-bottom: 8px;
}
.summary-tag {
  margin-left: 6px;
}
</style>
