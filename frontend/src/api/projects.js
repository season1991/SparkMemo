/**
 * 项目 API：列表（按公司筛选 + 关键词）、创建、详情、更新、删除。
 * company_id 缺失返回 400，不存在返回 422，同公司下重名返回 409。
 */
import client from './client.js'

export function listProjects({ company_id, keyword, page = 1, size = 100 } = {}) {
  return client.get('/projects', { params: { company_id, keyword, page, size } })
}

export function createProject(payload) {
  return client.post('/projects', payload)
}

export function getProject(id) {
  return client.get(`/projects/${id}`)
}

export function updateProject(id, payload) {
  return client.put(`/projects/${id}`, payload)
}

export function deleteProject(id) {
  return client.delete(`/projects/${id}`)
}