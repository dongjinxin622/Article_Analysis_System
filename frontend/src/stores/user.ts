import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User, LoginRequest } from '@/types'
import { userApi } from '@/api'

export const useUserStore = defineStore('user', () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('token'))
  const isAuthenticated = computed(() => !!token.value)

  // 检查登录状态
  async function checkAuth() {
    if (!token.value) return false
    try {
      const userData = await userApi.getCurrentUser()
      user.value = userData
      return true
    } catch {
      logout()
      return false
    }
  }

  // 登录
  async function login(credentials: LoginRequest) {
    const response = await userApi.login(credentials)
    if (response.success && response.token) {
      token.value = response.token.access_token
      user.value = response.user || null
      localStorage.setItem('token', response.token.access_token)
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

  // 登出
  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
  }

  return {
    user,
    token,
    isAuthenticated,
    checkAuth,
    login,
    register,
    logout
  }
})
