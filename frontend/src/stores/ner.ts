import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { NERResultDetail, EntityInfo, NERResponse, NERResultListItem, NERResultListResponse } from '@/types/ner'
import { nerApi } from '@/api'

export const useNerStore = defineStore('ner', () => {
  const nerResults = ref<NERResultDetail[]>([])
  const nerResultList = ref<NERResultListItem[]>([])
  const currentNer = ref<NERResultDetail | null>(null)
  const entities = ref<EntityInfo[]>([])
  const loading = ref(false)
  const total = ref(0)
  const nerListTotal = ref(0)

  // 获取 NER 结果列表
  async function fetchNERResultList(params?: { page?: number; page_size?: number }) {
    loading.value = true
    try {
      const response: NERResultListResponse = await nerApi.getNERResultList(params)
      nerResultList.value = response.items
      nerListTotal.value = response.total
      return response
    } finally {
      loading.value = false
    }
  }

  // 执行 NER
  async function executeNER(resultId: string, queryFile: string, options?: {
    skip_introduction?: boolean
    sentence_group_size?: number
    task_name?: string
  }) {
    loading.value = true
    try {
      const response: NERResponse = await nerApi.executeNER({
        result_id: resultId,
        query_file: queryFile,
        ...options
      })
      return response
    } finally {
      loading.value = false
    }
  }

  // 获取 NER 结果详情
  async function fetchNERResult(nerId: string) {
    loading.value = true
    try {
      currentNer.value = await nerApi.getNERResult(nerId)
      if (currentNer.value) {
        entities.value = currentNer.value.entities
      }
      return currentNer.value
    } finally {
      loading.value = false
    }
  }

  // 获取实体列表
  async function fetchEntities(nerId: string, params?: { entity_type?: string; limit?: number }) {
    loading.value = true
    try {
      const response = await nerApi.getEntities(nerId, params)
      entities.value = response.entities
      total.value = response.total
      return response
    } finally {
      loading.value = false
    }
  }

  // 下载 Excel
  async function downloadExcel(nerId: string) {
    const blob = await nerApi.downloadExcel(nerId)
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${nerId}.xlsx`
    link.click()
    window.URL.revokeObjectURL(url)
  }

  // 下载 PKL
  async function downloadPkl(nerId: string) {
    const blob = await nerApi.downloadPkl(nerId)
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${nerId}.pkl`
    link.click()
    window.URL.revokeObjectURL(url)
  }

  // 重置状态
  function reset() {
    nerResults.value = []
    nerResultList.value = []
    currentNer.value = null
    entities.value = []
    total.value = 0
    nerListTotal.value = 0
  }

  return {
    nerResults,
    nerResultList,
    currentNer,
    entities,
    loading,
    total,
    nerListTotal,
    fetchNERResultList,
    executeNER,
    fetchNERResult,
    fetchEntities,
    downloadExcel,
    downloadPkl,
    reset
  }
})