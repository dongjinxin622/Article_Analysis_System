/**
 * Excel 批量提取相关类型定义
 */

// 任务状态枚举
export enum ExcelExtractionTaskStatus {
  PENDING = 'pending',
  VALIDATING = 'validating',
  PROCESSING = 'processing',
  HITL_WAITING = 'hitl_waiting',
  EXPORTING = 'exporting',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled'
}

// 行数据状态枚举
export enum RowStatus {
  PENDING = 'pending',
  PROCESSING = 'processing',
  COMPLETED = 'completed',
  FAILED = 'failed'
}

// 检查类型枚举
export enum CheckType {
  FIELD = 'field',
  QUALITY = 'quality',
  FILTER = 'filter',
  PROMPT = 'prompt',
  EVAL = 'eval'
}

// 任务配置
export interface TaskConfig {
  domain_fields: Array<{ name: string; description: string }>
  extract_fields: string[]
  llm_model: string
  hitl_llm_model: string
  max_concurrent: number
  dedup_field: string
  quality_threshold: number
  enable_hitl: boolean
  enable_smart_hitl: boolean
  strategy_docx_path?: string
}

// 上传预览响应
export interface UploadPreviewResponse {
  success: boolean
  message: string
  session_id: string
  preview: {
    columns: string[]
    row_count: number
    quality_stats: Record<string, number>
    preview_rows: Record<string, any>[]
    upload_dir: string
    strategy_path?: string
  }
}

// 任务创建响应
export interface TaskCreateResponse {
  success: boolean
  message: string
  task_id: string
  session_id: string
  status: ExcelExtractionTaskStatus
  total_rows: number
}

// 任务详情
export interface TaskDetail {
  task_id: string
  task_name: string
  session_id?: string  // WebSocket 会话 ID
  status: ExcelExtractionTaskStatus
  total_rows: number
  processed_rows: number
  success_rows: number
  failed_rows: number
  progress: number
  current_step?: string
  current_node?: string
  pending_check?: CheckType
  config: Record<string, any>
  chat_history: ChatMessage[]
  created_at?: string
  started_at?: string
  completed_at?: string
  error_message?: string
  output_file_path?: string
}

// 任务列表响应
export interface TaskListResponse {
  items: TaskDetail[]
  total: number
  page: number
  page_size: number
}

// 行数据详情
export interface RowDetail {
  id: number
  row_index: number
  unique_key?: string
  raw_data: Record<string, any>
  quality_score?: number
  quality_issues?: string[]
  status: RowStatus
  extraction_result?: Record<string, any>
  error_message?: string
}

// 行数据列表响应
export interface RowListResponse {
  items: RowDetail[]
  total: number
  page: number
  page_size: number
}

// 对话消息
export interface ChatMessage {
  role: 'assistant' | 'user'
  content: string
}

// 建议动作
export interface SuggestedAction {
  value: string
  label: string
  type: 'primary' | 'success' | 'warning' | 'danger' | 'default'
}

// 问题详情
export interface IssueDetails {
  summary: string
  details: string
  affected_count: number
  affected_records?: Record<string, any>[]
  prompt_preview?: string
  prompt_full?: string
  success_rate?: number
  parse_rate?: number
}

// WebSocket 消息类型
export interface WSMessage {
  type: string
  content: Record<string, any>
  timestamp?: string
}

// 进度消息
export interface WSProgressMessage extends WSMessage {
  type: 'progress'
  content: {
    step: string
    progress: number
    message: string
    details?: Record<string, any>
  }
}

// LLM 对话消息
export interface WSLLMChatMessage extends WSMessage {
  type: 'llm_chat'
  content: {
    role: 'assistant'
    message: string
    suggested_actions?: SuggestedAction[]
    issue_details?: IssueDetails
  }
}

// 完成消息
export interface WSCompletedMessage extends WSMessage {
  type: 'completed'
  content: {
    output_xlsx_path?: string
    output_pkl_path?: string
    results_summary?: {
      total: number
      success: number
      failed: number
    }
  }
}

// 失败消息
export interface WSFailedMessage extends WSMessage {
  type: 'failed'
  content: {
    error: string
  }
}

// 日志消息
export interface WSLogMessage extends WSMessage {
  type: 'log'
  content: {
    level: string
    node: string
    message: string
  }
}

// 失败列表消息
export interface WSFailedListMessage extends WSMessage {
  type: 'failed_list'
  content: {
    total: number
    failed_list: Array<{
      doi: string
      title: string
      error: string
    }>
    showing: number
  }
}