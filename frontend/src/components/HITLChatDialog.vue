<template>
  <el-dialog
    v-model="visible"
    title="AI助手对话"
    width="700px"
    class="hitl-chat-dialog"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
  >
    <!-- 对话历史 -->
    <div class="chat-messages" ref="messagesContainer">
      <div v-for="(msg, index) in chatHistory" :key="index" :class="['chat-message', msg.role]">
        <div class="message-avatar">
          <span v-if="msg.role === 'assistant'">🤖</span>
          <span v-else>👤</span>
        </div>
        <div class="message-content">
          <div v-html="renderMarkdown(msg.content)"></div>
        </div>
      </div>

      <!-- 当前问题详情 -->
      <div v-if="issueDetails" class="issue-details">
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
    </div>

    <!-- 建议动作按钮 -->
    <div v-if="suggestedActions.length > 0 && pending" class="suggested-actions">
      <el-button
        v-for="action in suggestedActions"
        :key="action.value"
        :type="action.type"
        @click="handleAction(action.value)"
      >
        {{ action.label }}
      </el-button>
    </div>

    <!-- 用户输入 -->
    <div class="chat-input">
      <el-input
        v-model="userInput"
        type="textarea"
        :rows="2"
        placeholder="输入您的回复或问题..."
        :disabled="!pending"
        @keydown.enter.ctrl="handleSend"
      />
      <el-button type="primary" :disabled="!pending || !userInput.trim()" @click="handleSend">
        发送
      </el-button>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import { marked } from 'marked'
import { sanitizeHtml } from '@/utils/helpers'
import type { ChatMessage, SuggestedAction, IssueDetails } from '@/types/excel_extraction'

// Props
const props = defineProps<{
  chatHistory: ChatMessage[]
  currentMessage: string
  suggestedActions: SuggestedAction[]
  issueDetails: IssueDetails | null
  pending: boolean
}>()

// Emits
const emit = defineEmits<{
  (e: 'sendText', text: string): void
  (e: 'sendAction', action: string): void
  (e: 'close'): void
}>()

// 状态
const visible = ref(true)
const userInput = ref('')
const messagesContainer = ref<HTMLElement | null>(null)
let closeTimer: ReturnType<typeof setTimeout> | null = null

// 计算属性
const chatHistory = computed(() => props.chatHistory)
const suggestedActions = computed(() => props.suggestedActions)
const issueDetails = computed(() => props.issueDetails)
const pending = computed(() => props.pending)

// 方法
function renderMarkdown(content: string): string {
  try {
    return sanitizeHtml(marked.parse(content) as string)
  } catch {
    return sanitizeHtml(content)
  }
}

function getAlertType(): 'success' | 'warning' | 'danger' | 'info' {
  if (!props.issueDetails) return 'info'

  const summary = props.issueDetails.summary.toLowerCase()
  if (summary.includes('成功') || summary.includes('完成')) return 'success'
  if (summary.includes('失败') || summary.includes('错误')) return 'danger'
  if (summary.includes('未通过') || summary.includes('低于')) return 'warning'
  return 'info'
}

function handleSend() {
  if (!userInput.value.trim()) return
  emit('sendText', userInput.value.trim())
  userInput.value = ''
}

function handleAction(action: string) {
  emit('sendAction', action)
}

// 自动滚动到底部
watch(
  () => props.chatHistory.length,
  () => {
    nextTick(() => {
      if (messagesContainer.value) {
        messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
      }
    })
  }
)

// 监听 pending 变化，如果不再 pending 则关闭对话框
watch(
  () => props.pending,
  (newVal) => {
    if (!newVal && props.chatHistory.length > 0) {
      if (closeTimer) clearTimeout(closeTimer)
      closeTimer = setTimeout(() => {
        visible.value = false
      }, 1000)
    }
  }
)

// 关闭时发出事件
watch(visible, (newVal) => {
  if (!newVal) {
    emit('close')
  }
})

// 组件卸载时清理定时器
onUnmounted(() => {
  if (closeTimer) clearTimeout(closeTimer)
})
</script>

<style scoped>
.hitl-chat-dialog {
  --el-dialog-content-padding: 15px;
}

.chat-messages {
  max-height: 400px;
  overflow-y: auto;
  padding: 10px;
  background: var(--bg-page);
  border-radius: 8px;
}

.chat-message {
  display: flex;
  gap: 10px;
  margin-bottom: 15px;
}

.chat-message.assistant {
  flex-direction: row;
}

.chat-message.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  background: var(--bg-card);
}

.chat-message.assistant .message-avatar {
  background: var(--color-primary-lighter);
}

.chat-message.user .message-avatar {
  background: #f0f9eb;
}

.message-content {
  max-width: 80%;
  padding: 10px 15px;
  border-radius: 8px;
  background: var(--bg-card);
  line-height: 1.6;
}

.chat-message.user .message-content {
  background: var(--color-primary-lighter);
}

.issue-details {
  margin-top: 15px;
  padding: 10px;
}

.prompt-preview {
  margin-top: 10px;
}

.prompt-content {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  background: var(--bg-page);
  padding: 10px;
  border-radius: 4px;
  max-height: 200px;
  overflow-y: auto;
}

.suggested-actions {
  display: flex;
  gap: 10px;
  margin-top: 15px;
  padding: 10px;
  background: var(--bg-card);
  border-radius: 8px;
  justify-content: center;
}

.chat-input {
  display: flex;
  gap: 10px;
  margin-top: 15px;
  align-items: flex-end;
}

.chat-input .el-textarea {
  flex: 1;
}
</style>