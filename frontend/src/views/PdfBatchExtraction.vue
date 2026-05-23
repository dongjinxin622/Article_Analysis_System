<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { usePaperStore, useNerStore, useReStore } from '@/stores'
import { batchApi } from '@/api'
import { promptApi } from '@/api/prompt'
import { getStatusType, getStatusText, formatTime } from '@/utils/helpers'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Refresh, ArrowLeft, UploadFilled, CircleCheck, CircleClose, Loading } from '@element-plus/icons-vue'
import type { ProcessingResult } from '@/types/paper'
import type { BatchTaskDetail, TaskProgress } from '@/types/task'

const paperStore = usePaperStore()
const nerStore = useNerStore()
const reStore = useReStore()

// 当前步骤（0: 上传PDF, 1: 选择论文, 2: 执行NER/RE, 3: 查看结果）
const currentStep = ref(0)

// ========== 步骤 0: 批量上传 PDF ==========
const uploadingFiles = ref(false)
const uploadedResults = ref<any[]>([])
const fileList = ref<any[]>([])

// 处理文件选择
function handleFileChange(file: any) {
  fileList.value.push(file)
}

// 处理文件移除
function handleFileRemove(file: any) {
  fileList.value = fileList.value.filter(f => f !== file)
}

// 执行批量上传
async function executeBatchUpload() {
  if (fileList.value.length === 0) {
    ElMessage.warning('请先选择 PDF 文件')
    return
  }

  uploadingFiles.value = true
  try {
    // 创建 FormData
    const formData = new FormData()
    for (const file of fileList.value) {
      formData.append('files', file.raw)
    }

    const response = await batchApi.batchUploadPdf(formData)

    if (response.success) {
      ElMessage.success(response.message)
      uploadedResults.value = response.files || []

      // 刷新论文列表
      await paperStore.fetchPapers()

      // 自动跳转到下一步
      if (response.success_count > 0) {
        currentStep.value = 1
      }
    } else {
      ElMessage.error(response.message || '上传失败')
    }
  } catch (error: any) {
    console.error('[BatchUpload] 上传失败:', error)
    ElMessage.error(error.response?.data?.detail || error.message || '上传失败')
  } finally {
    uploadingFiles.value = false
    fileList.value = []
  }
}

// ========== 步骤 1: 选择论文 ==========
const selectedPapers = ref<ProcessingResult[]>([])

// 表格选择变化
function handleSelectionChange(selection: ProcessingResult[]) {
  selectedPapers.value = selection
}

// 继续下一步
function goToNextStep() {
  if (currentStep.value === 1 && selectedPapers.value.length === 0) {
    ElMessage.warning('请先选择要处理的论文')
    return
  }
  currentStep.value++
}

// ========== 步骤 2: 执行 NER/RE ==========
const taskName = ref('批量提取任务')
const createDialogVisible = ref(false)
const creatingTask = ref(false)

// 配置选项
const enableNER = ref(true)
const enableRE = ref(true)

// Prompt 文件配置
const nerQueryFile = ref('scipdf/ner_queries/material_ner.txt')
const reQueryFile = ref('scipdf/re_queries/material_re.txt')
const skipIntroduction = ref(true)
const sentenceGroupSize = ref(10)
const maxConcurrent = ref(3)  // 最大并发数

// Prompt 文件列表（从 API 动态获取）
const nerPromptFiles = ref<string[]>([])
const rePromptFiles = ref<string[]>([])

// 从 API 获取 Prompt 模板列表
async function fetchPrompts() {
  try {
    const nerResult = await promptApi.list('ner')
    nerPromptFiles.value = nerResult.templates.map(t => t.name)
    // 确保默认选中值在列表中，否则取第一个
    if (nerPromptFiles.value.length > 0 && !nerPromptFiles.value.includes(nerQueryFile.value)) {
      nerQueryFile.value = nerPromptFiles.value[0]
    }
  } catch (error) {
    console.error('[Batch] 获取 NER Prompt 列表失败:', error)
  }

  try {
    const reResult = await promptApi.list('re')
    rePromptFiles.value = reResult.templates.map(t => t.name)
    if (rePromptFiles.value.length > 0 && !rePromptFiles.value.includes(reQueryFile.value)) {
      reQueryFile.value = rePromptFiles.value[0]
    }
  } catch (error) {
    console.error('[Batch] 获取 RE Prompt 列表失败:', error)
  }
}

// 任务列表和进度
const taskList = ref<BatchTaskDetail[]>([])
const currentTask = ref<BatchTaskDetail | null>(null)
const taskDetailDialogVisible = ref(false)
const taskProgress = ref<TaskProgress | null>(null)
const progressPolling = ref<number | null>(null)

// 打开创建任务对话框
function openCreateDialog() {
  if (selectedPapers.value.length === 0) {
    ElMessage.warning('请先选择论文')
    return
  }
  createDialogVisible.value = true
}

// 创建批量任务
async function createBatchTask() {
  creatingTask.value = true
  try {
    const response = await batchApi.createBatchTask({
      task_name: taskName.value,
      result_ids: selectedPapers.value.map(p => p.result_id),
      config: {
        do_ner: enableNER.value,
        do_re: enableRE.value,
        ner_query_file: nerQueryFile.value,
        re_query_file: reQueryFile.value,
        skip_introduction: skipIntroduction.value,
        sentence_group_size: sentenceGroupSize.value,
        max_concurrent: maxConcurrent.value
      },
      enable_hitl: false
    })

    if (response.success) {
      ElMessage.success(`任务已创建: ${response.task_id}`)
      createDialogVisible.value = false

      // 开始轮询进度
      startProgressPolling(response.task_id)

      // 刷新任务列表
      await fetchTaskList()

      // 跳转到执行提取步骤（步骤2）
      currentStep.value = 2
    } else {
      ElMessage.error(response.message || '创建任务失败')
    }
  } catch (error: any) {
    console.error('[Batch] 创建任务失败:', error)
    ElMessage.error(error.response?.data?.detail || error.message || '创建任务失败')
  } finally {
    creatingTask.value = false
  }
}

// 开始进度轮询
function startProgressPolling(taskId: string) {
  if (progressPolling.value) {
    clearInterval(progressPolling.value)
  }

  progressPolling.value = window.setInterval(async () => {
    try {
      const progress = await batchApi.getTaskProgress(taskId)
      taskProgress.value = progress

      const detail = await batchApi.getTaskDetail(taskId)
      currentTask.value = detail

      // 任务完成或失败时停止轮询，并跳转到结果步骤
      if (progress.step === 'completed' || progress.step === 'failed' || progress.step === 'cancelled' || progress.progress >= 100) {
        stopProgressPolling()
        await fetchTaskList()
        // 任务完成后自动跳转到步骤3（查看结果）
        if (progress.step === 'completed') {
          currentStep.value = 3
        }
      }
    } catch (error) {
      console.error('[Batch] 获取进度失败:', error)
      stopProgressPolling()
    }
  }, 3000)
}

// 停止进度轮询
function stopProgressPolling() {
  if (progressPolling.value) {
    clearInterval(progressPolling.value)
    progressPolling.value = null
  }
}

// 获取任务列表
async function fetchTaskList() {
  try {
    const response = await batchApi.getTaskList({ page: 1, page_size: 20 })
    taskList.value = response.items || []
  } catch (error) {
    console.error('[Batch] 获取任务列表失败:', error)
  }
}

// 取消任务
async function cancelTask(taskId: string) {
  try {
    await ElMessageBox.confirm('确定要取消这个任务吗？', '提示', { type: 'warning' })
    const response = await batchApi.cancelTask(taskId)
    if (response.success) {
      ElMessage.success('任务已取消')
      stopProgressPolling()
      await fetchTaskList()
    }
  } catch (error) {
    // 用户取消
  }
}

// 查看任务详情
async function viewTaskDetail(task: BatchTaskDetail) {
  currentTask.value = task
  taskDetailDialogVisible.value = true
  if (task.status === 'processing') {
    startProgressPolling(task.task_id)
  } else {
    try {
      const detail = await batchApi.getTaskDetail(task.task_id)
      currentTask.value = detail
      taskProgress.value = {
        task_id: task.task_id,
        step: task.status,
        progress: task.progress,
        message: task.error_message || '',
        total_files: task.total_count
      }
    } catch (error) {
      console.error('[Batch] 获取任务详情失败:', error)
    }
  }
}

// 关闭任务详情对话框
function closeTaskDetailDialog() {
  taskDetailDialogVisible.value = false
  currentTask.value = null
  stopProgressPolling()
}

// 重置状态并开始新任务
function resetAndStartNew() {
  stopProgressPolling()
  taskProgress.value = null
  currentTask.value = null
  selectedPapers.value = []
  currentStep.value = 1  // 返回选择论文步骤
}

// 处理下载
async function handleDownload() {
  if (!currentTask.value) return
  try {
    await batchApi.downloadBatchResultsExcel(currentTask.value.task_id)
    ElMessage.success('下载完成')
  } catch (error: any) {
    console.error('[Batch] 下载失败:', error)
    ElMessage.error(error.message || '下载失败')
  }
}

// 从历史任务列表下载
async function downloadFromList(task: BatchTaskDetail) {
  try {
    await batchApi.downloadBatchResultsExcel(task.task_id)
    ElMessage.success('下载完成')
  } catch (error: any) {
    console.error('[Batch] 下载失败:', error)
    ElMessage.error(error.message || '下载失败')
  }
}

// 步骤标题
const stepTitles = ['批量上传 PDF', '选择论文', '执行提取', '查看结果']

onMounted(() => {
  paperStore.fetchPapers()
  fetchTaskList()
  fetchPrompts()
})

onUnmounted(() => {
  stopProgressPolling()
})
</script>

<template>
  <div class="page-container pdf-batch-extraction">
    <div class="page-header">
      <div class="page-header-left">
        <h2 class="page-title">PDF 批量提取</h2>
        <p class="page-description">完整的批量处理流程：上传 PDF → 解析 → NER 提取 → RE 提取（并行处理模式）</p>
      </div>
      <el-button text @click="fetchTaskList()">
        <el-icon><Refresh /></el-icon>
        刷新任务
      </el-button>
    </div>

    <!-- PDF 批量提取历史任务列表 -->
    <el-card class="history-card">
      <template #header>
        <div class="card-header">
          <span>历史任务列表 {{ taskList.length > 0 ? `(${taskList.length})` : '' }}</span>
          <el-button text @click="fetchTaskList()">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>
      <el-table v-if="taskList.length > 0" :data="taskList" style="width: 100%" size="small">
        <el-table-column prop="task_name" label="任务名称" min-width="150" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">{{ getStatusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="progress" label="进度" width="100">
          <template #default="{ row }">
            <el-progress
              :percentage="row.progress"
              :status="row.status === 'completed' ? 'success' : row.status === 'failed' ? 'exception' : ''"
              :stroke-width="15"
            />
          </template>
        </el-table-column>
        <el-table-column prop="total_count" label="总数" width="60" />
        <el-table-column prop="completed_count" label="成功" width="60">
          <template #default="{ row }">
            <el-text type="success" size="small">{{ row.completed_count }}</el-text>
          </template>
        </el-table-column>
        <el-table-column prop="failed_count" label="失败" width="60">
          <template #default="{ row }">
            <el-text v-if="row.failed_count > 0" type="danger" size="small">{{ row.failed_count }}</el-text>
            <el-text v-else type="info" size="small">0</el-text>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="130">
          <template #default="{ row }">
            <el-text size="small">{{ formatTime(row.created_at) }}</el-text>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="viewTaskDetail(row)">详情</el-button>
            <el-button v-if="row.status === 'completed'" size="small" type="success" link @click="downloadFromList(row)">下载</el-button>
            <el-button v-if="row.status === 'processing'" size="small" type="danger" link @click="cancelTask(row.task_id)">取消</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无历史任务，请先上传 PDF 并执行提取" :image-size="80" />
    </el-card>

    <!-- 步骤条 -->
    <el-steps :active="currentStep" align-center style="margin-bottom: 30px;">
      <el-step title="批量上传 PDF" description="上传多个 PDF 文件并解析" />
      <el-step title="选择论文" description="选择要处理的论文" />
      <el-step title="执行提取" description="并行执行 NER/RE" />
      <el-step title="查看结果" description="查看处理结果" />
    </el-steps>

    <!-- ========== 步骤 0: 批量上传 PDF ========== -->
    <el-card v-if="currentStep === 0" class="step-card">
      <template #header>
        <div class="card-header">
          <span>步骤 1: 批量上传 PDF 文件</span>
        </div>
      </template>

      <el-upload
        ref="uploadRef"
        class="upload-area"
        drag
        action="#"
        :auto-upload="false"
        :on-change="handleFileChange"
        :on-remove="handleFileRemove"
        :file-list="fileList"
        accept=".pdf"
        multiple
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">
          将 PDF 文件拖到此处，或 <em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            支持 PDF 文件，单文件最大 100MB，可同时上传多个文件
          </div>
        </template>
      </el-upload>

      <div class="upload-actions">
        <el-button
          type="primary"
          :loading="uploadingFiles"
          :disabled="fileList.length === 0"
          @click="executeBatchUpload"
        >
          开始上传并解析 {{ fileList.length }} 个文件
        </el-button>
      </div>

      <!-- 上传结果 -->
      <div v-if="uploadedResults.length > 0" class="upload-results">
        <el-divider content-position="left">上传结果</el-divider>
        <el-table :data="uploadedResults" max-height="300">
          <el-table-column prop="file_name" label="文件名" min-width="200" show-overflow-tooltip />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'completed' ? 'success' : 'danger'">
                {{ row.status === 'completed' ? '成功' : '失败' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="title" label="标题" min-width="250" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.title || '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="result_id" label="结果 ID" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">
              <el-text v-if="row.result_id" type="primary">{{ row.result_id }}</el-text>
              <el-text v-else type="info">-</el-text>
            </template>
          </el-table-column>
          <el-table-column prop="error" label="错误信息" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <el-text v-if="row.error" type="danger">{{ row.error }}</el-text>
              <el-text v-else>-</el-text>
            </template>
          </el-table-column>
        </el-table>
        <el-button
          type="success"
          style="margin-top: 15px;"
          @click="currentStep = 1"
        >
          继续下一步：选择论文
        </el-button>
      </div>
    </el-card>

    <!-- ========== 步骤 1: 选择论文 ========== -->
    <el-card v-if="currentStep === 1" class="step-card">
      <template #header>
        <div class="card-header">
          <span>步骤 2: 选择要处理的论文（已选 {{ selectedPapers.length }} 篇）</span>
          <div class="header-actions">
            <el-button text @click="paperStore.fetchPapers()">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
            <el-button @click="currentStep = 0">
              <el-icon><ArrowLeft /></el-icon>
              上传更多
            </el-button>
          </div>
        </div>
      </template>

      <el-table
        v-loading="paperStore.loading"
        :data="paperStore.papers"
        style="width: 100%"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="55" />
        <el-table-column prop="file_name" label="文件名" min-width="200" show-overflow-tooltip />
        <el-table-column prop="title" label="标题" min-width="300" show-overflow-tooltip />
        <el-table-column prop="doi" label="DOI" min-width="150" show-overflow-tooltip />
        <el-table-column label="NER 状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.ner_status === 'completed' ? 'success' : row.ner_status ? 'warning' : 'info'">
              {{ row.ner_status || '未处理' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="RE 状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.re_status === 'completed' ? 'success' : row.re_status ? 'warning' : 'info'">
              {{ row.re_status || '未处理' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="上传时间" width="180" />
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="paperStore.currentPage"
          v-model:page-size="paperStore.pageSize"
          :total="paperStore.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="paperStore.fetchPapers()"
          @current-change="paperStore.fetchPapers()"
        />
      </div>

      <div class="step-actions">
        <el-button @click="currentStep = 0">上一步</el-button>
        <el-button
          type="primary"
          :disabled="selectedPapers.length === 0"
          @click="openCreateDialog"
        >
          下一步：执行提取
        </el-button>
      </div>
    </el-card>

    <!-- ========== 步骤 2: 执行提取 ========== -->
    <el-card v-if="currentStep === 2" class="step-card">
      <template #header>
        <div class="card-header">
          <span>步骤 3: 执行提取（并行处理）</span>
          <div class="header-actions">
            <el-button @click="currentStep = 1">
              <el-icon><ArrowLeft /></el-icon>
              返回选择
            </el-button>
          </div>
        </div>
      </template>

      <!-- 当前任务进度 -->
      <div v-if="taskProgress && taskProgress.step !== 'completed'" class="progress-section">
        <h4>当前任务进度</h4>

        <!-- 统计卡片 -->
        <el-row :gutter="16" class="progress-stats">
          <el-col :span="6">
            <div class="stat-item">
              <div class="stat-value">{{ taskProgress.progress.toFixed(0) }}%</div>
              <div class="stat-label">总进度</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="stat-item stat-success">
              <div class="stat-value">{{ currentTask?.completed_count ?? 0 }}</div>
              <div class="stat-label">已完成</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="stat-item stat-failed">
              <div class="stat-value">{{ currentTask?.failed_count ?? 0 }}</div>
              <div class="stat-label">失败</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="stat-item stat-total">
              <div class="stat-value">{{ currentTask?.total_count ?? 0 }}</div>
              <div class="stat-label">总计</div>
            </div>
          </el-col>
        </el-row>

        <!-- 进度条 -->
        <el-progress
          :percentage="Math.min(taskProgress.progress, 100)"
          :status="taskProgress.step === 'failed' ? 'exception' : ''"
          :stroke-width="26"
          :text-inside="true"
        />

        <!-- 任务信息和操作 -->
        <div class="progress-info">
          <span>状态: <el-tag :type="getStatusType(taskProgress.step)" size="small">{{ getStatusText(taskProgress.step) }}</el-tag></span>
          <span v-if="taskProgress.message">{{ taskProgress.message }}</span>
          <span v-if="currentTask">完成: {{ currentTask.completed_count }}/{{ currentTask.total_count }} · 失败: {{ currentTask.failed_count }}/{{ currentTask.total_count }}</span>
          <el-button v-if="taskProgress.step === 'processing'" type="danger" size="small" @click="cancelTask(taskProgress.task_id)">取消任务</el-button>
        </div>

        <!-- 单个论文处理状态表 -->
        <div v-if="currentTask?.results && currentTask.results.length > 0" class="paper-progress-table">
          <h4 style="margin: var(--spacing-md) 0 var(--spacing-sm)">各论文处理状态</h4>
          <el-table :data="currentTask.results" size="small" max-height="300" stripe>
            <el-table-column label="#" type="index" width="50" />
            <el-table-column label="论文 ID" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                <el-tooltip :content="row.result_id || row.error" placement="top">
                  <span>{{ row.result_id || '(上传中)' }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="NER" width="140">
              <template #default="{ row }">
                <el-tag v-if="row.ner_id" type="success" size="small">已完成 ({{ row.entity_count ?? 0 }}实体)</el-tag>
                <el-tag v-else-if="row.ner_error" type="danger" size="small">失败</el-tag>
                <el-tag v-else type="info" size="small">等待中</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="RE" width="140">
              <template #default="{ row }">
                <el-tag v-if="row.re_id" type="success" size="small">已完成 ({{ row.relation_count ?? 0 }}关系)</el-tag>
                <el-tag v-else-if="row.re_error" type="danger" size="small">失败</el-tag>
                <el-tag v-else-if="row.ner_id" type="warning" size="small">处理中</el-tag>
                <el-tag v-else type="info" size="small">等待 NER</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-icon v-if="row.success" color="#67c23a"><CircleCheck /></el-icon>
                <el-icon v-else-if="row.re_error || row.ner_error" color="#f56c6c"><CircleClose /></el-icon>
                <el-icon v-else color="#e6a23c" class="is-loading"><Loading /></el-icon>
                <span style="margin-left: 4px">{{ row.success ? '成功' : row.re_error || row.ner_error ? '失败' : '处理中' }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>

      <!-- 任务完成提示 -->
      <div v-if="taskProgress && taskProgress.step === 'completed'" class="task-completed-section">
        <el-result icon="success" title="任务执行完成" sub-title="NER/RE 提取已完成">
          <template #extra>
            <el-button type="primary" @click="viewTaskDetail(currentTask!)">查看详细结果</el-button>
            <el-button @click="currentStep = 3">查看所有任务</el-button>
            <el-button @click="resetAndStartNew()">开始新任务</el-button>
          </template>
        </el-result>
      </div>

      <!-- 无任务时的提示 -->
      <div v-if="!taskProgress" class="no-task-section">
        <el-empty description="暂无正在执行的任务">
          <el-button type="primary" @click="currentStep = 1">返回选择论文</el-button>
        </el-empty>
      </div>
    </el-card>

    <!-- ========== 步骤 3: 查看结果 ========== -->
    <el-card v-if="currentStep === 3" class="step-card">
      <template #header>
        <div class="card-header">
          <span>步骤 4: 查看结果</span>
          <div class="header-actions">
            <el-button @click="currentStep = 1">
              <el-icon><ArrowLeft /></el-icon>
              返回选择
            </el-button>
            <el-button type="primary" @click="resetAndStartNew()">
              开始新任务
            </el-button>
          </div>
        </div>
      </template>

      <!-- 任务列表 -->
      <div class="task-list-section">
        <h4>历史任务列表</h4>
        <el-table :data="taskList" style="width: 100%" v-loading="!taskList.length">
          <el-table-column prop="task_id" label="任务 ID" min-width="200" show-overflow-tooltip />
          <el-table-column prop="task_name" label="任务名称" min-width="150" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="getStatusType(row.status)">{{ getStatusText(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="progress" label="进度" width="100">
            <template #default="{ row }">
              <el-progress
                :percentage="row.progress"
                :status="row.status === 'completed' ? 'success' : row.status === 'failed' ? 'exception' : ''"
                :stroke-width="15"
              />
            </template>
          </el-table-column>
          <el-table-column prop="total_count" label="总数" width="60" />
          <el-table-column prop="completed_count" label="成功" width="60">
            <template #default="{ row }">
              <el-text type="success">{{ row.completed_count }}</el-text>
            </template>
          </el-table-column>
          <el-table-column prop="failed_count" label="失败" width="60">
            <template #default="{ row }">
              <el-text v-if="row.failed_count > 0" type="danger">{{ row.failed_count }}</el-text>
              <el-text v-else type="info">0</el-text>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="150">
            <template #default="{ row }">
              {{ formatTime(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" @click="viewTaskDetail(row)">查看详情</el-button>
              <el-button v-if="row.status === 'processing'" size="small" type="danger" @click="cancelTask(row.task_id)">取消</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div v-if="taskList.length === 0" class="empty-task">
        <el-empty description="暂无批量任务，请先选择论文并创建任务">
          <el-button type="primary" @click="currentStep = 1">选择论文</el-button>
        </el-empty>
      </div>
    </el-card>

    <!-- 创建任务对话框 -->
    <el-dialog v-model="createDialogVisible" title="创建批量任务" width="600px">
      <el-form label-width="120px">
        <el-form-item label="任务名称">
          <el-input v-model="taskName" placeholder="输入任务名称" />
        </el-form-item>
        <el-form-item label="选中论文">
          <el-text type="primary">{{ selectedPapers.length }} 篇</el-text>
        </el-form-item>
        <el-form-item label="处理流程">
          <el-checkbox v-model="enableNER">NER 提取</el-checkbox>
          <el-checkbox v-model="enableRE">RE 提取</el-checkbox>
        </el-form-item>

        <el-divider content-position="left">NER 配置</el-divider>
        <el-form-item label="NER Prompt">
          <el-select v-model="nerQueryFile" :disabled="!enableNER">
            <el-option v-for="file in nerPromptFiles" :key="file" :label="file" :value="file" />
          </el-select>
        </el-form-item>
        <el-form-item label="跳过 Introduction">
          <el-switch v-model="skipIntroduction" :disabled="!enableNER" />
        </el-form-item>
        <el-form-item label="句子组大小">
          <el-input-number v-model="sentenceGroupSize" :min="5" :max="50" :disabled="!enableNER" />
        </el-form-item>

        <el-divider content-position="left">RE 配置</el-divider>
        <el-form-item label="RE Prompt">
          <el-select v-model="reQueryFile" :disabled="!enableRE">
            <el-option v-for="file in rePromptFiles" :key="file" :label="file" :value="file" />
          </el-select>
        </el-form-item>

        <el-divider content-position="left">并行处理配置</el-divider>
        <el-form-item label="最大并发数">
          <el-input-number v-model="maxConcurrent" :min="1" :max="10" />
          <el-text type="info" size="small" style="margin-left: 10px;">
            同时处理的论文数量（建议 3-5，避免 API 限流）
          </el-text>
        </el-form-item>

        <el-alert type="info" :closable="false" show-icon style="margin-top: 10px">
          <template #title>
            批量处理采用并行模式，最多同时处理 {{ maxConcurrent }} 篇论文。处理时间取决于论文数量和 API 速率限制。
          </template>
        </el-alert>
      </el-form>

      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creatingTask" @click="createBatchTask">创建任务</el-button>
      </template>
    </el-dialog>

    <!-- 任务详情对话框 -->
    <el-dialog v-model="taskDetailDialogVisible" title="任务详情" width="700px" @close="closeTaskDetailDialog">
      <el-descriptions :column="2" border v-if="currentTask">
        <el-descriptions-item label="任务 ID">{{ currentTask.task_id }}</el-descriptions-item>
        <el-descriptions-item label="任务名称">{{ currentTask.task_name }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusType(currentTask.status)">{{ getStatusText(currentTask.status) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="进度">{{ currentTask.progress.toFixed(1) }}%</el-descriptions-item>
        <el-descriptions-item label="总数">{{ currentTask.total_count }}</el-descriptions-item>
        <el-descriptions-item label="完成">{{ currentTask.completed_count }}</el-descriptions-item>
        <el-descriptions-item label="失败">{{ currentTask.failed_count }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatTime(currentTask.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="错误信息" v-if="currentTask.error_message" :span="2">
          <el-text type="danger">{{ currentTask.error_message }}</el-text>
        </el-descriptions-item>
      </el-descriptions>

      <!-- 处理结果列表 -->
      <div v-if="currentTask?.results?.length > 0" style="margin-top: 20px;">
        <el-divider content-position="left">处理结果</el-divider>
        <el-table :data="currentTask.results" max-height="300">
          <el-table-column prop="result_id" label="论文 ID" min-width="150" show-overflow-tooltip />
          <el-table-column prop="ner_id" label="NER ID" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">
              <el-text v-if="row.ner_id" type="success">{{ row.ner_id }}</el-text>
              <el-text v-else type="info">-</el-text>
            </template>
          </el-table-column>
          <el-table-column prop="re_id" label="RE ID" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">
              <el-text v-if="row.re_id" type="success">{{ row.re_id }}</el-text>
              <el-text v-else type="info">-</el-text>
            </template>
          </el-table-column>
          <el-table-column prop="entity_count" label="实体数" width="80" />
          <el-table-column prop="relation_count" label="关系数" width="80" />
        </el-table>
      </div>

      <!-- 错误列表 -->
      <div v-if="currentTask?.errors?.length > 0" style="margin-top: 20px;">
        <el-divider content-position="left">错误记录</el-divider>
        <el-table :data="currentTask.errors" max-height="200">
          <el-table-column prop="result_id" label="论文 ID" min-width="150" />
          <el-table-column prop="stage" label="阶段" width="80">
            <template #default="{ row }">
              <el-tag type="warning" size="small">{{ row.stage }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="error" label="错误信息" min-width="300" show-overflow-tooltip />
        </el-table>
      </div>

      <!-- 下载区域（任务完成时显示） -->
      <div v-if="currentTask?.status === 'completed' && currentTask?.results?.length > 0" style="margin-top: 20px;">
        <el-divider content-position="left">下载结果</el-divider>
        <div class="download-section">
          <el-button type="success" @click="handleDownload">
            <el-icon><Download /></el-icon>
            下载 Excel 文件
          </el-button>
          <el-text type="info" size="small" style="margin-left: 15px;">
            Excel 包含 content、NER、RE 三个 sheet
          </el-text>
        </div>
      </div>

      <template #footer>
        <el-button @click="closeTaskDetailDialog">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
/* 页面特有样式 — 全局布局类（page-container / page-header / card-header）由 common.css 提供，不再重复 */

.pdf-batch-extraction {
  /* page-container 全局类已提供 max-width 和 margin，无需重复 */
}

.history-card {
  margin-bottom: var(--spacing-lg);
}

.step-card {
  margin-bottom: var(--spacing-lg);
}

.header-actions {
  display: flex;
  gap: var(--spacing-sm);
}

.upload-area {
  width: 100%;
}

.upload-actions {
  margin-top: var(--spacing-lg);
  text-align: center;
}

.upload-results {
  margin-top: var(--spacing-lg);
}

.pagination {
  margin-top: var(--spacing-lg);
  display: flex;
  justify-content: flex-end;
}

.step-actions {
  margin-top: var(--spacing-lg);
  display: flex;
  justify-content: center;
  gap: var(--spacing-lg);
}

.progress-section,
.task-list-section {
  margin-bottom: var(--spacing-lg);
}

.progress-section h4,
.task-list-section h4 {
  margin: 0 0 var(--spacing-sm) 0;
  color: var(--text-primary);
}

.progress-stats {
  margin-bottom: var(--spacing-md);
}

.stat-item {
  text-align: center;
  padding: var(--spacing-sm);
  border-radius: var(--border-radius);
  background: var(--bg-page);
}

.stat-item .stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-primary);
}

.stat-item.stat-success .stat-value {
  color: var(--color-success);
}

.stat-item.stat-failed .stat-value {
  color: var(--color-danger);
}

.stat-item.stat-total .stat-value {
  color: var(--text-primary);
}

.stat-item .stat-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.paper-progress-table {
  margin-top: var(--spacing-sm);
}

.progress-info {
  margin-top: var(--spacing-sm);
  display: flex;
  gap: var(--spacing-lg);
  color: var(--text-regular);
  align-items: center;
}

.task-completed-section,
.no-task-section {
  padding: var(--spacing-lg);
}

.download-section {
  display: flex;
  align-items: center;
  padding: var(--spacing-md);
  background: var(--bg-page);
  border-radius: var(--border-radius);
}

.empty-task {
  padding: var(--spacing-lg);
}
</style>