<script setup>
/**
 * 整体布局：左 AppSidebar(220px) + 右 AppPage(AppHeader + <router-view/>)。
 * 全局字典（types / companies / projects）在此 mount 阶段并行预加载一次。
 */
import { onMounted } from 'vue'
import AppSidebar from './AppSidebar.vue'
import AppHeader from './AppHeader.vue'
import { useTypeStore } from '../stores/useTypeStore.js'
import { useCompanyStore } from '../stores/useCompanyStore.js'
import { useProjectStore } from '../stores/useProjectStore.js'

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
  <div class="app-layout">
    <AppSidebar />
    <div class="app-page">
      <AppHeader />
      <main class="app-main">
        <router-view v-slot="{ Component }">
          <!--
            keep-alive 只缓存 Dashboard（路由回退时仍命中 onActivated）。
            其他视图（TaskList / Settings）正常 unmount，避免陈旧筛选条件。
          -->
          <keep-alive include="Dashboard">
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </main>
    </div>
  </div>
</template>

<style scoped>
.app-layout {
  min-height: 100vh;
  display: flex;
  background: #f5f7fa;
}
.app-page {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.app-main {
  width: 100%;
  max-width: 1440px;
  margin: 0 auto;
  padding: 16px 24px;
  flex: 1;
  box-sizing: border-box;
}
</style>