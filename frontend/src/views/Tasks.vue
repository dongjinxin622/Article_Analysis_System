<template>
  <section class="main-panel">
    <header class="page-header">
      <div class="page-header__left">
        <h1 class="title">异步任务</h1>
        <p class="desc">
          <template v-if="projectName">查看项目「{{ projectName }}」的任务执行状态与进度控制</template>
          <template v-else-if="projectPublicId">任务执行状态与进度控制</template>
          <template v-else>请选择具体项目查看任务</template>
        </p>
      </div>

      <div class="page-header__right">
        <el-button class="header-action" size="large" @click="goBack">
          <el-icon><Back /></el-icon>
          返回
        </el-button>
        <el-button
          class="header-action"
          size="large"
          :loading="reloading"
          @click="handleManualRefresh"
        >
          <el-icon><Refresh /></el-icon>
          立即刷新
        </el-button>
      </div>
    </header>

    <TaskMetricsBar v-if="projectPublicId" class="metrics-bar" :project-public-id="projectPublicId" />
    <section v-else class="metrics-bar placeholder-card">
      <el-icon class="placeholder-icon"><DataAnalysis /></el-icon>
      <div class="placeholder-text">
        <strong>指标快照</strong>
        <span>请选择具体项目查看任务指标</span>
      </div>
    </section>

    <section v-if="listErrorMessage" class="task-error-banner">
      <el-icon><WarningFilled /></el-icon>
      <span>{{ listErrorMessage }}</span>
    </section>

    <section class="content-grid">
      <TaskListPanel
        class="list-panel"
        :items="jobs"
        :total="jobTotal"
        :loading="listLoading"
        :selected-id="selectedJobId"
        :active-filter="statusFilter"
        @select="onSelectJob"
        @update:filter="onUpdateFilter"
      />

      <TaskDetailPanel
        v-if="selectedJob"
        class="detail-panel"
        :project-public-id="projectPublicId"
        :job-public-id="selectedJob.publicId"
        :job="selectedJob"
        @mutated="onDetailMutated"
        @cleared="onDetailCleared"
      />
      <div v-else class="detail-panel placeholder-card">
        <el-icon class="placeholder-icon"><Tickets /></el-icon>
        <div class="placeholder-text">
          <strong>任务详情</strong>
          <span>选择左侧批次后可查看条目明细与执行控制</span>
        </div>
      </div>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Back,
  DataAnalysis,
  Refresh,
  Tickets,
  WarningFilled,
} from '@element-plus/icons-vue'
import {
  listTaskJobsApi,
  type TaskJobResponse,
  type TaskJobStatus,
} from '@/api/task'
import { useAdaptivePolling } from '@/composables/useAdaptivePolling'
import { usePollErrorNotice } from '@/composables/usePollErrorNotice'
import TaskListPanel from '@/components/task/TaskListPanel.vue'
import TaskDetailPanel from '@/components/task/TaskDetailPanel.vue'
import TaskMetricsBar from '@/components/task/TaskMetricsBar.vue'

type FilterValue = TaskJobStatus | ''

const ACTIVE_JOB_STATUSES: TaskJobStatus[] = ['pending', 'running', 'paused']
const POLL_ACTIVE_INTERVAL_MS = 5000
const POLL_IDLE_INTERVAL_MS = 15000

const router = useRouter()
const route = useRoute()

const projectPublicId = ref('')
const projectName = ref('')
const projectType = ref('')
const reloading = ref(false)

const jobs = ref<TaskJobResponse[]>([])
const jobTotal = ref(0)
const listLoading = ref(false)
const selectedJobId = ref<string | null>(null)
const statusFilter = ref<FilterValue>('')
const {
  errorMessage: listErrorMessage,
  clearError: clearListError,
  notifyError: notifyListError,
} = usePollErrorNotice('加载任务列表失败')

const hasActiveJob = computed(() =>
  jobs.value.some((job) => ACTIVE_JOB_STATUSES.includes(job.status)),
)

const selectedJob = computed(() => (
  jobs.value.find((job) => job.publicId === selectedJobId.value) ?? null
))

const resolveQueryString = (value: unknown) => {
  if (Array.isArray(value)) return typeof value[0] === 'string' ? value[0] : ''
  return typeof value === 'string' ? value : ''
}

const loadProjectMeta = () => {
  const id = resolveQueryString(route.query.id).trim()
  const idChanged = projectPublicId.value !== id
  if (idChanged) {
    projectPublicId.value = id
    projectName.value = resolveQueryString(route.query.name).trim() || id
    projectType.value = resolveQueryString(route.query.type).trim()
    jobs.value = []
    jobTotal.value = 0
    selectedJobId.value = null
    statusFilter.value = ''
    clearListError()
    if (listPoll.running.value) {
      void listPoll.refreshNow()
    }
  }
}

const loadJobs = async () => {
  const id = projectPublicId.value
  if (!id) return
  const requestedStatus = statusFilter.value || null
  listLoading.value = true
  try {
    const { data } = await listTaskJobsApi(id, {
      status: requestedStatus,
      page: 1,
      pageSize: 100,
    })
    if (requestedStatus !== (statusFilter.value || null)) {
      await loadJobs()
      return
    }
    const items = data?.items ?? []
    jobs.value = items
    jobTotal.value = data?.total ?? items.length
    if (selectedJobId.value && !items.some((job) => job.publicId === selectedJobId.value)) {
      selectedJobId.value = null
    }
    if (!selectedJobId.value && items.length > 0) {
      selectedJobId.value = items[0].publicId
    }
    clearListError()
  } catch (error) {
    if (notifyListError(error)) {
      console.error('加载任务列表失败', error)
    }
  } finally {
    listLoading.value = false
  }
}

const listPoll = useAdaptivePolling({
  task: loadJobs,
  interval: () => (hasActiveJob.value ? POLL_ACTIVE_INTERVAL_MS : POLL_IDLE_INTERVAL_MS),
  enabled: () => Boolean(projectPublicId.value),
})

const goBack = () => {
  const from = resolveQueryString(route.query.from).trim()
  if (from.startsWith('/') && !from.startsWith('/tasks')) {
    router.push(from)
    return
  }
  router.push('/')
}

const handleManualRefresh = async () => {
  if (!projectPublicId.value) return
  reloading.value = true
  try {
    loadProjectMeta()
    await listPoll.refreshNow()
  } finally {
    reloading.value = false
  }
}

const onSelectJob = (jobPublicId: string) => {
  selectedJobId.value = jobPublicId
}

const onUpdateFilter = (value: FilterValue) => {
  statusFilter.value = value
  selectedJobId.value = null
  void listPoll.refreshNow()
}

const onDetailMutated = () => {
  void listPoll.refreshNow()
}

const onDetailCleared = () => {
  selectedJobId.value = null
  void listPoll.refreshNow()
}

watch(() => [route.query.id, route.query.type, route.query.name] as const, loadProjectMeta, { immediate: true })

onMounted(() => {
  listPoll.start()
})
</script>

<style scoped>
.main-panel {
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.34) transparent;
  padding: 24px 28px 20px;
  gap: 16px;
  height: 100%;
  min-height: 0;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 22px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.025), rgba(255, 255, 255, 0.015));
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.45);
}

.main-panel::-webkit-scrollbar {
  width: 8px;
}

.main-panel::-webkit-scrollbar-track {
  background: transparent;
}

.main-panel::-webkit-scrollbar-thumb {
  min-height: 48px;
  border: 2px solid transparent;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.32);
  background-clip: padding-box;
}

.main-panel::-webkit-scrollbar-thumb:hover {
  background: rgba(203, 213, 225, 0.46);
  background-clip: padding-box;
}

.main-panel::-webkit-scrollbar-corner {
  background: transparent;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  flex-shrink: 0;
}

.page-header__right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.title {
  margin: 0;
  font-size: 32px;
  line-height: 1.1;
  font-weight: 800;
  background: linear-gradient(180deg, #ffffff 0%, #93a1b3 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.desc {
  margin: 6px 0 0;
  color: #8b949e;
  font-size: 13px;
  line-height: 1.4;
}

.header-action {
  height: 38px;
  padding: 0 14px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 10px;
  color: #e6edf3;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 14px;
  font-weight: 500;
  transition: background 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
}

.header-action :deep(.el-icon) {
  font-size: 16px;
}

.header-action:hover,
.header-action:focus {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.18);
  transform: translateY(-1px);
}

.metrics-bar {
  flex-shrink: 0;
  min-height: 76px;
}

.task-error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  padding: 10px 12px;
  border: 1px solid rgba(248, 113, 113, 0.25);
  border-radius: 10px;
  color: #fecaca;
  background: rgba(127, 29, 29, 0.18);
  font-size: 12px;
  line-height: 1.4;
}

.task-error-banner :deep(.el-icon) {
  flex: 0 0 auto;
  color: #f87171;
  font-size: 16px;
}

.content-grid {
  flex: 0 0 auto;
  display: grid;
  grid-template-columns: minmax(320px, 360px) 1fr;
  grid-template-rows: 1fr;
  gap: 16px;
  min-height: 560px;
  min-width: 0;
}

.content-grid > * {
  min-height: 0;
  min-width: 0;
}

.placeholder-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 20px;
  border: 1px dashed rgba(255, 255, 255, 0.12);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.02);
  color: #8b949e;
}

.list-panel {
  min-height: 0;
  height: 100%;
}

.detail-panel {
  height: 100%;
  min-height: 560px;
}

.detail-panel.placeholder-card {
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.placeholder-icon {
  font-size: 22px;
  color: #6e7681;
}

.placeholder-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.placeholder-text strong {
  color: #e6edf3;
  font-size: 15px;
  font-weight: 600;
}

.placeholder-text span {
  font-size: 12px;
  color: #6e7681;
}

.detail-panel .placeholder-text {
  align-items: center;
}

@media (max-height: 720px) {
  .content-grid {
    min-height: 480px;
  }

  .detail-panel {
    min-height: 480px;
  }
}
</style>
