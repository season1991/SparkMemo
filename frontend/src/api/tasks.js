/**
 * 任务 API：列表（多条件过滤 + 分页）、创建、详情（含 reminders）、更新、删除、完成。
 * 所有日期字段为 YYYY-MM-DD 字符串；422 字段错误由 detail[].loc 映射回表单红字。
 */
import client from './client.js'

export function listTasks({
  status,
  company_id,
  project_id,
  task_type_id,
  due_from,
  due_to,
  keyword,
  remind_today = false,
  page = 1,
  size = 20
} = {}) {
  return client.get('/tasks', {
    params: {
      status,
      company_id,
      project_id,
      task_type_id,
      due_from,
      due_to,
      keyword,
      remind_today,
      page,
      size
    }
  })
}

export function createTask(payload) {
  return client.post('/tasks', payload)
}

export function getTask(id) {
  return client.get(`/tasks/${id}`)
}

export function updateTask(id, payload) {
  return client.put(`/tasks/${id}`, payload)
}

export function deleteTask(id) {
  return client.delete(`/tasks/${id}`)
}

export function completeTask(id) {
  return client.post(`/tasks/${id}/complete`)
}