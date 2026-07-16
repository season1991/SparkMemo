<script setup>
/**
 * 页面页头：左 route.meta.title，右信息展示位（v0.1 留空）。
 * 样式遵循 spec/README.md §5.2：高 56px，背景 #fff，下方 1px 边框。
 */
import { useRoute } from 'vue-router'
import { computed } from 'vue'

const route = useRoute()
const pageTitle = computed(() => route.meta?.title || '')
</script>

<template>
  <header class="app-header">
    <h1 class="page-title">{{ pageTitle }}</h1>
    <div class="header-right">
      <slot name="right" />
    </div>
  </header>
</template>

<style scoped>
.app-header {
  height: 56px;
  flex-shrink: 0;
  background: #fff;
  border-bottom: 1px solid var(--el-border-color-lighter);
  display: flex;
  align-items: center;
  padding: 0 24px;
}
.page-title {
  flex: 1;
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  line-height: 1;
}
.header-right {
  font-size: 14px;
  color: #909399;
  text-align: right;
}
</style>