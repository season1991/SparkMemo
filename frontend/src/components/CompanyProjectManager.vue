<script setup>
/**
 * 公司/项目管理组件：弹窗承载，提供公司/项目的新建、编辑、删除。
 * 包含两个 Tab：公司和项目。
 */
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useCompanyStore } from '../stores/useCompanyStore.js'
import { useProjectStore } from '../stores/useProjectStore.js'
import { showApiError, ApiError } from '../api/client.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue', 'companies-changed', 'projects-changed'])

const companyStore = useCompanyStore()
const projectStore = useProjectStore()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const activeTab = ref('company')

// 公司相关状态
const newCompany = ref({ name: '', notes: '' })
const newCompanyErrors = ref({ name: '', notes: '' })
const editingCompanyId = ref(null)
const editingCompany = ref({ name: '', notes: '' })
const editingCompanyErrors = ref({ name: '', notes: '' })
const companySubmitting = ref(false)

// 项目相关状态
const companyFilter = ref(null)
const newProject = ref({ name: '', company_id: null, notes: '' })
const newProjectErrors = ref({ name: '', company_id: '', notes: '' })
const editingProjectId = ref(null)
const editingProject = ref({ name: '', company_id: null, notes: '' })
const editingProjectErrors = ref({ name: '', company_id: '', notes: '' })
const projectSubmitting = ref(false)

// 监听公司筛选变化，自动设置新建项目的默认公司
watch(companyFilter, (val) => {
  newProject.value.company_id = val || null
})

// 计算属性：过滤后的项目列表
const filteredProjects = computed(() => {
  let projects = projectStore.projects
  if (companyFilter.value) {
    projects = projects.filter(p => p.company_id === companyFilter.value)
  }
  // 过滤孤儿项目（company_id 不存在于公司列表中）
  const companyIds = new Set(companyStore.companies.map(c => c.id))
  return projects.filter(p => companyIds.has(p.company_id))
})

// 打开对话框时加载数据
watch(visible, async (v) => {
  if (v) {
    try {
      await Promise.all([
        companyStore.fetchAll(),
        projectStore.fetchAll()
      ])
    } catch (err) {
      showApiError(err)
      visible.value = false
    }
  }
})

onMounted(() => {
  if (visible.value) {
    loadData()
  }
})

async function loadData() {
  try {
    await Promise.all([
      companyStore.fetchAll(),
      projectStore.fetchAll()
    ])
  } catch (err) {
    showApiError(err)
    visible.value = false
  }
}

// 公司相关操作
async function handleCreateCompany() {
  const name = newCompany.value.name.trim()
  if (!name) {
    ElMessage.warning('请输入公司名称')
    return
  }
  // 清除之前的错误
  newCompanyErrors.value = { name: '', notes: '' }
  companySubmitting.value = true
  try {
    await companyStore.create({
      name,
      notes: newCompany.value.notes.trim() || undefined
    })
    newCompany.value = { name: '', notes: '' }
    ElMessage.success('创建成功')
    emit('companies-changed')
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.status === 422 && Array.isArray(err.detail)) {
        // 字段级错误
        for (const d of err.detail) {
          const field = d.loc && d.loc[d.loc.length - 1]
          if (field && field in newCompanyErrors.value) {
            newCompanyErrors.value[field] = d.msg
          }
        }
      } else if (err.status === 409) {
        // 重名错误
        newCompanyErrors.value.name = err.message
      } else {
        showApiError(err)
      }
    } else {
      showApiError(err)
    }
  } finally {
    companySubmitting.value = false
  }
}

function startEditCompany(row) {
  editingCompanyId.value = row.id
  editingCompany.value = { name: row.name, notes: row.notes || '' }
}

function cancelEditCompany() {
  editingCompanyId.value = null
  editingCompany.value = { name: '', notes: '' }
}

async function saveEditCompany(row) {
  const name = editingCompany.value.name.trim()
  if (!name) {
    ElMessage.warning('公司名称不能为空')
    return
  }
  // 清除之前的错误
  editingCompanyErrors.value = { name: '', notes: '' }
  companySubmitting.value = true
  try {
    await companyStore.update(row.id, {
      name,
      notes: editingCompany.value.notes.trim() || undefined
    })
    editingCompanyId.value = null
    editingCompany.value = { name: '', notes: '' }
    ElMessage.success('更新成功')
    emit('companies-changed')
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.status === 422 && Array.isArray(err.detail)) {
        // 字段级错误
        for (const d of err.detail) {
          const field = d.loc && d.loc[d.loc.length - 1]
          if (field && field in editingCompanyErrors.value) {
            editingCompanyErrors.value[field] = d.msg
          }
        }
      } else if (err.status === 409) {
        // 重名错误
        editingCompanyErrors.value.name = err.message
      } else {
        showApiError(err)
      }
    } else {
      showApiError(err)
    }
  } finally {
    companySubmitting.value = false
  }
}

async function handleDeleteCompany(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${row.name}」？若已被项目或任务引用将无法删除。`,
      '提示',
      { type: 'warning' }
    )
  } catch {
    return
  }
  companySubmitting.value = true
  try {
    await companyStore.remove(row.id)
    ElMessage.success('删除成功')
    emit('companies-changed')
  } catch (err) {
    if (err instanceof ApiError && err.status === 409) {
      ElMessageBox.alert(err.message, '无法删除', { type: 'warning' })
    } else {
      showApiError(err)
    }
  } finally {
    companySubmitting.value = false
  }
}

// 项目相关操作
async function handleCreateProject() {
  const name = newProject.value.name.trim()
  const companyId = newProject.value.company_id || companyFilter.value
  if (!name) {
    ElMessage.warning('请输入项目名称')
    return
  }
  if (!companyId) {
    ElMessage.warning('请选择所属公司')
    return
  }
  // 清除之前的错误
  newProjectErrors.value = { name: '', company_id: '', notes: '' }
  projectSubmitting.value = true
  try {
    await projectStore.create({
      name,
      company_id: companyId,
      notes: newProject.value.notes.trim() || undefined
    })
    newProject.value = { name: '', company_id: null, notes: '' }
    ElMessage.success('创建成功')
    emit('projects-changed')
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.status === 422 && Array.isArray(err.detail)) {
        // 字段级错误
        for (const d of err.detail) {
          const field = d.loc && d.loc[d.loc.length - 1]
          if (field && field in newProjectErrors.value) {
            newProjectErrors.value[field] = d.msg
          }
        }
      } else if (err.status === 409) {
        // 重名错误
        newProjectErrors.value.name = err.message
      } else {
        showApiError(err)
      }
    } else {
      showApiError(err)
    }
  } finally {
    projectSubmitting.value = false
  }
}

function startEditProject(row) {
  editingProjectId.value = row.id
  editingProject.value = {
    name: row.name,
    company_id: row.company_id,
    notes: row.notes || ''
  }
}

function cancelEditProject() {
  editingProjectId.value = null
  editingProject.value = { name: '', company_id: null, notes: '' }
}

async function saveEditProject(row) {
  const name = editingProject.value.name.trim()
  if (!name) {
    ElMessage.warning('项目名称不能为空')
    return
  }
  if (!editingProject.value.company_id) {
    ElMessage.warning('请选择所属公司')
    return
  }
  // 清除之前的错误
  editingProjectErrors.value = { name: '', company_id: '', notes: '' }
  projectSubmitting.value = true
  try {
    const oldCompanyId = row.company_id
    const newCompanyId = editingProject.value.company_id
    await projectStore.update(row.id, {
      name,
      company_id: newCompanyId,
      notes: editingProject.value.notes.trim() || undefined
    })
    // 如果 company_id 发生变化，可能需要加载新公司的项目
    if (oldCompanyId !== newCompanyId) {
      // 检查新公司的项目是否已加载
      if (!projectStore.byCompany[newCompanyId]) {
        await projectStore.fetchByCompany(newCompanyId)
      }
    }
    editingProjectId.value = null
    editingProject.value = { name: '', company_id: null, notes: '' }
    ElMessage.success('更新成功')
    emit('projects-changed')
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.status === 422 && Array.isArray(err.detail)) {
        // 字段级错误
        for (const d of err.detail) {
          const field = d.loc && d.loc[d.loc.length - 1]
          if (field && field in editingProjectErrors.value) {
            editingProjectErrors.value[field] = d.msg
          }
        }
      } else if (err.status === 409) {
        // 重名错误
        editingProjectErrors.value.name = err.message
      } else {
        showApiError(err)
      }
    } else {
      showApiError(err)
    }
  } finally {
    projectSubmitting.value = false
  }
}

async function handleDeleteProject(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除「${row.name}」？若已被任务引用将无法删除。`,
      '提示',
      { type: 'warning' }
    )
  } catch {
    return
  }
  projectSubmitting.value = true
  try {
    await projectStore.remove(row.id)
    ElMessage.success('删除成功')
    emit('projects-changed')
  } catch (err) {
    if (err instanceof ApiError && err.status === 409) {
      ElMessageBox.alert(err.message, '无法删除', { type: 'warning' })
    } else {
      showApiError(err)
    }
  } finally {
    projectSubmitting.value = false
  }
}

function getCompanyName(companyId) {
  const company = companyStore.companies.find(c => c.id === companyId)
  return company ? company.name : '未知公司'
}

function handleClose() {
  visible.value = false
}
</script>

<template>
  <el-dialog
    v-model="visible"
    title="公司 / 项目管理"
    width="800px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <el-tabs v-model="activeTab">
      <!-- 公司 Tab -->
      <el-tab-pane label="公司" name="company">
        <div class="create-bar">
          <div class="input-with-error">
            <el-input
              v-model="newCompany.name"
              placeholder="公司名称"
              maxlength="128"
              clearable
              style="width: 200px"
              @keyup.enter="handleCreateCompany"
            />
            <div v-if="newCompanyErrors.name" class="field-error">{{ newCompanyErrors.name }}</div>
          </div>
          <div class="input-with-error">
            <el-input
              v-model="newCompany.notes"
              placeholder="备注"
              maxlength="4000"
              clearable
              style="width: 300px"
            />
            <div v-if="newCompanyErrors.notes" class="field-error">{{ newCompanyErrors.notes }}</div>
          </div>
          <el-button type="primary" :loading="companySubmitting" @click="handleCreateCompany">
            + 新建
          </el-button>
        </div>

        <el-table :data="companyStore.companies" v-loading="companyStore.loading" empty-text="暂无数据">
          <el-table-column label="名称" min-width="150">
            <template #default="{ row }">
              <div v-if="editingCompanyId === row.id" class="input-with-error">
                <el-input
                  v-model="editingCompany.name"
                  maxlength="128"
                  size="small"
                />
                <div v-if="editingCompanyErrors.name" class="field-error">{{ editingCompanyErrors.name }}</div>
              </div>
              <span v-else>{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="200">
            <template #default="{ row }">
              <div v-if="editingCompanyId === row.id" class="input-with-error">
                <el-input
                  v-model="editingCompany.notes"
                  maxlength="4000"
                  size="small"
                />
                <div v-if="editingCompanyErrors.notes" class="field-error">{{ editingCompanyErrors.notes }}</div>
              </div>
              <span v-else>{{ row.notes || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="创建日" width="120">
            <template #default="{ row }">{{ row.created_at }}</template>
          </el-table-column>
          <el-table-column label="操作" width="180">
            <template #default="{ row }">
              <template v-if="editingCompanyId === row.id">
                <el-button size="small" type="primary" :loading="companySubmitting" @click="saveEditCompany(row)">
                  保存
                </el-button>
                <el-button size="small" @click="cancelEditCompany">取消</el-button>
              </template>
              <template v-else>
                <el-button size="small" @click="startEditCompany(row)">编辑</el-button>
                <el-button size="small" type="danger" @click="handleDeleteCompany(row)">删除</el-button>
              </template>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 项目 Tab -->
      <el-tab-pane label="项目" name="project">
        <div class="filter-bar">
          <el-select
            v-model="companyFilter"
            placeholder="按公司筛选"
            clearable
            style="width: 200px"
          >
            <el-option
              v-for="c in companyStore.companies"
              :key="c.id"
              :label="c.name"
              :value="c.id"
            />
          </el-select>
        </div>

        <div class="create-bar">
          <div class="input-with-error">
            <el-input
              v-model="newProject.name"
              placeholder="项目名称"
              maxlength="128"
              clearable
              style="width: 200px"
              @keyup.enter="handleCreateProject"
            />
            <div v-if="newProjectErrors.name" class="field-error">{{ newProjectErrors.name }}</div>
          </div>
          <div class="input-with-error">
            <el-input
              v-model="newProject.notes"
              placeholder="备注"
              maxlength="4000"
              clearable
              style="width: 300px"
            />
            <div v-if="newProjectErrors.notes" class="field-error">{{ newProjectErrors.notes }}</div>
          </div>
          <el-button
            type="primary"
            :loading="projectSubmitting"
            :disabled="!companyFilter"
            @click="handleCreateProject"
          >
            + 新建
          </el-button>
        </div>

        <el-table :data="filteredProjects" v-loading="projectStore.loading" empty-text="暂无数据">
          <el-table-column label="名称" min-width="150">
            <template #default="{ row }">
              <div v-if="editingProjectId === row.id" class="input-with-error">
                <el-input
                  v-model="editingProject.name"
                  maxlength="128"
                  size="small"
                />
                <div v-if="editingProjectErrors.name" class="field-error">{{ editingProjectErrors.name }}</div>
              </div>
              <span v-else>{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="所属公司" width="150">
            <template #default="{ row }">
              <div v-if="editingProjectId === row.id" class="input-with-error">
                <el-select
                  v-model="editingProject.company_id"
                  size="small"
                  style="width: 100%"
                >
                  <el-option
                    v-for="c in companyStore.companies"
                    :key="c.id"
                    :label="c.name"
                    :value="c.id"
                  />
                </el-select>
                <div v-if="editingProjectErrors.company_id" class="field-error">{{ editingProjectErrors.company_id }}</div>
              </div>
              <span v-else>{{ getCompanyName(row.company_id) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="200">
            <template #default="{ row }">
              <div v-if="editingProjectId === row.id" class="input-with-error">
                <el-input
                  v-model="editingProject.notes"
                  maxlength="4000"
                  size="small"
                />
                <div v-if="editingProjectErrors.notes" class="field-error">{{ editingProjectErrors.notes }}</div>
              </div>
              <span v-else>{{ row.notes || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="创建日" width="120">
            <template #default="{ row }">{{ row.created_at }}</template>
          </el-table-column>
          <el-table-column label="操作" width="180">
            <template #default="{ row }">
              <template v-if="editingProjectId === row.id">
                <el-button size="small" type="primary" :loading="projectSubmitting" @click="saveEditProject(row)">
                  保存
                </el-button>
                <el-button size="small" @click="cancelEditProject">取消</el-button>
              </template>
              <template v-else>
                <el-button size="small" @click="startEditProject(row)">编辑</el-button>
                <el-button size="small" type="danger" @click="handleDeleteProject(row)">删除</el-button>
              </template>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

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

.filter-bar {
  margin-bottom: 16px;
}

.input-with-error {
  display: flex;
  flex-direction: column;
}

.field-error {
  color: var(--el-color-danger);
  font-size: 12px;
  margin-top: 4px;
  line-height: 1.2;
}
</style>