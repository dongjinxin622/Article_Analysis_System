import { request } from './request'
import type {
  User, LoginRequest, LoginResponse, RegisterRequest,
  TokenRefreshRequest, TokenRefreshResponse,
  ProfileUpdateRequest, PasswordUpdateRequest,
  AdminUserUpdate, AvatarUpdateRequest,
} from '@/types/user'

export const userApi = {
  // === 认证 ===
  login(data: LoginRequest): Promise<LoginResponse> {
    return request.post('/users/login', data)
  },
  register(data: RegisterRequest): Promise<User> {
    return request.post('/users/register', data)
  },
  refreshToken(data: TokenRefreshRequest): Promise<TokenRefreshResponse> {
    return request.post('/users/refresh', data)
  },

  // === 个人中心 ===
  getCurrentUser(): Promise<User> {
    return request.get('/users/me')
  },
  updateProfile(data: ProfileUpdateRequest): Promise<User> {
    return request.put('/users/me/profile', data)
  },
  updatePassword(data: PasswordUpdateRequest): Promise<User> {
    return request.put('/users/me/password', data)
  },
  updateAvatar(data: AvatarUpdateRequest): Promise<User> {
    return request.put('/users/me/avatar', data)
  },
  uploadAvatar(formData: FormData): Promise<User> {
    return request.upload('/users/me/avatar/upload', formData)
  },

  // === 管理员 ===
  listUsers(): Promise<User[]> {
    return request.get('/users/')
  },
  getUserDetail(publicId: string): Promise<User> {
    return request.get(`/users/${publicId}`)
  },
  createUser(data: RegisterRequest): Promise<User> {
    return request.post('/users/', data)
  },
  updateUser(publicId: string, data: AdminUserUpdate): Promise<User> {
    return request.put(`/users/${publicId}`, data)
  },
  disableUser(publicId: string): Promise<User> {
    return request.patch(`/users/${publicId}/disable`)
  },
  deleteUser(publicId: string): Promise<void> {
    return request.delete(`/users/${publicId}`)
  },
}
