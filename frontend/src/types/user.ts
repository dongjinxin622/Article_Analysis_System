// 用户相关类型
export interface User {
  id: number
  username: string
  email?: string
  full_name?: string
  is_active: boolean
  is_admin: boolean
  created_at?: string
  last_login?: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  success: boolean
  message: string
  token?: {
    access_token: string
    expires_in: number
  }
  user?: User
}

export interface RegisterRequest {
  username: string
  password: string
  email?: string
  full_name?: string
}

export interface Token {
  access_token: string
  token_type: string
  expires_in: number
}
