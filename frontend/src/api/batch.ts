import { request } from './request'
import type { BatchTaskRequest, BatchTaskResponse, BatchTaskDetail, TaskProgress } from '@/types/task'
import type { BatchExtractionRequest } from '@/types/batch'

// API base URL for direct file downloads
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export interface BatchUploadResponse {
  success: boolean
  message: string
  files: Array<{
    file_name: string
    file_id?: string
    result_id?: string
    title?: string
    doi?: string
    status: string
    error?: string
    size?: number
  }>
  total: number
  success_count: number
  failed_count: number
}

export const batchApi = {
  // 批量上传 PDF 文件并解析
  batchUploadPdf(files: FormData): Promise<BatchUploadResponse> {
    return request.post('/batch/upload-pdf', files, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  },

  // 创建批量任务
  createBatchTask(data: BatchTaskRequest): Promise<BatchTaskResponse> {
    return request.post('/batch', data)
  },

  // 获取任务详情
  getTaskDetail(taskId: string): Promise<BatchTaskDetail> {
    return request.get(`/batch/${taskId}`)
  },

  // 取消任务
  cancelTask(taskId: string): Promise<{ success: boolean; message: string }> {
    return request.post(`/batch/${taskId}/cancel`)
  },

  // 获取任务进度
  getTaskProgress(taskId: string): Promise<TaskProgress> {
    return request.get(`/batch/${taskId}/progress`)
  },

  // 获取任务列表
  getTaskList(params?: { page?: number; page_size?: number }): Promise<{ items: BatchTaskDetail[]; total: number }> {
    return request.get('/batch', { params })
  },

  // 启动批量提取工作流
  startExtractionWorkflow(data: BatchExtractionRequest): Promise<BatchTaskResponse> {
    return request.post('/extraction', data)
  },

  // 获取检查点
  getCheckpoint(taskId: string) {
    return request.get(`/extraction/${taskId}/checkpoint`)
  },

  // 审核检查点
  reviewCheckpoint(taskId: string, action: string, modifications?: any) {
    return request.post(`/extraction/${taskId}/checkpoint/review`, { action, modifications })
  },

  // 批量下载结果 Excel（使用 fetch API 传递认证 token）
  async downloadBatchResultsExcel(taskId: string) {
    const token = localStorage.getItem('token')
    if (!token) {
      throw new Error('未登录，请先登录')
    }

    const url = `${API_BASE_URL}/batch/${taskId}/download`

    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`
      }
    })

    if (!response.ok) {
      if (response.status === 401) {
        throw new Error('认证失败，请重新登录')
      }
      const errorData = await response.json().catch(() => ({ detail: '下载失败' }))
      throw new Error(errorData.detail || '下载失败')
    }

    // 下载文件
    const blob = await response.blob()
    const downloadUrl = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = downloadUrl
    link.download = `${taskId}_results.xlsx`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(downloadUrl)
  }
}
