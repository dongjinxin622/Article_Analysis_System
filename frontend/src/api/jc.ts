/**
 * Jc 数据库搜索 API
 * 直接搜索云端 MySQL 历史数据，无需 NER ID
 */
import request from './request'

// API 响应类型
export interface JcDatabaseSearchResult {
  doi: string
  title?: string
  temperature_K?: number
  magnetic_field_T?: number
  angle_deg?: number
  jc_value?: number
  jc_unit: string
  class1_temp_field?: string
  method?: string
  thickness?: string
  substrate?: string
}

export interface JcDatabaseSearchResponse {
  success: boolean
  message: string
  search_conditions: Record<string, any>
  results: JcDatabaseSearchResult[]
  count: number
}

export interface JcDatabaseRankResponse {
  success: boolean
  message: string
  target_doi: string
  target_jc_max?: number
  target_rank?: number
  total_papers: number
  best_jc_max?: number
  rank_percentile?: number
  top_10: Array<{ doi: string; jc_max: number }>
  search_conditions: Record<string, any>
}

export interface JcDatabaseStatsResponse {
  success: boolean
  message: string
  statistics: {
    total_records: number
    unique_dois: number
  }
}

// 搜索请求参数
export interface JcDatabaseSearchRequest {
  temperature?: number
  magnetic_field?: number
  angle?: number
  top_k?: number
  min_jc?: number
  temp_tolerance?: number
  field_tolerance?: number
  angle_tolerance?: number
}

export interface JcDatabaseRankRequest {
  target_doi: string
  temperature?: number
  magnetic_field?: number
  angle?: number
  temp_tolerance?: number
  field_tolerance?: number
  angle_tolerance?: number
}

// API 函数
export const jcApi = {
  /**
   * 获取 Jc 数据库统计信息
   */
  async getStats(): Promise<JcDatabaseStatsResponse> {
    return request.get('/jc/stats')
  },

  /**
   * 搜索 Jc 数据库
   */
  async search(params: JcDatabaseSearchRequest): Promise<JcDatabaseSearchResponse> {
    return request.post('/jc/search', params)
  },

  /**
   * 计算 DOI 的 Jc 排名
   */
  async rank(params: JcDatabaseRankRequest): Promise<JcDatabaseRankResponse> {
    return request.post('/jc/rank', params)
  },

  /**
   * 获取 Jc 排名靠前的 DOI 列表
   */
  async getTopDois(topK: number = 20, temperature?: number, magneticField?: number): Promise<{
    success: boolean
    message: string
    results: Array<{
      rank: number
      doi: string
      title?: string
      jc_max?: number
      avg_temperature?: number
      avg_magnetic_field?: number
    }>
  }> {
    const params: Record<string, any> = { top_k: topK }
    if (temperature !== undefined) params.temperature = temperature
    if (magneticField !== undefined) params.magnetic_field = magneticField
    return request.get('/jc/top-dois', { params })
  }
}

export default jcApi