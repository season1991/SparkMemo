<script setup>
/**
 * 侧边栏导航条：Logo + 导航项；点击触发 router.push。
 * 激活态：route.path 命中项，左 3px 主色竖条 + 浅主色背景 + 主色文字。
 * 样式遵循 spec/README.md §5.2：宽 220px，Logo 区 64px，导航项 44px × N，间距 4px。
 *
 * v0.3 email_config 模块新增「邮箱配置」第三项；其余旧路径
 * （/tasks/today / /settings）保留可达但不在此处显示。
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { DataAnalysis, List, Message } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()

const navItems = [
  { name: '今日概述', icon: DataAnalysis, to: '/' },
  { name: '任务管理', icon: List, to: '/tasks' },
  { name: '邮箱配置', icon: Message, to: '/email-config' }
]

const activeTo = computed(() => route.path)

function go(to) {
  if (route.path !== to) router.push(to)
}
</script>

<template>
  <aside class="app-sidebar">
    <div class="logo">
      <span class="logo-icon">⚡</span>
      <span class="logo-text">SparkMemo</span>
    </div>
    <nav class="nav-list">
      <div
        v-for="item in navItems"
        :key="item.to"
        class="nav-item"
        :class="{ active: activeTo === item.to }"
        @click="go(item.to)"
      >
        <el-icon class="nav-icon"><component :is="item.icon" /></el-icon>
        <span class="nav-text">{{ item.name }}</span>
      </div>
    </nav>
  </aside>
</template>

<style scoped>
.app-sidebar {
  width: 220px;
  flex-shrink: 0;
  background: #fff;
  border-right: 1px solid var(--el-border-color-lighter);
  display: flex;
  flex-direction: column;
}
.logo {
  height: 64px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.logo-icon {
  font-size: 22px;
  line-height: 1;
}
.logo-text {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}
.nav-list {
  padding: 8px 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.nav-item {
  position: relative;
  height: 44px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 10px;
  cursor: pointer;
  color: #303133;
  font-size: 14px;
  font-weight: 400;
  border-radius: 0;
  transition: background-color 0.15s ease;
}
.nav-item:hover {
  background: #f5f7fa;
}
.nav-item.active {
  background: #ecf5ff;
  color: #409eff;
}
.nav-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: #409eff;
}
.nav-icon {
  font-size: 18px;
}
.nav-text {
  line-height: 1;
}
</style>