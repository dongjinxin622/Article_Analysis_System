import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { REResultDetail, RelationInfo, REResponse } from '@/types/relation'
import { reApi } from '@/api'

export const useReStore = defineStore('re', () => {
  const reResults = ref<REResultDetail[]>([])
  const currentRe = ref<REResultDetail | null>(null)
  const relations = ref<RelationInfo[]>([])
  const loading = ref(false)
  const total = ref(0)

  // 执行 RE
  async function executeRE(nerId: string, queryFile: string, taskName?: string) {
    loading.value = true
    try {
      const response: REResponse = await reApi.executeRE({
        ner_id: nerId,
        query_file: queryFile,
        task_name: taskName
      })
      return response
    } finally {
      loading.value = false
    }
  }

  // 获取 RE 结果详情
  async function fetchREResult(reId: string) {
    loading.value = true
    try {
      currentRe.value = await reApi.getREResult(reId)
      if (currentRe.value) {
        relations.value = currentRe.value.relations
      }
      return currentRe.value
    } finally {
      loading.value = false
    }
  }

  // 获取关系列表
  async function fetchRelations(reId: string, params?: { relation_type?: string }) {
    loading.value = true
    try {
      const response = await reApi.getRelations(reId, params)
      relations.value = response.relations
      total.value = response.total
      return response
    } finally {
      loading.value = false
    }
  }

  // 根据 NER ID 获取 RE 结果
  async function fetchREByNERId(nerId: string) {
    loading.value = true
    try {
      currentRe.value = await reApi.getREByNERId(nerId)
      if (currentRe.value) {
        relations.value = currentRe.value.relations
      }
      return currentRe.value
    } catch (error) {
      // 可能没有对应的 RE 结果
      currentRe.value = null
      relations.value = []
      return null
    } finally {
      loading.value = false
    }
  }

  // 下载 Excel
  async function downloadExcel(reId: string) {
    const blob = await reApi.downloadExcel(reId)
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${reId}.xlsx`
    link.click()
    window.URL.revokeObjectURL(url)
  }

  // 重置状态
  function reset() {
    reResults.value = []
    currentRe.value = null
    relations.value = []
    total.value = 0
  }

  return {
    reResults,
    currentRe,
    relations,
    loading,
    total,
    executeRE,
    fetchREResult,
    fetchRelations,
    fetchREByNERId,
    downloadExcel,
    reset
  }
})