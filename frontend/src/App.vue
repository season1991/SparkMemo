<script setup>
/**
 * 根组件：全局顶部 Header + 路由出口。
 * mount 阶段并行预加载字典（types / companies / projects），供任务表单下拉使用。
 */
import { onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTypeStore } from './stores/useTypeStore.js'
import { useCompanyStore } from './stores/useCompanyStore.js'
import { useProjectStore } from './stores/useProjectStore.js'

const route = useRoute()
const router = useRouter()

const activeTab = computed({
  get() {
    return route.path === '/tasks/today' ? 'today' : 'all'
  },
  set(value) {
    router.push(value === 'today' ? '/tasks/today' : '/')
  }
})

onMounted(async () => {
  const typeStore = useTypeStore()
  const companyStore = useCompanyStore()
  const projectStore = useProjectStore()
  await Promise.all([
    typeStore.fetchAll().catch(() => {}),
    companyStore.fetchAll().catch(() => {}),
    projectStore.fetchAll().catch(() => {})
  ])
})
</script>

<template>
  <el-container class="app-root">
    <el-header class="app-header" height="48px">
      <div class="brand">SparkMemo</div>
      <el-tabs v-model="activeTab" class="center-tabs">
        <el-tab-pane label="全部" name="all" />
        <el-tab-pane label="今日待提醒" name="today" />
      </el-tabs>
      <div class="right-nav">
        <router-link to="/settings" custom v-slot="{ navigate }">
          <el-button text @click="navigate">设置</el-button>
        </router-link>
      </div>
    </el-header>
    <el-main class="app-main">
      <router-view />
    </el-main>
  </el-container>
</template>

<style scoped>
.app-root {
  min-height: 100vh;
  background: #f5f7fa;
}
.app-header {
  display: flex;
  align-items: center;
  background: #fff;
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 0 24px;
}
.brand {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  width: 160px;
}
.center-tabs {
  flex: 1;
}
.center-tabs :deep(.el-tabs__header) {
  margin: 0;
  border-bottom: none;
}
.right-nav {
  width: 160px;
  text-align: right;
}
.app-main {
  max-width: 1440px;
  margin: 0 auto;
  padding: 16px 24px;
}
</style>