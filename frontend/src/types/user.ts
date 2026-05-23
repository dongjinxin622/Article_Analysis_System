// 用户相关类型
export interface User {
  public_id: string
  username: string
  nickname?: string
  email?: string
  avatar_url?: string
  is_superuser: boolean
  disabled: boolean
  created_at?: string
  last_login_at?: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  success: boolean
  message: string
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user?: User
}

export interface RegisterRequest {
  username: string
  password: string
  repassword: string
  email?: string
  full_name?: string
}

export interface AdminUserUpdate {
  username?: string
  email?: string
  nickname?: string
  avatar_url?: string
  password?: string
  sort_order?: number
  is_superuser?: boolean
  disabled_at?: string | null
}

export interface AvatarUpdateRequest {
  avatar_url: string
}

export interface TokenRefreshRequest {
  refresh_token: string
}

export interface TokenRefreshResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface ProfileUpdateRequest {
  email?: string
  full_name?: string
}

export interface PasswordUpdateRequest {
  old_password: string
  new_password: string
  confirm_password: string
}
