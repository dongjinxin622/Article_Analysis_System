// 批量提取相关类型
export interface BatchExtractionRequest {
  result_ids: string[]
  extraction_config: Record<string, any>
  enable_hitl?: boolean
  workflow_type?: string
}

export interface BatchExtractionResponse {
  success: boolean
  message: string
  task_id: string
  workflow_type?: string
  estimated_time?: number
}

export interface ExtractionCheckpoint {
  checkpoint_id: string
  step_name: string
  status: 'pending' | 'processing' | 'review_required' | 'approved' | 'rejected'
  data: Record<string, any>
  requires_review: boolean
  reviewed_at?: string
  reviewer_id?: string
  review_notes?: string
}

export interface CheckpointReviewRequest {
  action: 'approve' | 'reject' | 'modify'
  modifications?: Record<string, any>
  notes?: string
}

export interface CheckpointReviewResponse {
  success: boolean
  message: string
  checkpoint_id: string
  next_step?: string
}