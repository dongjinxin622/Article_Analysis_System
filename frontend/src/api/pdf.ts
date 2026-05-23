import { request } from './request'
import type { PaperUploadResponse, ProcessingResult, ResultListResponse, ResultDetail } from '@/types/paper'

export const pdfApi = {
  // 上传 PDF 文件
  uploadPaper(file: File): Promise<PaperUploadResponse> {
    const formData = new FormData()
    formData.append('file', file)
    return request.upload('/papers', formData)
  },

  // 获取论文列表
  getPaperList(params: {
    page?: number
    page_size?: number
    status?: string
  }): Promise<ResultListResponse> {
    return request.get('/papers', { params })
  },

  // 获取论文详情
  getPaperDetail(resultId: string): Promise<ResultDetail> {
    return request.get(`/papers/${resultId}`)
  },

  // 删除论文
  deletePaper(resultId: string): Promise<{ success: boolean; message: string }> {
    return request.delete(`/papers/${resultId}`)
  },

  // 获取解析状态
  getProcessingStatus(resultId: string): Promise<{ status: string; progress: number }> {
    return request.get(`/papers/${resultId}/status`)
  }
}
