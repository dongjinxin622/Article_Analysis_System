<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useUserStore } from '@/stores'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, View } from '@element-plus/icons-vue'
import { promptApi } from '@/api'
import type { User } from '@/types/user'
import type { PromptTemplate } from '@/api/prompt'

const userStore = useUserStore()

// 系统信息（从后端 API 获取）
const systemInfo = ref({
  app_name: '加载中...',
  version: '加载中...',
  debug: false,
  api_prefix: 'v1'
})

// 服务状态
const serviceStatus = ref<Record<string, any>>({})
const loadingStatus = ref(false)

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

// 用户设置表单
const userForm = ref({
  email: '',
  full_name: ''
})
const savingProfile = ref(false)

// 密码修改表单
const passwordForm = ref({
  old_password: '',
  new_password: '',
  confirm_password: ''
})
const savingPassword = ref(false)

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

// 加载系统配置
async function loadSystemConfig() {
  try {
    const { request } = await import('@/api/request')
    const [sysResp, statusResp] = await Promise.all([
      request.get('/config/system'),
      request.get('/config/status')
    ])
    systemInfo.value = sysResp
    serviceStatus.value = (statusResp as any).services || {}
  } catch (error: any) {
    console.error('加载系统配置失败:', error)
  }
}

onMounted(() => {
  currentUser.value = userStore.user
  if (currentUser.value) {
    userForm.value.email = currentUser.value.email || ''
    userForm.value.full_name = currentUser.value.nickname || ''
  }
  loadSystemConfig()
  loadPromptTemplates()
})

// 保存用户资料
async function saveProfile() {
  savingProfile.value = true
  try {
    await userStore.updateProfile({
      email: userForm.value.email,
      full_name: userForm.value.full_name
    })
    ElMessage.success('资料已更新')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || error.message || '保存失败')
  } finally {
    savingProfile.value = false
  }
}

// 修改密码
async function savePassword() {
  if (passwordForm.value.new_password !== passwordForm.value.confirm_password) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  savingPassword.value = true
  try {
    await userStore.updatePassword({
      old_password: passwordForm.value.old_password,
      new_password: passwordForm.value.new_password,
      confirm_password: passwordForm.value.confirm_password
    })
    ElMessage.success('密码已修改')
    passwordForm.value = { old_password: '', new_password: '', confirm_password: '' }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || error.message || '修改失败')
  } finally {
    savingPassword.value = false
  }
}
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
            <el-descriptions-item label="调试模式">{{ systemInfo.debug ? '开启' : '关闭' }}</el-descriptions-item>
            <el-descriptions-item label="API 前缀">{{ systemInfo.api_prefix }}</el-descriptions-item>
          </el-descriptions>

          <el-divider>服务状态</el-divider>

          <el-row :gutter="20">
            <el-col :span="6">
              <el-card shadow="hover" :class="{ 'service-card': true, 'service-error': !serviceStatus.postgres?.connected }">
                <div class="service-header">
                  <span class="service-title">PostgreSQL</span>
                  <el-tag :type="serviceStatus.postgres?.connected ? 'success' : 'danger'" size="small" effect="dark">
                    {{ serviceStatus.postgres?.connected ? '已连接' : '未连接' }}
                  </el-tag>
                </div>
                <div class="service-detail" v-if="serviceStatus.postgres">
                  <span>{{ serviceStatus.postgres.host }}:{{ serviceStatus.postgres.port }}</span>
                  <span class="service-db">{{ serviceStatus.postgres.database }}</span>
                </div>
                <div class="service-detail" v-else><span>加载中...</span></div>
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card shadow="hover" :class="{ 'service-card': true, 'service-error': !serviceStatus.milvus?.connected }">
                <div class="service-header">
                  <span class="service-title">Milvus</span>
                  <el-tag :type="serviceStatus.milvus?.connected ? 'success' : 'danger'" size="small" effect="dark">
                    {{ serviceStatus.milvus?.connected ? '已连接' : '未连接' }}
                  </el-tag>
                </div>
                <div class="service-detail" v-if="serviceStatus.milvus">
                  <span>{{ serviceStatus.milvus.host }}:{{ serviceStatus.milvus.port }}</span>
                  <span v-if="serviceStatus.milvus.collections !== undefined" class="service-db">{{ serviceStatus.milvus.collections }} 个集合</span>
                </div>
                <div class="service-detail" v-else><span>加载中...</span></div>
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card shadow="hover" :class="{ 'service-card': true, 'service-error': !serviceStatus.redis?.connected }">
                <div class="service-header">
                  <span class="service-title">Redis</span>
                  <el-tag :type="serviceStatus.redis?.connected ? 'success' : 'danger'" size="small" effect="dark">
                    {{ serviceStatus.redis?.connected ? '已连接' : '未连接' }}
                  </el-tag>
                </div>
                <div class="service-detail" v-if="serviceStatus.redis">
                  <span>{{ serviceStatus.redis.host }}:{{ serviceStatus.redis.port }}</span>
                  <span class="service-db">DB {{ serviceStatus.redis.db }}</span>
                </div>
                <div class="service-detail" v-else><span>加载中...</span></div>
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card shadow="hover" :class="{ 'service-card': true, 'service-error': !serviceStatus.grobid?.connected }">
                <div class="service-header">
                  <span class="service-title">GROBID</span>
                  <el-tag :type="serviceStatus.grobid?.connected ? 'success' : 'danger'" size="small" effect="dark">
                    {{ serviceStatus.grobid?.connected ? '已连接' : '未连接' }}
                  </el-tag>
                </div>
                <div class="service-detail" v-if="serviceStatus.grobid">
                  <span class="service-url">{{ serviceStatus.grobid.url }}</span>
                </div>
                <div class="service-detail" v-else><span>加载中...</span></div>
              </el-card>
            </el-col>
          </el-row>
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
                  v-else-if="currentUser?.is_superuser"
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

      <!-- 用户设置 -->
      <el-tab-pane label="用户设置" name="user">
        <el-card>
          <template #header>
            <span>个人信息</span>
          </template>

          <el-descriptions :column="2" border style="margin-bottom: 20px">
            <el-descriptions-item label="用户名">{{ currentUser?.username || '-' }}</el-descriptions-item>
            <el-descriptions-item label="角色">
              <el-tag :type="currentUser?.is_superuser ? 'warning' : 'info'">
                {{ currentUser?.is_superuser ? '管理员' : '普通用户' }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>

          <el-divider>编辑资料</el-divider>

          <el-form label-width="80px" style="max-width: 500px">
            <el-form-item label="邮箱">
              <el-input v-model="userForm.email" placeholder="输入邮箱" />
            </el-form-item>
            <el-form-item label="姓名">
              <el-input v-model="userForm.full_name" placeholder="输入姓名" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingProfile" @click="saveProfile">保存资料</el-button>
            </el-form-item>
          </el-form>

          <el-divider>修改密码</el-divider>

          <el-form label-width="100px" style="max-width: 500px">
            <el-form-item label="旧密码">
              <el-input v-model="passwordForm.old_password" type="password" show-password placeholder="输入旧密码" />
            </el-form-item>
            <el-form-item label="新密码">
              <el-input v-model="passwordForm.new_password" type="password" show-password placeholder="输入新密码" />
            </el-form-item>
            <el-form-item label="确认新密码">
              <el-input v-model="passwordForm.confirm_password" type="password" show-password placeholder="再次输入新密码" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingPassword" @click="savePassword">修改密码</el-button>
            </el-form-item>
          </el-form>
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

/* 服务状态卡片 */
.service-card {
  transition: border-color 0.2s;
}

.service-card .service-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.service-card .service-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.service-card .service-detail {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: var(--text-secondary);
}

.service-card .service-detail .service-db {
  font-size: 12px;
  color: var(--text-secondary);
  opacity: 0.8;
}

.service-card .service-detail .service-url {
  font-size: 12px;
  word-break: break-all;
  color: var(--text-secondary);
}

.service-card.service-error {
  border-left: 3px solid var(--el-color-danger);
}
</style>