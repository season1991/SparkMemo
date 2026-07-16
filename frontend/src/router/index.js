/**
 * 路由表：hash 模式，纯静态部署友好。
 * 三个路由：/（全部任务）、/tasks/today（今日待提醒）、/settings（占位）。
 */
import { createRouter, createWebHashHistory } from 'vue-router'
import TaskList from '../views/TaskList.vue'
import Settings from '../views/Settings.vue'

const routes = [
  {
    path: '/',
    name: 'TaskList',
    component: TaskList,
    meta: { remindToday: false, title: '全部任务' }
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
    component: Settings
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

export default router