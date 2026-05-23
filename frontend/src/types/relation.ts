// 关系抽取相关类型
export interface RERequest {
  ner_id: string
  query_file: string
  task_name?: string
}

export interface REResponse {
  success: boolean
  message: string
  re_id?: string
  ner_id: string
  relation_count?: number
  re_json_path?: string
  re_excel_path?: string
}

export interface RelationInfo {
  relation_type: string
  source_type: string
  source_entity: string
  target_type: string
  target_entity: string
  effect?: string
  supporting_sentence?: string
  confidence?: number
}

export interface REResultDetail {
  re_id: string
  ner_id: string
  result_id: string
  relations: RelationInfo[]
  relation_count: number
  status: string
  created_at?: string
  processed_at?: string
}

export interface RelationGraph {
  nodes: any[]
  edges: any[]
}
