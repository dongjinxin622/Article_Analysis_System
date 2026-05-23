import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { BatchTaskDetail, TaskProgress, BatchTaskStatus } from '@/types'
import { batchApi } from '@/api'

export const useTaskStore = defineStore('task', () => {
  const tasks = ref<BatchTaskDetail[]>([])
  const currentTask = ref<BatchTaskDetail | null>(null)
  const taskProgress = ref<TaskProgress | null>(null)
  const loading = ref(false)

  // 创建批量任务
  async function createTask(data: {
    task_name: string
    result_ids: string[]
    config?: Record<string, any>
    enable_hitl?: boolean
  }) {
    loading.value = true
    try {
      const response = await batchApi.createBatchTask(data)
      return response
    } finally {
      loading.value = false
    }
  }

  // 获取任务详情
  async function fetchTaskDetail(taskId: string) {
    loading.value = true
    try {
      currentTask.value = await batchApi.getTaskDetail(taskId)
      return currentTask.value
    } finally {
      loading.value = false
    }
  }

  // 获取任务进度
  async function fetchTaskProgress(taskId: string) {
    taskProgress.value = await batchApi.getTaskProgress(taskId)
    return taskProgress.value
  }

  // 取消任务
  async function cancelTask(taskId: string) {
    loading.value = true
    try {
      await batchApi.cancelTask(taskId)
      if (currentTask.value?.task_id === taskId) {
        currentTask.value.status = 'cancelled' as BatchTaskStatus
      }
    } finally {
      loading.value = false
    }
  }

  // 获取任务列表
  async function fetchTasks(params?: { page?: number; page_size?: number }) {
    loading.value = true
    try {
      const response = await batchApi.getTaskList(params)
      tasks.value = response.items
      return response
    } finally {
      loading.value = false
    }
  }

  // 重置
  function reset() {
    tasks.value = []
    currentTask.value = null
    taskProgress.value = null
  }

  // 计算总体进度
  const overallProgress = computed(() => {
    if (!currentTask.value) return 0
    return currentTask.value.progress
  })

  return {
    tasks,
    currentTask,
    taskProgress,
    loading,
    overallProgress,
    createTask,
    fetchTaskDetail,
    fetchTaskProgress,
    cancelTask,
    fetchTasks,
    reset
  }
})
