/**
 * Prompt模板管理 API
 */
import { request } from './request'

// 类型定义
export interface PromptTemplate {
  name: string
  content: string
  description?: string
  category: 'ner' | 're'
  domain?: string
  is_active: boolean
  user_id?: number | null  // 新增：null表示全局共享，有值表示用户私有
  created_at?: string
  updated_at?: string
}

export interface PromptTemplateList {
  templates: PromptTemplate[]
  total: number
}

export interface PromptCreateRequest {
  name: string
  content: string
  description?: string
  category: 'ner' | 're'
  domain?: string
}

export interface PromptUpdateRequest {
  content?: string
  description?: string
  is_active?: boolean
}

// API 函数
export const promptApi = {
  /**
   * 获取Prompt模板列表
   * @param category 分类筛选（ner/re）
   * @param domain 领域筛选
   */
  async list(category?: string, domain?: string): Promise<PromptTemplateList> {
    const params = new URLSearchParams()
    if (category) params.append('category', category)
    if (domain) params.append('domain', domain)
    const query = params.toString() ? `?${params.toString()}` : ''
    return request.get(`/config/prompts${query}`)
  },

  /**
   * 获取单个Prompt模板
   * @param name 模板名称
   */
  async get(name: string): Promise<PromptTemplate> {
    return request.get(`/config/prompts/${name}`)
  },

  /**
   * 创建Prompt模板
   * @param data 模板数据
   */
  async create(data: PromptCreateRequest): Promise<PromptTemplate> {
    return request.post('/config/prompts', data)
  },

  /**
   * 更新Prompt模板
   * @param name 模板名称
   * @param data 更新数据
   */
  async update(name: string, data: PromptUpdateRequest): Promise<PromptTemplate> {
    return request.put(`/config/prompts/${name}`, data)
  },

  /**
   * 删除Prompt模板
   * @param name 模板名称
   */
  async delete(name: string): Promise<{ success: boolean; message: string }> {
    return request.delete(`/config/prompts/${name}`)
  }
}

export default promptApi