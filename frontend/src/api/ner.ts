import { request } from './request'
import type { NERRequest, NERResponse, NERResultDetail, EntityInfo, NERBatchRequest, NERBatchResponse, NERResultListResponse } from '@/types/ner'

export const nerApi = {
  // 执行 NER（长时间处理，增加超时）
  executeNER(data: NERRequest): Promise<NERResponse> {
    return request.post('/ner', data, { timeout: 600000 }) // 10分钟超时
  },

  // 获取 NER 结果列表
  getNERResultList(params?: { page?: number; page_size?: number }): Promise<NERResultListResponse> {
    return request.get('/ner/list', { params })
  },

  // 获取 NER 结果详情
  getNERResult(nerId: string): Promise<NERResultDetail> {
    return request.get(`/ner/${nerId}`)
  },

  // 获取实体列表
  getEntities(nerId: string, params?: { entity_type?: string; limit?: number }): Promise<{ entities: EntityInfo[]; total: number }> {
    return request.get(`/ner/${nerId}/entities`, { params })
  },

  // 下载 Excel
  downloadExcel(nerId: string): Promise<Blob> {
    return request.get(`/ner/${nerId}/excel`, { responseType: 'blob' })
  },

  // 下载 PKL
  downloadPkl(nerId: string): Promise<Blob> {
    return request.get(`/ner/${nerId}/pkl`, { responseType: 'blob' })
  },

  // 批量 NER
  batchNER(data: NERBatchRequest): Promise<NERBatchResponse> {
    return request.post('/ner/batch', data)
  }
}
