// 任务相关类型
export type BatchTaskStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled'

export interface BatchTaskRequest {
  task_name: string
  result_ids: string[]
  config?: Record<string, any>
  enable_hitl?: boolean
}

export interface BatchTaskResponse {
  success: boolean
  message: string
  task_id: string
  status: BatchTaskStatus
  total_count: number
  processed_count?: number
}

export interface BatchTaskDetail {
  task_id: string
  task_name: string
  status: BatchTaskStatus
  total_count: number
  processed_count: number
  completed_count: number
  failed_count: number
  progress: number
  config?: Record<string, any>
  created_at?: string
  started_at?: string
  completed_at?: string
  error_message?: string
  results?: Record<string, any>[]
  errors?: Record<string, any>[]
}

export interface TaskProgress {
  task_id: string
  step: string
  progress: number
  message: string
  timestamp?: string
  current_file?: string
  total_files?: number
}

export interface BatchTaskListResponse {
  items: BatchTaskDetail[]
  total: number
  page: number
  page_size: number
}

export interface HITLCheckpoint {
  checkpoint_id: string
  step_name: string
  data: Record<string, any>
  requires_review: boolean
  reviewed: boolean
  review_result?: string
}

export interface BatchExtractionRequest {
  result_ids: string[]
  extraction_config: Record<string, any>
  enable_hitl?: boolean
  workflow_type?: string
}
