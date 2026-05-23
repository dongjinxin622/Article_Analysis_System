// NER 相关类型
export interface NERRequest {
  result_id: string
  query_file: string
  skip_introduction?: boolean
  sentence_group_size?: number
  task_name?: string
}

export interface NERResponse {
  success: boolean
  message: string
  ner_id?: string
  result_id: string
  entity_count?: number
  ner_json_path?: string
  ner_excel_path?: string
  ner_pkl_path?: string
  group_count?: number
}

export interface EntityInfo {
  entity_type: string
  entity_text: string
  start_pos: number
  end_pos: number
  confidence?: number
  section_idx?: number
  group_idx?: number
  sentence_idx?: number
}

export interface NERResultDetail {
  ner_id: string
  result_id: string
  entities: EntityInfo[]
  entity_count: number
  status: string
  created_at?: string
  processed_at?: string
}

export interface NERResultListItem {
  ner_id: string
  result_id: string
  entity_count: number
  status: string
  re_status?: string
  created_at?: string
}

export interface NERResultListResponse {
  total: number
  items: NERResultListItem[]
}

export interface NERBatchRequest {
  result_ids: string[]
  query_file: string
  skip_introduction?: boolean
  sentence_group_size?: number
}

export interface NERBatchResponse {
  success: boolean
  message: string
  task_id: string
  total_count: number
  results: NERResponse[]
}
