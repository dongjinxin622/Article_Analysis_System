import { request } from './request'
import type { DomainListResponse, DomainConfigResponse, TechRouteRequest, TechRouteResponse, ExpSchemeRequest, ExpSchemeResponse, JcSearchRequest, JcSearchResponse } from '@/types/domain'

export const domainApi = {
  // 获取领域列表
  getDomainList(): Promise<DomainListResponse> {
    return request.get('/domains')
  },

  // 获取领域配置
  getDomainConfig(domainName: string): Promise<DomainConfigResponse> {
    return request.get(`/domains/${domainName}/config`)
  },

  // 技术路线分析
  analyzeTechRoute(domainName: string, data: TechRouteRequest): Promise<TechRouteResponse> {
    return request.post(`/domains/${domainName}/techroute`, data)
  },

  // 实验方案分析
  analyzeExpScheme(domainName: string, data: ExpSchemeRequest): Promise<ExpSchemeResponse> {
    return request.post(`/domains/${domainName}/expscheme`, data)
  },

  // Jc 指标搜索
  searchJcIndicators(domainName: string, data: JcSearchRequest): Promise<JcSearchResponse> {
    return request.post(`/domains/${domainName}/jc/search`, data)
  },

  // Jc 对比分析
  compareJc(domainName: string, nerIds: string[]) {
    return request.post(`/domains/${domainName}/jc/compare`, { ner_ids: nerIds })
  }
}
