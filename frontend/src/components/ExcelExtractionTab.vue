<template>
  <div class="excel-extraction-tab">
    <!-- 步骤条 -->
    <el-steps :active="currentStep" align-center style="margin-bottom: 20px;">
      <el-step title="上传文件" description="上传 Excel 和策略文档" />
      <el-step title="配置任务" description="设置提取参数" />
      <el-step title="智能处理" description="实时对话处理" />
      <el-step title="下载结果" description="获取 Excel 结果" />
    </el-steps>

    <!-- ========== 步骤 0: 上传文件 ========== -->
    <el-card v-if="currentStep === 0" class="step-card">
      <template #header>
        <div class="card-header">
          <span>步骤 1: 上传 Excel 文件</span>
        </div>
      </template>

      <el-upload
        ref="excelUploadRef"
        class="upload-area"
        drag
        action="#"
        :auto-upload="false"
        :on-change="handleExcelFileChange"
        :on-remove="handleExcelFileRemove"
        :file-list="excelFileList"
        accept=".xlsx,.xls"
        multiple
      >
        <el-icon class="el-icon--upload"><upload-filled /></el-icon>
        <div class="el-upload__text">
          将 Excel 文件拖到此处，或 <em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            支持 .xlsx/.xls 文件，包含 DOI、Title、Abstract 等题录数据
          </div>
        </template>
      </el-upload>

      <!-- 策略文档上传（可选） -->
      <el-divider content-position="left">策略文档（可选）</el-divider>
      <el-upload
        class="strategy-upload"
        action="#"
        :auto-upload="false"
        :on-change="handleStrategyFileChange"
        :on-remove="handleStrategyFileRemove"
        :file-list="strategyFileList"
        accept=".docx"
        :limit="1"
      >
        <el-button size="small" type="primary">上传策略 Word 文档</el-button>
        <template #tip>
          <div class="el-upload__tip">
            上传 .docx 文件，定义领域特定提取字段
          </div>
        </template>
      </el-upload>

      <div class="upload-actions">
        <el-button
          type="primary"
          :loading="uploadingFiles"
          :disabled="excelFileList.length === 0"
          @click="uploadAndPreview"
        >
          上传并预览数据
        </el-button>
      </div>

      <!-- 预览结果 -->
      <div v-if="previewData" class="preview-section">
        <el-divider content-position="left">数据预览</el-divider>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="总记录数">{{ previewData.row_count }}</el-descriptions-item>
          <el-descriptions-item label="列字段">{{ previewData.columns.join(', ') }}</el-descriptions-item>
        </el-descriptions>

        <!-- 质量统计 -->
        <div class="quality-stats">
          <el-tag v-for="(value, key) in previewData.quality_stats" :key="key" :type="value > 0 ? 'warning' : 'success'">
            {{ key.replace('missing_', '缺少') }}: {{ value }}
          </el-tag>
        </div>

        <!-- 数据预览表格 -->
        <el-table :data="previewData.preview_rows" max-height="200" style="margin-top: 10px;">
          <el-table-column prop="doi" label="DOI" width="150" show-overflow-tooltip />
          <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
          <el-table-column prop="abstract" label="摘要" min-width="300" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.abstract?.substring(0, 100) }}...
            </template>
          </el-table-column>
        </el-table>

        <el-button type="success" style="margin-top: 15px;" @click="currentStep = 1">
          下一步：配置任务
        </el-button>
      </div>
    </el-card>

    <!-- ========== 步骤 1: 配置任务 ========== -->
    <el-card v-if="currentStep === 1" class="step-card">
      <template #header>
        <div class="card-header">
          <span>步骤 2: 配置提取任务</span>
        </div>
      </template>

      <el-form label-width="120px">
        <el-form-item label="任务名称">
          <el-input v-model="taskConfig.task_name" placeholder="输入任务名称" />
        </el-form-item>

        <el-form-item label="LLM 模型">
          <el-select v-model="taskConfig.llm_model">
            <el-option label="qwen3.5-flash" value="qwen3.5-flash" />
            <el-option label="qwen3.5-plus" value="qwen3.5-plus" />
          </el-select>
        </el-form-item>

        <el-form-item label="对话模型">
          <el-select v-model="taskConfig.hitl_llm_model">
            <el-option label="qwen3.5-flash (推荐)" value="qwen3.5-flash" />
            <el-option label="qwen3.5-plus" value="qwen3.5-plus" />
          </el-select>
        </el-form-item>

        <el-form-item label="最大并发数">
          <el-input-number v-model="taskConfig.max_concurrent" :min="1" :max="20" />
          <el-text type="info" size="small" style="margin-left: 10px;">
            建议 3-5，避免 API 限流
          </el-text>
        </el-form-item>

        <el-form-item label="质量阈值">
          <el-slider v-model="taskConfig.quality_threshold" :min="0" :max="1" :step="0.1" show-input />
        </el-form-item>

        <el-form-item label="启用智能对话">
          <el-switch v-model="taskConfig.enable_smart_hitl" />
          <el-text type="info" size="small" style="margin-left: 10px;">
            开启后可用自然语言与 AI 对话
          </el-text>
        </el-form-item>

        <el-divider content-position="left">提取字段</el-divider>
        <el-form-item label="基础字段">
          <el-checkbox-group v-model="taskConfig.extract_fields">
            <el-checkbox label="related" value="related">相关性</el-checkbox>
            <el-checkbox label="institution" value="institution">机构</el-checkbox>
            <el-checkbox label="summary" value="summary">摘要</el-checkbox>
            <el-checkbox label="key_technologies" value="key_technologies">关键技术</el-checkbox>
            <el-checkbox label="application_areas" value="application_areas">应用领域</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
      </el-form>

      <div class="step-actions">
        <el-button @click="currentStep = 0">上一步</el-button>
        <el-button type="primary" @click="createTaskAndStart">开始处理</el-button>
      </div>
    </el-card>

    <!-- ========== 步骤 2: 智能处理 ========== -->
    <el-card v-if="currentStep === 2" class="step-card">
      <template #header>
        <div class="card-header">
          <span>步骤 3: 智能处理</span>
          <el-button v-if="isConnected" type="danger" size="small" @click="cancelTask">取消任务</el-button>
        </div>
      </template>

      <!-- 进度显示 -->
      <div class="progress-section">
        <el-progress :percentage="progress" :stroke-width="20" />
        <div class="progress-info">
          <span>{{ progressMessage }}</span>
          <span v-if="currentStepName">当前步骤: {{ currentStepName }}</span>
        </div>
      </div>

      <!-- 日志区域 -->
      <el-divider content-position="left">处理日志</el-divider>
      <div class="log-container">
        <div v-for="log in logs" :key="log.time" :class="['log-item', log.level.toLowerCase()]">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-node">[{{ log.node }}]</span>
          <span class="log-message">{{ log.message }}</span>
        </div>
      </div>

      <!-- HITL 对话弹窗 -->
      <HITLChatDialog
        v-if="hitlPending"
        :chat-history="chatHistory"
        :current-message="currentLLMMessage"
        :suggested-actions="suggestedActions"
        :issue-details="issueDetails"
        :pending="hitlPending"
        @send-text="sendTextMessage"
        @send-action="sendAction"
        @close="handleHITLClose"
      />
    </el-card>

    <!-- ========== 步骤 3: 下载结果 ========== -->
    <el-card v-if="currentStep === 3" class="step-card">
      <template #header>
        <div class="card-header">
          <span>步骤 4: 处理完成</span>
        </div>
      </template>

      <el-result
        v-if="isCompleted"
        icon="success"
        title="处理完成"
        :sub-title="`成功处理 ${resultsSummary?.success || 0} 条记录，失败 ${resultsSummary?.failed || 0} 条`"
      >
        <template #extra>
          <el-button type="primary" @click="downloadResults">
            <el-icon><Download /></el-icon>
            下载 Excel 结果
          </el-button>
          <el-button @click="resetAndStartNew">开始新任务</el-button>
        </template>
      </el-result>

      <el-result
        v-if="isFailed"
        icon="error"
        title="处理失败"
        :sub-title="errorMessage"
      >
        <template #extra>
          <el-button type="primary" @click="currentStep = 1">重新配置</el-button>
          <el-button @click="resetAndStartNew">开始新任务</el-button>
        </template>
      </el-result>
    </el-card>

    <!-- 历史任务列表 -->
    <el-card class="history-card">
      <template #header>
        <div class="card-header">
          <span>历史 Excel 提取任务</span>
          <el-button text @click="fetchHistoryTasks">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <el-table v-if="historyTasks.length > 0" :data="historyTasks" style="width: 100%" size="small">
        <el-table-column prop="task_name" label="任务名称" min-width="150" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">{{ getStatusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="progress" label="进度" width="100">
          <template #default="{ row }">
            <el-progress :percentage="row.progress" :stroke-width="15" />
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="150">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button v-if="row.status === 'completed'" size="small" type="success" link @click="downloadFromHistory(row)">
              下载
            </el-button>
            <el-button v-if="row.status === 'processing'" size="small" type="danger" link @click="cancelHistoryTask(row.task_id)">
              取消
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无历史任务" :image-size="60" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, watchEffect } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Refresh, UploadFilled } from '@element-plus/icons-vue'
import { excelExtractionApi } from '@/api/excel_extraction'
import { useExcelExtractionWs } from '@/composables/useExcelExtractionWs'
import { getStatusType, getStatusText, formatTime, shouldHideCancelledTask } from '@/utils/helpers'
import HITLChatDialog from '@/components/HITLChatDialog.vue'
import type { UploadPreviewResponse, TaskDetail } from '@/types/excel_extraction'

// 当前步骤
const currentStep = ref(0)

// 文件上传
const excelFileList = ref<any[]>([])
const strategyFileList = ref<any[]>([])
const uploadingFiles = ref(false)
const previewData = ref<UploadPreviewResponse['preview'] | null>(null)
const sessionId = ref('')
const uploadDir = ref('')
const strategyPath = ref('')

// 任务配置
const taskConfig = ref({
  task_name: 'Excel 批量提取任务',
  llm_model: 'qwen3.5-flash',
  hitl_llm_model: 'qwen3.5-flash',
  max_concurrent: 5,
  quality_threshold: 0.6,
  enable_smart_hitl: true,
  extract_fields: ['related', 'institution', 'summary', 'key_technologies', 'application_areas'],
})

// 当前任务
const currentTaskId = ref('')

// 历史任务
const historyTasks = ref<TaskDetail[]>([])

// WebSocket
const ws = ref<ReturnType<typeof useExcelExtractionWs> | null>(null)

// WebSocket 状态（从 ws 解构）
const isConnected = ref(false)
const progress = ref(0)
const progressMessage = ref('')
const currentStepName = ref('')
const logs = ref<Array<{ level: string; node: string; message: string; time: string }>>([])
const chatHistory = ref<Array<{ role: string; content: string }>>([])
const currentLLMMessage = ref('')
const suggestedActions = ref<Array<{ value: string; label: string; type: string }>>([])
const issueDetails = ref<any>(null)
const hitlPending = ref(false)
const isCompleted = ref(false)
const isFailed = ref(false)
const errorMessage = ref('')
const resultsSummary = ref<{ total: number; success: number; failed: number } | null>(null)

// 文件处理
function handleExcelFileChange(file: any) {
  excelFileList.value.push(file)
}

function handleExcelFileRemove(file: any) {
  excelFileList.value = excelFileList.value.filter(f => f !== file)
}

function handleStrategyFileChange(file: any) {
  strategyFileList.value = [file]
}

function handleStrategyFileRemove() {
  strategyFileList.value = []
}

// 上传并预览
async function uploadAndPreview() {
  if (excelFileList.value.length === 0) {
    ElMessage.warning('请先选择 Excel 文件')
    return
  }

  uploadingFiles.value = true
  try {
    const files = excelFileList.value.map(f => f.raw)
    const strategyFile = strategyFileList.value[0]?.raw

    const response = await excelExtractionApi.uploadFiles(files, strategyFile)

    if (response.success) {
      previewData.value = response.preview
      sessionId.value = response.session_id
      uploadDir.value = response.preview.upload_dir
      strategyPath.value = response.preview.strategy_path || ''
      ElMessage.success(response.message)
    } else {
      ElMessage.error(response.message || '上传失败')
    }
  } catch (error: any) {
    console.error('[Upload] 上传失败:', error)
    ElMessage.error(error.message || '上传失败')
  } finally {
    uploadingFiles.value = false
  }
}

// 创建任务并启动
async function createTaskAndStart() {
  if (!sessionId.value) {
    ElMessage.warning('请先上传 Excel 文件')
    return
  }

  try {
    // 创建任务
    const response = await excelExtractionApi.createTask({
      task_name: taskConfig.value.task_name,
      session_id: sessionId.value,
      config: taskConfig.value,
      upload_dir: uploadDir.value,
      strategy_path: strategyPath.value,
    })

    if (response.success) {
      currentTaskId.value = response.task_id
      currentStep.value = 2

      // 连接 WebSocket 并启动
      ws.value = useExcelExtractionWs(sessionId.value)
      ws.value.connect()

      // 等待连接建立后启动任务
      setTimeout(() => {
        ws.value?.startTask({
          ...taskConfig.value,
          task_id: currentTaskId.value,
        })
      }, 500)

      // 使用 watchEffect 响应式同步 WebSocket 状态
      const stateSyncStopper = watchEffect(() => {
        if (!ws.value) return
        isConnected.value = ws.value.isConnected.value
        progress.value = ws.value.progress.value
        progressMessage.value = ws.value.progressMessage.value
        currentStepName.value = ws.value.currentStep.value
        logs.value = ws.value.logs.value
        chatHistory.value = ws.value.chatHistory.value
        currentLLMMessage.value = ws.value.currentLLMMessage.value
        suggestedActions.value = ws.value.suggestedActions.value
        issueDetails.value = ws.value.issueDetails.value
        hitlPending.value = ws.value.hitlPending.value
        isCompleted.value = ws.value.isCompleted.value
        isFailed.value = ws.value.isFailed.value
        errorMessage.value = ws.value.errorMessage.value
        resultsSummary.value = ws.value.resultsSummary.value

        if (isCompleted.value) {
          currentStep.value = 3
          stateSyncStopper()
        }
      })

      ElMessage.success('任务已启动')
    } else {
      ElMessage.error(response.message || '创建任务失败')
    }
  } catch (error: any) {
    console.error('[CreateTask] 创建任务失败:', error)
    ElMessage.error(error.message || '创建任务失败')
  }
}

// 发送文本消息
function sendTextMessage(text: string) {
  ws.value?.sendTextMessage(text)
}

// 发送动作
function sendAction(action: string) {
  ws.value?.sendAction(action)
}

// 取消任务
function cancelTask() {
  ws.value?.cancelTask()
}

// 处理 HITL 关闭
function handleHITLClose() {
  // 继续处理
}

// 下载结果
async function downloadResults() {
  if (!currentTaskId.value) return
  try {
    await excelExtractionApi.downloadResults(currentTaskId.value)
    ElMessage.success('下载完成')
  } catch (error: any) {
    ElMessage.error(error.message || '下载失败')
  }
}

// 重置并开始新任务
function resetAndStartNew() {
  currentStep.value = 0
  excelFileList.value = []
  strategyFileList.value = []
  previewData.value = null
  sessionId.value = ''
  currentTaskId.value = ''
  ws.value?.disconnect()
  ws.value = null
}

// 获取历史任务（取消超过24小时的任务由 shouldHideCancelledTask 过滤）
async function fetchHistoryTasks() {
  try {
    const response = await excelExtractionApi.getTaskList({ page: 1, page_size: 10 })
    historyTasks.value = (response.items || []).filter(t => !shouldHideCancelledTask(t))
  } catch (error) {
    console.error('[HistoryTasks] 获取失败:', error)
  }
}

// 从历史下载
async function downloadFromHistory(task: TaskDetail) {
  try {
    await excelExtractionApi.downloadResults(task.task_id)
    ElMessage.success('下载完成')
  } catch (error: any) {
    ElMessage.error(error.message || '下载失败')
  }
}

// 取消历史任务
async function cancelHistoryTask(taskId: string) {
  try {
    await excelExtractionApi.cancelTask(taskId)
    ElMessage.success('任务已取消')
    await fetchHistoryTasks()
  } catch (error: any) {
    ElMessage.error(error.message || '取消失败')
  }
}

onMounted(() => {
  fetchHistoryTasks()
})

onUnmounted(() => {
  ws.value?.disconnect()
})
</script>

<style scoped>
.excel-extraction-tab {
  padding: 0;
}

.step-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.upload-area {
  width: 100%;
}

.upload-actions {
  margin-top: 20px;
  text-align: center;
}

.preview-section {
  margin-top: 20px;
}

.quality-stats {
  display: flex;
  gap: 10px;
  margin-top: 10px;
}

.step-actions {
  margin-top: 20px;
  display: flex;
  justify-content: center;
  gap: 20px;
}

.progress-section {
  margin-bottom: 20px;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  margin-top: 10px;
  color: var(--text-regular);
}

.log-container {
  max-height: 200px;
  overflow-y: auto;
  background: var(--bg-page);
  padding: 10px;
  border-radius: 4px;
}

.log-item {
  padding: 5px 0;
  font-size: 12px;
}

.log-item.info {
  color: var(--text-secondary);
}

.log-item.warning {
  color: var(--color-warning);
}

.log-item.error {
  color: var(--color-danger);
}

.log-time {
  margin-right: 10px;
  color: var(--text-placeholder);
}

.log-node {
  margin-right: 5px;
  color: var(--color-primary);
}

.history-card {
  margin-top: 20px;
}
</style>