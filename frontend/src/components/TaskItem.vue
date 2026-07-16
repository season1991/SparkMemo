<script setup>
/**
 * 任务行组件：保留供后续行内复用（v0.1 由 TaskList 用 el-table 列模板直接渲染）。
 * Props：task；Emits：edit / complete / delete。
 */
import { computed } from 'vue'

const props = defineProps({
  task: { type: Object, required: true }
})
const emit = defineEmits(['edit', 'complete', 'delete'])

const statusInfo = computed(() => {
  switch (props.task.status) {
    case 'pending':
      return { type: 'warning', label: '待办', editable: true, completable: true }
    case 'completed':
      return { type: 'success', label: '已完成', editable: false, completable: false }
    case 'overdue_done':
      return { type: 'info', label: '逾期自动完成', editable: false, completable: false }
    default:
      return { type: 'info', label: props.task.status, editable: false, completable: false }
  }
})

function onEdit() {
  emit('edit', props.task)
}
function onComplete() {
  emit('complete', props.task)
}
function onDelete() {
  emit('delete', props.task)
}
</script>

<template>
  <div class="task-item">
    <span class="title">{{ task.title }}</span>
    <span class="type" v-if="task.task_type">{{ task.task_type.name }}</span>
    <span class="company">{{ task.company.name }}</span>
    <span class="project">{{ task.project.name }}</span>
    <span class="due">{{ task.due_at }}</span>
    <span class="remind-start">{{ task.remind_start_at }}</span>
    <el-tag :type="statusInfo.type" size="small">{{ statusInfo.label }}</el-tag>
    <span class="actions">
      <el-button size="small" :disabled="!statusInfo.editable" @click="onEdit">编辑</el-button>
      <el-button size="small" type="success" :disabled="!statusInfo.completable" @click="onComplete">
        完成
      </el-button>
      <el-button size="small" type="danger" @click="onDelete">删除</el-button>
    </span>
  </div>
</template>

<style scoped>
.task-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}
.title {
  flex: 1;
  min-width: 0;
}
.type,
.company,
.project {
  color: var(--el-text-color-regular);
  font-size: 13px;
}
.due,
.remind-start {
  font-variant-numeric: tabular-nums;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  min-width: 100px;
}
.actions {
  display: flex;
  gap: 4px;
}
</style>