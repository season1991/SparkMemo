/**
 * 任务类型 store：全量字典 CRUD。
 */
import { defineStore } from 'pinia'
import * as api from '../api/taskTypes.js'

export const useTypeStore = defineStore('type', {
  state: () => ({
    types: [],
    loading: false
  }),
  actions: {
    async fetchAll() {
      this.loading = true
      try {
        const data = await api.listTaskTypes()
        this.types = Array.isArray(data) ? data : []
      } finally {
        this.loading = false
      }
    },
    async create(payload) {
      const created = await api.createTaskType(payload)
      this.types.push(created)
      return created
    },
    async update(id, payload) {
      const updated = await api.updateTaskType(id, payload)
      const idx = this.types.findIndex((t) => t.id === id)
      if (idx >= 0) this.types.splice(idx, 1, updated)
      return updated
    },
    async remove(id) {
      await api.deleteTaskType(id)
      this.types = this.types.filter((t) => t.id !== id)
    }
  }
})