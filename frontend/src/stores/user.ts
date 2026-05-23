import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User, LoginRequest, ProfileUpdateRequest, PasswordUpdateRequest } from '@/types'
import { userApi } from '@/api'
import router from '@/router'

export const useUserStore = defineStore('user', () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('token'))
  const refreshToken = ref<string | null>(localStorage.getItem('refresh_token'))
  const isAuthenticated = computed(() => !!token.value)

  // 检查登录状态
  async function checkAuth() {
    if (!token.value) return false
    try {
      const userData = await userApi.getCurrentUser()
      user.value = userData
      return true
    } catch {
      // 尝试用 refresh token 刷新
      if (refreshToken.value) {
        const refreshed = await refreshAccessToken()
        if (refreshed) {
          return await checkAuth()
        }
      }
      logout()
      return false
    }
  }

  // 登录
  async function login(credentials: LoginRequest) {
    const response = await userApi.login(credentials)
    if (response.success && response.access_token) {
      token.value = response.access_token
      refreshToken.value = response.refresh_token
      user.value = response.user || null
      localStorage.setItem('token', response.access_token)
      localStorage.setItem('refresh_token', response.refresh_token)
      return true
    }
    return false
  }

  // 注册
  async function register(data: { username: string; password: string; email?: string; full_name?: string }) {
    const userData = await userApi.register(data)
    user.value = userData
    return userData
  }

  // 刷新 Access Token
  async function refreshAccessToken(): Promise<boolean> {
    if (!refreshToken.value) return false
    try {
      const response = await userApi.refreshToken({ refresh_token: refreshToken.value })
      token.value = response.access_token
      localStorage.setItem('token', response.access_token)
      return true
    } catch {
      logout()
      return false
    }
  }

  // 更新用户资料
  async function updateProfile(data: ProfileUpdateRequest) {
    const updated = await userApi.updateProfile(data)
    user.value = updated
    return updated
  }

  // 修改密码
  async function updatePassword(data: PasswordUpdateRequest) {
    await userApi.updatePassword(data)
  }

  // 登出
  function logout() {
    token.value = null
    refreshToken.value = null
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('refresh_token')
    router.push('/login')
  }

  return {
    user,
    token,
    refreshToken,
    isAuthenticated,
    checkAuth,
    login,
    register,
    logout,
    refreshAccessToken,
    updateProfile,
    updatePassword,
  }
})
