/**
 * 今日概述 store：聚合数据 + 加载 / 错误状态。
 * state 字段与 OpenAPI schema 完全 snake_case 直存；UI 字段（loading / error）独立维护。
 * 错误兜底策略：失败时只更新 error，保留旧数据（避免 empty stare），由 UI 决定渲染哪个三态。
 */
import { defineStore } from 'pinia'
import { getDashboardToday } from '../api/dashboard.js'

const EMPTY_SUMMARY = Object.freeze({
  urgent: 0,
  due_soon: 0,
  early: 0,
  total: 0
})

export const useDashboardStore = defineStore('dashboard', {
  state: () => ({
    today: '',
    summary: { ...EMPTY_SUMMARY },
    companies: [],
    loading: false,
    error: null
  }),
  getters: {
    /** 全局合计是否为零；用于决定渲染空态卡片还是 summary + 公司表。 */
    isEmpty: (state) => !state.summary || state.summary.total === 0,
    /** 公司表行数。 */
    companyCount: (state) => state.companies.length,
    /** 是否有任意公司存在非零计数；与 isEmpty 互为对照，分「无公司」与「公司全 0」两种空。 */
    hasAnyCount: (state) => (state.companies || []).some((c) => c.total > 0)
  },
  actions: {
    async fetch() {
      this.loading = true
      this.error = null
      try {
        const res = await getDashboardToday()
        this.today = res.today || ''
        this.summary = res.summary || { ...EMPTY_SUMMARY }
        this.companies = res.companies || []
      } catch (err) {
        this.error = (err && err.message) || '加载失败'
        // 保留旧数据可视化，由 UI 决定渲染哪个三态
      } finally {
        this.loading = false
      }
    },
    clear() {
      this.today = ''
      this.summary = { ...EMPTY_SUMMARY }
      this.companies = []
      this.error = null
    }
  }
})
