/**
 * 通用工具函数 — 跨页面高频复用的纯函数
 */

// ===== 状态映射 =====

/** 将任务状态映射为 Element Plus el-tag 的 type 值
 *  el-tag 合法 type: '' | 'success' | 'warning' | 'info' | 'danger'
 */
export function getStatusType(status: string): string {
  const map: Record<string, string> = {
    completed: 'success',
    processing: 'warning',
    pending: 'info',
    running: 'warning',
    failed: 'danger',
    cancelled: 'info',
  }
  return map[status] || 'info'
}

/** 将任务状态映射为中文显示文本 */
export function getStatusText(status: string): string {
  const map: Record<string, string> = {
    pending: '等待中',
    processing: '处理中',
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return map[status] || status
}

// ===== 任务可见性过滤 =====

/** 已取消任务超过指定小时数后隐藏（与后端 batch_service.py 保持一致）
 *  优先使用 updated_at（取消操作会更新此字段），缺失时回退到 created_at
 */
export function shouldHideCancelledTask(
  task: { status?: string; updated_at?: number | string; created_at?: number | string },
  hideAfterHours = 24
): boolean {
  if (task.status !== 'cancelled') return false
  const timestamp = task.updated_at ?? task.created_at
  if (!timestamp) return false
  let tsSeconds: number
  if (typeof timestamp === 'string') {
    tsSeconds = new Date(timestamp).getTime() / 1000
  } else {
    // 毫秒级时间戳 (>=1e12) 需除以 1000，秒级直接使用
    tsSeconds = timestamp < 1e12 ? timestamp : timestamp / 1000
  }
  const ageHours = (Date.now() / 1000 - tsSeconds) / 3600
  return ageHours > hideAfterHours
}

// ===== 时间格式化 =====

/** 格式化时间戳或日期字符串为本地时间显示
 *  自动区分秒级(<1e12)和毫秒级(>=1e12)时间戳
 */
export function formatTime(timestamp: number | string | undefined): string {
  if (!timestamp) return '-'
  if (typeof timestamp === 'number') {
    // 秒级时间戳(10位数字)乘以1000转换为毫秒级
    const ms = timestamp < 1e12 ? timestamp * 1000 : timestamp
    return new Date(ms).toLocaleString('zh-CN')
  }
  return new Date(timestamp).toLocaleString('zh-CN')
}

// ===== ID截断 =====

/** 截断长ID显示，保留前N位 + 省略号 */
export function truncateId(id: string, len = 8): string {
  if (!id || len <= 0 || id.length <= len + 3) return id
  return id.substring(0, len) + '...'
}

// ===== 文件下载 =====

/** 触发浏览器下载 Blob 文件 */
export function downloadFile(data: Blob, filename: string): void {
  const url = URL.createObjectURL(data)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

// ===== 实体/关系类型颜色动态分配 =====

/** 10色调色板，用于动态分配实体/关系类型颜色 */
const COLOR_PALETTE = [
  '#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#909399',
  '#b37feb', '#36cfc9', '#ff85c0', '#ffc53d', '#597ef7',
]

/** 根据类型名称从调色板动态分配颜色，相同名称始终返回相同颜色 */
export function getTypeColor(typeName: string): string {
  let hash = 0
  for (const char of typeName) {
    hash = ((hash << 5) - hash) + char.charCodeAt(0)
    hash |= 0
  }
  // 先取模再取绝对值，避免 Math.abs(-2147483648) 溢出返回负数
  const index = Math.abs(hash % COLOR_PALETTE.length)
  return COLOR_PALETTE[index]
}

// ===== Markdown 安全渲染 =====

/** 移除危险HTML标签，保留安全的Markdown渲染内容 */
export function sanitizeHtml(html: string): string {
  let safe = html

  // 多轮替换防止嵌套标签绕过 (如 <scr<script>ipt>)
  let prev = ''
  while (prev !== safe) {
    prev = safe
    safe = safe.replace(/<script[\s\S]*?<\/script>/gi, '')
    safe = safe.replace(/<style[\s\S]*?<\/style>/gi, '')
    safe = safe.replace(/<iframe[\s\S]*?<\/iframe>/gi, '')
    safe = safe.replace(/<object[\s\S]*?<\/object>/gi, '')
    safe = safe.replace(/<embed[\s\S]*?>/gi, '')
    safe = safe.replace(/<form[\s\S]*?<\/form>/gi, '')
    safe = safe.replace(/<link[^>]*>/gi, '')
    safe = safe.replace(/<svg[\s\S]*?<\/svg>/gi, '')
    safe = safe.replace(/<meta[^>]*>/gi, '')
  }

  // 移除 on* 事件属性
  safe = safe.replace(/\s+on\w+\s*=\s*["][^"]*["]/gi, '')
  safe = safe.replace(/\s+on\w+\s*=\s*['][^']*[']/gi, '')
  safe = safe.replace(/\s+on\w+\s*=\s*[^\s>]*/gi, '')

  // 移除 javascript: 和 data: 伪协议
  safe = safe.replace(/href\s*=\s*["']javascript:[^"']*["']/gi, 'href="#"')
  safe = safe.replace(/src\s*=\s*["']javascript:[^"']*["']/gi, 'src="#"')
  safe = safe.replace(/src\s*=\s*["']data:text\/html[^"']*["']/gi, 'src="#"')

  return safe
}