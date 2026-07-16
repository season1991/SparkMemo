<script setup>
/**
 * 设置页占位：通知推送模块启动后实装。
 * 页面标题由 layouts/AppHeader 渲染，此处不重复。
 */
</script>

<template>
  <div class="settings-view">
    <el-card shadow="never">
      <div class="placeholder">
        <p>通知推送开发中</p>
        <p class="hint">待后端补齐 WebSocket / notifications 接口后启动实装。</p>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.settings-view {
  max-width: 800px;
}
.placeholder {
  padding: 48px 0;
  text-align: center;
  color: var(--el-text-color-secondary);
}
.placeholder p {
  margin: 6px 0;
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
</style>