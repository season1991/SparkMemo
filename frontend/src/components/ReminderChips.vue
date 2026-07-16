<script setup>
/**
 * 提醒计划可视化组件：将后端返回的 reminders 数组渲染为 el-tag 列表。
 * 「今天」高亮，due_at 高亮（warning 色）。
 */
import { computed } from 'vue'

const props = defineProps({
  reminders: { type: Array, default: () => [] },
  dueAt: { type: String, default: '' }
})

const today = computed(() => {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
})

function chipType(date) {
  if (date === props.dueAt) return 'warning'
  if (date === today.value) return 'success'
  return 'info'
}
</script>

<template>
  <div class="reminder-chips">
    <el-tag
      v-for="item in reminders"
      :key="item.remind_at"
      :type="chipType(item.remind_at)"
      class="reminder-chip"
    >
      {{ item.remind_at }}
    </el-tag>
    <span v-if="reminders.length === 0" class="empty">无提醒计划</span>
  </div>
</template>

<style scoped>
.reminder-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 0;
}
.reminder-chip {
  font-variant-numeric: tabular-nums;
}
.empty {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
</style>