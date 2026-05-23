/**
 * Excel 批量提取 WebSocket 连接管理
 * 使用原生 WebSocket（FastAPI 兼容）
 * 单例模式 - 所有状态在模块级别定义，确保响应式正确
 */
import { ref, Ref } from 'vue'
import type {
  ChatMessage,
  SuggestedAction,
  IssueDetails
} from '@/types/excel_extraction'

// ============================================================================
// 模块级别的单例状态 - 所有 ref 在模块级别创建，确保响应式引用一致性
// ============================================================================

let socket: WebSocket | null = null
let currentSessionId = ''

// 连接状态
const isConnected = ref(false)

// 进度状态
const currentStep = ref('')
const progress = ref(0)
const progressMessage = ref('')

// 日志
const logs = ref<Array<{ level: string; node: string; message: string; time: string }>>([])

// HITL 对话状态
const chatHistory = ref<ChatMessage[]>([])
const currentLLMMessage = ref('')
const suggestedActions = ref<SuggestedAction[]>([])
const issueDetails = ref<IssueDetails | null>(null)
const hitlPending = ref(false)

// 完成状态
const isCompleted = ref(false)
const isFailed = ref(false)
const errorMessage = ref('')
const outputPath = ref('')
const resultsSummary = ref<{ total: number; success: number; failed: number } | null>(null)

// 失败列表
const failedList = ref<Array<{ doi: string; title: string; error: string }>>([])

// ============================================================================
// 内部方法
// ============================================================================

/**
 * 处理消息
 */
function handleMessage(data: any) {
  const messageType = data.type
  const content = data.content || {}

  console.log(`[WebSocket] 收到消息:`, messageType, content)

  switch (messageType) {
    case 'progress':
      currentStep.value = content.step || ''
      progress.value = content.progress || 0
      progressMessage.value = content.message || ''
      break

    case 'log':
      logs.value.push({
        level: content.level || 'info',
        node: content.node || '',
        message: content.message || '',
        time: new Date().toLocaleTimeString()
      })
      // 限制日志数量
      if (logs.value.length > 100) {
        logs.value = logs.value.slice(-50)
      }
      break

    case 'llm_chat':
      if (content.role === 'assistant') {
        currentLLMMessage.value = content.message || ''
        suggestedActions.value = content.suggested_actions || []
        issueDetails.value = content.issue_details || null
        hitlPending.value = true

        // 添加到对话历史
        chatHistory.value.push({
          role: 'assistant',
          content: content.message || ''
        })
      }
      break

    case 'completed':
      isCompleted.value = true
      outputPath.value = content.output_xlsx_path || ''
      resultsSummary.value = content.results_summary || null
      hitlPending.value = false
      progress.value = 100
      progressMessage.value = '处理完成，正在跳转到下载页面...'
      // 清空对话历史，避免干扰下载页面
      chatHistory.value = []
      currentLLMMessage.value = ''
      suggestedActions.value = []
      issueDetails.value = null
      break

    case 'failed':
      isFailed.value = true
      errorMessage.value = content.error || '处理失败'
      hitlPending.value = false
      break

    case 'failed_list':
      failedList.value = content.failed_list || []
      break

    case 'cancelled':
      isFailed.value = true
      errorMessage.value = '任务已取消'
      hitlPending.value = false
      break

    default:
      console.log(`[WebSocket] 未处理的消息类型: ${messageType}`)
  }
}

/**
 * 发送消息
 */
function sendMessage(data: any): boolean {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    console.error('[WebSocket] 未连接，无法发送消息')
    return false
  }

  socket.send(JSON.stringify(data))
  return true
}

/**
 * 重置所有状态
 */
function resetState() {
  currentStep.value = ''
  progress.value = 0
  progressMessage.value = ''
  logs.value = []
  chatHistory.value = []
  currentLLMMessage.value = ''
  suggestedActions.value = []
  issueDetails.value = null
  hitlPending.value = false
  isCompleted.value = false
  isFailed.value = false
  errorMessage.value = ''
  outputPath.value = ''
  resultsSummary.value = null
  failedList.value = []
}

// ============================================================================
// 公开方法
// ============================================================================

/**
 * 连接 WebSocket
 */
function connect(): Promise<void> {
  return new Promise((resolve, reject) => {
    // 如果已有连接，先断开
    if (socket && socket.readyState === WebSocket.OPEN) {
      console.log('[WebSocket] 断开旧连接...')
      socket.close()
      socket = null
      isConnected.value = false
    }

    // 构造 WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws/excel-extraction/${currentSessionId}`

    console.log(`[WebSocket] 连接: ${wsUrl}, sessionId: ${currentSessionId}`)
    console.log(`[WebSocket] 当前 isConnected ref:`, isConnected)
    console.log(`[WebSocket] 当前 isConnected.id:`, isConnected.value)

    socket = new WebSocket(wsUrl)

    socket.onopen = () => {
      console.log(`[WebSocket] onopen 触发，sessionId: ${currentSessionId}`)
      console.log(`[WebSocket] 设置 isConnected.value = true`)
      isConnected.value = true
      console.log(`[WebSocket] isConnected.value 现在是:`, isConnected.value)
      console.log(`[WebSocket] isConnected ref 对象:`, isConnected)
      resolve()
    }

    socket.onclose = (event) => {
      console.log(`[WebSocket] onclose 触发, code: ${event.code}, reason: ${event.reason}`)
      isConnected.value = false
      console.log(`[WebSocket] isConnected.value 设置为 false`)
    }

    socket.onerror = (error) => {
      console.error(`[WebSocket] onerror 触发:`, error)
      isConnected.value = false
      reject(error)
    }

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        handleMessage(data)
      } catch (e) {
        console.error('[WebSocket] 解析消息失败:', e)
      }
    }
  })
}

/**
 * 断开连接
 */
function disconnect() {
  if (socket) {
    socket.close()
    socket = null
  }
  isConnected.value = false
}

/**
 * 启动任务
 */
function startTask(config: Record<string, any>) {
  if (!isConnected.value) {
    console.error('[WebSocket] 未连接，无法启动任务')
    return
  }

  // 重置状态
  resetState()

  sendMessage({
    type: 'start',
    config: config
  })
}

/**
 * 发送文本消息（HITL 对话）
 */
function sendTextMessage(text: string) {
  if (!sendMessage({
    type: 'user_input',
    input_type: 'text',
    text: text
  })) {
    return
  }

  // 添加到对话历史
  chatHistory.value.push({
    role: 'user',
    content: text
  })

  hitlPending.value = false
}

/**
 * 发送快捷动作（HITL 按钮）
 */
function sendAction(action: string, extraData?: Record<string, any>) {
  if (!sendMessage({
    type: 'user_input',
    input_type: 'action',
    action: action,
    data: extraData || {}
  })) {
    return
  }

  // 添加到对话历史
  chatHistory.value.push({
    role: 'user',
    content: `选择: ${action}`
  })

  hitlPending.value = false
}

/**
 * 取消任务
 */
function cancelTask() {
  sendMessage({
    type: 'cancel'
  })
}

// ============================================================================
// 导出接口
// ============================================================================

/**
 * 获取 WebSocket 单例实例
 * @param sessionId 会话 ID
 * @returns WebSocket 实例对象，包含所有状态 ref 和方法
 */
export function useExcelExtractionWs(sessionId: string) {
  // 更新当前 sessionId
  console.log(`[useExcelExtractionWs] 调用，sessionId: ${sessionId}, 旧 sessionId: ${currentSessionId}`)
  currentSessionId = sessionId

  // 返回单例对象（所有 ref 都是模块级别的，确保响应式正确）
  return {
    // 状态 ref
    isConnected,
    currentStep,
    progress,
    progressMessage,
    logs,
    chatHistory,
    currentLLMMessage,
    suggestedActions,
    issueDetails,
    hitlPending,
    isCompleted,
    isFailed,
    errorMessage,
    outputPath,
    resultsSummary,
    failedList,

    // 方法
    connect,
    disconnect,
    startTask,
    sendTextMessage,
    sendAction,
    cancelTask
  }
}

/**
 * 获取当前单例实例（不创建新的）
 */
export function getExcelExtractionWs() {
  return {
    isConnected,
    currentStep,
    progress,
    progressMessage,
    logs,
    chatHistory,
    currentLLMMessage,
    suggestedActions,
    issueDetails,
    hitlPending,
    isCompleted,
    isFailed,
    errorMessage,
    outputPath,
    resultsSummary,
    failedList,
    connect,
    disconnect,
    startTask,
    sendTextMessage,
    sendAction,
    cancelTask
  }
}