<script setup>
/**
 * HTML 转 Excel 主页（路由 /html-to-excel，v0.2.1 patch）。
 *
 * 升级要点：原 v0.2.0 把「按标题查找」埋在底部 el-collapse，普通用户找不到。
 * 本版本重构为顶部 el-tabs，两个 mode 同级可见：
 *   Tab A（default）"🔍 自动检测" — 文件变化自动调 /inspect，渲染卡片网格，点卡片 → 一键下载
 *   Tab B            "✏️ 按标题查找" — 输入 title + filename_hint → /extract → 下载
 *
 * 切换 tab 不会丢失对方 state；文件是共享的（顶部同一 file picker）。
 *
 * 错误约定（见 frontend/spec/html_to_excel.md §2.x + backend spec §8）：
 *   413 / 422 html_unparseable → ElMessage.error
 *   422 index_out_of_range  → 卡片上方 el-alert 提示 candidates（不重置网格）
 *   404 title_not_found（title tab） → suggestions 渲染 + 回填
 *   409 multiple_matches（title tab） → candidates + 重提交
 *   5xx → ElMessage.error
 */
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ApiError, showApiError } from '../api/client.js'
import {
  inspectHtmlControls,
  extractHtmlToExcelByIndex,
  extractHtmlToExcel,
  downloadHtmlToExcelXlsx
} from '../api/htmlToExcel.js'
import { downloadBlob } from '../utils/downloadBlob.js'

const MAX_BYTES = 20 * 1024 * 1024

// ──────────────────────── Tab 切换 ────────────────────────

const activeTab = ref('auto')  // 'auto' | 'title'

// ──────────────────────── 共享（文件选择 / 重置） ────────────────────────

const fileInputRef = ref(null)
const form = reactive({ file: null })

function triggerPick() {
  fileInputRef.value?.click()
}

function onFileChange(ev) {
  const f = ev.target.files && ev.target.files[0]
  ev.target.value = ''
  if (!f) return
  if (f.size > MAX_BYTES) {
    ElMessage.error('文件大小超过 20 MB 限制')
    return
  }
  form.file = f
  resetAutoState()
  resetTitleState()
  refreshInspect()
}

function onReset() {
  form.file = null
  resetAutoState()
  resetTitleState()
}

// ===================== Tab A：自动检测（inspect + 卡片网格） =====================

const autoState = ref('IDLE')  // IDLE | UPLOADING_INSPECT | INSPECTED | DOWNLOADING
const inspection = ref(null)
const controls = computed(() => inspection.value?.controls || [])
const downloadingIdx = ref(null)
const topAlert = ref(null)  // auto tab 专用的下载错误提示

function resetAutoState() {
  autoState.value = 'IDLE'
  inspection.value = null
  downloadingIdx.value = null
  topAlert.value = null
}

async function refreshInspect() {
  if (!form.file) return
  autoState.value = 'UPLOADING_INSPECT'
  try {
    const res = await inspectHtmlControls(form.file)
    inspection.value = res
    autoState.value = 'INSPECTED'
  } catch (err) {
    handleInspectError(err)
  }
}

function handleInspectError(err) {
  if (!(err instanceof ApiError)) {
    ElMessage.error(err?.message || 'inspect 失败')
    autoState.value = 'IDLE'
    return
  }
  if (err.status === 413 || err.status === 422) {
    showApiError(err)
    autoState.value = 'IDLE'
    return
  }
  showApiError(err)
  autoState.value = 'IDLE'
}

async function onDownloadByIndex(idx) {
  if (!form.file || autoState.value !== 'INSPECTED') return
  const card = controls.value.find((c) => c.index === idx)
  if (!card) {
    topAlert.value = {
      type: 'warning',
      title: `卡片 #${idx} 不存在（请刷新）`,
      candidates: []
    }
    return
  }
  downloadingIdx.value = idx
  autoState.value = 'DOWNLOADING'
  topAlert.value = null
  try {
    const res = await extractHtmlToExcelByIndex(form.file, idx, {
      filename_hint: card.suggested_title || `control_${idx}`,
    })
    const blob = await downloadHtmlToExcelXlsx(res.download_filename)
    downloadBlob(blob, res.download_filename)
    ElMessage.success(`已下载「${res.matched_title}」${res.rows} 行 × ${res.columns} 列`)
  } catch (err) {
    handleDownloadError(err)
  } finally {
    downloadingIdx.value = null
    autoState.value = 'INSPECTED'
  }
}

function handleDownloadError(err) {
  if (!(err instanceof ApiError)) {
    ElMessage.error(err?.message || '下载失败')
    return
  }
  if (err.status === 422 && err.detail?.error === 'index_out_of_range') {
    topAlert.value = {
      type: 'warning',
      title: '索引越界：后端当前无此 index，请使用其它卡片',
      candidates: Array.isArray(err.detail.candidates) ? err.detail.candidates : []
    }
    return
  }
  showApiError(err)
}

// ===================== Tab B：按标题查找（v0.1.0 兼容） =====================

const titleState = ref('IDLE')  // IDLE | EXTRACTING | OK | NOT_FOUND | AMBIGUOUS
const titleForm = reactive({ title: '', filename_hint: '' })
const titleResult = ref(null)
const titleSuggestions = ref([])
const titleCandidates = ref([])
const titlePickedCandidate = ref('')

function resetTitleState() {
  titleState.value = 'IDLE'
  titleResult.value = null
  titleSuggestions.value = []
  titleCandidates.value = []
  titlePickedCandidate.value = ''
}

async function onTitleExtract() {
  if (!form.file || !titleForm.title.trim()) {
    ElMessage.warning('请先选择 HTML 文件并输入标题')
    return
  }
  titleState.value = 'EXTRACTING'
  try {
    const res = await extractHtmlToExcel(form.file, titleForm.title.trim(), {
      filename_hint: titleForm.filename_hint?.trim() || null,
      auto_select_first: true,
    })
    const blob = await downloadHtmlToExcelXlsx(res.download_filename)
    downloadBlob(blob, res.download_filename)
    titleResult.value = res
    titleState.value = 'OK'
    ElMessage.success(`已抽取「${res.matched_title}」${res.rows} 行 × ${res.columns} 列`)
  } catch (err) {
    handleTitleError(err)
  }
}

function handleTitleError(err) {
  if (!(err instanceof ApiError)) {
    ElMessage.error(err?.message || '请求失败')
    titleState.value = 'IDLE'
    return
  }
  const detail = err.detail
  if (err.status === 404 && detail && detail.error === 'title_not_found') {
    titleState.value = 'NOT_FOUND'
    titleSuggestions.value = Array.isArray(detail.candidates) ? detail.candidates : []
    return
  }
  if (err.status === 409 && detail && detail.error === 'multiple_matches') {
    titleState.value = 'AMBIGUOUS'
    titleCandidates.value = Array.isArray(detail.candidates) ? detail.candidates : []
    titlePickedCandidate.value = titleCandidates.value[0] || ''
    return
  }
  titleState.value = 'IDLE'
  showApiError(err)
}

function applyTitleSuggestion(text) {
  titleForm.title = text
  titleState.value = 'IDLE'
}

async function retryTitleWithPicked() {
  if (!titlePickedCandidate.value) return
  titleForm.title = titlePickedCandidate.value
  titleState.value = 'IDLE'
  await onTitleExtract()
}

// ──────────────────────── 辅助 ────────────────────────

function controlTypeLabel(t) {
  switch (t) {
    case 'table': return 'Table'
    case 'div_grid': return 'Div Grid'
    case 'field_group': return 'Field Group'
    case 'list_block': return 'List'
    default: return t || '未知'
  }
}

function controlTypeTagType(t) {
  switch (t) {
    case 'table': return 'primary'
    case 'div_grid': return 'success'
    case 'field_group': return 'warning'
    case 'list_block': return 'info'
    default: return 'info'
  }
}

function humanSize(n) {
  if (!n) return '0 B'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}
</script>

<template>
  <div class="html-to-excel-view">
    <h2 class="page-title">HTML 转 Excel</h2>
    <p class="page-hint">
      上传任意 HTML 内容的文本文件（<code>.html</code> / <code>.htm</code> / <code>.txt</code> 等）。
      页面提供两种抽取方式（顶部 tab 切换，state 互不干扰）：
      <strong>自动检测</strong>会枚举页面所有可下载控件并以卡片展示，点击即一键下载；
      <strong>按标题查找</strong>则根据你输入的精确标题（大小写不敏感）抽取并下载（兼容 v0.1.0）。
      详见 <code>frontend/spec/html_to_excel.md</code>。
    </p>

    <!-- 共享：文件输入卡 -->
    <el-card shadow="never" class="form-card">
      <div class="file-row">
        <el-button type="primary" plain @click="triggerPick">
          选择 HTML 文件
        </el-button>
        <span v-if="form.file" class="file-name">
          {{ form.file.name }} <small>({{ humanSize(form.file.size) }})</small>
          <el-button link type="danger" size="small" @click="onReset">移除</el-button>
        </span>
        <span v-else class="file-placeholder">尚未选择文件（最大 20 MB）</span>
      </div>
      <input
        ref="fileInputRef"
        type="file"
        accept=".html,.htm,.txt,text/html,text/plain"
        style="display: none"
        @change="onFileChange"
      />
    </el-card>

    <!-- 顶部两个 tab -->
    <el-tabs v-model="activeTab" class="feature-tabs">
      <!-- ═══════ Tab A：自动检测 ═══════ -->
      <el-tab-pane name="auto" label="🔍 自动检测（推荐）">
        <div v-if="!form.file" class="tab-pane-hint">
          请先在上方选择 HTML 文件。
        </div>

        <template v-else>
          <!-- auto tab 专用：顶层 alert（下载失败 / 越界） -->
          <el-alert
            v-if="topAlert"
            :type="topAlert.type"
            :closable="true"
            class="top-alert"
            :title="topAlert.title"
            @close="topAlert = null"
          >
            <template v-if="topAlert.candidates && topAlert.candidates.length">
              可选 candidates：
              <el-tag
                v-for="(c, idx) in topAlert.candidates"
                :key="idx"
                class="candidate-tag"
                size="small"
                effect="plain"
              >{{ c }}</el-tag>
            </template>
          </el-alert>

          <!-- inspect 进度 -->
          <div v-if="autoState === 'UPLOADING_INSPECT'" class="loading-row">
            <el-progress :percentage="100" :indeterminate="true" :duration="2" />
            <span class="loading-text">正在解析 HTML 并枚举控件...</span>
          </div>

          <!-- 卡片网格 -->
          <div v-if="autoState === 'INSPECTED' || autoState === 'DOWNLOADING'" class="cards-section">
            <div class="cards-header">
              <span class="cards-count">
                共找到 <strong>{{ controls.length }}</strong> 个可下载控件
                <small v-if="inspection?.html_size_kb" class="cards-meta">
                  （源文件 {{ inspection.html_size_kb }} KB）
                </small>
              </span>
            </div>

            <el-empty
              v-if="controls.length === 0"
              description="未发现可下载的显著表格 / 字段组 / 列表"
              class="cards-empty"
            />

            <div v-else class="card-grid">
              <el-card
                v-for="ctrl in controls"
                :key="ctrl.index"
                shadow="hover"
                class="control-card"
                :class="{ 'is-loading': downloadingIdx === ctrl.index }"
              >
                <div class="card-head">
                  <span class="card-index">#{{ ctrl.index }}</span>
                  <el-tag size="small" :type="controlTypeTagType(ctrl.control_type)" effect="light">
                    {{ controlTypeLabel(ctrl.control_type) }}
                  </el-tag>
                </div>
                <div class="card-title-row">
                  <span class="card-title-label">标题</span>
                  <span class="card-title-value" :title="ctrl.suggested_title || '(空)'">
                    {{ ctrl.suggested_title || '(未命名)' }}
                  </span>
                </div>
                <div class="card-meta-row">
                  <span>行数：<strong>{{ ctrl.row_count }}</strong></span>
                  <span>列数：<strong>{{ ctrl.column_count }}</strong></span>
                  <el-button
                    type="primary"
                    size="small"
                    :loading="downloadingIdx === ctrl.index"
                    :disabled="autoState === 'DOWNLOADING' && downloadingIdx !== ctrl.index"
                    class="card-download-btn"
                    @click="onDownloadByIndex(ctrl.index)"
                  >
                    下载
                  </el-button>
                </div>

                <div v-if="ctrl.preview?.headers?.length" class="card-preview">
                  <div class="card-preview-title">Preview（前 5 列 × 前 3 行）</div>
                  <table class="preview-table">
                    <thead>
                      <tr>
                        <th v-for="(h, i) in ctrl.preview.headers" :key="'h'+i">{{ h }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(row, ri) in ctrl.preview.first_rows" :key="'r'+ri">
                        <td v-for="(cell, ci) in row" :key="'c'+ri+'-'+ci">{{ cell }}</td>
                      </tr>
                      <tr v-if="ctrl.preview.first_rows.length === 0">
                        <td :colspan="ctrl.preview.headers.length" class="preview-empty">（无预览行）</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-else class="card-preview">
                  <div class="card-preview-title">Preview</div>
                  <div class="preview-empty">（无表头预览）</div>
                </div>
              </el-card>
            </div>
          </div>
        </template>
      </el-tab-pane>

      <!-- ═══════ Tab B：按标题查找 ═══════ -->
      <el-tab-pane name="title" label="✏️ 按标题查找">
        <div v-if="!form.file" class="tab-pane-hint">
          请先在上方选择 HTML 文件。
        </div>

        <template v-else>
          <el-card shadow="never" class="title-form-card">
            <el-form label-position="top">
              <el-form-item label="控件标题">
                <el-input
                  v-model="titleForm.title"
                  placeholder="如 Items / Line Number / 销售团队"
                  maxlength="64"
                  show-word-limit
                />
              </el-form-item>
              <el-form-item label="下载文件名提示（可选）">
                <el-input
                  v-model="titleForm.filename_hint"
                  placeholder="留空则按「匹配标题 + 时间戳」自动生成"
                  maxlength="64"
                />
              </el-form-item>
              <div class="title-actions">
                <el-button
                  type="primary"
                  :loading="titleState === 'EXTRACTING'"
                  :disabled="!titleForm.title.trim()"
                  @click="onTitleExtract"
                >
                  抽取 xlsx
                </el-button>
                <el-button @click="titleForm.title=''; titleForm.filename_hint='';">
                  清空标题
                </el-button>
              </div>
            </el-form>
          </el-card>

          <!-- 404 suggestions -->
          <el-card v-if="titleState === 'NOT_FOUND'" shadow="never" class="title-error-card">
            <el-alert
              type="warning"
              :closable="false"
              title="未找到该标题"
              description="请确认 HTML 中该标题确实存在；下面是后端给的近似建议（点击回填到标题输入框）。"
            />
            <div v-if="titleSuggestions.length" class="suggestion-block">
              <el-tag
                v-for="(s, idx) in titleSuggestions"
                :key="idx"
                class="suggestion-tag"
                effect="plain"
                @click="applyTitleSuggestion(s)"
              >{{ s }}</el-tag>
            </div>
          </el-card>

          <!-- 409 multi-match -->
          <el-card v-if="titleState === 'AMBIGUOUS'" shadow="never" class="title-error-card">
            <el-alert
              type="warning"
              :closable="false"
              title="找到多个同名控件"
              description="请从下方候选中挑选 1 个，再次重提交。"
            />
            <el-radio-group v-model="titlePickedCandidate" class="title-radio-group">
              <el-radio
                v-for="(c, idx) in titleCandidates"
                :key="idx"
                :value="c"
                :label="c"
              />
            </el-radio-group>
            <div class="title-actions">
              <el-button @click="titleState='IDLE'">取消</el-button>
              <el-button
                type="primary"
                :disabled="!titlePickedCandidate"
                @click="retryTitleWithPicked"
              >
                重提交
              </el-button>
            </div>
          </el-card>

          <!-- 成功 -->
          <el-card v-if="titleState === 'OK' && titleResult" shadow="never" class="title-result-card">
            <div class="title-result-row">
              ✓ 已抽取 <strong>{{ titleResult.matched_title }}</strong>
              <span class="title-result-meta">
                {{ controlTypeLabel(titleResult.control_type) }} · {{ titleResult.rows }} 行 × {{ titleResult.columns }} 列
              </span>
            </div>
          </el-card>
        </template>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.html-to-excel-view {
  max-width: 1200px;
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
.page-hint code,
.page-hint pre {
  font-family: SFMono-Regular, Consolas, monospace;
  background: #f5f7fa;
  padding: 1px 6px;
  border-radius: 3px;
}
.form-card {
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
.file-name small {
  color: #909399;
  font-size: 12px;
}
.file-placeholder {
  font-size: 13px;
  color: #c0c4cc;
}
/* tabs 容器（顶部 + 内容区） */
.feature-tabs {
  margin-top: 16px;
}
.feature-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}
.tab-pane-hint {
  padding: 24px 8px;
  text-align: center;
  font-size: 13px;
  color: #909399;
  background: #fafafa;
  border-radius: 4px;
}
.top-alert {
  margin-bottom: 12px;
}
.candidate-tag {
  margin-right: 6px;
  margin-left: 6px;
  margin-bottom: 4px;
}
.loading-row {
  margin-top: 12px;
}
.loading-text {
  display: block;
  text-align: center;
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
.cards-section {
  margin-top: 8px;
}
.cards-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.cards-count {
  font-size: 14px;
  color: #606266;
}
.cards-count strong {
  font-weight: 600;
  color: #409eff;
  margin: 0 2px;
}
.cards-meta {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}
.cards-empty {
  margin-top: 8px;
}
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 12px;
}
.control-card {
  border-radius: 4px;
  font-size: 12px;
}
.control-card.is-loading {
  opacity: 0.6;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.card-index {
  font-weight: 600;
  color: #303133;
  font-size: 13px;
}
.card-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.card-title-label {
  color: #909399;
  font-size: 11px;
  flex-shrink: 0;
}
.card-title-value {
  color: #303133;
  font-weight: 500;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 240px;
}
.card-meta-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.card-meta-row span {
  font-size: 12px;
  color: #606266;
}
.card-meta-row strong {
  color: #303133;
  font-weight: 600;
  margin-left: 4px;
}
.card-download-btn {
  margin-left: auto;
}
.card-preview {
  margin-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 8px;
}
.card-preview-title {
  font-size: 11px;
  color: #909399;
  margin-bottom: 4px;
}
.preview-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}
.preview-table th,
.preview-table td {
  border: 1px solid var(--el-border-color-lighter);
  padding: 2px 6px;
  text-align: left;
  max-width: 90px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.preview-table th {
  background: #fafafa;
  font-weight: 600;
  color: #303133;
}
.preview-table td {
  color: #606266;
}
.preview-empty {
  text-align: center;
  color: #c0c4cc;
  padding: 6px !important;
}
/* ──── Tab B：按标题查找 ──── */
.title-form-card {
  margin-bottom: 12px;
  border-radius: 4px;
}
.title-form-card :deep(.el-form-item) {
  margin-bottom: 14px;
}
.title-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
.title-error-card,
.title-result-card {
  margin-top: 12px;
}
.suggestion-tag {
  margin-right: 6px;
  margin-bottom: 6px;
  cursor: pointer;
}
.title-radio-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 12px 0;
}
.title-result-row {
  font-size: 13px;
  color: #67c23a;
}
.title-result-meta {
  margin-left: 12px;
  color: #606266;
  font-weight: 400;
  font-size: 12px;
}
</style>
