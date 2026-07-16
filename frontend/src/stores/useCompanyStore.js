/**
 * 公司 store：全量字典 CRUD（供任务表单下拉使用）。
 */
import { defineStore } from 'pinia'
import * as api from '../api/companies.js'

export const useCompanyStore = defineStore('company', {
  state: () => ({
    companies: [],
    loading: false
  }),
  actions: {
    async fetchAll() {
      this.loading = true
      try {
        const res = await api.listCompanies({ size: 100 })
        this.companies = res.items || []
      } finally {
        this.loading = false
      }
    },
    async create(payload) {
      const created = await api.createCompany(payload)
      this.companies.push(created)
      return created
    },
    async update(id, payload) {
      const updated = await api.updateCompany(id, payload)
      const idx = this.companies.findIndex((c) => c.id === id)
      if (idx >= 0) this.companies.splice(idx, 1, updated)
      return updated
    },
    async remove(id) {
      await api.deleteCompany(id)
      this.companies = this.companies.filter((c) => c.id !== id)
    }
  }
})