/**
 * 任务类型 API：全量列表（不分页）、创建、详情、更新、删除。
 * 后端 name 缺失返回 422，全表唯一冲突返回 409，被任务引用时删除返回 409。
 */
import client from './client.js'

export function listTaskTypes() {
  return client.get('/task-types')
}

export function createTaskType(payload) {
  return client.post('/task-types', payload)
}

export function getTaskType(id) {
  return client.get(`/task-types/${id}`)
}

export function updateTaskType(id, payload) {
  return client.put(`/task-types/${id}`, payload)
}

export function deleteTaskType(id) {
  return client.delete(`/task-types/${id}`)
}