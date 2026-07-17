/**
 * 邮箱配置 API：单行 GET / 单行 PUT upsert / 测试发送 POST。
 * 契约来源：backend/openapi/email_notification.json（EmailConfigRead / EmailConfigWrite）。
 * 全局 axios 拦截器会把 4xx/5xx 统一抛 ApiError；本模块无需额外错误处理。
 *
 * 注意：smtp_password 留空（"" / null）时由后端「保留旧值」语义处理。
 * send_test 端点不受 active 开关约束（纯连通性验证），后端会自动 upsert 入参配置再发送。
 */
import client from './client.js'

export function getEmailConfig() {
  return client.get('/email-config')
}

export function saveEmailConfig(payload) {
  return client.put('/email-config', payload)
}

export function sendTestEmail(payload) {
  return client.post('/email/send-test', payload)
}