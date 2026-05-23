<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { usePaperStore } from '@/stores'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadFile } from 'element-plus'
import type { ResultDetail } from '@/types'

const paperStore = usePaperStore()
const uploading = ref(false)
const uploadProgress = ref(0)

// 详情弹窗
const detailDialogVisible = ref(false)
const currentDetail = ref<ResultDetail | null>(null)
const detailLoading = ref(false)

// 摘要截断控制
const abstractExpanded = ref(false)
const ABSTRACT_TRUNCATE_LENGTH = 300

/** 截断后的摘要文本 */
const truncatedAbstract = computed(() => {
  const text = currentDetail.value?.abstract || '无摘要'
  if (text.length <= ABSTRACT_TRUNCATE_LENGTH) return text
  return abstractExpanded.value ? text : text.slice(0, ABSTRACT_TRUNCATE_LENGTH) + '...'
})

/** 是否需要截断 */
const needsTruncation = computed(() => {
  const text = currentDetail.value?.abstract || ''
  return text.length > ABSTRACT_TRUNCATE_LENGTH
})

/** 切换摘要展开/收起 */
function toggleAbstract() {
  abstractExpanded.value = !abstractExpanded.value
}

/** 复制摘要到剪贴板 */
async function copyAbstract() {
  const text = currentDetail.value?.abstract || ''
  if (!text) {
    ElMessage.warning('暂无摘要内容')
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('摘要已复制到剪贴板')
  } catch {
    // clipboard API 不可用时降级处理
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    ElMessage.success('摘要已复制到剪贴板')
  }
}

// 文件上传处理
async function handleFileUpload(uploadFile: UploadFile) {
  const file = uploadFile.raw

  if (!file) return

  if (!file.name.toLowerCase().endsWith('.pdf')) {
    ElMessage.error('只能上传 PDF 文件')
    return
  }

  if (file.size > 100 * 1024 * 1024) {
    ElMessage.error('文件大小不能超过 100MB')
    return
  }

  uploading.value = true
  uploadProgress.value = 0

  try {
    const response = await paperStore.uploadPaper(file)

    if (response.success) {
      ElMessage.success('文件上传成功，正在解析...')
      // 刷新列表
      await paperStore.fetchPapers()
    } else {
      ElMessage.error(response.message || '上传失败')
    }
  } catch (error: any) {
    ElMessage.error(error.message || '上传失败')
  } finally {
    uploading.value = false
    uploadProgress.value = 0
  }
}

// 删除论文
async function handleDelete(row: any) {
  try {
    await ElMessageBox.confirm('确定要删除这篇论文吗？', '提示', {
      type: 'warning'
    })

    await paperStore.deletePaper(row.result_id)
    ElMessage.success('删除成功')
  } catch (error) {
    // 用户取消删除
  }
}

// 查看详情
async function handleView(row: any) {
  detailLoading.value = true
  detailDialogVisible.value = true
  // 每次打开弹窗时重置截断状态
  abstractExpanded.value = false
  try {
    currentDetail.value = await paperStore.fetchPaperDetail(row.result_id)
  } catch (error: any) {
    ElMessage.error('获取详情失败: ' + error.message)
    detailDialogVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

// 下载 JSON 结果
function downloadJson() {
  if (!currentDetail.value) return
  const data = JSON.stringify(currentDetail.value, null, 2)
  const blob = new Blob([data], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${currentDetail.value.result_id}.json`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(() => {
  paperStore.fetchPapers()
})
</script>

<template>
  <div class="page-container pdf-processor">
    <div class="page-header">
      <div class="page-header-left">
        <h2 class="page-title">PDF 论文处理</h2>
        <p class="page-description">上传 PDF 论文文件，系统将自动解析提取结构化信息</p>
      </div>
      <el-upload
        :show-file-list="false"
        :auto-upload="false"
        :on-change="handleFileUpload"
        accept=".pdf"
        :drag="true"
        class="upload-dragger-inline"
      >
        <el-button type="primary" :loading="uploading">
          <el-icon><Upload /></el-icon>
          上传 PDF
        </el-button>
      </el-upload>
    </div>

    <el-card class="paper-list-card">
      <template #header>
        <div class="card-header">
          <span>论文列表</span>
          <el-button text @click="paperStore.fetchPapers()">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <el-table
        v-loading="paperStore.loading"
        :data="paperStore.papers"
        stripe
        style="width: 100%"
        @row-click="handleView"
      >
        <el-table-column prop="file_name" label="文件名" min-width="200" show-overflow-tooltip />
        <el-table-column prop="title" label="标题" min-width="300" show-overflow-tooltip />
        <el-table-column prop="doi" label="DOI" min-width="200" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'completed' ? 'success' : row.status === 'failed' ? 'danger' : row.status === 'processing' ? 'warning' : 'info'">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="上传时间" width="180" />
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button-group>
              <el-button size="small" @click.stop="handleView(row)">查看</el-button>
              <el-button size="small" type="danger" @click.stop="handleDelete(row)">删除</el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

      <!-- 空状态引导 -->
      <el-empty
        v-if="!paperStore.loading && paperStore.papers.length === 0"
        description="请先上传PDF"
      >
        <el-upload
          :show-file-list="false"
          :auto-upload="false"
          :on-change="handleFileUpload"
          accept=".pdf"
          :drag="true"
        >
          <el-button type="primary">
            <el-icon><Upload /></el-icon>
            上传 PDF
          </el-button>
        </el-upload>
      </el-empty>

      <div class="pagination">
        <el-pagination
          v-model:current-page="paperStore.currentPage"
          v-model:page-size="paperStore.pageSize"
          :total="paperStore.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="paperStore.fetchPapers()"
          @current-change="paperStore.fetchPapers()"
        />
      </div>
    </el-card>

    <!-- 详情弹窗 -->
    <el-dialog
      v-model="detailDialogVisible"
      title="论文解析结果"
      width="80%"
      top="5vh"
    >
      <div v-loading="detailLoading">
        <template v-if="currentDetail">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="文件名">{{ currentDetail.file_name }}</el-descriptions-item>
            <el-descriptions-item label="DOI">{{ currentDetail.doi || '无' }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="currentDetail.status === 'completed' ? 'success' : currentDetail.status === 'failed' ? 'danger' : 'warning'">
                {{ currentDetail.status }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="处理时间">{{ currentDetail.processed_at || '无' }}</el-descriptions-item>
          </el-descriptions>

          <el-divider content-position="left">标题</el-divider>
          <p class="detail-text">{{ currentDetail.title || '无标题' }}</p>

          <el-divider content-position="left">
            <div class="abstract-divider-title">
              <span>摘要</span>
              <el-button
                v-if="needsTruncation"
                size="small"
                text
                type="primary"
                @click="toggleAbstract"
              >
                {{ abstractExpanded ? '收起' : '展开' }}
              </el-button>
              <el-button
                size="small"
                text
                type="primary"
                @click="copyAbstract"
              >
                <el-icon><CopyDocument /></el-icon>
                复制摘要
              </el-button>
            </div>
          </el-divider>
          <p class="detail-text abstract">{{ truncatedAbstract }}</p>

          <el-divider content-position="left">章节列表 ({{ currentDetail.sections?.length || 0 }})</el-divider>
          <el-collapse v-if="currentDetail.sections?.length">
            <el-collapse-item
              v-for="(section, index) in currentDetail.sections"
              :key="index"
              :title="section.heading"
            >
              <p class="section-text">{{ section.text }}</p>
            </el-collapse-item>
          </el-collapse>
          <p v-else class="no-data">无章节信息</p>

          <el-divider content-position="left">参考文献 ({{ currentDetail.references?.length || 0 }})</el-divider>
          <el-table v-if="currentDetail.references?.length" :data="currentDetail.references" max-height="300">
            <el-table-column prop="title" label="标题" show-overflow-tooltip />
            <el-table-column prop="doi" label="DOI" width="200" show-overflow-tooltip />
            <el-table-column prop="authors" label="作者" show-overflow-tooltip />
          </el-table>
          <p v-else class="no-data">无参考文献</p>
        </template>
      </div>

      <template #footer>
        <el-button @click="detailDialogVisible = false">关闭</el-button>
        <el-button type="primary" @click="downloadJson" :disabled="!currentDetail">
          <el-icon><Download /></el-icon>
          下载 JSON
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.pdf-processor {
  /* page-container 全局类已提供 max-width 和 margin，无需重复 */
  padding: var(--page-padding);
}

/* 页面头部 — 横向布局由全局 .page-header 提供 */

.upload-dragger-inline .el-upload-dragger {
  /* 拖拽区域在按钮模式下不显示拖拽框，仅保持按钮样式 */
  padding: 0;
  border: none;
  background: transparent;
}

.paper-list-card {
  margin-bottom: var(--spacing-lg);
}

/* card-header 已由全局 common.css 提供 */

.pagination {
  margin-top: var(--spacing-lg);
  display: flex;
  justify-content: flex-end;
}

.detail-text {
  margin: 0;
  line-height: 1.8;
  color: var(--text-primary);
}

.detail-text.abstract {
  background: var(--bg-page);
  padding: var(--spacing-md);
  border-radius: var(--border-radius-sm);
}

.abstract-divider-title {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.section-text {
  white-space: pre-wrap;
  line-height: 1.6;
}

.no-data {
  color: var(--text-secondary);
  text-align: center;
  padding: var(--spacing-sm);
}
</style>