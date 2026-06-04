<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock, Message, UserFilled } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores'

const router = useRouter()
const userStore = useUserStore()

// 模式切换
const isLoginMode = ref(true)

// 登录表单
const loginFormRef = ref()
const loginForm = reactive({
  username: '',
  password: ''
})
const loginLoading = ref(false)
const loginRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

async function handleLogin() {
  if (loginLoading.value) return
  const valid = await loginFormRef.value?.validate().catch(() => false)
  if (!valid) return

  loginLoading.value = true
  try {
    const success = await userStore.login(loginForm)
    if (success) {
      ElMessage.success('登录成功')
      router.push('/')
    } else {
      ElMessage.error('用户名或密码错误')
    }
  } catch (error: any) {
    ElMessage.error(error.message || '登录失败')
  } finally {
    loginLoading.value = false
  }
}

// 注册表单
const registerFormRef = ref()
const registerForm = reactive({
  username: '',
  password: '',
  repassword: '',
  email: '',
  full_name: ''
})
const registerLoading = ref(false)

const validateRepassword = (_rule: any, value: string, callback: Function) => {
  if (value !== registerForm.password) {
    callback(new Error('两次密码不一致'))
  } else {
    callback()
  }
}

const registerRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '用户名长度 3-50 字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 100, message: '密码长度 6-100 字符', trigger: 'blur' }
  ],
  repassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    { validator: validateRepassword, trigger: 'blur' }
  ],
  email: [
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' }
  ]
}

async function handleRegister() {
  if (registerLoading.value) return
  const valid = await registerFormRef.value?.validate().catch(() => false)
  if (!valid) return

  registerLoading.value = true
  try {
    await userStore.register({
      username: registerForm.username,
      password: registerForm.password,
      repassword: registerForm.repassword,
      email: registerForm.email || undefined,
      full_name: registerForm.full_name || undefined
    })
    // 注册成功 → 自动登录
    const success = await userStore.login({
      username: registerForm.username,
      password: registerForm.password
    })
    if (success) {
      ElMessage.success('注册成功')
      router.push('/')
    } else {
      ElMessage.success('注册成功，请登录')
      switchToLogin()
    }
  } catch (error: any) {
    const msg = error?.response?.data?.detail || error?.message || '注册失败'
    ElMessage.error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  } finally {
    registerLoading.value = false
  }
}

function switchToLogin() {
  isLoginMode.value = true
}

function switchToRegister() {
  isLoginMode.value = false
}
</script>

<template>
  <div class="login-container">
    <div class="login-box">
      <div class="login-header">
        <h1>SciPDF AI</h1>
        <p>科学论文智能处理系统</p>
      </div>

      <!-- 登录模式 -->
      <template v-if="isLoginMode">
        <el-form
          ref="loginFormRef"
          :model="loginForm"
          :rules="loginRules"
          class="login-form"
        >
          <el-form-item prop="username">
            <el-input
              v-model="loginForm.username"
              placeholder="用户名"
              size="large"
              :prefix-icon="User"
            />
          </el-form-item>

          <el-form-item prop="password">
            <el-input
              v-model="loginForm.password"
              type="password"
              placeholder="密码"
              size="large"
              :prefix-icon="Lock"
              show-password
              @keyup.enter="handleLogin"
            />
          </el-form-item>

          <el-form-item>
            <el-button
              type="primary"
              size="large"
              :loading="loginLoading"
              class="login-button"
              @click="handleLogin"
            >
              登录
            </el-button>
          </el-form-item>
        </el-form>

        <!-- 注册功能暂时关闭 -->
        <!--
        <div class="switch-row">
          <span class="switch-text">没有账号？</span>
          <el-link type="primary" :underline="false" @click="switchToRegister">
            立即注册
          </el-link>
        </div>
        -->
      </template>

      <!-- 注册模式 -->
      <template v-else>
        <el-form
          ref="registerFormRef"
          :model="registerForm"
          :rules="registerRules"
          class="login-form"
        >
          <el-form-item prop="username">
            <el-input
              v-model="registerForm.username"
              placeholder="用户名"
              size="large"
              :prefix-icon="User"
            />
          </el-form-item>

          <el-form-item prop="password">
            <el-input
              v-model="registerForm.password"
              type="password"
              placeholder="密码"
              size="large"
              :prefix-icon="Lock"
              show-password
            />
          </el-form-item>

          <el-form-item prop="repassword">
            <el-input
              v-model="registerForm.repassword"
              type="password"
              placeholder="确认密码"
              size="large"
              :prefix-icon="Lock"
              show-password
            />
          </el-form-item>

          <el-form-item prop="email">
            <el-input
              v-model="registerForm.email"
              placeholder="邮箱（选填）"
              size="large"
              :prefix-icon="Message"
            />
          </el-form-item>

          <el-form-item prop="full_name">
            <el-input
              v-model="registerForm.full_name"
              placeholder="姓名（选填）"
              size="large"
              :prefix-icon="UserFilled"
            />
          </el-form-item>

          <el-form-item>
            <el-button
              type="primary"
              size="large"
              :loading="registerLoading"
              class="login-button"
              @click="handleRegister"
            >
              注册
            </el-button>
          </el-form-item>
        </el-form>

        <div class="switch-row">
          <span class="switch-text">已有账号？</span>
          <el-link type="primary" :underline="false" @click="switchToLogin">
            返回登录
          </el-link>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-dark) 100%);
}

.login-box {
  width: 420px;
  padding: 40px;
  background: var(--bg-card);
  border-radius: var(--border-radius-lg);
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.login-header h1 {
  font-size: 32px;
  color: var(--text-primary);
  margin-bottom: 10px;
}

.login-header p {
  font-size: 14px;
  color: var(--text-secondary);
}

.login-form {
  margin-bottom: 16px;
}

.login-form .el-input:focus-within {
  box-shadow: 0 0 0 2px var(--color-primary-light);
}

.login-button {
  width: 100%;
}

.switch-row {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 4px;
  font-size: 13px;
}

.switch-text {
  color: var(--text-secondary);
}
</style>
