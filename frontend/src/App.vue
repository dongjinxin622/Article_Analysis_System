<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const isCollapse = ref(false)
const SIDEBAR_WIDTH = '200px'
const SIDEBAR_WIDTH_COLLAPSED = '64px'

const handleCommand = (command: string) => {
  if (command === 'settings') {
    router.push('/settings')
  } else if (command === 'logout') {
    userStore.logout()
    router.push('/login')
  }
}

const menuItems = [
  { path: '/', icon: 'House', title: '首页' },
  { path: '/pdf', icon: 'Document', title: 'PDF处理' },
  { path: '/ner', icon: 'Aim', title: 'NER处理' },
  { path: '/re', icon: 'Connection', title: '关系抽取' },
  { path: '/pdf-batch', icon: 'Files', title: 'PDF批量提取' },
  { path: '/excel-batch', icon: 'Grid', title: '题录批量评估' },
  { path: '/domain', icon: 'DataAnalysis', title: 'REBCO领域分析' },
  { path: '/settings', icon: 'Setting', title: '系统设置' },
  { path: '/logs', icon: 'Notebook', title: '日志查看' }
]

onMounted(() => {
  // 检查登录状态
  userStore.checkAuth()
})
</script>

<template>
  <el-container class="app-container">
    <el-aside :width="isCollapse ? SIDEBAR_WIDTH_COLLAPSED : SIDEBAR_WIDTH" class="app-aside">
      <div class="logo">
        <el-icon v-if="isCollapse" :size="24"><Reading /></el-icon>
        <span v-else class="logo-text">SciPDF AI</span>
      </div>
      <el-menu
        :default-active="$route.path"
        :collapse="isCollapse"
        router
        class="app-menu"
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409eff"
      >
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.title }}</template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="app-header">
        <div class="header-left">
          <el-icon class="collapse-icon" @click="isCollapse = !isCollapse">
            <Fold v-if="!isCollapse" />
            <Expand v-else />
          </el-icon>
        </div>
        <div class="header-right">
          <el-dropdown @command="handleCommand">
            <span class="user-info">
              <el-icon><User /></el-icon>
              <span>{{ userStore.user?.username || '未登录' }}</span>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="settings">系统设置</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="app-main">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.app-container {
  height: 100vh;
}

.app-aside {
  background-color: var(--bg-sidebar);
  transition: width 0.3s;
  overflow: hidden;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 20px;
  font-weight: bold;
  background-color: var(--bg-sidebar-hover);
}

.logo-text {
  white-space: nowrap;
}

.app-menu {
  border-right: none;
}

/* 选中态增加左侧竖条指示器 */
.app-menu .el-menu-item.is-active {
  border-left: 3px solid var(--color-primary) !important;
  padding-left: calc(var(--spacing-md) - 3px) !important;
}

.app-header {
  background-color: #fff;
  box-shadow: var(--shadow-sm);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--page-padding);
}

.header-left {
  display: flex;
  align-items: center;
}

.collapse-icon {
  font-size: 20px;
  cursor: pointer;
  color: var(--text-regular);
}

.collapse-icon:hover {
  color: var(--color-primary);
}

.header-right {
  display: flex;
  align-items: center;
}

.user-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  cursor: pointer;
  color: var(--text-regular);
}

.user-info:hover {
  color: var(--color-primary);
}

.app-main {
  background-color: var(--bg-page);
  padding: var(--page-padding);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
