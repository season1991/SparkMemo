<script setup>
/**
 * 全局通知占位组件：通知推送模块未实现，保留作为后续 WS 通知挂载点。
 */
import { ref } from 'vue'

const notifications = ref([])

function dismiss(id) {
  notifications.value = notifications.value.filter((n) => n.id !== id)
}
</script>

<template>
  <div class="notification-stack" aria-live="polite">
    <transition-group name="notif">
      <div v-for="n in notifications" :key="n.id" class="notification" :class="`is-${n.type}`">
        <span class="msg">{{ n.message }}</span>
        <button class="close" @click="dismiss(n.id)">×</button>
      </div>
    </transition-group>
    <span v-if="notifications.length === 0" class="placeholder">通知推送开发中</span>
  </div>
</template>

<style scoped>
.notification-stack {
  position: fixed;
  top: 64px;
  right: 24px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}
.notification {
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12);
  padding: 10px 14px;
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 240px;
  pointer-events: auto;
}
.notification.is-warning {
  border-left: 3px solid var(--el-color-warning);
}
.notification.is-success {
  border-left: 3px solid var(--el-color-success);
}
.notification.is-error {
  border-left: 3px solid var(--el-color-danger);
}
.close {
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--el-text-color-secondary);
  font-size: 18px;
  line-height: 1;
}
.placeholder {
  background: rgba(255, 255, 255, 0.9);
  color: var(--el-text-color-placeholder);
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 12px;
}
.notif-enter-active,
.notif-leave-active {
  transition: all 0.2s ease;
}
.notif-enter-from,
.notif-leave-to {
  opacity: 0;
  transform: translateX(20px);
}
</style>