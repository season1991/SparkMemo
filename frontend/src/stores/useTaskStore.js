/**
 * 任务 store：列表 / 详情 / 筛选状态 / CRUD actions。
 * store 内统一保存后端原样的 snake_case 字段；表单层用本地 ref 做中转，submit 前映射。
 */
import { defineStore } from 'pinia'
import * as api from '../api/tasks.js'

// 重新导出反推工具，方便上层（TaskForm.vue 等）直接从 store 引用。
export { inferRemindRule, previewRemindStartAt } from '../utils/remindRule.js'

export const useTaskStore = defineStore('task', {
  state: () => ({
    tasks: [],
    total: 0,
    filters: {
      status: '',
      company_id: null,
      project_id: null,
      task_type_id: null,
      due_from: '',
      due_to: '',
      keyword: '',
      remind_today: false,
      page: 1,
      size: 20
    },
    savedStatus: '',
    loading: false,
    error: null,
    current: null
  }),
  getters: {
    isEmpty: (state) => state.total === 0,
    hasActiveFilter: (state) =>
      Boolean(
        state.filters.status ||
          state.filters.company_id ||
          state.filters.project_id ||
          state.filters.task_type_id ||
          state.filters.due_from ||
          state.filters.due_to ||
          state.filters.keyword ||
          state.filters.remind_today
      ),
    activeFilterTags: (state) => {
      const tags = []
      const f = state.filters
      if (f.status) tags.push({ key: 'status', label: `状态：${f.status}` })
      if (f.company_id) tags.push({ key: 'company_id', label: '公司已选' })
      if (f.project_id) tags.push({ key: 'project_id', label: '项目已选' })
      if (f.task_type_id) tags.push({ key: 'task_type_id', label: '类型已选' })
      if (f.due_from) tags.push({ key: 'due_from', label: `从：${f.due_from}` })
      if (f.due_to) tags.push({ key: 'due_to', label: `至：${f.due_to}` })
      if (f.keyword) tags.push({ key: 'keyword', label: `关键词：${f.keyword}` })
      if (f.remind_today) tags.push({ key: 'remind_today', label: '今日待提醒' })
      return tags
    }
  },
  actions: {
    setFilter(key, value) {
      this.filters[key] = value
      this.filters.page = 1
      return this.fetchList(false)
    },
    _applyRemindToday(on) {
      if (this.filters.remind_today === on) return false
      this.filters.remind_today = on
      if (on) {
        this.savedStatus = this.filters.status
        this.filters.status = 'pending'
      } else {
        this.filters.status = this.savedStatus || ''
        this.savedStatus = ''
      }
      this.filters.page = 1
      return true
    },
    toggleRemindToday(on) {
      const changed = this._applyRemindToday(on)
      if (!changed) return
      return this.fetchList(false)
    },
    syncRemindTodayFromRoute(on) {
      this._applyRemindToday(on)
    },
    resetFilters() {
      this.filters = {
        status: '',
        company_id: null,
        project_id: null,
        task_type_id: null,
        due_from: '',
        due_to: '',
        keyword: '',
        remind_today: false,
        page: 1,
        size: this.filters.size
      }
      this.savedStatus = ''
      return this.fetchList(false)
    },
    removeFilter(key) {
      if (key === 'remind_today') {
        if (this.filters.remind_today) {
          this.filters.remind_today = false
          this.filters.status = this.savedStatus || ''
          this.savedStatus = ''
        }
      } else if (key === 'status') {
        this.filters.status = ''
        this.savedStatus = ''
      } else if (key === 'company_id') {
        this.filters.company_id = null
        this.filters.project_id = null
      } else if (key === 'project_id') {
        this.filters.project_id = null
      } else if (key === 'task_type_id') {
        this.filters.task_type_id = null
      } else {
        this.filters[key] = ''
      }
      this.filters.page = 1
      return this.fetchList(false)
    },
    async fetchList() {
      this.loading = true
      this.error = null
      try {
        const f = this.filters
        const res = await api.listTasks({
          status: f.status || undefined,
          company_id: f.company_id || undefined,
          project_id: f.project_id || undefined,
          task_type_id: f.task_type_id || undefined,
          due_from: f.due_from || undefined,
          due_to: f.due_to || undefined,
          keyword: f.keyword || undefined,
          remind_today: f.remind_today,
          page: f.page,
          size: f.size
        })
        this.tasks = res.items || []
        this.total = res.total || 0
      } catch (err) {
        this.error = err.message || '加载失败'
        this.tasks = []
        this.total = 0
        throw err
      } finally {
        this.loading = false
      }
    },
    async fetchOne(id) {
      this.current = await api.getTask(id)
      return this.current
    },
    clearCurrent() {
      this.current = null
    },
    async create(payload) {
      const created = await api.createTask(payload)
      await this.fetchList()
      return created
    },
    async update(id, payload) {
      const updated = await api.updateTask(id, payload)
      const idx = this.tasks.findIndex((t) => t.id === id)
      if (idx >= 0) this.tasks.splice(idx, 1, updated)
      if (this.current && this.current.id === id) {
        this.current = updated
      }
      return updated
    },
    async remove(id) {
      await api.deleteTask(id)
      const idx = this.tasks.findIndex((t) => t.id === id)
      if (idx >= 0) {
        this.tasks.splice(idx, 1)
        this.total = Math.max(0, this.total - 1)
      }
    },
    async markComplete(id) {
      const updated = await api.completeTask(id)
      const idx = this.tasks.findIndex((t) => t.id === id)
      if (idx >= 0) this.tasks.splice(idx, 1, updated)
      return updated
    }
  }
})