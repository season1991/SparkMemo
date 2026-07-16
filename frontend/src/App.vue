<script setup>
/**
 * 根组件薄壳：仅挂载 AppLayout。
 * 字典加载已下放到 layouts/AppLayout.vue，避免在此处重复预加载。
 */
import AppLayout from './layouts/AppLayout.vue'
</script>

<template>
  <AppLayout />
</template>