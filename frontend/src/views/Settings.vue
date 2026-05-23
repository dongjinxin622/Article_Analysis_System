<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useUserStore } from '@/stores'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, View } from '@element-plus/icons-vue'
import { promptApi } from '@/api'
import type { User } from '@/types/user'
import type { PromptTemplate } from '@/api/prompt'

const userStore = useUserStore()

// 系统信息
const systemInfo = ref({
  app_name: 'SciPDF AI论文处理系统',
  version: '3.0.0',
  backend_url: 'http://127.0.0.1:8000',
  api_version: 'v1'
})

// Prompt模板管理
const promptTemplates = ref<PromptTemplate[]>([])
const loadingPrompts = ref(false)
const promptFilterCategory = ref<string>('')
const promptDialogVisible = ref(false)
const promptDialogContent = ref('')
const promptDialogName = ref('')
const promptDialogDescription = ref('')
const promptDialogCategory = ref<'ner' | 're'>('ner')
const promptDialogDomain = ref('')
const promptDialogMode = ref<'create' | 'edit'>('create')

// Prompt预览对话框
const previewDialogVisible = ref(false)
const previewTemplateName = ref('')
const previewTemplateContent = ref('')
const previewTemplateDescription = ref('')
const previewTemplateCategory = ref('')
const previewTemplateDomain = ref('')

// 当前用户信息
const currentUser = ref<User | null>(null)

// 用户设置表单（仅展示，不可编辑）
const userForm = ref({
  email: '',
  full_name: ''
})

// 系统配置标签页
const activeTab = ref('system')

// 加载Prompt模板列表
async function loadPromptTemplates() {
  loadingPrompts.value = true
  try {
    const result = await promptApi.list(promptFilterCategory.value || undefined)
    promptTemplates.value = result.templates
  } catch (error: any) {
    ElMessage.error(error.message || '加载Prompt模板失败')
  } finally {
    loadingPrompts.value = false
  }
}

// 打开创建对话框
function openCreateDialog() {
  promptDialogMode.value = 'create'
  promptDialogName.value = ''
  promptDialogContent.value = ''
  promptDialogDescription.value = ''
  promptDialogCategory.value = 'ner'
  promptDialogDomain.value = 'material'
  promptDialogVisible.value = true
}

// 打开编辑对话框
function openEditDialog(template: PromptTemplate) {
  promptDialogMode.value = 'edit'
  promptDialogName.value = template.name
  promptDialogContent.value = template.content
  promptDialogDescription.value = template.description || ''
  promptDialogCategory.value = template.category
  promptDialogDomain.value = template.domain || ''
  promptDialogVisible.value = true
}

// 打开预览对话框（只读）
function openPreviewDialog(template: PromptTemplate) {
  previewTemplateName.value = template.name
  previewTemplateContent.value = template.content
  previewTemplateDescription.value = template.description || ''
  previewTemplateCategory.value = template.category === 'ner' ? 'NER (实体识别)' : 'RE (关系抽取)'
  previewTemplateDomain.value = template.domain || ''
  previewDialogVisible.value = true
}

// 保存Prompt模板
async function savePromptTemplate() {
  if (!promptDialogName.value.trim()) {
    ElMessage.warning('请输入模板名称')
    return
  }
  if (!promptDialogContent.value.trim()) {
    ElMessage.warning('请输入模板内容')
    return
  }

  try {
    if (promptDialogMode.value === 'create') {
      await promptApi.create({
        name: promptDialogName.value,
        content: promptDialogContent.value,
        description: promptDialogDescription.value,
        category: promptDialogCategory.value,
        domain: promptDialogDomain.value
      })
      ElMessage.success('创建成功')
    } else {
      await promptApi.update(promptDialogName.value, {
        content: promptDialogContent.value,
        description: promptDialogDescription.value
      })
      ElMessage.success('更新成功')
    }
    promptDialogVisible.value = false
    await loadPromptTemplates()
  } catch (error: any) {
    ElMessage.error(error.message || '保存失败')
  }
}

// 删除Prompt模板
async function deletePromptTemplate(name: string) {
  try {
    await ElMessageBox.confirm(`确定删除Prompt模板 "${name}"？`, '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await promptApi.delete(name)
    ElMessage.success('删除成功')
    await loadPromptTemplates()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error.message || '删除失败')
    }
  }
}

onMounted(() => {
  currentUser.value = userStore.user
  if (currentUser.value) {
    userForm.value.email = currentUser.value.email || ''
    userForm.value.full_name = currentUser.value.full_name || ''
  }
  loadPromptTemplates()
})
</script>

<template>
  <div class="page-container settings">
    <div class="page-header">
      <div class="page-header-left">
        <h2 class="page-title">系统设置</h2>
        <p class="page-description">管理用户信息、Prompt 模板和系统配置</p>
      </div>
    </div>

    <el-tabs v-model="activeTab">
      <!-- 系统信息 -->
      <el-tab-pane label="系统信息" name="system">
        <el-card>
          <template #header>
            <span>系统信息</span>
          </template>

          <el-descriptions :column="2" border>
            <el-descriptions-item label="应用名称">{{ systemInfo.app_name }}</el-descriptions-item>
            <el-descriptions-item label="版本">{{ systemInfo.version }}</el-descriptions-item>
            <el-descriptions-item label="后端地址">{{ systemInfo.backend_url }}</el-descriptions-item>
            <el-descriptions-item label="API 版本">{{ systemInfo.api_version }}</el-descriptions-item>
          </el-descriptions>

          <el-divider>服务状态</el-divider>

          <el-row :gutter="20">
            <el-col :span="6">
              <el-card shadow="hover">
                <el-statistic title="MySQL" value="示例数据" />
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card shadow="hover">
                <el-statistic title="Milvus" value="示例数据" />
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card shadow="hover">
                <el-statistic title="GROBID" value="示例数据" />
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card shadow="hover">
                <el-statistic title="LLM API" value="示例数据" />
              </el-card>
            </el-col>
          </el-row>
          <p class="sample-data-notice">此为示例数据，实际状态需后端接口支持</p>
        </el-card>
      </el-tab-pane>

      <!-- Prompt 模板 -->
      <el-tab-pane label="Prompt 模板" name="prompts">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>Prompt 模板管理</span>
              <div class="header-actions">
                <el-select v-model="promptFilterCategory" placeholder="筛选分类" clearable style="width: 120px; margin-right: 10px" @change="loadPromptTemplates">
                  <el-option label="NER" value="ner" />
                  <el-option label="RE" value="re" />
                </el-select>
                <el-button type="primary" @click="openCreateDialog">
                  <el-icon><Plus /></el-icon>
                  新建模板
                </el-button>
              </div>
            </div>
          </template>

          <el-table v-loading="loadingPrompts" :data="promptTemplates" style="width: 100%">
            <el-table-column prop="name" label="名称" width="180" />
            <el-table-column prop="category" label="分类" width="100">
              <template #default="{ row }">
                <el-tag :type="row.category === 'ner' ? 'info' : 'success'" size="small">
                  {{ row.category === 'ner' ? 'NER' : 'RE' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="domain" label="领域" width="120">
              <template #default="{ row }">
                <el-tag v-if="row.domain" type="warning" size="small">{{ row.domain }}</el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column label="归属" width="100">
              <template #default="{ row }">
                <el-tag v-if="row.user_id === null || row.user_id === undefined" type="info" size="small">系统共享</el-tag>
                <el-tag v-else type="info" size="small">我的</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
            <el-table-column prop="is_active" label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                  {{ row.is_active ? '活跃' : '禁用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="240">
              <template #default="{ row }">
                <el-button size="small" @click="openPreviewDialog(row)">
                  <el-icon><View /></el-icon>
                  预览
                </el-button>
                <el-button
                  v-if="row.user_id !== null && row.user_id !== undefined"
                  size="small"
                  @click="openEditDialog(row)"
                >编辑</el-button>
                <el-button
                  v-else-if="currentUser?.is_admin"
                  size="small"
                  @click="openEditDialog(row)"
                >编辑</el-button>
                <span v-else class="text-secondary text-sm">不可编辑</span>
                <el-button
                  v-if="row.user_id !== null && row.user_id !== undefined"
                  size="small"
                  type="danger"
                  @click="deletePromptTemplate(row.name)"
                >删除</el-button>
                <span v-else class="text-secondary text-sm">不可删除</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- Prompt预览对话框（只读） -->
        <el-dialog v-model="previewDialogVisible" title="Prompt 模板预览" width="80%">
          <el-descriptions :column="2" border style="margin-bottom: var(--spacing-md)">
            <el-descriptions-item label="模板名称">{{ previewTemplateName }}</el-descriptions-item>
            <el-descriptions-item label="分类">{{ previewTemplateCategory }}</el-descriptions-item>
            <el-descriptions-item label="领域">{{ previewTemplateDomain || '-' }}</el-descriptions-item>
            <el-descriptions-item label="描述">{{ previewTemplateDescription || '-' }}</el-descriptions-item>
          </el-descriptions>
          <div class="prompt-preview-content">{{ previewTemplateContent }}</div>
          <template #footer>
            <el-button @click="previewDialogVisible = false">关闭</el-button>
          </template>
        </el-dialog>

        <!-- Prompt编辑对话框 -->
        <el-dialog v-model="promptDialogVisible" :title="promptDialogMode === 'create' ? '新建 Prompt 模板' : '编辑 Prompt 模板'" width="700px">
          <el-form label-width="100px">
            <el-form-item label="模板名称">
              <el-input v-model="promptDialogName" :disabled="promptDialogMode === 'edit'" placeholder="输入模板名称" />
            </el-form-item>
            <el-form-item label="分类">
              <el-select v-model="promptDialogCategory" :disabled="promptDialogMode === 'edit'" style="width: 100%">
                <el-option label="NER (实体识别)" value="ner" />
                <el-option label="RE (关系抽取)" value="re" />
              </el-select>
            </el-form-item>
            <el-form-item label="领域">
              <el-input v-model="promptDialogDomain" :disabled="promptDialogMode === 'edit'" placeholder="如: material" />
            </el-form-item>
            <el-form-item label="描述">
              <el-input v-model="promptDialogDescription" placeholder="模板描述" />
            </el-form-item>
            <el-form-item label="模板内容">
              <el-input v-model="promptDialogContent" type="textarea" :autosize="{ minRows: 10, maxRows: 20 }" placeholder="输入Prompt模板内容" class="prompt-editor-input" />
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="promptDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="savePromptTemplate">保存</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>

      <!-- 用户设置（仅展示，不可编辑） -->
      <el-tab-pane label="用户设置" name="user">
        <el-card>
          <template #header>
            <span>个人信息</span>
          </template>

          <el-descriptions :column="2" border>
            <el-descriptions-item label="用户名">{{ currentUser?.username || '-' }}</el-descriptions-item>
            <el-descriptions-item label="邮箱">{{ currentUser?.email || '-' }}</el-descriptions-item>
            <el-descriptions-item label="姓名">{{ currentUser?.full_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="角色">
              <el-tag :type="currentUser?.is_admin ? 'warning' : 'info'">
                {{ currentUser?.is_admin ? '管理员' : '普通用户' }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>

          <p class="feature-notice">个人信息编辑功能将在后续版本提供</p>
        </el-card>
      </el-tab-pane>

      <!-- 领域配置 -->
      <el-tab-pane label="领域配置" name="domain">
        <el-empty description="敬请期待">
          <template #extra>
            <p class="text-secondary">领域配置功能将在后续版本提供</p>
          </template>
        </el-empty>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
/* 仅保留组件特有样式，通用样式由 common.css 提供 */

.header-actions {
  display: flex;
  align-items: center;
}

.el-row .el-card {
  margin-bottom: 0;
}

/* 示例数据提示文字 */
.sample-data-notice {
  color: var(--text-secondary);
  font-size: 12px;
  margin-top: var(--spacing-sm);
  text-align: center;
}

/* 功能未提供提示文字 */
.feature-notice {
  color: var(--text-secondary);
  font-size: 13px;
  margin-top: var(--spacing-md);
  text-align: center;
}

/* Prompt预览内容区域 — 等宽字体 */
.prompt-preview-content {
  font-family: Consolas, Monaco, monospace;
  background-color: var(--bg-page);
  border: 1px solid var(--border-color-light);
  border-radius: var(--border-radius-sm);
  padding: var(--spacing-md);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
  max-height: 60vh;
  overflow-y: auto;
}

/* Prompt编辑器等宽字体 */
.prompt-editor-input .el-textarea__inner {
  font-family: Consolas, Monaco, monospace;
}
</style>