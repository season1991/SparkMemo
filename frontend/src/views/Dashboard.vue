<script setup>
/**
 * 今日概述主页（路由 /）。
 *
 * 数据来源：GET /api/dashboard/today；详见 OpenAPI DashboardTodayResponse。
 * 刷新策略：onMounted / onActivated（keep-alive 路由回退）/ visibilitychange / 页头按钮。
 * 钻取跳转：summary 数字与公司行数字点击 → router.push('/tasks?...')。
 * 三态：加载中（首屏）/ 失败（无旧数据）/ 失败（有旧数据，toast 不替换）。
 * 空态：summary.total === 0 时展示「✨ 今日无事」+ 「+ 新建任务」按钮。
 *
 * 全局规则遵循 frontend/spec/README.md；本文档聚焦本模块特有的交互与展示。
 */
import { onMounted, onActivated, onBeforeUnmount, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useDashboardStore } from '../stores/useDashboardStore.js'

const router = useRouter()
const store = useDashboardStore()

// 三态派生：首屏加载 / 全失败 / 正常 / 空态
const isFirstLoad = computed(
  () => store.loading && store.companies.length === 0
)
const isFatal = computed(
  () => store.error && store.companies.length === 0
)
const isEmpty = computed(() => store.isEmpty && !isFirstLoad.value && !isFatal.value)

// 千分位显示：>= 1000 用 1,234，否则原样
function nFormatter(n) {
  if (typeof n !== 'number') return '0'
  return n >= 1000 ? n.toLocaleString('en-US') : String(n)
}

// 数字 > 0 视为可点击钻取
function isPositive(n) {
  return typeof n === 'number' && n > 0
}

// 钻取：点击 summary 数字 → /tasks（全局）；点击公司行任意位置 → /tasks?company_id={id}
function goGlobalPending() {
  router.push({ path: '/tasks', query: { status: 'pending' } })
}
function goGlobalToday() {
  router.push({ path: '/tasks', query: { remind_today: 'true' } })
}
function goCompany(companyId) {
  router.push({ path: '/tasks', query: { company_id: companyId } })
}
function onCompanyRowClick(row) {
  goCompany(row.company_id)
}

function goEmptyCreate() {
  router.push({ path: '/tasks' })
}

async function refresh() {
  await store.fetch()
  // 失败时 toast；成功静默
  if (store.error && store.companies.length > 0) {
    ElMessage.warning('刷新失败')
  }
}

function onVisibilityChange() {
  if (!document.hidden) refresh()
}

onMounted(() => {
  store.fetch()
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onActivated(() => {
  // 从 /tasks 路由返回时被命中（keep-alive）
  store.fetch()
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<template>
  <div class="dashboard-view">
    <!-- Sub-header：日期 + 刷新（与 AppHeader 解耦，由 view 自身渲染） -->
    <div class="sub-header">
      <div class="sub-header-left">
        <span class="dashboard-today-label">服务端日期</span>
        <span class="dashboard-today">{{ store.today || '—' }}</span>
      </div>
      <el-button :loading="store.loading" plain @click="refresh">刷新</el-button>
    </div>

    <!-- 首屏加载 -->
    <div v-if="isFirstLoad" class="dashboard-skeleton">
      <el-skeleton :rows="4" animated />
    </div>

    <!-- 全失败且无旧数据 -->
    <el-card v-else-if="isFatal" shadow="never" class="error-card">
      <div class="error-content">
        <p class="error-title">加载失败</p>
        <p class="error-msg">{{ store.error }}</p>
        <el-button type="primary" @click="refresh">重试</el-button>
      </div>
    </el-card>

    <!-- 空态：summary.total === 0 -->
    <el-card v-else-if="isEmpty" shadow="never" class="empty-card">
      <div class="empty-content">
        <div class="empty-icon">✨</div>
        <p class="empty-title">今日无事</p>
        <p class="empty-sub">当前没有需要处理的任务提醒。</p>
        <el-button type="primary" @click="goEmptyCreate">+ 新建任务</el-button>
      </div>
    </el-card>

    <!-- 正常 -->
    <template v-else>
      <!-- Summary 4 卡片 -->
      <el-row :gutter="16" class="summary-row">
        <el-col :span="6">
          <div class="metric-card">
            <div class="metric-value">{{ nFormatter(store.summary.urgent) }}</div>
            <div class="metric-label">紧急</div>
            <el-link
              v-if="isPositive(store.summary.urgent)"
              type="primary"
              :underline="false"
              @click="goGlobalPending"
            >查看</el-link>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-card">
            <div class="metric-value">{{ nFormatter(store.summary.due_soon) }}</div>
            <div class="metric-label">临期</div>
            <el-link
              v-if="isPositive(store.summary.due_soon)"
              type="primary"
              :underline="false"
              @click="goGlobalPending"
            >查看</el-link>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-card">
            <div class="metric-value">{{ nFormatter(store.summary.early) }}</div>
            <div class="metric-label">尚早</div>
            <el-link
              v-if="isPositive(store.summary.early)"
              type="primary"
              :underline="false"
              @click="goGlobalPending"
            >查看</el-link>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="metric-card">
            <div class="metric-value">{{ nFormatter(store.summary.total) }}</div>
            <div class="metric-label">合计</div>
            <el-link
              v-if="isPositive(store.summary.total)"
              type="primary"
              :underline="false"
              @click="goGlobalToday"
            >查看</el-link>
          </div>
        </el-col>
      </el-row>

      <!-- 公司表 -->
      <el-card shadow="never" class="company-card">
        <el-table
          :data="store.companies"
          stripe
          style="width: 100%"
          empty-text="暂无公司"
          class="company-table"
          row-class-name="company-row"
          @row-click="onCompanyRowClick"
        >
          <el-table-column label="公司" min-width="180">
            <template #default="{ row }">
              <span class="company-name">{{ row.company_name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="紧急" width="120" align="center">
            <template #default="{ row }">
              <span
                class="metric-num"
                :class="{ positive: isPositive(row.urgent) }"
              >{{ row.urgent }}</span>
            </template>
          </el-table-column>
          <el-table-column label="临期" width="120" align="center">
            <template #default="{ row }">
              <span
                class="metric-num"
                :class="{ positive: isPositive(row.due_soon) }"
              >{{ row.due_soon }}</span>
            </template>
          </el-table-column>
          <el-table-column label="尚早" width="120" align="center">
            <template #default="{ row }">
              <span
                class="metric-num"
                :class="{ positive: isPositive(row.early) }"
              >{{ row.early }}</span>
            </template>
          </el-table-column>
          <el-table-column label="合计" width="120" align="center">
            <template #default="{ row }">
              <span
                class="metric-num"
                :class="{ positive: isPositive(row.total) }"
              >{{ row.total }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.dashboard-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Sub-header：日期 + 刷新按钮 */
.sub-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 12px 16px;
}
.sub-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dashboard-today-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.dashboard-today {
  font-variant-numeric: tabular-nums;
  color: #303133;
  font-size: 14px;
  font-weight: 500;
}

/* 加载骨架 */
.dashboard-skeleton {
  background: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 32px 24px;
}

/* summary 行间距 */
.summary-row {
  margin-bottom: 0;
}

/* metric 卡片 */
.metric-card {
  background: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 20px 16px;
  text-align: center;
  height: 120px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 6px;
  transition: border-color 0.15s ease;
}
.metric-card:hover {
  border-color: var(--el-color-primary-light-5);
}
.metric-card :deep(.el-link) {
  font-size: 12px;
}
.metric-value {
  font-size: 28px;
  font-weight: 600;
  color: #303133;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}
.metric-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1;
}

/* 公司表卡片 */
.company-card :deep(.el-card__body) {
  padding: 16px;
}

/* 公司表：整行可点击 */
.company-table {
  width: 100%;
}
/* 行：cursor pointer + hover 高亮 */
.company-table :deep(tr.company-row) {
  cursor: pointer;
}
.company-table :deep(tr.company-row:hover > td) {
  background-color: var(--el-fill-color-light) !important;
}
/* 公司名：主色文本（视觉强调，不响应点击，row-click 接管） */
.company-name {
  color: var(--el-color-primary);
  font-weight: 500;
}
/* 数字 cell：> 0 主色，= 0 灰色 */
.metric-num {
  display: inline-block;
  min-width: 24px;
  font-variant-numeric: tabular-nums;
  color: var(--el-text-color-placeholder);
}
.metric-num.positive {
  color: var(--el-color-primary);
  font-weight: 500;
}

/* 错误 / 空态卡片 */
.error-card,
.empty-card {
  max-width: 720px;
  margin: 32px auto;
}
.error-content,
.empty-content {
  padding: 48px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
.error-title,
.empty-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
.error-msg {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.empty-icon {
  font-size: 32px;
  line-height: 1;
}
.empty-sub {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
