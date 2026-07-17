<script setup>
/**
 * 邮箱配置主页（路由 /email-config）。
 *
 * 数据来源：GET /api/email-config；详见 OpenAPI EmailConfigRead。
 * 提交接口：
 *   - PUT /api/email-config（单行 upsert；smtp_password 留空 = 保留旧值；send_time / active 每次显式覆盖）。
 *   - POST /api/email/send-test（连通性测试；不受 active 开关约束；后端自动 upsert）。
 * 加载策略：onMounted 触发 store.fetch()。
 * 三态：加载中（首屏骨架）/ 加载失败（无旧数据 error 卡片）/ 正常表单。
 * 密码框 placeholder 三态：未配置 / 已设置留空保留 / 已设置可改 → 由 store.passwordIsSet 控制。
 * 按钮互斥：saving / testing / loading 互斥（详见 spec §2.8 按钮状态表）。
 *
 * 全局规则遵循 frontend/spec/README.md；本文档聚焦本模块特有的交互与展示。
 */
import { onMounted, ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ApiError, showApiError } from '../api/client.js'
import { useEmailConfigStore } from '../stores/useEmailConfigStore.js'

const store = useEmailConfigStore()

// ========== 端口预设 + TLS 联动 ==========
const TLS_PRESETS = [
  { port: 465, use_tls: true,  label: 'SSL (465)' },
  { port: 587, use_tls: true,  label: 'STARTTLS (587)' },
  { port: 25,  use_tls: false, label: '无加密 (25)' }
]

// 24h HH:MM 正则：与后端 Pydantic _validate_send_time 完全一致
const SEND_TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/

// 表单本地状态（不直接绑定到 store.config，方便用户自由编辑）
const formRef = ref(null)
const form = reactive({
  smtp_host: '',
  smtp_port: 465,
  use_tls: true,
  smtp_user: '',
  smtp_password: '',
  sender_email: '',
  sender_name: '',
  recipient_email: '',
  recipient_name: '',
  send_time: '08:00',
  active: false
})

// ========== 三态派生 ==========
const isFirstLoad = computed(
  () => store.loading && !store.hasLoadedData && store.config.id === null
)
const isFatal = computed(
  () => store.error && !store.hasLoadedData && store.config.id === null && !store.loading
)

// ========== 密码框 placeholder 策略 ==========
const passwordPlaceholder = computed(() => {
  if (!store.isConfigured) return '(请输入)'
  if (store.passwordIsSet) return '(已设置，留空表示不修改)'
  return '(请输入)'
})

// ========== 校验规则 ==========
const EMAIL_PATTERN = /^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$/

function validateEmail(_, value, callback) {
  if (!value) {
    callback(new Error('请输入邮箱'))
    return
  }
  if (!EMAIL_PATTERN.test(value)) {
    callback(new Error('请输入正确的邮箱'))
    return
  }
  callback()
}

function validateOptionalPassword(_, value, callback) {
  if (value === '' || value === null || value === undefined) {
    callback()
    return
  }
  if (typeof value !== 'string' || value.length < 1 || value.length > 256) {
    callback(new Error('密码长度 1-256 字符'))
    return
  }
  callback()
}

function validateOptionalName(_, value, callback) {
  if (value === '' || value === null || value === undefined) {
    callback()
    return
  }
  if (typeof value !== 'string' || value.length < 1 || value.length > 64) {
    callback(new Error('长度 1-64 字符'))
    return
  }
  callback()
}

function validateSendTime(_, value, callback) {
  if (!value) {
    callback(new Error('请选择每日发送时间'))
    return
  }
  if (!SEND_TIME_PATTERN.test(value)) {
    callback(new Error('请输入 24h HH:MM（如 08:30）'))
    return
  }
  callback()
}

const rules = {
  smtp_host: [
    { required: true, message: '请输入 SMTP 服务器', trigger: 'blur' },
    { min: 1, max: 128, message: '长度 1-128 字符', trigger: 'blur' }
  ],
  smtp_port: [
    { required: true, message: '请选择端口', trigger: 'change' }
  ],
  smtp_user: [
    { required: true, message: '请输入登录账号', trigger: 'blur' },
    { min: 1, max: 128, message: '长度 1-128 字符', trigger: 'blur' }
  ],
  smtp_password: [
    { validator: validateOptionalPassword, trigger: 'blur' }
  ],
  sender_email: [
    { required: true, validator: validateEmail, trigger: 'blur' }
  ],
  sender_name: [
    { required: true, message: '请输入发件人显示名', trigger: 'blur' },
    { min: 1, max: 64, message: '长度 1-64 字符', trigger: 'blur' }
  ],
  recipient_email: [
    { required: true, validator: validateEmail, trigger: 'blur' }
  ],
  recipient_name: [
    { validator: validateOptionalName, trigger: 'blur' }
  ],
  send_time: [
    { required: true, validator: validateSendTime, trigger: 'change' },
    { validator: validateSendTime, trigger: 'blur' }
  ],
  active: [
    { type: 'boolean', required: true, message: '请设置启用开关', trigger: 'change' }
  ]
}

// ========== 端口 ↔ use_tls 联动 ==========
watch(() => form.smtp_port, (newPort) => {
  const preset = TLS_PRESETS.find((p) => p.port === newPort)
  if (preset) {
    form.use_tls = preset.use_tls
  }
})

// ========== 把 store.config 灌入表单（仅初次加载 + 保存成功后） ==========
function hydrateForm() {
  form.smtp_host = store.config.smtp_host || ''
  form.smtp_port = store.config.smtp_port != null ? store.config.smtp_port : 465
  form.use_tls = !!store.config.use_tls
  form.smtp_user = store.config.smtp_user || ''
  form.smtp_password = ''
  form.sender_email = store.config.sender_email || ''
  form.sender_name = store.config.sender_name || ''
  form.recipient_email = store.config.recipient_email || ''
  form.recipient_name = store.config.recipient_name || ''
  form.send_time = store.config.send_time || '08:00'
  form.active = !!store.config.active
}

// 监听 store.config 变化（GET 成功后 / save 成功后由 store 替换 config）→ 灌入表单
watch(
  () => store.config,
  () => {
    // 首屏加载中不灌入（避免覆盖 form 初始值闪烁）；仅当 store 完成 fetch 时灌入
    if (!store.loading) {
      hydrateForm()
    }
  },
  { deep: true }
)

// ========== 生命周期 ==========
onMounted(async () => {
  await store.fetch()
  hydrateForm()
})

// ========== 操作 ==========
function buildPayload() {
  return {
    smtp_host: form.smtp_host.trim(),
    smtp_port: Number(form.smtp_port),
    smtp_user: form.smtp_user.trim(),
    smtp_password: form.smtp_password === '' ? null : form.smtp_password,
    use_tls: !!form.use_tls,
    sender_email: form.sender_email.trim(),
    sender_name: form.sender_name.trim(),
    recipient_email: form.recipient_email.trim(),
    recipient_name: form.recipient_name === '' ? null : form.recipient_name.trim(),
    send_time: form.send_time,
    active: !!form.active
  }
}

async function onSubmit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    // el-form validate 失败：字段红字已自动展示，停止提交
    return
  }

  const result = await store.save(buildPayload())
  if (result.ok) {
    ElMessage.success('保存成功')
    // 清空密码框（语义：用户提交的新密码已落库；下次 GET 之前 placeholder 由 store.passwordIsSet 决定）
    form.smtp_password = ''
    formRef.value?.clearValidate()
  } else {
    const err = result.error
    if (err instanceof ApiError) {
      if (err.status === 422) {
        // 422：字段红字由 el-form rules 校验已捕获；此处仅聚合 toast
        ElMessage.error(err.message)
      } else {
        showApiError(err)
      }
    } else {
      showApiError(err)
    }
  }
}

async function onSendTest() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  const result = await store.sendTest(buildPayload())
  if (result.ok) {
    const recipient = result.response?.recipient || form.recipient_email
    ElMessage.success(`已发送测试邮件至 ${recipient}`)
    form.smtp_password = ''
    formRef.value?.clearValidate()
  } else {
    const err = result.error
    if (err instanceof ApiError && err.status === 422) {
      // 422 字段红字由 el-form 触发；聚合 toast
      ElMessage.error(err.message)
    } else {
      showApiError(err)
    }
  }
}

function onReset() {
  hydrateForm()
  formRef.value?.clearValidate()
}

async function onRetry() {
  await store.fetch()
  hydrateForm()
}
</script>

<template>
  <div class="email-config-view">
    <!-- 首屏加载：骨架 -->
    <el-card v-if="isFirstLoad" shadow="never" class="loading-card">
      <el-skeleton :rows="11" animated />
    </el-card>

    <!-- 加载失败（无旧数据） -->
    <el-card v-else-if="isFatal" shadow="never" class="error-card">
      <div class="error-state">
        <p class="error-text">加载失败</p>
        <el-button type="primary" :loading="store.loading" @click="onRetry">重试</el-button>
      </div>
    </el-card>

    <!-- 正常表单 -->
    <template v-else>
      <div class="title-block">
        <h2>邮箱配置</h2>
      </div>

      <el-card shadow="never" class="form-card">
        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          @submit.prevent
        >
          <el-form-item label="SMTP 服务器" prop="smtp_host">
            <el-input v-model="form.smtp_host" placeholder="如 smtp.qq.com" />
          </el-form-item>

          <el-form-item label="端口" prop="smtp_port">
            <el-select v-model.number="form.smtp_port" placeholder="请选择" style="width: 240px">
              <el-option
                v-for="preset in TLS_PRESETS"
                :key="preset.port"
                :label="preset.label"
                :value="preset.port"
              />
            </el-select>
            <span class="hint">加密方式与端口联动，保存即生效</span>
          </el-form-item>

          <el-form-item label="登录账号" prop="smtp_user">
            <el-input v-model="form.smtp_user" placeholder="SMTP 登录账号（通常与发件人邮箱相同）" />
          </el-form-item>

          <el-form-item label="密码" prop="smtp_password">
            <el-input
              v-model="form.smtp_password"
              type="password"
              show-password
              :placeholder="passwordPlaceholder"
            />
            <span class="hint">不修改密码请留空；新密码将覆盖原值。</span>
          </el-form-item>

          <el-divider>发件人</el-divider>

          <el-form-item label="发件人邮箱" prop="sender_email">
            <el-input v-model="form.sender_email" type="email" placeholder="如 user@qq.com" />
          </el-form-item>

          <el-form-item label="发件人显示名" prop="sender_name">
            <el-input v-model="form.sender_name" placeholder="如 SparkMemo" />
          </el-form-item>

          <el-divider>收件人</el-divider>

          <el-form-item label="收件人邮箱" prop="recipient_email">
            <el-input v-model="form.recipient_email" type="email" placeholder="如 user@qq.com" />
          </el-form-item>

          <el-form-item label="收件人显示名（可选）" prop="recipient_name">
            <el-input v-model="form.recipient_name" placeholder="如 我自己" />
          </el-form-item>

          <el-divider>定时调度</el-divider>

          <el-form-item label="每日发送时间" prop="send_time">
            <el-time-picker
              v-model="form.send_time"
              format="HH:mm"
              value-format="HH:mm"
              placeholder="例如 08:00"
              style="width: 240px"
            />
            <span class="hint">24h HH:MM；仅在「启用定时发送」打开后由后端调度器按此时点每日触发。</span>
          </el-form-item>

          <el-form-item label="启用定时发送" prop="active">
            <el-switch
              v-model="form.active"
              active-text="启用"
              inactive-text="停用"
            />
            <span class="hint">关闭后调度器 Job 暂停；「测试发送」不受此开关约束。</span>
          </el-form-item>

          <div class="form-actions form-actions--split">
            <el-button :disabled="store.saving || store.testing" @click="onReset">重置</el-button>
            <el-button
              :loading="store.testing"
              :disabled="store.testing || store.saving"
              @click="onSendTest"
            >测试发送</el-button>
            <el-button
              type="primary"
              :loading="store.saving"
              :disabled="store.saving || store.testing"
              @click="onSubmit"
            >保存配置</el-button>
          </div>
        </el-form>
      </el-card>

      <div v-if="store.isConfigured" class="meta">
        创建于 {{ store.config.created_at }}
        <span class="meta-sep">·</span>
        最后更新于 {{ store.config.updated_at }}
      </div>
    </template>
  </div>
</template>

<style scoped>
.email-config-view {
  max-width: 720px;
}

.title-block h2 {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 16px 0;
  line-height: 1.3;
}

.loading-card,
.error-card {
  min-height: 240px;
}

.error-state {
  padding: 48px 0;
  text-align: center;
}

.error-text {
  color: var(--el-text-color-secondary);
  margin-bottom: 16px;
  font-size: 14px;
}

.form-card {
  margin-bottom: 16px;
}

.hint {
  display: block;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  line-height: 1.5;
  margin-top: 4px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.meta {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  padding: 8px 4px;
}

.meta-sep {
  margin: 0 8px;
}
</style>