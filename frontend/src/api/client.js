/**
 * axios 实例与拦截器。
 *
 * 拦截器将后端 4xx/5xx 统一抛 ApiError（含 status / detail / message），
 * 字段级 422 错误由调用方按 detail[].loc 映射回表单红字。
 *
 * v0.6.0 新增 request interceptor：拦截 FormData 上传请求，
 * 自动 `delete headers['Content-Type']`，让 axios 自动补 boundary=...。
 * 详见 frontend/spec/README.md §3.6 FormData 上传规则。
 */
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'

export class ApiError extends Error {
  constructor(status, detail, message) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.message = message
  }
}

const client = axios.create({
  baseURL: '/api',
  timeout: 10000
})

// ---------------- v0.6.0 新增：FormData request interceptor ----------------

/**
 * request interceptor 函数（v0.6.0 新增）。
 * 当请求体为 FormData 实例时，自动清掉用户/默认可能设置的 Content-Type 头，
 * 让 axios 内置 FormData 处理流程接管 —— 它会自动追加 `boundary=...`，
 * 避免「multipart/form-data 无 boundary」导致后端把文件字段误读为字符串
 * （即 Pydantic 抛「Value error, Expected UploadFile, received: <class 'str'>」）。
 *
 * 触发条件：cfg.data instanceof FormData
 * 作用：delete cfg.headers['Content-Type']
 * 兜底兼容：若旧 API 代码（如 `api/dsp_uploads.js`）仍手动 `headers: { 'Content-Type': 'multipart/form-data' }`，
 *           也会被本函数兜住，行为正确。
 *
 * 注：函数必须**返回值**（即便未修改 cfg）；return 缺失 axios 会抛。
 *
 * 导出供单测直接调用（避免依赖 axios adapter 的复杂 mocking）。
 *
 * @param {object} cfg axios request config
 * @returns {object} 原 cfg（必要时修改 headers）
 */
export function formDataRequestInterceptor(cfg) {
  try {
    if (cfg && cfg.data instanceof FormData) {
      if (cfg.headers) {
        // 大小写都覆盖；axios 1.x 默认用 'Content-Type'，但用户可能写 'content-type'
        delete cfg.headers['Content-Type']
        delete cfg.headers['content-type']
      }
    }
  } catch (_) {
    // 防御性：拦截器不应抛；万一 instanceof 检查失败等异常吞掉，让请求照常发出
  }
  return cfg
}

client.interceptors.request.use(formDataRequestInterceptor)

// ---------------- 既有的 response interceptor ----------------

client.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response) {
      const { status, data } = error.response
      const detail = data && data.detail !== undefined ? data.detail : null
      const message = humanizeError(status, detail)
      return Promise.reject(new ApiError(status, detail, message))
    }
    if (error.code === 'ECONNABORTED') {
      return Promise.reject(new ApiError(0, null, '网络异常，请稍后重试'))
    }
    return Promise.reject(new ApiError(0, null, '网络异常，请稍后重试'))
  }
)

function humanizeError(status, detail) {
  if (status === 400) {
    return typeof detail === 'string' ? detail : '请求参数有误，请检查后重试'
  }
  if (status === 404) return '资源不存在'
  if (status === 409) {
    return typeof detail === 'string' ? detail : '操作冲突'
  }
  if (status === 422) {
    if (Array.isArray(detail) && detail.length > 0) {
      return detail.map((d) => d.msg).join('；')
    }
    return '请求参数有误，请检查后重试'
  }
  if (status >= 500) {
    // 5xx 时若后端带了 detail 字符串（如 /api/email/send-test 的 MailerError），
    // 透传给前端用户，便于定位 SMTP 连接 / 认证 / 超时等具体原因；
    // 否则保持通用文案。
    return typeof detail === 'string' && detail ? detail : '服务异常，请稍后重试'
  }
  return '请求失败'
}

export function showApiError(err) {
  if (err instanceof ApiError) {
    if (err.status === 409) {
      ElMessageBox.alert(err.message, '无法操作', { type: 'warning' })
    } else {
      ElMessage.error(err.message)
    }
  } else {
    ElMessage.error('请求失败')
  }
}

export default client
