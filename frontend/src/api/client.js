/**
 * axios 实例与拦截器。
 * 拦截器将后端 4xx/5xx 统一抛 ApiError（含 status / detail / message），
 * 字段级 422 错误由调用方按 detail[].loc 映射回表单红字。
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
  if (status >= 500) return '服务异常，请稍后重试'
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