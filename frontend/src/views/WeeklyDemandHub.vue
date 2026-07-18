<script setup>
/**
 * 周需求管理 Hub 页（路由 /dsp-uploads，v0.5.4）。
 *
 * 3 张功能卡片导航到 3 个子功能页面：
 * - DSP 上传：/dsp-uploads/upload
 * - 查询：/dsp-uploads/query
 * - 删除：/dsp-uploads/delete
 *
 * 全局规则遵循 frontend/spec/README.md（220 导航 + 56 页面页头 + 1440 主内容区 + 720 子卡片宽度）。
 */
import { useRouter } from 'vue-router'
import { Upload, Search, Delete } from '@element-plus/icons-vue'

const router = useRouter()

const cards = [
  {
    key: 'upload',
    title: 'DSP 上传',
    desc: '上传 DSP 周预测 Excel 文件并入库。文件名自动解析 → 表头识别字段（v0.5.3）→ 数据展开后写入 dsp_uploads / dsp_upload_rows。',
    icon: Upload,
    to: '/dsp-uploads/upload'
  },
  {
    key: 'query',
    title: '查询',
    desc: '按 (供应商 / 业务项 / 子业务项 / 版本日期) 精确查找已入库批次；命中后展示元数据与前 50 条事实行预览。',
    icon: Search,
    to: '/dsp-uploads/query'
  },
  {
    key: 'delete',
    title: '删除',
    desc: '按 4 字段定位批次 → 预览元数据与「即将删除 N 行」警告 → 二次确认 → 整批 DELETE（CASCADE 清事实行）。',
    icon: Delete,
    to: '/dsp-uploads/delete'
  }
]

function go(to) {
  router.push(to)
}
</script>

<template>
  <div class="hub">
    <h2 class="page-title">周需求管理</h2>
    <p class="page-hint">
      管理 DSP 周预测数据的 3 个子功能。请选择要进入的功能。
    </p>

    <div class="card-grid">
      <el-card
        v-for="card in cards"
        :key="card.key"
        shadow="hover"
        class="function-card"
        @click="go(card.to)"
      >
        <div class="card-inner">
          <el-icon class="card-icon" :size="36" color="#409EFF">
            <component :is="card.icon" />
          </el-icon>
          <h3 class="card-title">{{ card.title }}</h3>
          <p class="card-desc">{{ card.desc }}</p>
          <span class="card-cta">进入 →</span>
        </div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.hub {
  max-width: 1080px;
  margin: 0 auto;
}
.page-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 4px;
}
.page-hint {
  font-size: 13px;
  color: #909399;
  margin: 0 0 20px;
  line-height: 1.5;
}
.card-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}
@media (max-width: 1024px) {
  .card-grid {
    grid-template-columns: 1fr;
  }
}
.function-card {
  cursor: pointer;
  border-radius: 6px;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.function-card:hover {
  transform: translateY(-2px);
}
.card-inner {
  padding: 16px 8px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
}
.card-icon {
  flex-shrink: 0;
}
.card-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}
.card-desc {
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
  margin: 0;
}
.card-cta {
  font-size: 13px;
  color: #409eff;
  font-weight: 500;
  margin-top: auto;
  padding-top: 4px;
}
</style>
