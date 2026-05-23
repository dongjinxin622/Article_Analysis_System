// 论文相关类型
export interface ProcessingResult {
  result_id: string
  file_name: string
  title?: string
  doi?: string
  abstract?: string
  status: ProcessingStatus
  error_message?: string
  ner_status?: ProcessingStatus  // NER 处理状态
  re_status?: ProcessingStatus   // RE 处理状态
  created_at?: string
  processed_at?: string
}

export type ProcessingStatus = 'pending' | 'processing' | 'completed' | 'failed'

export interface Section {
  heading: string
  text: string
}

export interface PaperUploadResponse {
  success: boolean
  message: string
  result_id?: string
  file_name: string
  title?: string
  doi?: string
}

export interface ResultListResponse {
  total: number
  page: number
  page_size: number
  items: ProcessingResult[]
}

export interface ResultDetail extends ProcessingResult {
  sections: Section[]
  references: any[]
  figures: any[]
  result_pkl_path?: string
  result_json_path?: string
}
