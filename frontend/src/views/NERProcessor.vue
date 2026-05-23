<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { usePaperStore, useNerStore } from '@/stores'
import { ElMessage, ElMessageBox } from 'element-plus'
import { promptApi } from '@/api'
import { getTypeColor } from '@/utils/helpers'
import type { ProcessingResult } from '@/types/paper'
import type { EntityInfo } from '@/types/ner'
import type { PromptTemplate } from '@/api/prompt'

const paperStore = usePaperStore()
const nerStore = useNerStore()

// Prompt模板列表（从API获取）
const nerPrompts = ref<PromptTemplate[]>([])
const loadingPrompts = ref(false)
const selectedPromptName = ref('material_ner')

// NER 执行表单
const nerDialogVisible = ref(false)
const selectedPaper = ref<ProcessingResult | null>(null)
const skipIntroduction = ref(false)
const sentenceGroupSize = ref(10)
const executing = ref(false)

// NER 结果查看
const nerResultDialogVisible = ref(false)
const nerResultLoading = ref(false)
const nerEntities = ref<EntityInfo[]>([])
const currentNerId = ref('')

// 实体类型过滤（多选数组）
const entityTypeFilter = ref<string[]>([])

// 实体文本搜索（debounce 300ms）
const entitySearchText = ref('')
const entitySearchDebounced = ref('')
let searchTimer: ReturnType<typeof setTimeout> | null = null

watch(entitySearchText, (val) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    entitySearchDebounced.value = val
  }, 300)
})

// 5个主要默认实体类型
const DEFAULT_ENTITY_TYPES = [
  'Material',
  'Microstructural_Hierarchy',
  'Transport_Behavior',
  'Manufacturing_Process_Chain',
  '错误'
]

// 动态提取实体类型：默认类型优先，追加数据中出现的新类型
const entityTypes = computed(() => {
  const dataTypes = new Set<string>()
  for (const e of nerEntities.value) {
    dataTypes.add(e.entity_type)
  }
  const merged = [...DEFAULT_ENTITY_TYPES]
  for (const t of dataTypes) {
    if (!merged.includes(t)) merged.push(t)
  }
  return merged
})

// 加载NER Prompt列表
async function loadNerPrompts() {
  loadingPrompts.value = true
  try {
    const result = await promptApi.list('ner')
    nerPrompts.value = result.templates
    if (!selectedPromptName.value && nerPrompts.value.length > 0) {
      selectedPromptName.value = nerPrompts.value[0].name
    }
  } catch (error: any) {
    console.error('加载NER Prompt列表失败:', error)
    selectedPromptName.value = 'material_ner'
  } finally {
    loadingPrompts.value = false
  }
}

// 选择论文执行 NER
function selectPaper(row: ProcessingResult) {
  selectedPaper.value = row
  nerDialogVisible.value = true
}

// 页面头部"执行 NER"按钮 — 提示需先选择论文
function handleHeaderNERClick() {
  ElMessage.info('请在下方论文列表中选择论文后执行 NER')
}

// 执行 NER
async function executeNER() {
  if (!selectedPaper.value) return

  executing.value = true
  try {
    const response = await nerStore.executeNER(
      selectedPaper.value.result_id,
      selectedPromptName.value,
      {
        skip_introduction: skipIntroduction.value,
        sentence_group_size: sentenceGroupSize.value
      }
    )

    if (response.success) {
      ElMessage.success(`NER 处理完成，提取实体 ${response.entity_count} 个`)
      nerDialogVisible.value = false
      await paperStore.fetchPapers()
    } else {
      ElMessage.error(response.message || 'NER 处理失败')
    }
  } catch (error: any) {
    ElMessage.error(error.message || 'NER 处理失败')
  } finally {
    executing.value = false
  }
}

// 查看 NER 结果
async function viewNERResult(row: ProcessingResult) {
  currentNerId.value = `ner_${row.result_id}`
  nerResultLoading.value = true
  nerResultDialogVisible.value = true
  entityTypeFilter.value = []
  entitySearchText.value = ''
  entitySearchDebounced.value = ''

  try {
    const response = await nerStore.fetchEntities(currentNerId.value, { limit: 500 })
    nerEntities.value = response.entities || []
    ElMessage.success(`已加载 ${nerEntities.value.length} 个实体`)
  } catch (error: any) {
    ElMessage.error('获取NER结果失败: ' + error.message)
    nerResultDialogVisible.value = false
  } finally {
    nerResultLoading.value = false
  }
}

// 过滤实体（类型多选 + 文本搜索）
const filteredEntities = computed(() => {
  let result = nerEntities.value
  if (entityTypeFilter.value.length > 0) {
    result = result.filter(e => entityTypeFilter.value.includes(e.entity_type))
  }
  if (entitySearchDebounced.value) {
    const keyword = entitySearchDebounced.value.toLowerCase()
    result = result.filter(e => e.entity_text.toLowerCase().includes(keyword))
  }
  return result
})

// 下载 Excel（从结果弹窗）
async function downloadExcelFromResult() {
  if (!currentNerId.value) return
  try {
    await nerStore.downloadExcel(currentNerId.value)
    ElMessage.success('下载成功')
  } catch (error) {
    ElMessage.error('下载失败')
  }
}

// 下载 Excel（按 nerId）
async function downloadExcel(nerId: string) {
  try {
    await nerStore.downloadExcel(nerId)
    ElMessage.success('下载成功')
  } catch (error) {
    ElMessage.error('下载失败')
  }
}

// 删除论文
async function handleDelete(row: ProcessingResult) {
  try {
    await ElMessageBox.confirm('确定要删除这篇论文吗？相关 NER 结果也会被删除', '提示', {
      type: 'warning'
    })
    await paperStore.deletePaper(row.result_id)
    ElMessage.success('删除成功')
  } catch (error) {
    // 用户取消
  }
}

onMounted(() => {
  paperStore.fetchPapers()
  loadNerPrompts()
})
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-header-left">
        <h2 class="page-title">NER 命名实体识别</h2>
        <p class="page-description">对 PDF 论文进行命名实体识别，提取关键实体信息</p>
      </div>
      <el-button type="primary" @click="handleHeaderNERClick">
        <el-icon><Aim /></el-icon>
        执行 NER
      </el-button>
    </div>

    <!-- 论文列表 -->
    <el-card class="paper-list-card">
      <template #header>
        <div class="card-header">
          <span>论文列表（选择论文执行 NER）</span>
          <el-button text @click="paperStore.fetchPapers()">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <el-table
        v-loading="paperStore.loading"
        :data="paperStore.papers"
        style="width: 100%"
      >
        <el-table-column prop="file_name" label="文件名" min-width="200" show-overflow-tooltip />
        <el-table-column prop="title" label="标题" min-width="300" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'completed' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="NER 状态" width="120">
          <template #default="{ row }">
            <el-tag type="info" v-if="!row.ner_status">未处理</el-tag>
            <el-tag type="success" v-else-if="row.ner_status === 'completed'">已完成</el-tag>
            <el-tag type="warning" v-else-if="row.ner_status === 'processing'">处理中</el-tag>
            <el-tag type="danger" v-else>{{ row.ner_status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="上传时间" width="180" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button-group>
              <el-button size="small" type="primary" @click="selectPaper(row)">
                执行 NER
              </el-button>
              <el-button size="small" v-if="row.ner_status === 'completed'" @click="viewNERResult(row)">
                查看
              </el-button>
              <el-button size="small" type="danger" @click="handleDelete(row)">
                删除
              </el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

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

    <!-- NER 执行对话框 -->
    <el-dialog
      v-model="nerDialogVisible"
      title="执行 NER"
      width="500px"
    >
      <el-form label-width="120px">
        <el-form-item label="论文标题">
          <el-text>{{ selectedPaper?.title || selectedPaper?.file_name }}</el-text>
        </el-form-item>
        <el-form-item label="Prompt 模板">
          <el-select v-model="selectedPromptName" placeholder="选择 Prompt 模板" :loading="loadingPrompts" style="width: 100%">
            <el-option
              v-for="prompt in nerPrompts"
              :key="prompt.name"
              :label="prompt.description || prompt.name"
              :value="prompt.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="跳过 Introduction">
          <el-switch v-model="skipIntroduction" />
        </el-form-item>
        <el-form-item label="句子组大小">
          <el-input-number v-model="sentenceGroupSize" :min="5" :max="50" />
        </el-form-item>
        <el-alert type="info" :closable="false" show-icon style="margin-top: 10px">
          <template #title>
            NER 处理需要调用 LLM API，可能需要数分钟时间，请耐心等待
          </template>
        </el-alert>
      </el-form>

      <template #footer>
        <el-button @click="nerDialogVisible = false" :disabled="executing">取消</el-button>
        <el-button type="primary" :loading="executing" @click="executeNER">
          {{ executing ? '正在处理...' : '执行 NER' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- NER 结果查看弹窗 -->
    <el-dialog
      v-model="nerResultDialogVisible"
      title="NER 实体结果"
      width="80%"
      top="5vh"
    >
      <div v-loading="nerResultLoading">
        <div class="result-toolbar">
          <span class="result-count">共 {{ nerEntities.length }} 个实体</span>
          <el-select
            v-model="entityTypeFilter"
            multiple
            collapse-tags
            collapse-tags-tooltip
            placeholder="按类型过滤"
            clearable
            style="width: 280px"
          >
            <el-option
              v-for="type in entityTypes"
              :key="type"
              :label="type"
              :value="type"
            >
              <span class="type-option-dot" :style="{ backgroundColor: getTypeColor(type) }"></span>
              <span>{{ type }}</span>
            </el-option>
          </el-select>
          <el-input
            v-model="entitySearchText"
            placeholder="搜索实体文本"
            clearable
            prefix-icon="Search"
            style="width: 200px"
          />
          <el-button type="primary" @click="downloadExcelFromResult">
            <el-icon><Download /></el-icon>
            下载 Excel
          </el-button>
        </div>

        <el-table :data="filteredEntities" max-height="500" style="margin-top: var(--spacing-md)">
          <el-table-column prop="entity_type" label="实体类型" width="200">
            <template #default="{ row }">
              <span class="type-dot" :style="{ backgroundColor: getTypeColor(row.entity_type) }"></span>
              <span>{{ row.entity_type }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="entity_text" label="实体内容" min-width="300" show-overflow-tooltip />
          <el-table-column prop="section_idx" label="章节索引" width="100" />
          <el-table-column prop="group_idx" label="组索引" width="100" />
          <el-table-column prop="confidence" label="置信度" width="100">
            <template #default="{ row }">
              {{ row.confidence ? (row.confidence * 100).toFixed(1) + '%' : '-' }}
            </template>
          </el-table-column>
        </el-table>
      </div>

      <template #footer>
        <el-button @click="nerResultDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
/* 页面特有样式 — 全局布局类（page-container / page-header / page-header-left / page-title
   / page-description / card-header）已在 common.css 中定义，此处不再重复 */

.paper-list-card {
  margin-bottom: var(--spacing-lg);
}

.pagination {
  margin-top: var(--spacing-lg);
  display: flex;
  justify-content: flex-end;
}

/* NER 结果弹窗工具栏 */
.result-toolbar {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  flex-wrap: wrap;
}

.result-count {
  color: var(--text-regular);
  font-size: 14px;
}

/* 实体类型色点 — 表格行内 */
.type-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}

/* 实体类型色点 — 下拉选项 */
.type-option-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 8px;
  vertical-align: middle;
}
</style>