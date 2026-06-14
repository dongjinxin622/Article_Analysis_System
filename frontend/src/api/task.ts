import { request } from '@/api/request'

export type TaskJobStatus =
  | 'pending'
  | 'running'
  | 'paused'
  | 'succeeded'
  | 'partial_failed'
  | 'failed'
  | 'canceled'

export type TaskItemStatus =
  | 'pending'
  | 'running'
  | 'paused'
  | 'succeeded'
  | 'failed'
  | 'canceled'

export type AgentTaskType = string

export interface AgentModelOverrides {
  textModel?: string | null
  imageModel?: string | null
}

export interface TaskItemInput {
  inputPayload?: Record<string, unknown> | unknown[] | null
}

export interface TaskJobCreateRequest {
  taskType: AgentTaskType
  name: string
  modelOverrides?: AgentModelOverrides
  queueName?: string
  defaultParams?: Record<string, unknown> | null
  items: TaskItemInput[]
}

export interface TaskJobCancelRequest {
  itemPublicIds?: string[] | null
}

export interface TaskJobRetryRequest {
  itemPublicIds: string[]
}

export interface TaskJobPauseRequest {
  itemPublicIds?: string[] | null
}

export interface TaskJobResumeRequest {
  itemPublicIds?: string[] | null
}

export interface TaskItemDiagnostics {
  modelId: string
  providerKey: string
  workerConsumerName?: string | null
  claimToCallMs?: number | null
  durationMs?: number | null
  attemptCount: number
  composedPromptLength?: number | null
  startedAt?: string | null
  finishedAt?: string | null
}

export interface TaskItemResponse {
  publicId: string
  seq: number
  status: TaskItemStatus
  inputPayload?: Record<string, unknown> | unknown[] | null
  composedPrompt?: string | null
  finalPrompt?: string | null
  outputText?: string | null
  errorMessage?: string | null
  retryOfPublicId?: string | null
  diagnostics?: TaskItemDiagnostics | null
  createdAt: string
  updatedAt: string
  startedAt?: string | null
  finishedAt?: string | null
}

export interface TaskJobResponse {
  publicId: string
  projectPublicId: string
  creatorPublicId: string
  taskType: AgentTaskType
  name: string
  status: TaskJobStatus
  totalCount: number
  pendingCount: number
  runningCount: number
  succeededCount: number
  failedCount: number
  canceledCount: number
  pausedCount: number
  modelId: string
  providerKey: string
  defaultParams?: Record<string, unknown> | null
  createdAt: string
  updatedAt: string
  startedAt?: string | null
  finishedAt?: string | null
}

export interface TaskJobListResponse {
  items: TaskJobResponse[]
  total: number
  page: number
  pageSize: number
}

export interface TaskItemListResponse {
  items: TaskItemResponse[]
  total: number
  page: number
  pageSize: number
}

export interface TaskJobCancelResponse {
  canceledCount: number
}

export interface TaskJobPauseResponse {
  pausedCount: number
}

export interface TaskJobResumeResponse {
  resumedCount: number
}

export interface TaskJobRetryResponse {
  newItemPublicIds: string[]
}

export interface TaskJobDeleteResponse {
  status: string
}

export interface QueueStatsView {
  pendingItemCount: number
  runningItemCount: number
  requeueLast5Min: number
}

export interface ActivityWindowView {
  submittedItemCount: number
  completedItemCount: number
  failedItemCount: number
  avgDurationMs: number
}

export interface RecentActivityView {
  lastMinute: ActivityWindowView
  lastThirtyMinutes: ActivityWindowView
  lastHour: ActivityWindowView
  lastSixHours: ActivityWindowView
}

export interface TaskMetricsResponse {
  queueStats: QueueStatsView
  recentActivity: RecentActivityView
}

export interface TimeseriesPoint {
  bucketStart: string
  submittedItemCount: number
  completedItemCount: number
  failedItemCount: number
  avgDurationMs: number
}

export interface TaskMetricsTimeseriesResponse {
  windowSeconds: number
  bucketSeconds: number
  points: TimeseriesPoint[]
}

export const TIMESERIES_WINDOW_OPTIONS = [
  { label: '最近 1 分钟', value: 60 },
  { label: '最近 5 分钟', value: 300 },
  { label: '最近 10 分钟', value: 600 },
  { label: '最近 15 分钟', value: 900 },
  { label: '最近 30 分钟', value: 1800 },
  { label: '最近 1 小时', value: 3600 },
  { label: '最近 3 小时', value: 10800 },
  { label: '最近 6 小时', value: 21600 },
  { label: '最近 12 小时', value: 43200 },
  { label: '最近 24 小时', value: 86400 },
] as const

export type TimeseriesWindowSeconds = (typeof TIMESERIES_WINDOW_OPTIONS)[number]['value']

export interface TaskJobListQuery {
  status?: TaskJobStatus | null
  page?: number
  pageSize?: number
}

export interface TaskItemListQuery {
  status?: TaskItemStatus | null
  page?: number
  pageSize?: number
}

type BackendTaskStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'partial'
  | 'paused'

interface BackendTaskJobRead {
  id: number
  public_id: string
  task_type: string
  queue_name: string
  name: string
  status: BackendTaskStatus
  created_by: string
  total_items: number
  pending_items?: number
  queued_items?: number
  running_items?: number
  completed_items: number
  failed_items: number
  cancelled_items: number
  paused_items?: number
  payload: Record<string, unknown>
  result: Record<string, unknown>
  error_message: string
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

interface BackendTaskItemRead {
  id: number
  public_id: string
  item_type: string
  item_key: string | null
  status: BackendTaskStatus
  attempt_count: number
  max_attempts: number
  worker_id: string
  payload: Record<string, unknown>
  result: Record<string, unknown>
  error_message: string
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

interface BackendTaskJobDetail extends BackendTaskJobRead {
  items: BackendTaskItemRead[]
}

interface BackendTaskJobPage {
  data: BackendTaskJobRead[]
  total: number
  page: number
  limit: number
}

interface BackendTaskItemPage {
  data: BackendTaskItemRead[]
  total: number
  page: number
  limit: number
}

interface BackendTaskJobCancelResponse {
  canceled_count: number
}

interface BackendTaskJobPauseResponse {
  paused_count: number
}

interface BackendTaskJobResumeResponse {
  resumed_count: number
}

interface BackendTaskJobRetryResponse {
  new_item_public_ids: string[]
}

interface BackendTaskJobDeleteResponse {
  status: string
}

interface BackendQueueStatsView {
  pending_item_count: number
  running_item_count: number
  requeue_last5_min: number
}

interface BackendActivityWindowView {
  submitted_item_count: number
  completed_item_count: number
  failed_item_count: number
  avg_duration_ms: number
}

interface BackendRecentActivityView {
  last_minute: BackendActivityWindowView
  last_thirty_minutes: BackendActivityWindowView
  last_hour: BackendActivityWindowView
  last_six_hours: BackendActivityWindowView
}

interface BackendTaskMetricsResponse {
  queue_stats: BackendQueueStatsView
  recent_activity: BackendRecentActivityView
}

interface BackendTimeseriesPoint {
  bucket_start: string
  submitted_item_count: number
  completed_item_count: number
  failed_item_count: number
  avg_duration_ms: number
}

interface BackendTaskMetricsTimeseriesResponse {
  window_seconds: number
  bucket_seconds: number
  points: BackendTimeseriesPoint[]
}

const tasksBase = (projectPublicId: string) => (
  `/projects/${encodeURIComponent(projectPublicId.trim())}/tasks`
)

const normalizeJobStatus = (status: BackendTaskStatus | string): TaskJobStatus => {
  if (status === 'cancelled') return 'canceled'
  if (status === 'partial') return 'partial_failed'
  if (status === 'queued') return 'pending'
  if (
    status === 'pending' ||
    status === 'running' ||
    status === 'paused' ||
    status === 'succeeded' ||
    status === 'failed' ||
    status === 'canceled' ||
    status === 'partial_failed'
  ) {
    return status
  }
  return 'pending'
}

const normalizeItemStatus = (status: BackendTaskStatus | string): TaskItemStatus => {
  if (status === 'cancelled') return 'canceled'
  if (status === 'queued') return 'pending'
  if (
    status === 'pending' ||
    status === 'running' ||
    status === 'paused' ||
    status === 'succeeded' ||
    status === 'failed' ||
    status === 'canceled'
  ) {
    return status
  }
  return 'failed'
}

const itemSeq = (item: BackendTaskItemRead) => {
  const raw = item.payload?.chapter_index ?? item.id
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : item.id
}

const durationMs = (startedAt: string | null, finishedAt: string | null) => {
  if (!startedAt || !finishedAt) return null
  const started = new Date(startedAt).getTime()
  const finished = new Date(finishedAt).getTime()
  if (!Number.isFinite(started) || !Number.isFinite(finished) || finished < started) return null
  return finished - started
}

const isRecord = (value: unknown): value is Record<string, unknown> => (
  Boolean(value) && typeof value === 'object' && !Array.isArray(value)
)

const firstText = (...values: unknown[]) => {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) return String(value)
    if (typeof value !== 'string') continue
    const text = value.trim()
    if (text) return text
  }
  return ''
}

const formatMessagePrompt = (messages: unknown) => {
  if (!Array.isArray(messages)) return ''
  const parts = messages
    .map((message, index) => {
      if (typeof message === 'string') return message.trim()
      if (!isRecord(message)) return ''
      const role = firstText(message.role) || `message_${index + 1}`
      const content = firstText(message.content, message.text)
      return content ? `${role}：\n${content}` : ''
    })
    .filter(Boolean)
  return parts.join('\n\n')
}

const taskItemPrompt = (item: BackendTaskItemRead) => {
  const payload = item.payload ?? {}
  const result = item.result ?? {}
  const explicitPrompt = firstText(
    result.composed_prompt,
    result.composedPrompt,
    result.prompt,
    result.input_prompt,
    result.inputPrompt,
    payload.composed_prompt,
    payload.composedPrompt,
    payload.prompt,
    payload.input_prompt,
    payload.inputPrompt,
  )
  if (explicitPrompt) return explicitPrompt

  const systemPrompt = firstText(result.system_prompt, result.systemPrompt, payload.system_prompt, payload.systemPrompt)
  const userPrompt = firstText(result.user_prompt, result.userPrompt, payload.user_prompt, payload.userPrompt)
  if (systemPrompt || userPrompt) {
    return [
      systemPrompt ? `系统提示词：\n${systemPrompt}` : '',
      userPrompt ? `用户提示词：\n${userPrompt}` : '',
    ].filter(Boolean).join('\n\n')
  }

  const messagePrompt = formatMessagePrompt(result.messages) || formatMessagePrompt(payload.messages)
  if (messagePrompt) return messagePrompt

  return ''
}

const taskItemOutputText = (item: BackendTaskItemRead) => {
  const result = item.result ?? {}
  const text = firstText(result.output_text, result.outputText, result.text, result.raw_output, result.rawOutput)
  if (text) return text
  if (typeof result.event === 'string') return result.event
  if (result.event !== null && result.event !== undefined) {
    try {
      return JSON.stringify(result.event, null, 2)
    } catch {
      return String(result.event)
    }
  }
  return null
}

const toTaskItem = (item: BackendTaskItemRead, job?: BackendTaskJobRead): TaskItemResponse => {
  const status = normalizeItemStatus(item.status)
  const terminal = status === 'succeeded' || status === 'failed' || status === 'canceled'
  const prompt = taskItemPrompt(item)
  const modelId = firstText(
    item.result?.model_id,
    item.result?.modelId,
    item.payload?.model_id,
    item.payload?.modelId,
    job?.payload?.model_id,
    job?.payload?.modelId,
  )
  return {
    publicId: item.public_id,
    seq: itemSeq(item),
    status,
    inputPayload: item.payload,
    composedPrompt: prompt || null,
    finalPrompt: prompt || null,
    outputText: taskItemOutputText(item),
    errorMessage: item.error_message || null,
    retryOfPublicId: null,
    diagnostics: terminal
      ? {
          modelId,
          providerKey: job?.queue_name ?? '',
          workerConsumerName: item.worker_id || null,
          claimToCallMs: null,
          durationMs: durationMs(item.started_at, item.completed_at),
          attemptCount: item.attempt_count,
          composedPromptLength: prompt ? prompt.length : null,
          startedAt: item.started_at,
          finishedAt: item.completed_at,
        }
      : null,
    createdAt: item.created_at,
    updatedAt: item.updated_at,
    startedAt: item.started_at,
    finishedAt: item.completed_at,
  }
}

const countsFromItems = (items: BackendTaskItemRead[]) => {
  const counts = {
    pending: 0,
    running: 0,
    paused: 0,
    succeeded: 0,
    failed: 0,
    canceled: 0,
  }
  for (const item of items) {
    counts[normalizeItemStatus(item.status)] += 1
  }
  return counts
}

const countsFromJob = (job: BackendTaskJobRead, items?: BackendTaskItemRead[]) => {
  if (items) return countsFromItems(items)
  const total = job.total_items || 0
  const succeeded = job.completed_items || 0
  const failed = job.failed_items || 0
  const canceled = job.cancelled_items || 0
  if (
    typeof job.pending_items === 'number' ||
    typeof job.queued_items === 'number' ||
    typeof job.running_items === 'number' ||
    typeof job.paused_items === 'number'
  ) {
    return {
      pending: (job.pending_items || 0) + (job.queued_items || 0),
      running: job.running_items || 0,
      paused: job.paused_items || 0,
      succeeded,
      failed,
      canceled,
    }
  }
  const remaining = Math.max(0, total - succeeded - failed - canceled)
  const status = normalizeJobStatus(job.status)
  return {
    pending: status === 'pending' ? remaining : 0,
    running: status === 'running' ? remaining : 0,
    paused: status === 'paused' ? remaining : 0,
    succeeded,
    failed,
    canceled,
  }
}

const toTaskJob = (
  job: BackendTaskJobRead,
  projectPublicId: string,
  items?: BackendTaskItemRead[],
): TaskJobResponse => {
  const counts = countsFromJob(job, items)
  return {
    publicId: job.public_id,
    projectPublicId: String(job.payload?.project_public_id || projectPublicId),
    creatorPublicId: job.created_by,
    taskType: job.task_type,
    name: job.name || job.task_type,
    status: normalizeJobStatus(job.status),
    totalCount: items?.length ?? job.total_items,
    pendingCount: counts.pending,
    runningCount: counts.running,
    succeededCount: counts.succeeded,
    failedCount: counts.failed,
    canceledCount: counts.canceled,
    pausedCount: counts.paused,
    modelId: String(job.payload?.model_id || ''),
    providerKey: job.queue_name,
    defaultParams: job.payload,
    createdAt: job.created_at,
    updatedAt: job.updated_at,
    startedAt: job.started_at,
    finishedAt: job.completed_at,
  }
}

const toJobList = (
  page: BackendTaskJobPage,
  projectPublicId: string,
): TaskJobListResponse => ({
  items: page.data.map((job) => toTaskJob(job, projectPublicId)),
  total: page.total,
  page: page.page,
  pageSize: page.limit,
})

const toItemList = (
  page: BackendTaskItemPage,
  job?: BackendTaskJobRead,
): TaskItemListResponse => ({
  items: page.data.map((item) => toTaskItem(item, job)),
  total: page.total,
  page: page.page,
  pageSize: page.limit,
})

const toBackendItemStatus = (statusValue: TaskItemStatus | null | undefined) => {
  if (statusValue === 'canceled') return 'cancelled'
  return statusValue || undefined
}

const toBackendJobStatus = (statusValue: TaskJobStatus | null | undefined) => {
  if (statusValue === 'canceled') return 'cancelled'
  if (statusValue === 'partial_failed') return 'partial'
  return statusValue || undefined
}

const toBackendItemIdsPayload = (itemPublicIds?: string[] | null) => ({
  item_public_ids: itemPublicIds?.filter(Boolean) ?? null,
})

const toActivityWindow = (value: BackendActivityWindowView): ActivityWindowView => ({
  submittedItemCount: value.submitted_item_count,
  completedItemCount: value.completed_item_count,
  failedItemCount: value.failed_item_count,
  avgDurationMs: value.avg_duration_ms,
})

const toTaskMetrics = (value: BackendTaskMetricsResponse): TaskMetricsResponse => ({
  queueStats: {
    pendingItemCount: value.queue_stats.pending_item_count,
    runningItemCount: value.queue_stats.running_item_count,
    requeueLast5Min: value.queue_stats.requeue_last5_min,
  },
  recentActivity: {
    lastMinute: toActivityWindow(value.recent_activity.last_minute),
    lastThirtyMinutes: toActivityWindow(value.recent_activity.last_thirty_minutes),
    lastHour: toActivityWindow(value.recent_activity.last_hour),
    lastSixHours: toActivityWindow(value.recent_activity.last_six_hours),
  },
})

const toTaskTimeseries = (
  value: BackendTaskMetricsTimeseriesResponse,
): TaskMetricsTimeseriesResponse => ({
  windowSeconds: value.window_seconds,
  bucketSeconds: value.bucket_seconds,
  points: value.points.map((point) => ({
    bucketStart: point.bucket_start,
    submittedItemCount: point.submitted_item_count,
    completedItemCount: point.completed_item_count,
    failedItemCount: point.failed_item_count,
    avgDurationMs: point.avg_duration_ms,
  })),
})

export const listTaskJobsApi = (
  projectPublicId: string,
  query: TaskJobListQuery = {},
) => (
  request
    .get<BackendTaskJobPage>(`${tasksBase(projectPublicId)}/`, {
      params: {
        status: toBackendJobStatus(query.status),
        page: query.page,
        page_size: query.pageSize,
      },
    })
    .then((raw) => ({ data: toJobList(raw, projectPublicId) }))
)

export const getTaskJobApi = (
  projectPublicId: string,
  jobPublicId: string,
) => (
  request
    .get<BackendTaskJobDetail>(`${tasksBase(projectPublicId)}/${encodeURIComponent(jobPublicId)}`)
    .then((raw) => ({ data: toTaskJob(raw, projectPublicId, raw.items) }))
)

export const listTaskItemsApi = (
  projectPublicId: string,
  jobPublicId: string,
  query: TaskItemListQuery = {},
) => (
  request
    .get<BackendTaskItemPage>(
      `${tasksBase(projectPublicId)}/${encodeURIComponent(jobPublicId)}/items`,
      {
        params: {
          status: toBackendItemStatus(query.status),
          page: query.page,
          page_size: query.pageSize,
        },
      },
    )
    .then((raw) => ({ data: toItemList(raw) }))
)

export const getTaskItemApi = (
  projectPublicId: string,
  jobPublicId: string,
  itemPublicId: string,
) => (
  request
    .get<BackendTaskItemRead>(
      `${tasksBase(projectPublicId)}/${encodeURIComponent(jobPublicId)}/items/${encodeURIComponent(itemPublicId)}`,
    )
    .then((raw) => ({ data: toTaskItem(raw) }))
)

export const createTaskJobApi = (
  projectPublicId: string,
  payload: TaskJobCreateRequest,
) => (
  request
    .post<BackendTaskJobDetail>(`${tasksBase(projectPublicId)}/`, {
      task_type: payload.taskType,
      queue_name: payload.queueName,
      name: payload.name,
      payload: {
        project_public_id: projectPublicId,
        ...(payload.defaultParams ?? {}),
        ...(payload.modelOverrides?.textModel ? { model_id: payload.modelOverrides.textModel } : {}),
      },
      items: payload.items.map((item, index) => ({
        item_key: `item:${index + 1}`,
        payload: item.inputPayload ?? {},
      })),
    })
    .then((raw) => ({ data: toTaskJob(raw, projectPublicId, raw.items) }))
)

export const cancelTaskJobApi = (
  projectPublicId: string,
  jobPublicId: string,
  payload: TaskJobCancelRequest = {},
) => (
  request
    .post<BackendTaskJobCancelResponse>(
      `${tasksBase(projectPublicId)}/${encodeURIComponent(jobPublicId)}/cancel`,
      toBackendItemIdsPayload(payload.itemPublicIds),
    )
    .then((raw) => ({ data: { canceledCount: raw.canceled_count } }))
)

export const retryTaskJobApi = (
  projectPublicId: string,
  jobPublicId: string,
  payload: TaskJobRetryRequest,
) => (
  request
    .post<BackendTaskJobRetryResponse>(
      `${tasksBase(projectPublicId)}/${encodeURIComponent(jobPublicId)}/retry`,
      { item_public_ids: payload.itemPublicIds.filter(Boolean) },
    )
    .then((raw) => ({ data: { newItemPublicIds: raw.new_item_public_ids } }))
)

export const pauseTaskJobApi = (
  projectPublicId: string,
  jobPublicId: string,
  payload: TaskJobPauseRequest = {},
) => (
  request
    .post<BackendTaskJobPauseResponse>(
      `${tasksBase(projectPublicId)}/${encodeURIComponent(jobPublicId)}/pause`,
      toBackendItemIdsPayload(payload.itemPublicIds),
    )
    .then((raw) => ({ data: { pausedCount: raw.paused_count } }))
)

export const resumeTaskJobApi = (
  projectPublicId: string,
  jobPublicId: string,
  payload: TaskJobResumeRequest = {},
) => (
  request
    .post<BackendTaskJobResumeResponse>(
      `${tasksBase(projectPublicId)}/${encodeURIComponent(jobPublicId)}/resume`,
      toBackendItemIdsPayload(payload.itemPublicIds),
    )
    .then((raw) => ({ data: { resumedCount: raw.resumed_count } }))
)

export const deleteTaskJobApi = (
  projectPublicId: string,
  jobPublicId: string,
) => (
  request
    .delete<BackendTaskJobDeleteResponse>(`${tasksBase(projectPublicId)}/${encodeURIComponent(jobPublicId)}`)
    .then((raw) => ({ data: { status: raw?.status ?? 'deleted' } }))
)

export const getTaskMetricsApi = (projectPublicId: string) => (
  request
    .get<BackendTaskMetricsResponse>(`${tasksBase(projectPublicId)}/metrics`)
    .then((raw) => ({ data: toTaskMetrics(raw) }))
)

export const getTaskMetricsTimeseriesApi = (
  projectPublicId: string,
  windowSeconds: TimeseriesWindowSeconds,
) => (
  request
    .get<BackendTaskMetricsTimeseriesResponse>(`${tasksBase(projectPublicId)}/metrics/timeseries`, {
      params: { window: windowSeconds },
    })
    .then((raw) => ({ data: toTaskTimeseries(raw) }))
)
