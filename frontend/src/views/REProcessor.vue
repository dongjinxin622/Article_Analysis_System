<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useNerStore, useReStore } from '@/stores'
import { ElMessage, ElMessageBox } from 'element-plus'
import { promptApi } from '@/api'
import { getTypeColor, truncateId } from '@/utils/helpers'
import type { NERResultListItem, EntityInfo } from '@/types/ner'
import type { RelationInfo } from '@/types/relation'
import type { PromptTemplate } from '@/api/prompt'

const router = useRouter()
const nerStore = useNerStore()
const reStore = useReStore()

// Prompt模板列表（从API获取）
const rePrompts = ref<PromptTemplate[]>([])
const loadingPrompts = ref(false)
const selectedPromptName = ref('material_re')

// 选中的 NER 结果
const selectedNer = ref<NERResultListItem | null>(null)

// RE 执行对话框
const reDialogVisible = ref(false)
const executing = ref(false)

// RE 结果查看对话框
const reResultDialogVisible = ref(false)
const reRelations = ref<RelationInfo[]>([])
const currentReId = ref('')
const relationTypeFilter = ref('')

// 加载RE Prompt列表
async function loadRePrompts() {
  loadingPrompts.value = true
  try {
    const result = await promptApi.list('re')
    rePrompts.value = result.templates
    // 如果没有选中的prompt，默认选第一个
    if (!selectedPromptName.value && rePrompts.value.length > 0) {
      selectedPromptName.value = rePrompts.value[0].name
    }
  } catch (error: any) {
    console.error('加载RE Prompt列表失败:', error)
    // 失败时使用默认值
    selectedPromptName.value = 'material_re'
  } finally {
    loadingPrompts.value = false
  }
}

// 关系类型统计
const relationStats = computed(() => {
  const stats: Record<string, number> = {}
  reRelations.value.forEach(rel => {
    stats[rel.relation_type] = (stats[rel.relation_type] || 0) + 1
  })
  return stats
})

// 动态获取关系类型列表（从已加载的数据中提取）
const availableRelationTypes = computed(() => {
  const types = new Set<string>()
  reRelations.value.forEach(rel => {
    if (rel.relation_type && rel.relation_type !== '') {
      types.add(rel.relation_type)
    }
  })
  return Array.from(types).sort()
})

// 获取 NER 结果列表
async function fetchNERResults() {
  await nerStore.fetchNERResultList({ page: 1, page_size: 50 })
}

// 选择 NER 结果执行 RE
function selectNER(ner: NERResultListItem) {
  selectedNer.value = ner
  reDialogVisible.value = true
}

// 执行 RE
async function executeRE() {
  if (!selectedNer.value) return

  executing.value = true
  try {
    const response = await reStore.executeRE(
      selectedNer.value.ner_id,
      selectedPromptName.value  // 使用prompt name
    )

    if (response.success) {
      ElMessage.success(`关系抽取完成，提取关系 ${response.relation_count} 个`)
      reDialogVisible.value = false
      // 刷新NER列表以更新RE状态
      await fetchNERResults()
    } else {
      ElMessage.error(response.message || '关系抽取失败')
    }
  } catch (error: any) {
    console.error('[RE] 执行失败:', error)
    ElMessage.error(error.message || '关系抽取失败')
  } finally {
    executing.value = false
  }
}

// 查看 RE 结果详情
async function viewREResult(ner: NERResultListItem) {
  reResultDialogVisible.value = true
  reRelations.value = []
  relationTypeFilter.value = ''

  try {
    // 通过NER ID获取对应的RE结果
    const reDetail = await reStore.fetchREByNERId(ner.ner_id)
    if (reDetail) {
      currentReId.value = reDetail.re_id
      // relations可能在reDetail中直接返回
      if (reDetail.relations && reDetail.relations.length > 0) {
        // 过滤出有效的关系（有relation_type的）
        const validRelations = reDetail.relations.filter(r => r.relation_type && r.relation_type !== '')
        const errorRelations = reDetail.relations.filter(r => !r.relation_type || r.relation_type === '' || r.error)

        reRelations.value = validRelations

        if (validRelations.length > 0) {
          ElMessage.success(`已加载 ${validRelations.length} 个有效关系`)
        } else if (errorRelations.length > 0) {
          ElMessage.warning(`RE处理完成但未产生有效关系（${errorRelations.length}条处理记录为空或错误）`)
        }
      } else {
        ElMessage.warning('RE结果中没有关系数据')
      }
    } else {
      ElMessage.warning('暂无RE结果数据')
    }
  } catch (error: any) {
    ElMessage.error('获取RE结果失败: ' + error.message)
    reResultDialogVisible.value = false
  }
}

// 过滤关系
const filteredRelations = computed(() => {
  if (!relationTypeFilter.value) return reRelations.value
  return reRelations.value.filter(r => r.relation_type === relationTypeFilter.value)
})

// 下载 Excel
async function downloadExcel(reId: string) {
  try {
    await reStore.downloadExcel(reId)
    ElMessage.success('下载成功')
  } catch (error) {
    ElMessage.error('下载失败')
  }
}

// 下载 Excel 从当前结果
async function downloadExcelFromResult() {
  if (!currentReId.value) return
  await downloadExcel(currentReId.value)
}

// NER 结果列表是否为空（加载完成后无数据）
const isNerListEmpty = computed(() => {
  return !nerStore.loading && nerStore.nerResultList.length === 0
})

// RE 结果是否为空（加载完成后无数据或被过滤为空）
const isRelationListEmpty = computed(() => {
  return !reStore.loading && filteredRelations.value.length === 0
})

onMounted(() => {
  fetchNERResults()
  loadRePrompts()
})
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-header-left">
        <h2 class="page-title">RE 关系抽取</h2>
        <p class="page-description">基于 NER 结果进行实体关系抽取，分析实体间因果关系</p>
      </div>
      <el-button text @click="fetchNERResults()">
        <el-icon><Refresh /></el-icon>
        刷新数据
      </el-button>
    </div>

    <!-- NER 结果列表 -->
    <el-card class="ner-list-card">
      <template #header>
        <div class="card-header">
          <span>NER 结果列表（选择 NER 结果执行 RE）</span>
        </div>
      </template>

      <el-empty
        v-if="isNerListEmpty"
        description="暂无 NER 结果，请先在 NER 页面处理论文"
      >
        <el-button type="primary" @click="router.push('/ner')">
          前往 NER 页面
        </el-button>
      </el-empty>

      <el-table
        v-else
        v-loading="nerStore.loading"
        :data="nerStore.nerResultList"
        style="width: 100%"
      >
        <el-table-column prop="ner_id" label="NER ID" min-width="230" show-overflow-tooltip />
        <el-table-column prop="result_id" label="论文 ID" min-width="230" show-overflow-tooltip />
        <el-table-column prop="entity_count" label="实体数量" width="100">
          <template #default="{ row }">
            <el-tag type="info">{{ row.entity_count }} 个</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="NER 状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'completed' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="RE 状态" width="120">
          <template #default="{ row }">
            <el-tag type="info" v-if="!row.re_status">未处理</el-tag>
            <el-tag type="success" v-else-if="row.re_status === 'completed'">已完成</el-tag>
            <el-tag type="warning" v-else-if="row.re_status === 'processing'">处理中</el-tag>
            <el-tag type="danger" v-else>{{ row.re_status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button-group>
              <el-button size="small" type="primary" @click="selectNER(row)">
                执行 RE
              </el-button>
              <el-button size="small" v-if="row.re_status === 'completed'" @click="viewREResult(row)">
                查看
              </el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- RE 执行对话框 -->
    <el-dialog
      v-model="reDialogVisible"
      title="执行关系抽取"
      width="500px"
    >
      <el-form label-width="120px">
        <el-form-item label="NER 结果 ID">
          <el-tooltip :content="selectedNer?.ner_id || ''" placement="top">
            <el-text>{{ truncateId(selectedNer?.ner_id || '') }}</el-text>
          </el-tooltip>
        </el-form-item>
        <el-form-item label="实体数量">
          <el-text>{{ selectedNer?.entity_count }} 个</el-text>
        </el-form-item>
        <el-form-item label="Prompt 模板">
          <el-select v-model="selectedPromptName" placeholder="选择 Prompt 模板" :loading="loadingPrompts" style="width: 100%">
            <el-option
              v-for="prompt in rePrompts"
              :key="prompt.name"
              :label="prompt.description || prompt.name"
              :value="prompt.name"
            />
          </el-select>
        </el-form-item>
        <el-alert type="info" :closable="false" show-icon style="margin-top: 10px">
          <template #title>
            关系抽取需要调用 LLM API，可能需要数分钟时间，请耐心等待
          </template>
        </el-alert>
      </el-form>

      <template #footer>
        <el-button @click="reDialogVisible = false" :disabled="executing">取消</el-button>
        <el-button type="primary" :loading="executing" @click="executeRE">
          {{ executing ? '正在处理...' : '执行 RE' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- RE 结果查看弹窗 -->
    <el-dialog
      v-model="reResultDialogVisible"
      title="RE 关系结果"
      width="80%"
      top="5vh"
    >
      <div v-loading="reStore.loading">
        <div class="result-header">
          <span>共 {{ reRelations.length }} 个关系</span>
          <el-select v-model="relationTypeFilter" placeholder="按类型过滤" clearable style="width: 200px">
            <el-option v-for="type in availableRelationTypes" :key="type" :label="type" :value="type" />
          </el-select>
          <el-button type="primary" @click="downloadExcelFromResult">
            <el-icon><Download /></el-icon>
            下载 Excel
          </el-button>
        </div>

        <el-empty
          v-if="isRelationListEmpty"
          :description="reRelations.length === 0 ? '暂无关系数据' : '没有匹配该类型的关系'"
        />

        <el-table v-else :data="filteredRelations" max-height="500" style="margin-top: var(--spacing-sm)">
          <el-table-column prop="relation_type" label="关系类型" width="120">
            <template #default="{ row }">
              <el-tag :color="getTypeColor(row.relation_type)" effect="dark" size="small">
                {{ row.relation_type }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="源实体" min-width="200">
            <template #default="{ row }">
              <el-tag :color="getTypeColor(row.source_type)" size="small" class="entity-tag">
                {{ row.source_type }}
              </el-tag>
              <span class="entity-text">{{ row.source_entity }}</span>
            </template>
          </el-table-column>
          <el-table-column label="目标实体" min-width="200">
            <template #default="{ row }">
              <el-tag :color="getTypeColor(row.target_type)" size="small" class="entity-tag">
                {{ row.target_type }}
              </el-tag>
              <span class="entity-text">{{ row.target_entity }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="effect" label="效应" width="100">
            <template #default="{ row }">
              <el-tag v-if="row.effect" :type="row.effect === 'positive' ? 'success' : row.effect === 'negative' ? 'danger' : 'info'" size="small">
                {{ row.effect }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="supporting_sentence" label="支撑句子" min-width="300" show-overflow-tooltip />
        </el-table>
      </div>

      <template #footer>
        <el-button @click="reResultDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.ner-list-card {
  margin-bottom: var(--spacing-lg);
}

.result-header {
  display: flex;
  gap: var(--spacing-md);
  align-items: center;
}

.entity-tag {
  margin-right: var(--spacing-xs);
}

.entity-text {
  font-weight: 500;
}
</style>