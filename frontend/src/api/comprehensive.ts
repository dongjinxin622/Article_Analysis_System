/**
 * 综合分析 API
 * 整合 PDF → NER → RE → 技术路线 → 实验方案 → Jc → 报告
 */
import { request } from './request'

// API 响应类型
export interface ComprehensiveAnalysisRequest {
  ner_id?: string
  pdf_result_id?: string
  top_k?: number
}

export interface ComprehensiveAnalysisResponse {
  success: boolean
  message: string
  task_id: string
  status: string
}

export interface OneClickResponse {
  success: boolean
  message: string
  task_id: string
  status: string
}

export interface TaskStatusResponse {
  task_id: string
  task_type: string
  status: string
  progress: number
  current_step: string
  message: string
  result?: ComprehensiveResult
  error?: string
  created_at?: number
  updated_at?: number
}

export interface TaskListItem {
  task_id: string
  task_type: string
  status: string
  progress: number
  current_step: string
  message: string
  created_at?: number
  updated_at?: number
}

export interface TaskListResponse {
  total: number
  tasks: TaskListItem[]
}

export interface ComprehensiveStatusResponse {
  task_id: string
  status: string
  progress: number
  current_step: string
  message: string
  result?: ComprehensiveResult
}

export interface ComprehensiveResult {
  success: boolean
  message: string
  pdf_info: {
    result_id?: string
    ner_id?: string
    re_id?: string
    doi?: string
    title?: string
    file_name?: string
    ner_query_file?: string
    re_query_file?: string
    ner_entity_count?: number
    re_relation_count?: number
    ner_json_path?: string
    ner_excel_path?: string
    re_json_path?: string
    re_excel_path?: string
  }
  tech_route: {
    success: boolean
    message: string
    tech_route_text: string
    similar_papers: Array<{
      doi: string
      title?: string
      score: number
    }>
    similar_count: number
  }
  exp_scheme: {
    success: boolean
    message: string
    exp_scheme_text: string
    dimensions: Record<string, string[]>
    similar_papers: Array<{
      doi: string
      title?: string
      score: number
    }>
    similar_count: number
  }
  jc_analysis: {
    success: boolean
    message: string
    jc_indicators: Array<{
      jc_value: number
      entity_text: string
    }>
    conditions: {
      temperature?: number
      magnetic_field?: number
      angle?: number
    }
    database_search: Record<string, any>
    ranking: Record<string, any>
  }
  llm_comparison: string
  report_path?: string
  report_paths?: {
    markdown?: string
    excel?: string
    pdf?: string
  }
}

export interface ReportExportResponse {
  success: boolean
  message: string
  file_path?: string
  download_url?: string
}

export interface ReportListResponse {
  task_id: string
  reports: Array<{
    format: string
    file_path: string
    download_url: string
    file_size: number
  }>
  total: number
}

// API 函数
export const comprehensiveApi = {
  /**
   * 一键处理 PDF（上传并自动完成全流程）
   */
  async oneClickAnalyze(
    file: File,
    options?: {
      top_k?: number
      ner_query_file?: string
      re_query_file?: string
    }
  ): Promise<OneClickResponse> {
    const formData = new FormData()
    formData.append('file', file)
    if (options?.top_k) formData.append('top_k', String(options.top_k))
    if (options?.ner_query_file) formData.append('ner_query_file', options.ner_query_file)
    if (options?.re_query_file) formData.append('re_query_file', options.re_query_file)
    return request.upload('/comprehensive/one-click', formData)
  },

  /**
   * 获取用户任务列表
   */
  async getTaskList(): Promise<TaskListResponse> {
    return request.get('/comprehensive/tasks')
  },

  /**
   * 获取活跃任务列表（正在运行的任务）
   */
  async getActiveTasks(): Promise<TaskListResponse> {
    return request.get('/comprehensive/active')
  },

  /**
   * 查询任务状态
   */
  async getStatus(taskId: string): Promise<TaskStatusResponse> {
    return request.get(`/comprehensive/status/${taskId}`)
  },

  /**
   * 删除任务
   */
  async deleteTask(taskId: string): Promise<{ success: boolean; message: string }> {
    return request.delete(`/comprehensive/task/${taskId}`)
  },

  /**
   * 下载分析报告
   * @param taskId 任务 ID
   * @param format 报告格式：md/excel/pdf
   */
  getReportDownloadUrl(taskId: string, format: string): string {
    return `/api/v1/comprehensive/report/${taskId}?format=${format}`
  },

  /**
   * 获取任务报告列表
   */
  async getReportList(taskId: string): Promise<ReportListResponse> {
    return request.get(`/comprehensive/report/list/${taskId}`)
  },

  /**
   * 导出报告
   */
  async exportReport(taskId: string, format: string): Promise<ReportExportResponse> {
    return request.post('/comprehensive/report/export', { task_id: taskId, format })
  }
}

export default comprehensiveApi