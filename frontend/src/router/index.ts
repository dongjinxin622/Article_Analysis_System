import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/Home.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/pdf',
    name: 'PDFProcessor',
    component: () => import('@/views/PDFProcessor.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/ner',
    name: 'NERProcessor',
    component: () => import('@/views/NERProcessor.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/re',
    name: 'REProcessor',
    component: () => import('@/views/REProcessor.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/pdf-batch',
    name: 'PdfBatchExtraction',
    component: () => import('@/views/PdfBatchExtraction.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/excel-batch',
    name: 'ExcelBatchExtraction',
    component: () => import('@/views/ExcelBatchExtraction.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/domain',
    name: 'DomainAnalysis',
    component: () => import('@/views/DomainAnalysis.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('@/views/Settings.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/tasks',
    name: 'Tasks',
    component: () => import('@/views/Tasks.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/logs',
    name: 'LogViewer',
    component: () => import('@/views/LogViewer.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/user',
    redirect: '/settings'
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫
router.beforeEach(async (to, from, next) => {
  const userStore = useUserStore()
  const requiresAuth = to.meta.requiresAuth !== false

  // 已登录用户访问登录页，重定向到首页
  if (to.path === '/login') {
    if (userStore.isAuthenticated) {
      next('/')
      return
    }
    next()
    return
  }

  // 需要认证但未登录
  if (requiresAuth && !userStore.isAuthenticated) {
    const token = localStorage.getItem('token')
    if (token) {
      // 有 token 但未验证，尝试验证
      const isValid = await userStore.checkAuth()
      if (isValid) {
        next()
        return
      }
    }
    next('/login')
    return
  }

  next()
})

export default router
