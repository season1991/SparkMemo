/**
 * 今日概述 API：单次聚合 GET，返回 today + summary + companies[]。
 * 契约来源：backend/openapi/dashboard.json（DashboardTodayResponse）。
 * 全局 axios 拦截器会把 4xx/5xx 统一抛 ApiError；本调用无需额外错误处理。
 */
import client from './client.js'

export function getDashboardToday() {
  return client.get('/dashboard/today')
}
