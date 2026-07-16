/**
 * 公司 API：列表（分页 + 关键词）、创建、详情、更新、删除。
 * 后端 name 缺失返回 422，重名返回 409，被任务/项目引用时删除返回 409。
 */
import client from './client.js'

export function listCompanies({ keyword, page = 1, size = 20 } = {}) {
  return client.get('/companies', { params: { keyword, page, size } })
}

export function createCompany(payload) {
  return client.post('/companies', payload)
}

export function getCompany(id) {
  return client.get(`/companies/${id}`)
}

export function updateCompany(id, payload) {
  return client.put(`/companies/${id}`, payload)
}

export function deleteCompany(id) {
  return client.delete(`/companies/${id}`)
}