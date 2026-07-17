/**
 * 路由表：hash 模式，纯静态部署友好。
 * `/` 为主页「今日概述」（Dashboard）；`/tasks` 走原 TaskList 列表（默认全部状态）。
 * 旧路由 `/tasks/today` 与 `/settings` 仍保留可达（不删除既有链接），但不在侧边栏中显示。
 */
import { createRouter, createWebHashHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import TaskList from '../views/TaskList.vue'
import Settings from '../views/Settings.vue'

const routes = [
  {
    path: '/',
    name: 'Dashboard',
    component: Dashboard,
    meta: { title: '今日概述' }
  },
  {
    path: '/tasks',
    name: 'TaskList',
    component: TaskList,
    meta: { remindToday: false, title: '任务管理' }
  },
  {
    path: '/tasks/today',
    name: 'TaskListToday',
    component: TaskList,
    meta: { remindToday: true, title: '今日待提醒' }
  },
  {
    path: '/settings',
    name: 'Settings',
    component: Settings,
    meta: { title: '设置' }
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

export default router
