import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'
import { createModuleLogger } from '@/utils/logger'

const log = createModuleLogger('API')

// 创建 axios 实例
const api: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 300000, // 5分钟超时，用于大文件处理
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    // 记录请求日志
    log.info(`请求: ${config.method?.toUpperCase()} ${config.url}`, {
      params: config.params,
      data: config.data ? (typeof config.data === 'string' ? config.data.slice(0, 200) : 'FormData/Object') : null
    })
    return config
  },
  (error) => {
    log.error(`请求配置错误: ${error.message}`)
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  (response: AxiosResponse) => {
    // 记录成功响应日志
    log.info(`响应成功: ${response.config.method?.toUpperCase()} ${response.config.url}`, {
      status: response.status,
      dataSize: JSON.stringify(response.data).length
    })
    return response.data
  },
  (error) => {
    const { response } = error

    // 记录错误日志
    log.error(`响应错误: ${error.config?.method?.toUpperCase()} ${error.config?.url}`, {
      status: response?.status,
      message: response?.data?.detail || error.message,
      errorType: response?.data?.error_type,
      timestamp: response?.data?.timestamp
    })

    if (response) {
      switch (response.status) {
        case 401:
          ElMessage.error('登录已过期，请重新登录')
          localStorage.removeItem('token')
          router.push('/login')
          break
        case 403:
          ElMessage.error('没有权限执行此操作')
          break
        case 404:
          ElMessage.error('请求的资源不存在')
          break
        case 422:
          ElMessage.error(response.data?.detail || '请求参数错误')
          break
        case 500:
          ElMessage.error(`服务器错误: ${response.data?.detail || 'Internal Server Error'}`)
          break
        case 503:
          ElMessage.error('服务不可用')
          break
        default:
          ElMessage.error(response.data?.detail || '请求失败')
      }
    } else {
      ElMessage.error('网络连接失败')
    }

    return Promise.reject(error)
  }
)

// 扩展 axios 实例方法，添加泛型支持
export interface ApiResponse<T = any> {
  success: boolean
  message: string
  data?: T
}

export default api

// 通用请求方法
export const request = {
  get<T = any>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return api.get(url, config)
  },
  post<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    return api.post(url, data, config)
  },
  put<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    return api.put(url, data, config)
  },
  delete<T = any>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return api.delete(url, config)
  },
  upload<T = any>(url: string, formData: FormData, config?: AxiosRequestConfig): Promise<T> {
    return api.post(url, formData, {
      ...config,
      headers: {
        'Content-Type': 'multipart/form-data',
        ...config?.headers
      }
    })
  }
}
