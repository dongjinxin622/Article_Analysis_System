// 领域分析相关类型
export interface DomainConfigResponse {
  domain_name: string
  description?: string
  entity_types: Record<string, string>
  relation_types: Record<string, string>
  prompt_templates?: Record<string, string>
  is_active: boolean
}

export interface DomainListResponse {
  domains: string[]
  count: number
}

export interface TechRouteRequest {
  ner_id: string
  domain?: string
  top_k?: number
}

export interface TechRouteResponse {
  success: boolean
  message: string
  profile_text?: string
  profile_id?: string
  similar_papers: any[]
}

export interface ExpSchemeRequest {
  ner_id: string
  domain?: string
  top_k?: number
}

export interface ExpSchemeResponse {
  success: boolean
  message: string
  scheme_text?: string
  scheme_id?: string
  dimensions: Record<string, any>
  similar_papers: any[]
}

export interface JcSearchRequest {
  ner_id: string
  domain?: string
  temperature?: number
  magnetic_field?: number
  angle?: number
  top_k?: number
}

export interface JcIndicator {
  jc_value: number
  unit: string
  temperature?: number
  magnetic_field?: number
  angle?: number
  source_paper?: string
  source_sentence?: string
}

export interface JcSearchResponse {
  success: boolean
  message: string
  indicators: JcIndicator[]
  count: number
}

export interface JcCompareRequest {
  ner_ids: string[]
  domain?: string
}

export interface JcCompareResponse {
  success: boolean
  message: string
  comparison_table: any[]
  analysis_report?: string
}
