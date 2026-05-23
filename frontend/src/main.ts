import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import './assets/styles/variables.css'
import './assets/styles/common.css'

import App from './App.vue'
import router from './router'
import { setupAuthRefresh } from './api/request'

const app = createApp(App)
const pinia = createPinia()

// 注册所有图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(pinia)
app.use(router)
app.use(ElementPlus, { size: 'default', zIndex: 3000 })

app.mount('#app')

// 初始化 Token 自动刷新机制（在 pinia 激活后）
import { useUserStore } from '@/stores'
const userStore = useUserStore()
setupAuthRefresh(async () => {
  const success = await userStore.refreshAccessToken()
  return success ? userStore.token : null
})
