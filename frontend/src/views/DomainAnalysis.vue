<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { jcApi, comprehensiveApi, promptApi } from '@/api'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { getStatusType, formatTime, shouldHideCancelledTask } from '@/utils/helpers'
import type { JcDatabaseSearchResponse, JcDatabaseStatsResponse } from '@/api/jc'
import type { ComprehensiveStatusResponse, ComprehensiveResult, TaskListItem, TaskListResponse } from '@/api/comprehensive'
import type { PromptTemplate } from '@/api/prompt'

// 当前激活的Tab
const activeTab = ref('jcsearch')

// ========== Jc 数据库搜索 ==========
const jcDbTemperature = ref<number | undefined>(undefined)
const jcDbMagneticField = ref<number | undefined>(undefined)
const jcDbAngle = ref<number | undefined>(undefined)
const jcDbTopK = ref(50)
const jcDbMinJc = ref<number | undefined>(undefined)
const jcDbTempTolerance = ref(1)
const jcDbFieldTolerance = ref(0.5)
const jcDbAngleTolerance = ref(1)
const jcDbSearchResult = ref<JcDatabaseSearchResponse | null>(null)
const loadingJcDbSearch = ref(false)

// Jc 搜索折叠面板 — 默认展开基础参数
const jcActiveParams = ref(['basic'])

// Jc 数据库统计
const jcDbStats = ref<JcDatabaseStatsResponse | null>(null)

/** 搜索参数的默认值映射 — 供"重置为默认"按钮使用 */
const JC_DEFAULTS: Record<string, number | undefined> = {
  temperature: undefined,
  magneticField: undefined,
  angle: undefined,
  topK: 50,
  minJc: undefined,
  tempTolerance: 1,
  fieldTolerance: 0.5,
  angleTolerance: 1,
}

async function searchJcDatabase() {
  // 输入范围验证
  if (jcDbTemperature.value !== undefined) {
    if (jcDbTemperature.value < 0) {
      ElMessage.error('温度不能为负数')
      return
    }
    if (jcDbTemperature.value > 200) {
      ElMessage.error('温度超出范围，最大允许 200K')
      return
    }
  }
  if (jcDbMagneticField.value !== undefined) {
    if (jcDbMagneticField.value < 0) {
      ElMessage.error('磁场不能为负数')
      return
    }
    if (jcDbMagneticField.value > 80) {
      ElMessage.error('磁场超出范围，最大允许 80T')
      return
    }
  }
  if (jcDbAngle.value !== undefined && jcDbAngle.value < 0) {
    ElMessage.error('角度不能为负数')
    return
  }

  loadingJcDbSearch.value = true
  try {
    jcDbSearchResult.value = await jcApi.search({
      temperature: jcDbTemperature.value,
      magnetic_field: jcDbMagneticField.value,
      angle: jcDbAngle.value,
      top_k: jcDbTopK.value,
      min_jc: jcDbMinJc.value,
      temp_tolerance: jcDbTempTolerance.value,
      field_tolerance: jcDbFieldTolerance.value,
      angle_tolerance: jcDbAngleTolerance.value
    })

    if (jcDbSearchResult.value.success) {
      ElMessage.success(`找到 ${jcDbSearchResult.value.count} 条记录`)
    } else {
      ElMessage.error(jcDbSearchResult.value.message || '搜索失败')
    }
  } catch (error: any) {
    ElMessage.error(error.message || 'Jc 数据库搜索失败')
  } finally {
    loadingJcDbSearch.value = false
  }
}

async function fetchJcDbStats() {
  try {
    jcDbStats.value = await jcApi.getStats()
  } catch (error) {
    ElMessage.error('获取统计信息失败')
  }
}

function clearJcSearch() {
  jcDbSearchResult.value = null
  jcDbTemperature.value = undefined
  jcDbMagneticField.value = undefined
  jcDbAngle.value = undefined
  jcDbMinJc.value = undefined
}

/** 重置所有 Jc 搜索表单值为默认值 */
function resetJcDefaults() {
  jcDbTemperature.value = JC_DEFAULTS.temperature as number | undefined
  jcDbMagneticField.value = JC_DEFAULTS.magneticField as number | undefined
  jcDbAngle.value = JC_DEFAULTS.angle as number | undefined
  jcDbTopK.value = JC_DEFAULTS.topK as number
  jcDbMinJc.value = JC_DEFAULTS.minJc as number | undefined
  jcDbTempTolerance.value = JC_DEFAULTS.tempTolerance as number
  jcDbFieldTolerance.value = JC_DEFAULTS.fieldTolerance as number
  jcDbAngleTolerance.value = JC_DEFAULTS.angleTolerance as number
  ElMessage.info('已重置为默认参数')
}

// ========== 一键处理（PDF上传并自动完成全流程） ==========
const uploadFile = ref<File | null>(null)
const uploadRef = ref()
const oneClickTopK = ref(10)
const oneClickLoading = ref(false)

// Prompt 模板选择（从API获取）
const nerPrompts = ref<PromptTemplate[]>([])
const rePrompts = ref<PromptTemplate[]>([])
const loadingPrompts = ref(false)
const selectedNerPrompt = ref('material_ner')
const selectedRePrompt = ref('material_re')

// 当前使用的Prompt文件名（基于已选Prompt派生）
const nerQueryFile = computed(() => selectedNerPrompt.value || '未选择')
const reQueryFile = computed(() => selectedRePrompt.value || '未选择')

// 加载Prompt模板列表
async function loadPrompts() {
  loadingPrompts.value = true
  try {
    const [nerResult, reResult] = await Promise.all([
      promptApi.list('ner'),
      promptApi.list('re')
    ])
    nerPrompts.value = nerResult.templates
    rePrompts.value = reResult.templates
    // 设置默认值
    if (!selectedNerPrompt.value && nerPrompts.value.length > 0) {
      selectedNerPrompt.value = nerPrompts.value[0].name
    }
    if (!selectedRePrompt.value && rePrompts.value.length > 0) {
      selectedRePrompt.value = rePrompts.value[0].name
    }
  } catch (error: any) {
    ElMessage.error('加载Prompt模板失败')
    selectedNerPrompt.value = 'material_ner'
    selectedRePrompt.value = 'material_re'
  } finally {
    loadingPrompts.value = false
  }
}

// 任务状态
const taskId = ref('')
const taskStatus = ref('idle')
const taskProgress = ref(0)
const currentStep = ref('')
const statusMessage = ref('')

// 分析结果
const analysisResult = ref<ComprehensiveResult | null>(null)

// ========== 任务历史 ==========
const taskList = ref<TaskListItem[]>([])
const loadingTaskList = ref(false)

// 任务历史 el-tabs 激活项
const historyActiveTab = ref('active')

// 状态轮询定时器
let pollTimer: ReturnType<typeof setInterval> | null = null
let pollRunning = false  // 防止并发轮询

// 步骤名称映射
const stepNames: Record<string, string> = {
  'pdf_parse': 'PDF 解析',
  'ner': 'NER 实体识别',
  're': '关系抽取',
  'tech_route': '技术路线分析',
  'exp_scheme': '实验方案分析',
  'jc_analysis': 'Jc 指标分析',
  'llm_comparison': 'LLM 综合分析',
  'complete': '完成',
  'error': '错误',
  '初始化': '初始化'
}

function getStepName(step: string): string {
  return stepNames[step] || step
}

function getProgressColor(progress: number): string {
  if (progress < 30) return '#e6a23c'
  if (progress < 70) return '#409eff'
  return '#67c23a'
}

// ========== 分析结果文本截断（超过500字自动截断） ==========
const expandedTexts = ref<Record<string, boolean>>({})

/** 判断文本是否需要截断 */
function needsTruncation(text: string | undefined): boolean {
  return !!text && text.length > 500
}

/** 获取截断后的显示文本 */
function getDisplayText(text: string | undefined, key: string): string {
  if (!text) return ''
  if (expandedTexts.value[key] || text.length <= 500) return text
  return text.substring(0, 500) + '...'
}

/** 切换文本展开/收起状态 */
function toggleTextExpand(key: string) {
  expandedTexts.value[key] = !expandedTexts.value[key]
}

function handleFileChange(uploadFileObj: any, uploadFiles: any) {
  if (uploadFileObj && uploadFileObj.raw) {
    uploadFile.value = uploadFileObj.raw
  } else if (uploadFileObj) {
    uploadFile.value = uploadFileObj
  }
  return false
}

function clearFile() {
  uploadFile.value = null
  uploadRef.value?.clearFiles()
}

async function startOneClickAnalysis() {
  if (!uploadFile.value) {
    ElMessage.warning('请先上传 PDF 文件')
    return
  }

  oneClickLoading.value = true
  taskStatus.value = 'pending'
  taskProgress.value = 0
  statusMessage.value = '正在启动分析...'

  try {
    const response = await comprehensiveApi.oneClickAnalyze(uploadFile.value, {
      top_k: oneClickTopK.value,
      ner_query_file: selectedNerPrompt.value,
      re_query_file: selectedRePrompt.value
    })

    if (response.success) {
      taskId.value = response.task_id
      ElMessage.success('一键处理任务已启动')
      startPolling()
      // 刷新任务列表
      await fetchTaskList()
    } else {
      ElMessage.error(response.message || '启动失败')
      taskStatus.value = 'failed'
      oneClickLoading.value = false
    }
  } catch (error: any) {
    ElMessage.error(error.message || '启动分析失败')
    taskStatus.value = 'failed'
    oneClickLoading.value = false
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    if (pollRunning) return  // 上一次请求未完成则跳过
    pollRunning = true
    try {
      const status = await comprehensiveApi.getStatus(taskId.value)
      taskStatus.value = status.status
      taskProgress.value = status.progress
      currentStep.value = status.current_step
      statusMessage.value = status.message

      if (status.status === 'completed') {
        stopPolling()
        analysisResult.value = status.result || null
        oneClickLoading.value = false
        ElMessage.success('分析完成')
        await fetchTaskList()
      } else if (status.status === 'failed') {
        stopPolling()
        oneClickLoading.value = false
        ElMessage.error(status.message || status.error || '分析失败')
        await fetchTaskList()
      }
    } catch (error) {
      stopPolling()
      oneClickLoading.value = false
      ElMessage.error('状态查询失败')
    } finally {
      pollRunning = false
    }
  }, 2000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function deleteTask() {
  if (!taskId.value) return
  try {
    await comprehensiveApi.deleteTask(taskId.value)
    taskId.value = ''
    taskStatus.value = 'idle'
    taskProgress.value = 0
    analysisResult.value = null
    ElMessage.success('任务已删除')
    // 刷新任务列表
    await fetchTaskList()
  } catch (error) {
    ElMessage.error('删除任务失败')
  }
}

async function deleteTaskFromList(taskIdToDelete: string) {
  try {
    await comprehensiveApi.deleteTask(taskIdToDelete)
    ElMessage.success('任务已删除')
    await fetchTaskList()
  } catch (error) {
    ElMessage.error('删除任务失败')
  }
}

async function resumeTask(taskItem: TaskListItem) {
  // 恢复一个正在运行的任务
  taskId.value = taskItem.task_id
  taskStatus.value = taskItem.status
  taskProgress.value = taskItem.progress
  currentStep.value = taskItem.current_step
  statusMessage.value = taskItem.message

  if (taskItem.status === 'running' || taskItem.status === 'pending') {
    oneClickLoading.value = true
    startPolling()
    ElMessage.info('已恢复任务进度监控')
  } else if (taskItem.status === 'completed') {
    // 加载已完成的结果
    try {
      const status = await comprehensiveApi.getStatus(taskItem.task_id)
      if (status.result) {
        analysisResult.value = status.result
        ElMessage.success('已加载任务结果')
      }
    } catch (error) {
      ElMessage.error('加载结果失败')
    }
  }
}

function clearAnalysis() {
  clearFile()
  taskId.value = ''
  taskStatus.value = 'idle'
  taskProgress.value = 0
  analysisResult.value = null
}

// ========== 报告下载 ==========
async function downloadReport(format: string) {
  if (!taskId.value) {
    ElMessage.warning('没有可下载的报告')
    return
  }

  try {
    // 使用 axios 请求以自动携带认证 token
    const { default: api } = await import('@/api/request')
    // 拦截器返回 response.data，所以这里直接拿到 Blob（或错误对象）
    const response = await api.get(`/comprehensive/report/${taskId.value}`, {
      params: { format },
      responseType: 'blob'
    })

    // 检查返回的是否是 Blob（后端错误时可能返回 JSON）
    if (!(response instanceof Blob)) {
      throw new Error('下载响应格式异常')
    }

    // 如果 blob 是错误 JSON（后端返回错误），尝试解析
    if (response.type === 'application/json' && response.size > 0) {
      const text = await response.text()
      const errorData = JSON.parse(text)
      throw new Error(errorData.detail || '下载失败')
    }

    const url = window.URL.createObjectURL(response)
    const link = document.createElement('a')
    link.href = url
    link.download = `${taskId.value}_report.${format === 'excel' ? 'xlsx' : format}`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success(`${format.toUpperCase()} 报告下载成功`)
  } catch (error: any) {
    ElMessage.error(error.message || '报告下载失败')
  }
}

// ========== 任务列表管理 ==========

async function fetchTaskList() {
  loadingTaskList.value = true
  try {
    const response = await comprehensiveApi.getTaskList()
    taskList.value = (response.tasks || []).filter(t => !shouldHideCancelledTask(t))
  } catch (error: any) {
    ElMessage.error(error.message || '加载任务列表失败')
    taskList.value = []
  } finally {
    loadingTaskList.value = false
  }
}

async function checkAndResumeActiveTask() {
  try {
    const response = await comprehensiveApi.getActiveTasks()
    const activeTasks = response.tasks || []

    if (activeTasks.length > 0) {
      const task = activeTasks[0]
      resumeTask(task)
      ElMessage.info('发现正在运行的任务，已自动恢复进度监控')
    }
  } catch {
    // 忽略检查失败
  }
}

// 活跃任务（正在运行）
const activeTasks = computed(() => {
  return taskList.value.filter(t => t.status === 'running' || t.status === 'pending')
})

// 已完成任务
const completedTasks = computed(() => {
  return taskList.value.filter(t => t.status === 'completed')
})

// 失败任务
const failedTasks = computed(() => {
  return taskList.value.filter(t => t.status === 'failed')
})

onMounted(async () => {
  fetchJcDbStats()
  // 加载任务列表
  await fetchTaskList()
  // 加载Prompt模板列表（同时为 nerQueryFile/reQueryFile 提供初始值）
  await loadPrompts()
  // 检查并恢复活跃任务
  await checkAndResumeActiveTask()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <div class="page-header-left">
        <h2 class="page-title">REBCO 领域分析</h2>
        <p class="page-description">REBCO 超导材料领域专用分析工具：Jc 历史数据检索、论文综合对比分析</p>
      </div>
    </div>

    <!-- 统计信息 -->
    <el-card class="stats-card" v-if="jcDbStats">
      <template #header>
        <div class="card-header">
          <span>Jc 数据库统计</span>
          <el-button size="small" @click="fetchJcDbStats" icon="Refresh">刷新</el-button>
        </div>
      </template>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="总记录数">
          <el-tag type="primary">{{ jcDbStats.statistics.total_records }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="唯一 DOI 数">
          <el-tag type="success">{{ jcDbStats.statistics.unique_dois }}</el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 功能标签页 -->
    <el-card class="main-card">
      <el-tabs v-model="activeTab">
        <!-- Tab 1: Jc 数据库检索 -->
        <el-tab-pane label="Jc 数据库检索" name="jcsearch">
          <el-alert type="info" :closable="false" style="margin-bottom: 15px">
            直接搜索云端 MySQL 历史 Jc 数据。支持按温度、磁场、角度条件筛选，无需 NER ID。
          </el-alert>

          <el-form label-width="120px">
            <!-- 基础参数（默认展开）与高级参数（默认折叠）分组 -->
            <el-collapse v-model="jcActiveParams">
              <el-collapse-item title="基础参数" name="basic">
                <el-row :gutter="20">
                  <el-col :span="8">
                    <el-form-item label="温度 (K)">
                      <el-input-number v-model="jcDbTemperature" :min="0" :max="300" :precision="1" placeholder="可选" style="width: 100%" />
                    </el-form-item>
                  </el-col>
                  <el-col :span="8">
                    <el-form-item label="磁场 (T)">
                      <el-input-number v-model="jcDbMagneticField" :min="0" :max="20" :precision="2" placeholder="可选" style="width: 100%" />
                    </el-form-item>
                  </el-col>
                  <el-col :span="8">
                    <el-form-item label="角度 (deg)">
                      <el-input-number v-model="jcDbAngle" :min="0" :max="360" :precision="1" placeholder="可选" style="width: 100%" />
                    </el-form-item>
                  </el-col>
                </el-row>
              </el-collapse-item>

              <el-collapse-item title="高级参数" name="advanced">
                <el-row :gutter="20">
                  <el-col :span="6">
                    <el-form-item label="返回数量">
                      <el-input-number v-model="jcDbTopK" :min="10" :max="200" style="width: 100%" />
                    </el-form-item>
                  </el-col>
                  <el-col :span="6">
                    <el-form-item label="最小 Jc 值">
                      <el-input-number v-model="jcDbMinJc" :min="0" placeholder="可选" style="width: 100%" />
                    </el-form-item>
                  </el-col>
                  <el-col :span="6">
                    <el-form-item label="温度容差 (K)">
                      <el-input-number v-model="jcDbTempTolerance" :min="0" :max="50" :precision="1" style="width: 100%" />
                    </el-form-item>
                  </el-col>
                  <el-col :span="6">
                    <el-form-item label="磁场容差 (T)">
                      <el-input-number v-model="jcDbFieldTolerance" :min="0" :max="5" :precision="1" style="width: 100%" />
                    </el-form-item>
                  </el-col>
                </el-row>

                <el-form-item label="角度容差 (deg)">
                  <el-input-number v-model="jcDbAngleTolerance" :min="0" :max="45" :precision="1" style="width: 200px" />
                </el-form-item>
              </el-collapse-item>
            </el-collapse>

            <el-form-item style="margin-top: 15px">
              <el-button type="primary" :loading="loadingJcDbSearch" @click="searchJcDatabase">执行搜索</el-button>
              <el-button @click="clearJcSearch">清空结果</el-button>
              <el-button @click="resetJcDefaults">重置为默认</el-button>
            </el-form-item>
          </el-form>

          <!-- 搜索结果 -->
          <div class="result-section" v-if="jcDbSearchResult && jcDbSearchResult.results.length > 0">
            <el-divider>搜索结果（{{ jcDbSearchResult.count }} 条）</el-divider>
            <el-table :data="jcDbSearchResult.results" style="width: 100%" max-height="500" stripe border>
              <el-table-column type="index" label="#" width="50" />
              <el-table-column prop="doi" label="DOI" min-width="180" show-overflow-tooltip>
                <template #default="{ row }">
                  <el-link :href="`https://doi.org/${row.doi}`" target="_blank" type="primary">{{ row.doi }}</el-link>
                </template>
              </el-table-column>
              <el-table-column prop="jc_value" label="Jc 值" width="120" sortable>
                <template #default="{ row }">
                  <el-tag type="success">{{ row.jc_value?.toFixed(2) }}</el-tag> {{ row.jc_unit }}
                </template>
              </el-table-column>
              <el-table-column prop="temperature_K" label="温度 (K)" width="100" sortable />
              <el-table-column prop="magnetic_field_T" label="磁场 (T)" width="100" sortable />
              <el-table-column prop="angle_deg" label="角度 (deg)" width="100" />
              <el-table-column prop="method" label="测量方法" width="120" show-overflow-tooltip />
              <el-table-column prop="substrate" label="基底" width="120" show-overflow-tooltip />
            </el-table>
          </div>
        </el-tab-pane>

        <!-- Tab 2: 一键处理 -->
        <el-tab-pane label="论文综合分析" name="comprehensive">
          <el-alert type="info" :closable="false" style="margin-bottom: 15px">
            一键完成论文综合分析：上传 PDF → 解析 → NER → RE → 技术路线 → 实验方案 → Jc 指标 → LLM 对比报告
          </el-alert>

          <el-form label-width="120px">
            <el-form-item label="上传 PDF">
              <el-upload
                ref="uploadRef"
                :auto-upload="false"
                :limit="1"
                accept=".pdf"
                :on-change="handleFileChange"
                drag
                style="width: 100%"
              >
                <el-icon class="el-icon--upload"><upload-filled /></el-icon>
                <div class="el-upload__text">
                  将 PDF 文件拖到此处，或 <em>点击上传</em>
                </div>
                <template #tip>
                  <div class="el-upload__tip">只支持 PDF 文件，最大 100MB</div>
                </template>
              </el-upload>
            </el-form-item>

            <el-form-item label="NER Prompt">
              <el-select v-model="selectedNerPrompt" placeholder="选择 NER Prompt 模板" :loading="loadingPrompts" style="width: 350px">
                <el-option
                  v-for="prompt in nerPrompts"
                  :key="prompt.name"
                  :label="prompt.description || prompt.name"
                  :value="prompt.name"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="RE Prompt">
              <el-select v-model="selectedRePrompt" placeholder="选择 RE Prompt 模板" :loading="loadingPrompts" style="width: 350px">
                <el-option
                  v-for="prompt in rePrompts"
                  :key="prompt.name"
                  :label="prompt.description || prompt.name"
                  :value="prompt.name"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="相似论文数量">
              <el-input-number v-model="oneClickTopK" :min="5" :max="50" />
            </el-form-item>

            <el-form-item>
              <el-button type="primary" :loading="oneClickLoading" @click="startOneClickAnalysis">
                开始一键处理
              </el-button>
              <el-button v-if="taskId" type="danger" @click="deleteTask">删除任务</el-button>
              <el-button @click="clearAnalysis">清空</el-button>
            </el-form-item>

            <el-alert type="warning" :closable="false" show-icon style="margin-top: 10px">
              <template #title>
                一键处理需要调用 LLM API 进行 NER、RE 和深度分析，可能需要数分钟时间，请耐心等待
              </template>
            </el-alert>
          </el-form>

          <!-- 任务进度 -->
          <div class="progress-section" v-if="taskId">
            <el-divider>任务进度</el-divider>
            <div class="progress-info">
              <div class="status-row">
                <span>任务 ID：</span>
                <el-tag>{{ taskId }}</el-tag>
                <span style="margin-left: 20px">状态：</span>
                <el-tag :type="getStatusType(taskStatus)">
                  {{ taskStatus }}
                </el-tag>
              </div>
              <!-- 显示当前使用的Prompt文件 -->
              <div class="config-row" v-if="taskStatus === 'running'">
                <el-descriptions :column="2" border size="small">
                  <el-descriptions-item label="NER Prompt">
                    <el-tag type="info" size="small">{{ nerQueryFile }}</el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item label="RE Prompt">
                    <el-tag type="info" size="small">{{ reQueryFile }}</el-tag>
                  </el-descriptions-item>
                </el-descriptions>
              </div>
              <div class="progress-row">
                <span>当前步骤：{{ getStepName(currentStep) }}</span>
                <el-progress
                  :percentage="taskProgress"
                  :color="getProgressColor(taskProgress)"
                  :stroke-width="20"
                  :text-inside="true"
                  style="margin-top: 10px"
                />
              </div>
              <div class="message-row">{{ statusMessage }}</div>
            </div>
          </div>

          <!-- 分析结果 -->
          <div class="result-section" v-if="analysisResult">
            <el-divider>分析结果</el-divider>

            <!-- PDF 信息 -->
            <el-card shadow="never" style="margin-bottom: 15px">
              <el-descriptions title="基本信息" :column="4" border>
                <el-descriptions-item label="文件名">{{ analysisResult.pdf_info?.file_name || 'N/A' }}</el-descriptions-item>
                <el-descriptions-item label="DOI">
                  <el-link v-if="analysisResult.pdf_info?.doi" :href="`https://doi.org/${analysisResult.pdf_info.doi}`" target="_blank" type="primary">
                    {{ analysisResult.pdf_info.doi }}
                  </el-link>
                  <span v-else>N/A</span>
                </el-descriptions-item>
                <el-descriptions-item label="标题">{{ analysisResult.pdf_info?.title || 'N/A' }}</el-descriptions-item>
                <el-descriptions-item label="PDF ID">{{ analysisResult.pdf_info?.result_id || 'N/A' }}</el-descriptions-item>
              </el-descriptions>

              <el-descriptions title="NER/RE 信息" :column="4" border style="margin-top: 10px">
                <el-descriptions-item label="NER ID">{{ analysisResult.pdf_info?.ner_id || 'N/A' }}</el-descriptions-item>
                <el-descriptions-item label="NER 实体数">
                  <el-tag type="success">{{ analysisResult.pdf_info?.ner_entity_count || 0 }}</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="NER Prompt">
                  <el-tag type="info" size="small">{{ analysisResult.pdf_info?.ner_query_file || 'N/A' }}</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="NER Excel">
                  <span v-if="analysisResult.pdf_info?.ner_excel_path">{{ analysisResult.pdf_info.ner_excel_path }}</span>
                  <span v-else>N/A</span>
                </el-descriptions-item>
                <el-descriptions-item label="RE ID">{{ analysisResult.pdf_info?.re_id || 'N/A' }}</el-descriptions-item>
                <el-descriptions-item label="RE 关系数">
                  <el-tag type="success">{{ analysisResult.pdf_info?.re_relation_count || 0 }}</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="RE Prompt">
                  <el-tag type="info" size="small">{{ analysisResult.pdf_info?.re_query_file || 'N/A' }}</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="RE Excel">
                  <span v-if="analysisResult.pdf_info?.re_excel_path">{{ analysisResult.pdf_info.re_excel_path }}</span>
                  <span v-else>N/A</span>
                </el-descriptions-item>
              </el-descriptions>
            </el-card>

            <!-- 技术路线 -->
            <el-collapse>
              <el-collapse-item title="技术路线分析" name="tech_route">
                <el-card shadow="never" class="text-card">
                  <pre class="profile-text">{{ getDisplayText(analysisResult.tech_route?.tech_route_text, 'tech_route') || '无技术路线数据' }}</pre>
                  <el-button
                    v-if="needsTruncation(analysisResult.tech_route?.tech_route_text)"
                    type="primary"
                    link
                    size="small"
                    @click="toggleTextExpand('tech_route')"
                  >
                    {{ expandedTexts['tech_route'] ? '收起' : '展开全部' }}
                  </el-button>
                </el-card>
                <el-table :data="analysisResult.tech_route?.similar_papers || []" v-if="(analysisResult.tech_route?.similar_papers || []).length > 0" style="margin-top: 10px">
                  <el-table-column type="index" label="#" width="50" />
                  <el-table-column prop="doi" label="DOI" min-width="180" show-overflow-tooltip />
                  <el-table-column prop="score" label="相似度" width="100">
                    <template #default="{ row }">{{ (row.score * 100).toFixed(1) }}%</template>
                  </el-table-column>
                </el-table>
              </el-collapse-item>

              <!-- 实验方案 -->
              <el-collapse-item title="实验方案分析（8维度）" name="exp_scheme">
                <el-card shadow="never" class="text-card">
                  <pre class="profile-text">{{ getDisplayText(analysisResult.exp_scheme?.exp_scheme_text, 'exp_scheme') || '无实验方案数据' }}</pre>
                  <el-button
                    v-if="needsTruncation(analysisResult.exp_scheme?.exp_scheme_text)"
                    type="primary"
                    link
                    size="small"
                    @click="toggleTextExpand('exp_scheme')"
                  >
                    {{ expandedTexts['exp_scheme'] ? '收起' : '展开全部' }}
                  </el-button>
                </el-card>
              </el-collapse-item>

              <!-- Jc 分析 -->
              <el-collapse-item title="Jc 指标分析" name="jc_analysis">
                <el-descriptions v-if="analysisResult.jc_analysis?.ranking?.target_doi" :column="2" border size="small" style="margin-bottom: 10px">
                  <el-descriptions-item label="目标 DOI">
                    <el-link v-if="analysisResult.jc_analysis.ranking.target_doi" :href="`https://doi.org/${analysisResult.jc_analysis.ranking.target_doi}`" target="_blank" type="primary">
                      {{ analysisResult.jc_analysis.ranking.target_doi }}
                    </el-link>
                  </el-descriptions-item>
                  <el-descriptions-item v-if="analysisResult.jc_analysis.ranking.target_jc_max" label="目标 Jc 最大值">
                    {{ analysisResult.jc_analysis.ranking.target_jc_max }} A/cm²
                  </el-descriptions-item>
                </el-descriptions>
                <el-descriptions v-if="analysisResult.jc_analysis?.conditions" :column="3" border>
                  <el-descriptions-item label="温度">{{ analysisResult.jc_analysis.conditions.temperature || 'N/A' }} K</el-descriptions-item>
                  <el-descriptions-item label="磁场">{{ analysisResult.jc_analysis.conditions.magnetic_field || 'N/A' }} T</el-descriptions-item>
                  <el-descriptions-item label="角度">{{ analysisResult.jc_analysis.conditions.angle || 'N/A' }} deg</el-descriptions-item>
                </el-descriptions>
                <el-alert v-if="!analysisResult.jc_analysis?.conditions && !analysisResult.jc_analysis?.ranking?.target_doi" type="info" :closable="false">未提取到 Jc 条件参数</el-alert>
                <div v-if="analysisResult.jc_analysis?.jc_indicators && analysisResult.jc_analysis.jc_indicators.length > 0" style="margin-top: 10px">
                  <el-table :data="analysisResult.jc_analysis.jc_indicators" stripe border size="small">
                    <el-table-column type="index" label="#" width="50" />
                    <el-table-column prop="jc_value" label="Jc 值" width="120" />
                    <el-table-column prop="unit" label="单位" width="100" />
                    <el-table-column label="温度 (K)" width="100">
                      <template #default="{ row }">{{ row.temperature ?? 'N/A' }}</template>
                    </el-table-column>
                    <el-table-column label="磁场 (T)" width="100">
                      <template #default="{ row }">{{ row.magnetic_field ?? 'N/A' }}</template>
                    </el-table-column>
                    <el-table-column label="角度 (°)" width="100">
                      <template #default="{ row }">{{ row.angle ?? 'N/A' }}</template>
                    </el-table-column>
                  </el-table>
                </div>
                <div v-if="analysisResult.jc_analysis?.ranking && analysisResult.jc_analysis.ranking.success" style="margin-top: 10px">
                  <el-descriptions title="Jc 排名" :column="2" border size="small">
                    <el-descriptions-item label="目标排名">
                      {{ analysisResult.jc_analysis.ranking.target_rank ?? '未排名' }}
                    </el-descriptions-item>
                    <el-descriptions-item label="总论文数">
                      {{ analysisResult.jc_analysis.ranking.total_papers ?? 0 }}
                    </el-descriptions-item>
                    <el-descriptions-item v-if="analysisResult.jc_analysis.ranking.rank_percentile" label="百分位">
                      {{ (analysisResult.jc_analysis.ranking.rank_percentile * 100).toFixed(1) }}%
                    </el-descriptions-item>
                  </el-descriptions>
                </div>
              </el-collapse-item>

              <!-- LLM 报告 -->
              <el-collapse-item title="LLM 综合分析报告" name="llm">
                <el-card shadow="never" class="text-card">
                  <pre class="profile-text">{{ getDisplayText(analysisResult.llm_comparison, 'llm') || '无 LLM 分析结果' }}</pre>
                  <el-button
                    v-if="needsTruncation(analysisResult.llm_comparison)"
                    type="primary"
                    link
                    size="small"
                    @click="toggleTextExpand('llm')"
                  >
                    {{ expandedTexts['llm'] ? '收起' : '展开全部' }}
                  </el-button>
                </el-card>
              </el-collapse-item>
            </el-collapse>

            <!-- 报告下载 -->
            <div v-if="analysisResult.report_paths || analysisResult.report_path" style="margin-top: 15px">
              <el-divider>报告下载</el-divider>
              <div class="report-download-buttons">
                <el-button
                  v-if="analysisResult.report_paths?.markdown || analysisResult.report_path"
                  type="primary"
                  @click="downloadReport('md')"
                  icon="Download"
                >
                  Markdown 报告
                </el-button>
                <el-button
                  v-if="analysisResult.report_paths?.excel"
                  type="success"
                  @click="downloadReport('excel')"
                  icon="Download"
                >
                  Excel 报告
                </el-button>
                <el-button
                  v-if="analysisResult.report_paths?.pdf"
                  type="warning"
                  @click="downloadReport('pdf')"
                  icon="Download"
                >
                  PDF 报告
                </el-button>
              </div>
            </div>

            <!-- 原报告路径显示（兼容） -->
            <div v-if="analysisResult.report_path && !analysisResult.report_paths" style="margin-top: 15px">
              <el-tag type="info">报告路径: {{ analysisResult.report_path }}</el-tag>
            </div>
          </div>

          <!-- 任务历史列表 — 使用 el-tabs 切换 -->
          <div class="task-history-section">
            <el-divider>
              <span>历史任务列表</span>
              <el-button size="small" type="primary" link @click="fetchTaskList" :loading="loadingTaskList" style="margin-left: 10px">
                刷新
              </el-button>
            </el-divider>

            <!-- 无任务整体空状态 -->
            <el-empty v-if="taskList.length === 0" description="暂无历史任务" :image-size="80" />

            <!-- 任务分类标签页 -->
            <el-tabs v-else v-model="historyActiveTab">
              <el-tab-pane name="active">
                <template #label>
                  <span>运行中 <el-tag size="small" type="warning">{{ activeTasks.length }}</el-tag></span>
                </template>
                <el-empty v-if="activeTasks.length === 0" description="暂无运行中任务" :image-size="60" />
                <el-table v-else :data="activeTasks" stripe border size="small">
                  <el-table-column prop="task_id" label="任务 ID" min-width="200" show-overflow-tooltip />
                  <el-table-column prop="current_step" label="当前步骤" width="150">
                    <template #default="{ row }">
                      <el-tag size="small">{{ getStepName(row.current_step) }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="progress" label="进度" width="120">
                    <template #default="{ row }">
                      <el-progress :percentage="row.progress" :color="getProgressColor(row.progress)" :stroke-width="15" :text-inside="true" />
                    </template>
                  </el-table-column>
                  <el-table-column prop="message" label="消息" min-width="150" show-overflow-tooltip />
                  <el-table-column prop="created_at" label="创建时间" width="150">
                    <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
                  </el-table-column>
                  <el-table-column label="操作" width="150">
                    <template #default="{ row }">
                      <el-button size="small" type="primary" link @click="resumeTask(row)">恢复监控</el-button>
                      <el-button size="small" type="danger" link @click="deleteTaskFromList(row.task_id)">删除</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </el-tab-pane>

              <el-tab-pane name="completed">
                <template #label>
                  <span>已完成 <el-tag size="small" type="success">{{ completedTasks.length }}</el-tag></span>
                </template>
                <el-empty v-if="completedTasks.length === 0" description="暂无已完成任务" :image-size="60" />
                <el-table v-else :data="completedTasks" stripe border size="small">
                  <el-table-column prop="task_id" label="任务 ID" min-width="200" show-overflow-tooltip />
                  <el-table-column prop="message" label="消息" min-width="150" show-overflow-tooltip />
                  <el-table-column prop="created_at" label="创建时间" width="150">
                    <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
                  </el-table-column>
                  <el-table-column prop="updated_at" label="完成时间" width="150">
                    <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
                  </el-table-column>
                  <el-table-column label="操作" width="150">
                    <template #default="{ row }">
                      <el-button size="small" type="primary" link @click="resumeTask(row)">查看结果</el-button>
                      <el-button size="small" type="danger" link @click="deleteTaskFromList(row.task_id)">删除</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </el-tab-pane>

              <el-tab-pane name="failed">
                <template #label>
                  <span>失败 <el-tag size="small" type="danger">{{ failedTasks.length }}</el-tag></span>
                </template>
                <el-empty v-if="failedTasks.length === 0" description="暂无失败任务" :image-size="60" />
                <el-table v-else :data="failedTasks" stripe border size="small">
                  <el-table-column prop="task_id" label="任务 ID" min-width="200" show-overflow-tooltip />
                  <el-table-column prop="message" label="错误信息" min-width="150" show-overflow-tooltip />
                  <el-table-column prop="created_at" label="创建时间" width="150">
                    <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
                  </el-table-column>
                  <el-table-column label="操作" width="100">
                    <template #default="{ row }">
                      <el-button size="small" type="danger" link @click="deleteTaskFromList(row.task_id)">删除</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </el-tab-pane>
            </el-tabs>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<style scoped>
/* 页面特有样式 — 全局布局类（page-container / page-header / page-header-left
   / page-title / page-description / card-header）已在 common.css 中定义，此处不再重复 */

.stats-card,
.main-card {
  margin-bottom: 20px;
}

.result-section,
.progress-section {
  margin-top: 20px;
}

.progress-info {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.status-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.config-row {
  margin-top: 10px;
}

.progress-row {
  display: flex;
  flex-direction: column;
}

.message-row {
  color: var(--text-regular);
  font-size: 14px;
}

.text-card {
  background: var(--bg-page);
}

.profile-text {
  white-space: pre-wrap;
  word-wrap: break-word;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-primary);
  margin: 0;
}

.task-history-section {
  margin-top: 20px;
}

.report-download-buttons {
  display: flex;
  gap: 15px;
  justify-content: center;
  padding: 10px 0;
}

.report-download-buttons .el-button {
  min-width: 180px;
}
</style>
