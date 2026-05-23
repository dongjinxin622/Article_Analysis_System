import { request } from './request'
import type { RERequest, REResponse, REResultDetail, RelationInfo } from '@/types/relation'

export const reApi = {
  // 执行关系抽取（长时间处理，增加超时）
  executeRE(data: RERequest): Promise<REResponse> {
    return request.post('/re', data, { timeout: 600000 }) // 10分钟超时
  },

  // 获取 RE 结果详情
  getREResult(reId: string): Promise<REResultDetail> {
    return request.get(`/re/${reId}`)
  },

  // 获取关系列表
  getRelations(reId: string, params?: { relation_type?: string }): Promise<{ relations: RelationInfo[]; total: number }> {
    return request.get(`/re/${reId}/relations`, { params })
  },

  // 下载 Excel
  downloadExcel(reId: string): Promise<Blob> {
    return request.get(`/re/${reId}/excel`, { responseType: 'blob' })
  },

  // 根据 NER ID 获取 RE 结果
  getREByNERId(nerId: string): Promise<REResultDetail> {
    return request.get(`/re/by-ner/${nerId}`)
  }
}
