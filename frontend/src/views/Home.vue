<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { usePaperStore } from '@/stores'

const router = useRouter()
const paperStore = usePaperStore()

const stats = ref({
  paperCount: 0,
  processingCount: 0,
})

const displayStats = ref({
  paperCount: 0,
  processingCount: 0,
})

const loading = ref(true)

const quickActions = [
  { icon: 'Upload', title: '上传论文', path: '/pdf', color: 'var(--color-primary)' },
  { icon: 'Aim', title: 'NER处理', path: '/ner', color: 'var(--color-success)' },
  { icon: 'Connection', title: '关系抽取', path: '/re', color: 'var(--color-warning)' },
  { icon: 'Files', title: 'PDF批量', path: '/pdf-batch', color: 'var(--color-danger)' },
  { icon: 'DataAnalysis', title: '领域分析', path: '/domain', color: 'var(--color-info)' }
]

onMounted(async () => {
  try {
    const paperList = await paperStore.fetchPapers({ page: 1, page_size: 100 })
    stats.value.paperCount = paperList.total
    stats.value.processingCount = paperList.items.filter(p => p.status === 'processing').length
    animateNumbers()
  } catch (error) {
    console.error('加载统计数据失败:', error)
  } finally {
    loading.value = false
  }
})

/** 数字递增动画 */
function animateNumbers() {
  const duration = 800
  const startTime = performance.now()
  function update(currentTime: number) {
    const elapsed = currentTime - startTime
    const progress = Math.min(elapsed / duration, 1)
    displayStats.value.paperCount = Math.round(stats.value.paperCount * progress)
    displayStats.value.processingCount = Math.round(stats.value.processingCount * progress)
    if (progress < 1) requestAnimationFrame(update)
  }
  requestAnimationFrame(update)
}

function navigateTo(path: string) {
  router.push(path)
}

function handleView(row: any) {
  router.push(`/pdf`)
}
</script>

<template>
  <div class="page-container home-container">
    <div class="welcome-section">
      <h1>欢迎使用 SciPDF AI</h1>
      <p>基于 AI 的科学论文智能处理与分析系统</p>
    </div>

    <el-row :gutter="20" class="stats-row">
      <el-col :span="12">
        <el-card shadow="hover" class="stat-card" v-if="!loading">
          <el-tooltip content="已上传的论文总数" placement="top">
            <div class="stat-content">
              <el-icon :size="40" color="var(--color-primary)"><Document /></el-icon>
              <div class="stat-info">
                <span class="stat-value">{{ displayStats.paperCount }}</span>
                <span class="stat-label">论文总数</span>
              </div>
            </div>
          </el-tooltip>
        </el-card>
        <el-skeleton animated v-else :rows="2" />
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover" class="stat-card" v-if="!loading">
          <el-tooltip content="正在处理中的论文数量" placement="top">
            <div class="stat-content">
              <el-icon :size="40" color="var(--color-success)"><Loading /></el-icon>
              <div class="stat-info">
                <span class="stat-value">{{ displayStats.processingCount }}</span>
                <span class="stat-label">处理中</span>
              </div>
            </div>
          </el-tooltip>
        </el-card>
        <el-skeleton animated v-else :rows="2" />
      </el-col>
    </el-row>

    <div class="quick-actions">
      <h2>快速入口</h2>
      <div class="action-grid">
        <el-card
          shadow="hover"
          class="action-card"
          v-for="action in quickActions"
          :key="action.path"
          @click="navigateTo(action.path)"
        >
          <div class="action-content">
            <div class="action-icon" :style="{ backgroundColor: action.color }">
              <el-icon :size="32" color="white">
                <component :is="action.icon" />
              </el-icon>
            </div>
            <span class="action-title">{{ action.title }}</span>
          </div>
        </el-card>
      </div>
    </div>

    <div class="recent-papers">
      <h2>最近处理</h2>
      <el-skeleton animated v-if="loading" :rows="5" />
      <el-table v-else-if="paperStore.papers.length > 0" :data="paperStore.papers.slice(0, 5)" stripe style="width: 100%">
        <el-table-column prop="file_name" label="文件名" show-overflow-tooltip />
        <el-table-column prop="title" label="标题" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'completed' ? 'success' : row.status === 'failed' ? 'danger' : 'info'" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="handleView(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && paperStore.papers.length === 0" description="暂无论文，请先上传PDF">
        <el-button type="primary" @click="navigateTo('/pdf')">上传PDF</el-button>
      </el-empty>
    </div>
  </div>
</template>

<style scoped>
.home-container {
  max-width: var(--page-max-width);
  margin: 0 auto;
  padding: var(--page-padding);
}

.welcome-section {
  text-align: center;
  padding: 40px 0;
}

.welcome-section h1 {
  font-size: 36px;
  color: var(--text-primary);
  margin-bottom: 10px;
}

.welcome-section p {
  font-size: 16px;
  color: var(--text-regular);
}

.stats-row {
  margin-bottom: var(--spacing-lg);
}

.stat-card {
  cursor: default;
  border-radius: var(--border-radius);
  transition: transform 0.2s, box-shadow 0.2s;
}

.stat-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-card-hover);
}

.stat-content {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
}

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 32px;
  font-weight: bold;
  color: var(--text-primary);
}

.stat-label {
  font-size: 14px;
  color: var(--text-secondary);
}

.quick-actions,
.recent-papers {
  margin-bottom: var(--spacing-lg);
}

.quick-actions h2,
.recent-papers h2 {
  font-size: 20px;
  margin-bottom: var(--spacing-lg);
  color: var(--text-primary);
}

/* 5个等宽卡片 flex 布局 */
.action-grid {
  display: flex;
  gap: var(--spacing-md);
}

.action-card {
  cursor: pointer;
  flex: 1;
  min-width: 0;
  transition: transform 0.2s, box-shadow 0.2s;
  border-radius: var(--border-radius);
}

.action-card:hover {
  transform: translateY(-5px);
  box-shadow: var(--shadow-card-hover);
}

.action-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--spacing-lg);
}

.action-icon {
  width: 60px;
  height: 60px;
  border-radius: var(--border-radius);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: var(--spacing-md);
}

.action-title {
  font-size: 16px;
  color: var(--text-primary);
  font-weight: 500;
}
</style>