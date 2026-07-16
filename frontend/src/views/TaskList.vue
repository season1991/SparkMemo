<script setup>
/**
 * 任务列表视图：操作条 + 筛选条 + 任务表 + 分页器。
 * 浮层：TaskForm（新建 / 编辑）、TypeManager（任务类型管理）。
 * 行为完全遵循 spec/task_management.md §2 功能点。
 *
 * 路由 / 筛选双向联动：
 *   - 路由变化 → watch(route.path) 同步 filters.remind_today + 加载
 *   - 筛选条「今日开关」变化 → onRemindTodayChange：与当前路由不一致时 router.push
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTaskStore } from '../stores/useTaskStore.js'
import { useTypeStore } from '../stores/useTypeStore.js'
import { useCompanyStore } from '../stores/useCompanyStore.js'
import { useProjectStore } from '../stores/useProjectStore.js'
import { ApiError, showApiError } from '../api/client.js'
import TaskForm from '../components/TaskForm.vue'
import TypeManager from '../components/TypeManager.vue'

const route = useRoute()
const router = useRouter()
const taskStore = useTaskStore()
const typeStore = useTypeStore()
const companyStore = useCompanyStore()
const projectStore = useProjectStore()

const formVisible = ref(false)
const formMode = ref('create')
const editingTask = ref(null)
const typeDialogVisible = ref(false)
const loadFailed = ref(false)

let keywordTimer = null
const keywordInput = ref('')

const remindToday = computed(() => Boolean(route.meta?.remindToday))

const availableProjects = computed(() => {
  if (!taskStore.filters.company_id) return []
  return projectStore.byCompany[taskStore.filters.company_id] || []
})

watch(
  () => route.path,
  async () => {
    const next = remindToday.value
    if (taskStore.filters.remind_today !== next) {
      taskStore.syncRemindTodayFromRoute(next)
    }
    await loadWithCatch()
  }
)

onMounted(async () => {
  if (taskStore.filters.remind_today !== remindToday.value) {
    taskStore.syncRemindTodayFromRoute(remindToday.value)
  }
  keywordInput.value = taskStore.filters.keyword || ''
  await loadWithCatch()
})

async function loadWithCatch() {
  loadFailed.value = false
  try {
    await taskStore.fetchList()
  } catch (err) {
    loadFailed.value = true
    showApiError(err)
  }
}

function onKeywordInput(val) {
  if (keywordTimer) clearTimeout(keywordTimer)
  keywordTimer = setTimeout(() => {
    taskStore.setFilter('keyword', val || '')
  }, 300)
}

function onCompanyFilterChange(val) {
  taskStore.filters.project_id = null
  taskStore.setFilter('company_id', val || null)
}

function onRemindTodayChange(val) {
  const wantToday = Boolean(val)
  if (remindToday.value !== wantToday) {
    router.push(wantToday ? '/tasks/today' : '/')
    return
  }
  taskStore.toggleRemindToday(wantToday)
}

async function onPageChange(page) {
  taskStore.filters.page = page
  await loadWithCatch()
}

async function onSizeChange(size) {
  taskStore.filters.size = size
  taskStore.filters.page = 1
  await loadWithCatch()
}

function statusTagType(status) {
  if (status === 'pending') return 'warning'
  if (status === 'completed') return 'success'
  if (status === 'overdue_done') return 'info'
  return 'info'
}

function statusLabel(status) {
  if (status === 'pending') return '待办'
  if (status === 'completed') return '已完成'
  if (status === 'overdue_done') return '逾期自动完成'
  return status
}

function openCreate() {
  formMode.value = 'create'
  editingTask.value = null
  formVisible.value = true
}

async function openEdit(task) {
  formMode.value = 'edit'
  editingTask.value = null
  formVisible.value = true
  try {
    editingTask.value = await taskStore.fetchOne(task.id)
  } catch (err) {
    showApiError(err)
    formVisible.value = false
  }
}

async function handleComplete(task) {
  try {
    await taskStore.markComplete(task.id)
    ElMessage.success('已完成')
  } catch (err) {
    if (err instanceof ApiError && err.status === 422) {
      ElMessage.error('当前状态不允许此操作')
    } else {
      showApiError(err)
    }
  }
}

async function handleDelete(task) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${task.title}」？删除后不可恢复。`,
      '提示',
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await taskStore.remove(task.id)
    ElMessage.success('删除成功')
  } catch (err) {
    showApiError(err)
  }
}

function resetAll() {
  keywordInput.value = ''
  taskStore.resetFilters()
}

async function onFormSaved() {
  await loadWithCatch()
}

function openTypeManager() {
  typeDialogVisible.value = true
}

async function retryLoad() {
  await loadWithCatch()
}

function onRemoveFilter(key) {
  if (key === 'remind_today' && remindToday.value) {
    router.push('/')
    return
  }
  taskStore.removeFilter(key)
}
</script>

<template>
  <div class="task-list-view">
    <!-- 操作条 -->
    <div class="action-bar">
      <div class="action-left">
        <el-button @click="openTypeManager">管理类型</el-button>
      </div>
      <div class="action-right">
        <el-button type="primary" @click="openCreate">+ 新建任务</el-button>
      </div>
    </div>

    <!-- 筛选条 -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <el-select
          :model-value="taskStore.filters.company_id"
          placeholder="公司"
          clearable
          style="width: 160px"
          @update:model-value="onCompanyFilterChange"
        >
          <el-option
            v-for="c in companyStore.companies"
            :key="c.id"
            :label="c.name"
            :value="c.id"
          />
        </el-select>

        <el-select
          :model-value="taskStore.filters.project_id"
          placeholder="项目"
          clearable
          :disabled="!taskStore.filters.company_id"
          style="width: 160px"
          @update:model-value="(v) => taskStore.setFilter('project_id', v || null)"
        >
          <el-option
            v-for="p in availableProjects"
            :key="p.id"
            :label="p.name"
            :value="p.id"
          />
        </el-select>

        <el-select
          :model-value="taskStore.filters.task_type_id"
          placeholder="类型"
          clearable
          style="width: 140px"
          @update:model-value="(v) => taskStore.setFilter('task_type_id', v || null)"
        >
          <el-option
            v-for="t in typeStore.types"
            :key="t.id"
            :label="t.name"
            :value="t.id"
          />
        </el-select>

        <el-select
          :model-value="taskStore.filters.status"
          placeholder="状态"
          clearable
          :disabled="remindToday"
          style="width: 120px"
          @update:model-value="(v) => taskStore.setFilter('status', v || '')"
        >
          <el-option label="待办" value="pending" />
          <el-option label="已完成" value="completed" />
          <el-option label="逾期自动完成" value="overdue_done" />
        </el-select>

        <el-input
          v-model="keywordInput"
          placeholder="搜索标题 / 描述"
          clearable
          style="width: 200px"
          @input="onKeywordInput"
        />

        <el-switch
          :model-value="remindToday"
          @update:model-value="onRemindTodayChange"
          active-text="今日待提醒"
        />

        <el-button @click="resetAll">重置</el-button>
      </div>

      <!-- 已生效筛选条件 tag -->
      <div v-if="taskStore.activeFilterTags.length > 0" class="active-tags">
        <el-tag
          v-for="tag in taskStore.activeFilterTags"
          :key="tag.key"
          closable
          type="info"
          @close="onRemoveFilter(tag.key)"
        >
          {{ tag.label }}
        </el-tag>
      </div>
    </el-card>

    <!-- 列表区 -->
    <el-card shadow="never" class="list-card">
      <el-table
        :data="taskStore.tasks"
        v-loading="taskStore.loading"
        empty-text="暂无数据"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="title" label="标题" min-width="180">
          <template #default="{ row }">
            <span class="title-cell">{{ row.title }}</span>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <span v-if="row.task_type">{{ row.task_type.name }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="公司" width="140">
          <template #default="{ row }">{{ row.company.name }}</template>
        </el-table-column>
        <el-table-column label="项目" width="140">
          <template #default="{ row }">{{ row.project.name }}</template>
        </el-table-column>
        <el-table-column label="截止日" width="120">
          <template #default="{ row }">{{ row.due_at }}</template>
        </el-table-column>
        <el-table-column label="提醒起" width="120">
          <template #default="{ row }">{{ row.remind_start_at }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              :disabled="row.status !== 'pending'"
              @click="openEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              size="small"
              type="success"
              :disabled="row.status !== 'pending'"
              @click="handleComplete(row)"
            >
              完成
            </el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">
              删除
            </el-button>
          </template>
        </el-table-column>

        <template #empty>
          <div v-if="loadFailed" class="empty-state">
            <p>加载失败</p>
            <el-button type="primary" @click="retryLoad">点此重试</el-button>
          </div>
          <div v-else-if="taskStore.hasActiveFilter" class="empty-state">
            <p>无匹配任务，建议调整筛选条件</p>
            <el-button @click="resetAll">重置筛选</el-button>
          </div>
          <div v-else class="empty-state">
            <p>暂无任务</p>
            <el-button type="primary" @click="openCreate">+ 新建任务</el-button>
          </div>
        </template>
      </el-table>

      <!-- 分页器 -->
      <div class="pagination-wrap">
        <el-pagination
          :current-page="taskStore.filters.page"
          :page-size="taskStore.filters.size"
          :page-sizes="[10, 20, 50]"
          :total="taskStore.total"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @current-change="onPageChange"
          @size-change="onSizeChange"
        />
      </div>
    </el-card>

    <!-- 浮层 -->
    <TaskForm
      v-model="formVisible"
      :mode="formMode"
      :task="editingTask"
      @saved="onFormSaved"
    />
    <TypeManager v-model="typeDialogVisible" />
  </div>
</template>

<style scoped>
.task-list-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.action-left,
.action-right {
  display: flex;
  gap: 12px;
}
.filter-card :deep(.el-card__body) {
  padding: 16px;
}
.filter-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.active-tags {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.list-card :deep(.el-card__body) {
  padding: 16px;
}
.title-cell {
  font-weight: 500;
}
.muted {
  color: var(--el-text-color-placeholder);
}
.empty-state {
  padding: 24px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: var(--el-text-color-secondary);
}
.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>