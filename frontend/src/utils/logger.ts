/**
 * 前端日志工具
 * 将日志记录到本地文件（通过localStorage模拟）和控制台
 */

// 日志级别
type LogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR'

// 日志条目
interface LogEntry {
  timestamp: string
  level: LogLevel
  module: string
  message: string
  data?: any
}

// 最大日志条数（localStorage限制）
const MAX_LOG_ENTRIES = 1000

class Logger {
  private logs: LogEntry[] = []
  private storageKey = 'scipdf_frontend_logs'

  constructor() {
    this.loadLogs()
  }

  // 从localStorage加载日志
  private loadLogs() {
    try {
      const stored = localStorage.getItem(this.storageKey)
      if (stored) {
        this.logs = JSON.parse(stored)
      }
    } catch (e) {
      this.logs = []
    }
  }

  // 保存日志到localStorage
  private saveLogs() {
    try {
      // 限制日志数量
      if (this.logs.length > MAX_LOG_ENTRIES) {
        this.logs = this.logs.slice(-MAX_LOG_ENTRIES)
      }
      localStorage.setItem(this.storageKey, JSON.stringify(this.logs))
    } catch (e) {
      // localStorage满了，清理旧日志
      this.logs = this.logs.slice(-500)
      localStorage.setItem(this.storageKey, JSON.stringify(this.logs))
    }
  }

  // 添加日志
  private log(level: LogLevel, module: string, message: string, data?: any) {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      module,
      message,
      data
    }

    this.logs.push(entry)
    this.saveLogs()

    // 同时输出到控制台
    const consoleMethod = level === 'ERROR' ? 'error' : level === 'WARN' ? 'warn' : 'log'
    console[consoleMethod](`[${entry.timestamp}] [${level}] [${module}] ${message}`, data || '')
  }

  debug(module: string, message: string, data?: any) {
    this.log('DEBUG', module, message, data)
  }

  info(module: string, message: string, data?: any) {
    this.log('INFO', module, message, data)
  }

  warn(module: string, message: string, data?: any) {
    this.log('WARN', module, message, data)
  }

  error(module: string, message: string, data?: any) {
    this.log('ERROR', module, message, data)
  }

  // 获取所有日志
  getAllLogs(): LogEntry[] {
    return this.logs
  }

  // 获取错误日志
  getErrorLogs(): LogEntry[] {
    return this.logs.filter(l => l.level === 'ERROR')
  }

  // 清空日志
  clearLogs() {
    this.logs = []
    localStorage.removeItem(this.storageKey)
  }

  // 导出日志为文本
  exportLogs(): string {
    return this.logs.map(l =>
      `[${l.timestamp}] [${l.level}] [${l.module}] ${l.message}${l.data ? ' | ' + JSON.stringify(l.data) : ''}`
    ).join('\n')
  }

  // 导出日志为JSON文件（可下载）
  downloadLogs() {
    const blob = new Blob([this.exportLogs()], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `frontend_logs_${new Date().toISOString().slice(0, 10)}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }
}

// 导出单例
export const logger = new Logger()

// 模块级日志器
export const createModuleLogger = (module: string) => ({
  debug: (msg: string, data?: any) => logger.debug(module, msg, data),
  info: (msg: string, data?: any) => logger.info(module, msg, data),
  warn: (msg: string, data?: any) => logger.warn(module, msg, data),
  error: (msg: string, data?: any) => logger.error(module, msg, data),
})