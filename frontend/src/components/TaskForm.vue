<script setup>
/**
 * 任务表单组件：抽屉承载，mode='create' | 'edit'。
 * 字段：title / description / task_type_id / company_id / project_id / due_at / remind_start_at。
 * 公司 → 项目下拉联动；due_at 改变时 remind_start_at 默认 = due_at - 1 天。
 * 422 字段错误按 detail[].loc 映射回表单字段红字。
 */
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTypeStore } from '../stores/useTypeStore.js'
import { useCompanyStore } from '../stores/useCompanyStore.js'
import { useProjectStore } from '../stores/useProjectStore.js'
import { useTaskStore } from '../stores/useTaskStore.js'
import { ApiError, showApiError } from '../api/client.js'
import ReminderChips from './ReminderChips.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  mode: { type: String, default: 'create' },
  task: { type: Object, default: null }
})
const emit = defineEmits(['update:modelValue', 'saved'])

const typeStore = useTypeStore()
const companyStore = useCompanyStore()
const projectStore = useProjectStore()
const taskStore = useTaskStore()

const formRef = ref(null)
const submitting = ref(false)
const initialSnapshot = ref('')

const today = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const subtractDay = (yyyy_mm_dd, days = 1) => {
  const [y, m, d] = yyyy_mm_dd.split('-').map(Number)
  const dt = new Date(y, m - 1, d)
  dt.setDate(dt.getDate() - days)
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`
}

const form = reactive({
  title: '',
  description: '',
  task_type_id: null,
  company_id: null,
  project_id: null,
  due_at: today(),
  remind_start_at: subtractDay(today(), 1)
})

const rules = {
  title: [
    { required: true, message: '请输入任务标题', trigger: 'blur' },
    { max: 200, message: '标题不超过 200 字符', trigger: 'blur' }
  ],
  description: [{ max: 4000, message: '描述不超过 4000 字符', trigger: 'blur' }],
  company_id: [{ required: true, message: '请选择公司', trigger: 'change' }],
  project_id: [{ required: true, message: '请选择项目', trigger: 'change' }],
  due_at: [{ required: true, message: '请选择截止日', trigger: 'change' }],
  remind_start_at: [
    {
      validator: (rule, value, cb) => {
        if (!value) return cb()
        if (form.due_at && value > form.due_at) {
          return cb(new Error('提醒起必须早于或等于截止日'))
        }
        cb()
      },
      trigger: 'change'
    }
  ]
}

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const isEdit = computed(() => props.mode === 'edit')
const title = computed(() => (isEdit.value ? '编辑任务' : '新建任务'))

const availableProjects = computed(() => {
  if (!form.company_id) return []
  return projectStore.byCompany[form.company_id] || []
})

watch(
  () => props.modelValue,
  async (v) => {
    if (v) {
      clearFieldErrors()
      if (isEdit.value && props.task) {
        await loadFromTask(props.task)
      } else {
        resetForm()
      }
      initialSnapshot.value = JSON.stringify(form)
    }
  }
)

watch(
  () => props.task,
  async (t) => {
    if (t && visible.value && isEdit.value) {
      await loadFromTask(t)
      initialSnapshot.value = JSON.stringify(form)
    }
  },
  { deep: true }
)

onMounted(() => {
  if (visible.value) {
    if (isEdit.value && props.task) {
      loadFromTask(props.task)
    }
    initialSnapshot.value = JSON.stringify(form)
  }
})

async function loadFromTask(t) {
  if (t.company_id) {
    try {
      await projectStore.fetchByCompany(t.company_id)
    } catch (err) {
      // ignore: 项目加载失败时仍允许表单呈现
    }
  }
  form.title = t.title || ''
  form.description = t.description || ''
  form.task_type_id = t.task_type ? t.task_type.id : null
  form.company_id = t.company ? t.company.id : null
  form.project_id = t.project ? t.project.id : null
  form.due_at = t.due_at || today()
  form.remind_start_at = t.remind_start_at || subtractDay(form.due_at, 1)
}

function resetForm() {
  form.title = ''
  form.description = ''
  form.task_type_id = null
  form.company_id = null
  form.project_id = null
  form.due_at = today()
  form.remind_start_at = subtractDay(form.due_at, 1)
}

const fieldErrors = reactive({})
function clearFieldErrors() {
  for (const k of Object.keys(fieldErrors)) delete fieldErrors[k]
}

function apply422(detail) {
  clearFieldErrors()
  if (!Array.isArray(detail)) return
  for (const err of detail) {
    const loc = err.loc || []
    if (loc[0] !== 'body') continue
    const fieldName = loc[1]
    if (!fieldName) continue
    fieldErrors[fieldName] = err.msg || '校验失败'
  }
  if (Object.keys(fieldErrors).length > 0) {
    ElMessage.error(Object.values(fieldErrors)[0])
  }
}

async function handleCompanyChange(val) {
  form.project_id = null
  if (val) {
    try {
      await projectStore.fetchByCompany(val)
    } catch (err) {
      ElMessage.warning('项目加载失败')
    }
  }
}

function handleDueAtChange(val) {
  if (!val) return
  const expected = subtractDay(val, 1)
  if (!form.remind_start_at || form.remind_start_at === subtractDay(form.due_at, 1)) {
    form.remind_start_at = expected
  }
}

function isDirty() {
  return initialSnapshot.value !== JSON.stringify(form)
}

async function handleClose() {
  if (isDirty()) {
    try {
      await ElMessageBox.confirm('当前修改尚未保存，确定离开？', '提示', {
        type: 'warning'
      })
    } catch {
      return
    }
  }
  visible.value = false
}

async function handleSubmit() {
  if (!formRef.value) return
  clearFieldErrors()
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  const payload = {
    title: form.title.trim(),
    description: form.description.trim() || null,
    task_type_id: form.task_type_id || null,
    company_id: form.company_id,
    project_id: form.project_id,
    due_at: form.due_at,
    remind_start_at: form.remind_start_at || null
  }
  submitting.value = true
  try {
    if (isEdit.value) {
      await taskStore.update(props.task.id, payload)
      ElMessage.success('更新成功')
    } else {
      await taskStore.create(payload)
      ElMessage.success('创建成功')
    }
    emit('saved')
    visible.value = false
  } catch (err) {
    if (err instanceof ApiError && err.status === 422) {
      apply422(err.detail)
    } else {
      showApiError(err)
    }
  } finally {
    submitting.value = false
  }
}

function fieldError(name) {
  return fieldErrors[name] || ''
}
</script>

<template>
  <el-drawer
    v-model="visible"
    :title="title"
    direction="rtl"
    size="560px"
    :close-on-click-modal="false"
    :before-close="handleClose"
  >
    <template v-if="isEdit && task && task.reminders">
      <div class="reminder-section">
        <div class="section-label">提醒计划</div>
        <ReminderChips :reminders="task.reminders" :due-at="task.due_at" />
      </div>
    </template>

    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="80px"
      label-position="right"
    >
      <el-form-item label="标题" prop="title" :error="fieldError('title')">
        <el-input v-model="form.title" placeholder="请输入任务标题" maxlength="200" show-word-limit />
      </el-form-item>

      <el-form-item label="描述" prop="description" :error="fieldError('description')">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="3"
          placeholder="可选"
          maxlength="4000"
          show-word-limit
        />
      </el-form-item>

      <el-form-item label="类型" prop="task_type_id" :error="fieldError('task_type_id')">
        <el-select v-model="form.task_type_id" placeholder="可选" clearable style="width: 100%">
          <el-option
            v-for="t in typeStore.types"
            :key="t.id"
            :label="t.name"
            :value="t.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="公司" prop="company_id" :error="fieldError('company_id')">
        <el-select
          v-model="form.company_id"
          placeholder="请选择公司"
          style="width: 100%"
          @change="handleCompanyChange"
        >
          <el-option
            v-for="c in companyStore.companies"
            :key="c.id"
            :label="c.name"
            :value="c.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="项目" prop="project_id" :error="fieldError('project_id')">
        <el-select
          v-model="form.project_id"
          placeholder="请选择项目"
          :disabled="!form.company_id"
          style="width: 100%"
        >
          <el-option
            v-for="p in availableProjects"
            :key="p.id"
            :label="p.name"
            :value="p.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="截止日" prop="due_at" :error="fieldError('due_at')">
        <el-date-picker
          v-model="form.due_at"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择截止日"
          style="width: 100%"
          @change="handleDueAtChange"
        />
      </el-form-item>

      <el-form-item label="提醒起" prop="remind_start_at" :error="fieldError('remind_start_at')">
        <el-date-picker
          v-model="form.remind_start_at"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="默认为截止日前 1 天"
          style="width: 100%"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="drawer-footer">
        <el-button @click="handleClose">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          保存
        </el-button>
      </div>
    </template>
  </el-drawer>
</template>

<style scoped>
.reminder-section {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: var(--el-bg-color-page);
  border-radius: 4px;
}
.section-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>