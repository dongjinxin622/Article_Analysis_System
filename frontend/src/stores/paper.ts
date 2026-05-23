import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ProcessingResult, ResultListResponse, ResultDetail } from '@/types'
import { pdfApi } from '@/api'

export const usePaperStore = defineStore('paper', () => {
  const papers = ref<ProcessingResult[]>([])
  const currentPaper = ref<ResultDetail | null>(null)
  const loading = ref(false)
  const total = ref(0)
  const currentPage = ref(1)
  const pageSize = ref(10)

  // 获取论文列表
  async function fetchPapers(params?: { page?: number; page_size?: number; status?: string }) {
    loading.value = true
    try {
      const response: ResultListResponse = await pdfApi.getPaperList({
        page: params?.page || currentPage.value,
        page_size: params?.page_size || pageSize.value,
        status: params?.status
      })
      papers.value = response.items
      total.value = response.total
      currentPage.value = response.page
      return response
    } finally {
      loading.value = false
    }
  }

  // 获取论文详情
  async function fetchPaperDetail(resultId: string) {
    loading.value = true
    try {
      currentPaper.value = await pdfApi.getPaperDetail(resultId)
      return currentPaper.value
    } finally {
      loading.value = false
    }
  }

  // 上传论文
  async function uploadPaper(file: File) {
    loading.value = true
    try {
      const response = await pdfApi.uploadPaper(file)
      return response
    } finally {
      loading.value = false
    }
  }

  // 删除论文
  async function deletePaper(resultId: string) {
    loading.value = true
    try {
      await pdfApi.deletePaper(resultId)
      papers.value = papers.value.filter(p => p.result_id !== resultId)
    } finally {
      loading.value = false
    }
  }

  // 重置状态
  function reset() {
    papers.value = []
    currentPaper.value = null
    total.value = 0
    currentPage.value = 1
  }

  return {
    papers,
    currentPaper,
    loading,
    total,
    currentPage,
    pageSize,
    fetchPapers,
    fetchPaperDetail,
    uploadPaper,
    deletePaper,
    reset
  }
})
