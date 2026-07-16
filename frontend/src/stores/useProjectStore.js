/**
 * 项目 store：列表 + 按公司分组（byCompany）。
 */
import { defineStore } from 'pinia'
import * as api from '../api/projects.js'

export const useProjectStore = defineStore('project', {
  state: () => ({
    projects: [],
    loading: false
  }),
  getters: {
    byCompany: (state) => {
      const map = {}
      for (const p of state.projects) {
        if (!map[p.company_id]) map[p.company_id] = []
        map[p.company_id].push(p)
      }
      return map
    }
  },
  actions: {
    async fetchAll(params = {}) {
      this.loading = true
      try {
        const res = await api.listProjects({ size: 100, ...params })
        this.projects = res.items || []
      } finally {
        this.loading = false
      }
    },
    async fetchByCompany(companyId) {
      const cached = this.projects.filter((p) => p.company_id === companyId)
      if (cached.length > 0) return cached
      const res = await api.listProjects({ company_id: companyId, size: 100 })
      const items = res.items || []
      const existingIds = new Set(this.projects.map((p) => p.id))
      for (const p of items) {
        if (!existingIds.has(p.id)) this.projects.push(p)
      }
      return items
    },
    async create(payload) {
      const created = await api.createProject(payload)
      this.projects.push(created)
      return created
    },
    async update(id, payload) {
      const updated = await api.updateProject(id, payload)
      const idx = this.projects.findIndex((p) => p.id === id)
      if (idx >= 0) this.projects.splice(idx, 1, updated)
      return updated
    },
    async remove(id) {
      await api.deleteProject(id)
      this.projects = this.projects.filter((p) => p.id !== id)
    }
  }
})