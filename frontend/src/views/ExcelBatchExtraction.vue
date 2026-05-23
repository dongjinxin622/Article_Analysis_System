<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Refresh, UploadFilled } from '@element-plus/icons-vue'
import { marked } from 'marked'
import { excelExtractionApi } from '@/api/excel_extraction'
import { useExcelExtractionWs } from '@/composables/useExcelExtractionWs'
import { getStatusType, getStatusText, formatTime, sanitizeHtml } from '@/utils/helpers'
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

// WebSocket 状态
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

// 用户输入
const userInputText = ref('')
const chatMessagesRef = ref<HTMLElement | null>(null)

// 聊天面板 Tab 切换
const activeChatTab = ref('chat')

// 自动滚动到底部开关
const autoScrollEnabled = ref(true)

// Prompt 编辑器状态
const showPromptEditor = ref(false)
const editedPrompt = ref('')

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

      // 连接 WebSocket 并等待连接成功
      ws.value = useExcelExtractionWs(sessionId.value)
      await ws.value.connect()

      // 连接成功，立即更新连接状态
      isConnected.value = ws.value?.isConnected?.value || false

      // 连接成功后启动任务
      ws.value.startTask({
        ...taskConfig.value,
        task_id: currentTaskId.value,
      })

      // 监听状态变化（每 200ms 更新一次，更快响应）
      const intervalId = setInterval(() => {
        if (!ws.value) {
          clearInterval(intervalId)
          return
        }
        const instance = ws.value

        // 正确读取 ref 值（考虑 Vue Proxy 自动解包）
        const checkRef = (val: any) => {
          if (typeof val === 'boolean' || typeof val === 'number' || typeof val === 'string') {
            return val
          }
          if (val && typeof val === 'object' && '__v_isRef' in val) {
            return val.value
          }
          return val ?? false
        }

        isConnected.value = checkRef(instance.isConnected)

        if (instance.logs) {
          progress.value = checkRef(instance.progress) ?? 0
          progressMessage.value = checkRef(instance.progressMessage) ?? ''
          currentStepName.value = checkRef(instance.currentStep) ?? ''

          const logsArray = checkRef(instance.logs)
          logs.value = Array.isArray(logsArray) ? [...logsArray] : []

          const chatArray = checkRef(instance.chatHistory)
          chatHistory.value = Array.isArray(chatArray) ? [...chatArray] : []

          currentLLMMessage.value = checkRef(instance.currentLLMMessage) ?? ''
          suggestedActions.value = checkRef(instance.suggestedActions) ?? []
          issueDetails.value = checkRef(instance.issueDetails) ?? null
          hitlPending.value = checkRef(instance.hitlPending) ?? false
          isCompleted.value = checkRef(instance.isCompleted) ?? false
          isFailed.value = checkRef(instance.isFailed) ?? false
          errorMessage.value = checkRef(instance.errorMessage) ?? ''
          resultsSummary.value = checkRef(instance.resultsSummary) ?? null

          if (isCompleted.value || isFailed.value) {
            currentStep.value = 3
            clearInterval(intervalId)
            fetchHistoryTasks()
            // 任务完成时自动提示用户下载
            if (isCompleted.value) {
              setTimeout(() => {
                ElMessage.success('任务完成！请下载结果文件')
              }, 300)
            }
          }
        }
      }, 200)

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
  // 特殊处理 "edit" 动作：发送动作到后端并显示编辑器
  if (action === 'edit') {
    editedPrompt.value = issueDetails.value?.prompt_full || ''
    ws.value?.sendAction(action)
    showPromptEditor.value = true
    return
  }
  ws.value?.sendAction(action)
}

// 提交编辑后的 Prompt
function submitEditedPrompt() {
  if (!editedPrompt.value.trim()) {
    ElMessage.warning('Prompt 不能为空')
    return
  }
  showPromptEditor.value = false
  // 将编辑后的内容作为文本消息发送给后端
  sendTextMessage(editedPrompt.value)
}

// 取消编辑
function cancelEditPrompt() {
  showPromptEditor.value = false
  // 发送取消编辑的动作
  ws.value?.sendAction('cancel_edit')
}

// 取消任务
function cancelTask() {
  ws.value?.cancelTask()
}

// 处理 HITL 关闭
function handleHITLClose() {
  // 继续处理
}

// 处理发送文本
function handleSendText() {
  if (!userInputText.value.trim()) return
  sendTextMessage(userInputText.value.trim())
  userInputText.value = ''
}

function renderMarkdown(content: string): string {
  try {
    return sanitizeHtml(marked.parse(content) as string)
  } catch {
    return content
  }
}

// 获取警告类型
function getAlertType(): 'success' | 'warning' | 'danger' | 'info' {
  if (!issueDetails.value) return 'info'
  const summary = (issueDetails.value.summary || '').toLowerCase()
  if (summary.includes('成功') || summary.includes('完成')) return 'success'
  if (summary.includes('失败') || summary.includes('错误')) return 'danger'
  if (summary.includes('未通过') || summary.includes('低于')) return 'warning'
  return 'info'
}

// 自动滚动对话区域
watch(
  () => chatHistory.value.length,
  () => {
    if (!autoScrollEnabled.value) return
    nextTick(() => {
      if (chatMessagesRef.value) {
        chatMessagesRef.value.scrollTop = chatMessagesRef.value.scrollHeight
      }
    })
  }
)

watch(
  () => currentLLMMessage.value,
  () => {
    if (!autoScrollEnabled.value) return
    nextTick(() => {
      if (chatMessagesRef.value) {
        chatMessagesRef.value.scrollTop = chatMessagesRef.value.scrollHeight
      }
    })
  }
)

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

// 获取历史任务
async function fetchHistoryTasks() {
  try {
    const response = await excelExtractionApi.getTaskList({ page: 1, page_size: 10 })
    historyTasks.value = response.items || []
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

// 恢复监控处理中的任务
async function resumeTaskMonitoring(task: TaskDetail) {
  try {
    // 检查 session_id
    if (!task.session_id) {
      ElMessage.error('该任务缺少 session_id，无法恢复监控')
      console.error('[ResumeTask] task.session_id 为空:', task)
      return
    }

    // 设置当前任务信息
    currentTaskId.value = task.task_id
    sessionId.value = task.session_id
    currentStep.value = 2

    // 重置状态
    progress.value = task.progress || 0
    progressMessage.value = ''
    currentStepName.value = task.current_step || ''
    logs.value = []
    chatHistory.value = task.chat_history || []
    currentLLMMessage.value = ''
    suggestedActions.value = []
    issueDetails.value = null
    hitlPending.value = false
    isCompleted.value = task.status === 'completed'
    isFailed.value = task.status === 'failed'
    errorMessage.value = task.error_message || ''
    resultsSummary.value = null

    // 断开旧连接
    if (ws.value) {
      ws.value.disconnect()
      ws.value = null
    }

    // 如果任务还在处理中，建立 WebSocket 连接
    if (task.status === 'processing') {
      ws.value = useExcelExtractionWs(task.session_id)

      try {
        await ws.value.connect()
      } catch (wsError) {
        console.error('[ResumeTask] WebSocket连接失败:', wsError)
        ElMessage.error('WebSocket连接失败，请检查后端服务')
        isConnected.value = false
        return
      }

      // 立即更新连接状态
      const wsInstance = ws.value

      // 正确读取：先检查类型，如果是对象再检查是否是 Ref
      const val = wsInstance?.isConnected
      if (typeof val === 'boolean') {
        isConnected.value = val
      } else if (val && typeof val === 'object' && '__v_isRef' in val) {
        isConnected.value = val.value
      } else {
        isConnected.value = false
      }

      // 开始监控状态变化
      const intervalId = setInterval(() => {
        if (!ws.value) {
          clearInterval(intervalId)
          return
        }
        const instance = ws.value
        if (instance) {
          // 正确读取 ref 值（考虑 Vue Proxy 自动解包）
          const checkRef = (val: any) => {
            if (typeof val === 'boolean' || typeof val === 'number' || typeof val === 'string') {
              return val
            }
            if (val && typeof val === 'object' && '__v_isRef' in val) {
              return val.value
            }
            return val ?? false
          }

          isConnected.value = checkRef(instance.isConnected)

          progress.value = checkRef(instance.progress) ?? 0
          progressMessage.value = checkRef(instance.progressMessage) ?? ''
          currentStepName.value = checkRef(instance.currentStep) ?? ''

          const logsArray = checkRef(instance.logs)
          logs.value = Array.isArray(logsArray) ? [...logsArray] : []

          const chatArray = checkRef(instance.chatHistory)
          chatHistory.value = Array.isArray(chatArray) ? [...chatArray] : []

          currentLLMMessage.value = checkRef(instance.currentLLMMessage) ?? ''
          suggestedActions.value = checkRef(instance.suggestedActions) ?? []
          issueDetails.value = checkRef(instance.issueDetails) ?? null
          hitlPending.value = checkRef(instance.hitlPending) ?? false
          isCompleted.value = checkRef(instance.isCompleted) ?? false
          isFailed.value = checkRef(instance.isFailed) ?? false
          errorMessage.value = checkRef(instance.errorMessage) ?? ''
          resultsSummary.value = checkRef(instance.resultsSummary) ?? null

          if (isCompleted.value || isFailed.value) {
            currentStep.value = 3
            clearInterval(intervalId)
            fetchHistoryTasks()
            // 任务完成时自动提示用户下载
            if (isCompleted.value) {
              setTimeout(() => {
                ElMessage.success('任务完成！请下载结果文件')
              }, 300)
            }
          }
        }
      }, 200)

      ElMessage.success('已恢复任务监控')
    } else if (task.status === 'completed') {
      // 已完成的任务，直接显示结果
      currentStep.value = 3
      isConnected.value = false
      ElMessage.success('任务已完成，可下载结果')
    } else if (task.status === 'failed') {
      // 失败的任务
      currentStep.value = 3
      isConnected.value = false
    } else {
      // 等待中的任务
      isConnected.value = false
      ElMessage.info('任务等待中，请稍后刷新')
    }
  } catch (error: any) {
    console.error('[ResumeTask] 恢复监控失败:', error)
    ElMessage.error(error.message || '恢复监控失败')
  }
}

onMounted(() => {
  fetchHistoryTasks()
})

onUnmounted(() => {
  ws.value?.disconnect()
})
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-header-left">
        <h2 class="page-title">题录批量评估</h2>
        <p class="page-description">上传题录数据 → 配置评估参数 → LLM 批量评估 → 下载结果</p>
      </div>
    </div>

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
          <el-table-column prop="doi" label="DOI" width="150" show-overflow-tooltip fixed />
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
    <el-card v-if="currentStep === 2" class="step-card processing-card">
      <template #header>
        <div class="card-header">
          <span>步骤 3: 智能处理</span>
          <div class="header-status">
            <el-tag v-if="isConnected" type="success" size="small">已连接</el-tag>
            <el-tag v-else type="danger" size="small">未连接</el-tag>
            <el-button v-if="isConnected" type="danger" size="small" @click="cancelTask">取消任务</el-button>
          </div>
        </div>
      </template>

      <!-- 进度显示 -->
      <div class="progress-section">
        <el-progress :percentage="progress" :stroke-width="20" />
        <div class="progress-info">
          <span>{{ progressMessage || '等待开始...' }}</span>
          <span v-if="currentStepName">当前步骤: {{ currentStepName }}</span>
        </div>
      </div>

      <!-- 日志与对话 Tabs -->
      <el-tabs v-model="activeChatTab" class="chat-tabs">
        <!-- 日志 Tab -->
        <el-tab-pane label="处理日志" name="logs">
          <div class="log-container">
            <div v-if="logs.length === 0" class="log-empty">
              <el-empty description="等待任务开始..." :image-size="40" />
            </div>
            <div v-for="log in logs" :key="log.time + log.message" :class="['log-item', log.level.toLowerCase()]">
              <span class="log-time">{{ log.time }}</span>
              <span class="log-node">[{{ log.node }}]</span>
              <span class="log-message">{{ log.message }}</span>
            </div>
          </div>
        </el-tab-pane>

        <!-- 对话 Tab -->
        <el-tab-pane label="AI 助手对话" name="chat">
          <div class="chat-panel">
            <!-- 对话头部 -->
            <div class="chat-header">
              <span>AI 助手对话</span>
              <el-tag v-if="hitlPending" type="warning" size="small">等待响应</el-tag>
            </div>

            <!-- 对话历史 -->
            <div class="chat-messages" ref="chatMessagesRef">
              <div v-if="chatHistory.length === 0 && !currentLLMMessage" class="chat-empty">
                <el-empty description="任务开始后将显示对话内容" :image-size="60" />
              </div>
              <div v-for="(msg, index) in chatHistory" :key="index" :class="['chat-message', msg.role]">
                <div class="message-avatar">
                  <span v-if="msg.role === 'assistant'">AI</span>
                  <span v-else>我</span>
                </div>
                <div class="message-content">
                  <div v-html="renderMarkdown(msg.content)"></div>
                </div>
              </div>
              <!-- 当前 LLM 消息 -->
              <div v-if="currentLLMMessage && hitlPending" class="chat-message assistant current">
                <div class="message-avatar">AI</div>
                <div class="message-content">
                  <div v-html="renderMarkdown(currentLLMMessage)"></div>
                </div>
              </div>
            </div>

            <!-- 问题详情 -->
            <div v-if="issueDetails && hitlPending" class="issue-details">
              <el-alert :type="getAlertType()" :closable="false">
                <template #title>
                  <strong>{{ issueDetails.summary }}</strong>
                </template>
                <div v-if="issueDetails.details">{{ issueDetails.details }}</div>
                <div v-if="issueDetails.affected_count">
                  受影响记录: {{ issueDetails.affected_count }} 条
                </div>
                <div v-if="issueDetails.success_rate">
                  成功率: {{ (issueDetails.success_rate * 100).toFixed(0) }}%
                </div>
              </el-alert>
              <!-- Prompt 预览 -->
              <div v-if="issueDetails.prompt_preview" class="prompt-preview">
                <el-collapse>
                  <el-collapse-item title="查看完整 Prompt" name="prompt">
                    <pre class="prompt-content">{{ issueDetails.prompt_full || issueDetails.prompt_preview }}</pre>
                  </el-collapse-item>
                </el-collapse>
              </div>
            </div>

            <!-- 建议动作按钮 -->
            <div v-if="suggestedActions.length > 0 && hitlPending" class="suggested-actions">
              <el-button
                v-for="action in suggestedActions"
                :key="action.value"
                :type="action.type || 'default'"
                @click="sendAction(action.value)"
              >
                {{ action.label }}
              </el-button>
            </div>

            <!-- 用户输入 -->
            <div class="chat-input">
              <el-input
                v-model="userInputText"
                type="textarea"
                :rows="2"
                placeholder="输入您的回复或问题..."
                :disabled="!hitlPending"
                @keydown.enter.ctrl="handleSendText"
              />
              <el-button type="primary" :disabled="!hitlPending || !userInputText.trim()" @click="handleSendText">
                发送
              </el-button>
            </div>

            <!-- 自动滚动到底部开关 -->
            <div class="chat-auto-scroll">
              <el-switch v-model="autoScrollEnabled" size="small" />
              <span class="auto-scroll-label">自动滚动到底部</span>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- ========== Prompt 编辑器弹窗 ========== -->
    <el-dialog v-model="showPromptEditor" title="编辑 Prompt" width="80%" top="5vh" :close-on-click-modal="false">
      <el-input
        v-model="editedPrompt"
        type="textarea"
        :rows="25"
        placeholder="在此编辑 Prompt 内容..."
        class="prompt-editor-input"
      />
      <template #footer>
        <el-button @click="cancelEditPrompt">取消</el-button>
        <el-button type="primary" :disabled="!editedPrompt.trim()" @click="submitEditedPrompt">
          提交修改
        </el-button>
      </template>
    </el-dialog>

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
        <el-table-column prop="task_name" label="任务名称" min-width="150" fixed />
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
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-button v-if="row.status === 'completed'" size="small" type="success" link @click="downloadFromHistory(row)">
              下载
            </el-button>
            <el-button v-if="row.status === 'processing' || row.status === 'pending'" size="small" type="primary" link @click="resumeTaskMonitoring(row)">
              查看
            </el-button>
            <el-button v-if="row.status === 'processing'" size="small" type="danger" link @click="cancelHistoryTask(row.task_id)">
              取消
            </el-button>
            <el-button v-if="row.status === 'failed'" size="small" type="warning" link @click="resumeTaskMonitoring(row)">
              详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无历史任务" :image-size="60" />
    </el-card>
  </div>
</template>

<style scoped>
/* 页面特有样式 — 基于CSS变量，common.css 中已定义 .page-container/.page-header/.card-header 等 */

.step-card {
  margin-bottom: var(--spacing-lg);
}

.upload-area {
  width: 100%;
}

.upload-actions {
  margin-top: var(--spacing-lg);
  text-align: center;
}

.preview-section {
  margin-top: var(--spacing-lg);
}

.quality-stats {
  display: flex;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-sm);
}

.step-actions {
  margin-top: var(--spacing-lg);
  display: flex;
  justify-content: center;
  gap: var(--spacing-lg);
}

.progress-section {
  margin-bottom: var(--spacing-lg);
}

.progress-info {
  display: flex;
  justify-content: space-between;
  margin-top: var(--spacing-sm);
  color: var(--text-secondary);
}

/* 日志区域 */
.log-container {
  max-height: 300px;
  overflow-y: auto;
  background: var(--bg-page);
  padding: var(--spacing-sm);
  border-radius: var(--border-radius-sm);
}

.log-item {
  padding: var(--spacing-xs) 0;
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
  margin-right: var(--spacing-sm);
  color: var(--text-placeholder);
}

.log-node {
  margin-right: var(--spacing-xs);
  color: var(--color-primary);
}

.log-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100px;
}

/* 智能处理页面样式 */
.processing-card {
  min-height: 500px;
}

.chat-tabs {
  margin-top: var(--spacing-md);
}

/* 对话面板 */
.chat-panel {
  border: 1px solid var(--border-color-light);
  border-radius: var(--border-radius);
  background: var(--bg-card);
  display: flex;
  flex-direction: column;
}

.chat-header {
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-page);
  border-bottom: 1px solid var(--border-color-light);
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-md);
  background: var(--bg-page);
  min-height: 200px;
  max-height: 400px;
}

.chat-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.chat-message {
  display: flex;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
}

.chat-message.assistant {
  flex-direction: row;
}

.chat-message.user {
  flex-direction: row-reverse;
}

.chat-message.current {
  animation: fadeIn 0.3s ease-in;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 500;
  background: var(--bg-card);
}

.chat-message.assistant .message-avatar {
  background: var(--color-primary-lighter);
  color: var(--color-primary-dark);
}

.chat-message.user .message-avatar {
  background: #f0f9eb;
  color: var(--color-success);
}

.message-content {
  max-width: 80%;
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--border-radius);
  background: var(--bg-card);
  line-height: 1.6;
}

.chat-message.user .message-content {
  background: var(--color-primary-lighter);
}

.issue-details {
  padding: var(--spacing-sm) var(--spacing-md);
  border-top: 1px solid var(--border-color-light);
}

.prompt-preview {
  margin-top: var(--spacing-sm);
}

.prompt-content {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  background: var(--bg-page);
  padding: var(--spacing-sm);
  border-radius: var(--border-radius-sm);
  max-height: 150px;
  overflow-y: auto;
}

.suggested-actions {
  display: flex;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-page);
  border-top: 1px solid var(--border-color-light);
  justify-content: center;
  flex-wrap: wrap;
}

.chat-input {
  display: flex;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-card);
  border-top: 1px solid var(--border-color-light);
  align-items: flex-end;
}

.chat-input .el-textarea {
  flex: 1;
}

.chat-auto-scroll {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-xs) var(--spacing-md);
  background: var(--bg-page);
  border-top: 1px solid var(--border-color-light);
}

.auto-scroll-label {
  color: var(--text-secondary);
  font-size: 12px;
}

.header-status {
  display: flex;
  gap: var(--spacing-sm);
  align-items: center;
}

.history-card {
  margin-top: var(--spacing-lg);
}

/* Prompt 编辑器等宽字体 */
.prompt-editor-input :deep(.el-textarea__inner) {
  font-family: Consolas, Monaco, monospace;
  font-size: 13px;
}
</style>