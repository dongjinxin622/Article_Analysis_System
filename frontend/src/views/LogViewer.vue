<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { logger } from '@/utils/logger'
import { ElMessage } from 'element-plus'
import { Download } from '@element-plus/icons-vue'

// 日志列表
const logs = ref<any[]>([])
const filterLevel = ref('')
const filterModule = ref('')
const searchText = ref('')
const loading = ref(false)

// 分页
const currentPage = ref(1)
const pageSize = ref(50)

// 搜索防抖定时器
let debounceTimer: ReturnType<typeof setTimeout> | null = null

/** 防抖搜索处理 */
function onSearchInput() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    currentPage.value = 1
    refreshLogs()
  }, 300)
}

/** 过滤条件变更处理 */
function onFilterChange() {
  currentPage.value = 1
  refreshLogs()
}

/** 刷新日志 */
function refreshLogs() {
  loading.value = true
  let allLogs = logger.getAllLogs()

  // 按级别过滤
  if (filterLevel.value) {
    allLogs = allLogs.filter(l => l.level === filterLevel.value)
  }

  // 按模块过滤
  if (filterModule.value) {
    allLogs = allLogs.filter(l => l.module.includes(filterModule.value))
  }

  // 搜索
  if (searchText.value) {
    allLogs = allLogs.filter(l =>
      l.message.includes(searchText.value) ||
      (l.data && JSON.stringify(l.data).includes(searchText.value))
    )
  }

  logs.value = allLogs
  loading.value = false
}

/** 分页后的日志数据 */
const paginatedLogs = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return logs.value.slice(start, end)
})

/** 清空日志 */
function clearLogs() {
  logger.clearLogs()
  logs.value = []
  currentPage.value = 1
  ElMessage.success('日志已清空')
}

/** 下载日志文件 */
function downloadLogs() {
  logger.downloadLogs()
  ElMessage.success('日志文件已下载')
}

/** 导出为JSON */
function exportAsJSON() {
  const data = JSON.stringify(logs.value, null, 2)
  const blob = new Blob([data], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `logs_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.json`
  link.click()
  URL.revokeObjectURL(url)
  ElMessage.success('日志已导出为JSON文件')
}

/** 只看错误 */
function showErrorsOnly() {
  logs.value = logger.getErrorLogs()
  currentPage.value = 1
}

/** 获取级别圆点颜色 */
function getLevelDotColor(level: string) {
  switch (level) {
    case 'ERROR': return 'var(--color-danger)'
    case 'WARN': return 'var(--color-warning)'
    case 'INFO': return 'var(--color-success)'
    case 'DEBUG': return 'var(--color-info)'
    default: return 'var(--color-info)'
  }
}

/** 获取级别标签类型 */
function getLevelTagType(level: string) {
  switch (level) {
    case 'ERROR': return 'danger'
    case 'WARN': return 'warning'
    case 'INFO': return 'success'
    case 'DEBUG': return 'info'
    default: return ''
  }
}

onMounted(() => {
  refreshLogs()
})
</script>

<template>
  <div class="page-container log-viewer">
    <!-- 页面头部 — 使用全局通用样式 -->
    <div class="page-header">
      <div class="page-header-left">
        <h1 class="page-title">日志查看</h1>
        <p class="page-description">查看前端运行日志，记录所有API请求和错误信息</p>
      </div>
    </div>

    <!-- 操作栏 -->
    <el-card class="toolbar-card">
      <div class="toolbar">
        <el-select v-model="filterLevel" placeholder="日志级别" clearable @change="onFilterChange" style="width: 120px">
          <el-option label="ERROR" value="ERROR" />
          <el-option label="WARN" value="WARN" />
          <el-option label="INFO" value="INFO" />
          <el-option label="DEBUG" value="DEBUG" />
        </el-select>

        <el-input v-model="filterModule" placeholder="模块名" clearable @change="onFilterChange" style="width: 150px" />

        <el-input v-model="searchText" placeholder="搜索内容" clearable @input="onSearchInput" style="width: 200px" />

        <el-button-group>
          <el-button type="primary" @click="refreshLogs">刷新</el-button>
          <el-button type="danger" @click="showErrorsOnly">只看错误</el-button>
          <el-button type="warning" @click="clearLogs">清空</el-button>
          <el-button type="success" @click="downloadLogs">下载日志</el-button>
          <el-button type="primary" :icon="Download" @click="exportAsJSON">导出JSON</el-button>
        </el-button-group>
      </div>

      <div class="stats">
        <el-tag>总日志: {{ logger.getAllLogs().length }}</el-tag>
        <el-tag type="danger">错误: {{ logger.getErrorLogs().length }}</el-tag>
        <el-tag v-if="logs.length !== logger.getAllLogs().length" type="info">当前筛选: {{ logs.length }} 条</el-tag>
      </div>
    </el-card>

    <!-- 日志列表 -->
    <el-card class="log-list-card">
      <!-- 骨架屏加载态 -->
      <template v-if="loading">
        <el-skeleton animated :rows="8" :throttle="0" />
      </template>

      <template v-else>
        <el-table :data="paginatedLogs" style="width: 100%" max-height="600">
          <el-table-column prop="timestamp" label="时间" width="180">
            <template #default="{ row }">
              {{ row.timestamp.slice(0, 19).replace('T', ' ') }}
            </template>
          </el-table-column>

          <el-table-column prop="level" label="级别" width="100">
            <template #default="{ row }">
              <div class="level-cell">
                <span class="level-dot" :style="{ backgroundColor: getLevelDotColor(row.level) }" />
                <el-tag :type="getLevelTagType(row.level)" size="small">{{ row.level }}</el-tag>
              </div>
            </template>
          </el-table-column>

          <el-table-column prop="module" label="模块" width="100" />

          <el-table-column label="消息/数据" min-width="400">
            <template #default="{ row }">
              <div class="log-content">
                <div class="log-message">{{ row.message }}</div>
                <div class="log-data" v-if="row.data">
                  <pre>{{ JSON.stringify(row.data, null, 2) }}</pre>
                </div>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <!-- 分页 -->
        <div class="pagination-wrapper" v-if="logs.length > pageSize">
          <el-pagination
            v-model:current-page="currentPage"
            :page-size="pageSize"
            :total="logs.length"
            layout="total, prev, pager, next"
            background
            small
          />
        </div>

        <el-empty v-if="logs.length === 0" description="暂无日志记录" />
      </template>
    </el-card>
  </div>
</template>

<style scoped>
/* ========== 操作栏 ========== */
.toolbar-card,
.log-list-card {
  margin-bottom: var(--spacing-lg);
}

.toolbar {
  display: flex;
  gap: 15px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 15px;
}

.stats {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

/* ========== 日志级别圆点指示器 ========== */
.level-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.level-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* ========== 日志内容区域 ========== */
.log-content {
  font-size: 12px;
}

.log-message {
  font-weight: 500;
  color: var(--text-primary);
}

.log-data {
  margin-top: 5px;
  background: var(--bg-page);
  padding: 5px;
  border-radius: var(--border-radius-sm);
}

.log-data pre {
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
  color: var(--text-secondary);
  font-size: 11px;
}

/* ========== 分页 ========== */
.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: var(--spacing-lg);
}
</style>
