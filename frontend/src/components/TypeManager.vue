<script setup>
/**
 * 任务类型管理组件：弹窗承载，提供新建 / 编辑 / 删除。
 * 实际行展示由 el-table 完成；保留本组件供后续作为行内编辑器复用。
 */
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTypeStore } from '../stores/useTypeStore.js'
import { showApiError } from '../api/client.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue', 'changed'])

const typeStore = useTypeStore()
const newName = ref('')
const editingId = ref(null)
const editingName = ref('')
const submitting = ref(false)

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

async function refresh() {
  await typeStore.fetchAll()
}

watch(visible, async (v) => {
  if (v) {
    try {
      await refresh()
    } catch (err) {
      showApiError(err)
    }
  }
})

onMounted(() => {
  if (visible.value) refresh()
})

function statusType(type) {
  return 'warning'
}

async function handleCreate() {
  const name = newName.value.trim()
  if (!name) {
    ElMessage.warning('请输入类型名称')
    return
  }
  submitting.value = true
  try {
    await typeStore.create({ name })
    newName.value = ''
    ElMessage.success('创建成功')
    emit('changed')
  } catch (err) {
    showApiError(err)
  } finally {
    submitting.value = false
  }
}

function startEdit(row) {
  editingId.value = row.id
  editingName.value = row.name
}

function cancelEdit() {
  editingId.value = null
  editingName.value = ''
}

async function saveEdit(row) {
  const name = editingName.value.trim()
  if (!name) {
    ElMessage.warning('名称不能为空')
    return
  }
  submitting.value = true
  try {
    await typeStore.update(row.id, { name })
    editingId.value = null
    editingName.value = ''
    ElMessage.success('更新成功')
    emit('changed')
  } catch (err) {
    showApiError(err)
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除任务类型「${row.name}」？`, '提示', {
      type: 'warning'
    })
  } catch {
    return
  }
  submitting.value = true
  try {
    await typeStore.remove(row.id)
    ElMessage.success('删除成功')
    emit('changed')
  } catch (err) {
    showApiError(err)
  } finally {
    submitting.value = false
  }
}

function handleClose() {
  visible.value = false
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="任务类型管理"
    width="800px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <!-- 顶部新建区 -->
    <div class="create-bar">
      <el-input
        v-model="newName"
        placeholder="输入新类型名称"
        maxlength="64"
        clearable
        style="width: 320px"
        @keyup.enter="handleCreate"
      />
      <el-button type="primary" :loading="submitting" @click="handleCreate">
        + 新建
      </el-button>
    </div>

    <!-- 列表区 -->
    <el-table :data="typeStore.types" v-loading="typeStore.loading" empty-text="暂无任务类型">
      <el-table-column type="index" label="#" width="60" />
      <el-table-column label="名称">
        <template #default="{ row }">
          <el-input
            v-if="editingId === row.id"
            v-model="editingName"
            maxlength="64"
            size="small"
          />
          <span v-else>{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default>
          <el-tag :type="statusType()" size="small">可用</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220">
        <template #default="{ row }">
          <template v-if="editingId === row.id">
            <el-button size="small" type="primary" :loading="submitting" @click="saveEdit(row)">
              保存
            </el-button>
            <el-button size="small" @click="cancelEdit">取消</el-button>
          </template>
          <template v-else>
            <el-button size="small" @click="startEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <template #footer>
      <el-button @click="handleClose">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.create-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
</style>