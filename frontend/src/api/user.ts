import { request } from './request'
import type { User, LoginRequest, LoginResponse, RegisterRequest } from '@/types/user'

export const userApi = {
  // 用户登录
  login(data: LoginRequest): Promise<LoginResponse> {
    return request.post('/users/login', data)
  },

  // 用户注册
  register(data: RegisterRequest): Promise<User> {
    return request.post('/users/register', data)
  },

  // 获取当前用户信息
  getCurrentUser(): Promise<User> {
    return request.get('/users/me')
  },

  // 更新用户信息
  updateUser(data: { email?: string; full_name?: string; password?: string }): Promise<User> {
    return request.put('/users/me', data)
  }
}
