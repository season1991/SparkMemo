/**
 * 路由表：hash 模式，纯静态部署友好。
 * `/` 为主页「今日概述」（Dashboard）；`/tasks` 走原 TaskList 列表（默认全部状态）。
 * `/email-config` 为邮箱配置页（v0.3 新增）。
 * 旧路由 `/tasks/today` 与 `/settings` 仍保留可达（不删除既有链接），但不在侧边栏中显示。
 */
import { createRouter, createWebHashHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import TaskList from '../views/TaskList.vue'
import Settings from '../views/Settings.vue'
import EmailConfig from '../views/EmailConfig.vue'
import WeeklyDemandHub from '../views/WeeklyDemandHub.vue'
import DspUpload from '../views/DspUpload.vue'
import WeeklyDemandQuery from '../views/WeeklyDemandQuery.vue'
import WeeklyDemandDelete from '../views/WeeklyDemandDelete.vue'

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
    // v0.5.4：模块重命名为「周需求管理」；/dsp-uploads 现在是 Hub 页
    path: '/dsp-uploads',
    name: 'WeeklyDemandHub',
    component: WeeklyDemandHub,
    meta: { title: '周需求管理' }
  },
  {
    path: '/dsp-uploads/upload',
    name: 'DspUpload',
    component: DspUpload,
    meta: { title: 'DSP 上传' }
  },
  {
    path: '/dsp-uploads/query',
    name: 'WeeklyDemandQuery',
    component: WeeklyDemandQuery,
    meta: { title: '查询' }
  },
  {
    path: '/dsp-uploads/delete',
    name: 'WeeklyDemandDelete',
    component: WeeklyDemandDelete,
    meta: { title: '删除' }
  },
  {
    path: '/email-config',
    name: 'EmailConfig',
    component: EmailConfig,
    meta: { title: '邮箱配置' }
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

