/**
 * Excel 批量提取 API 封装
 */
import { request } from './request'
import type {
  UploadPreviewResponse,
  TaskCreateResponse,
  TaskDetail,
  TaskListResponse,
  RowListResponse
} from '@/types/excel_extraction'

export const excelExtractionApi = {
  /**
   * 上传 Excel 文件并预览
   */
  async uploadFiles(files: File[], strategyFile?: File): Promise<UploadPreviewResponse> {
    const formData = new FormData()
    for (const file of files) {
      formData.append('files', file)
    }
    if (strategyFile) {
      formData.append('strategy_file', strategyFile)
    }

    return request.post('/excel-extraction/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },

  /**
   * 创建任务
   */
  createTask(data: {
    task_name: string
    session_id: string
    config: Record<string, any>
    upload_dir: string
    strategy_path?: string
  }): Promise<TaskCreateResponse> {
    return request.post('/excel-extraction/tasks', data)
  },

  /**
   * 获取任务列表
   */
  getTaskList(params?: { page?: number; page_size?: number }): Promise<TaskListResponse> {
    return request.get('/excel-extraction/tasks', { params })
  },

  /**
   * 获取任务详情
   */
  getTaskDetail(taskId: string): Promise<TaskDetail> {
    return request.get(`/excel-extraction/tasks/${taskId}`)
  },

  /**
   * 取消任务
   */
  cancelTask(taskId: string): Promise<{ success: boolean; message: string }> {
    return request.post(`/excel-extraction/tasks/${taskId}/cancel`)
  },

  /**
   * 获取行数据列表
   */
  getTaskRows(taskId: string, params?: { page?: number; page_size?: number; status?: string }): Promise<RowListResponse> {
    return request.get(`/excel-extraction/tasks/${taskId}/rows`, { params })
  },

  /**
   * 下载结果文件
   */
  async downloadResults(taskId: string): Promise<void> {
    const token = localStorage.getItem('token')
    const url = `/api/v1/excel-extraction/tasks/${taskId}/download`

    const response = await fetch(url, {
      headers: { 'Authorization': `Bearer ${token}` }
    })

    if (!response.ok) {
      throw new Error('下载失败')
    }

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