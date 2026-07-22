// API 封装：调用 Lihua Python 后端
//
// v0.7：支持 Agent 模式返回（text + tool_calls）和规则模式返回（intent + result）双轨

const BACKEND_URL = 'http://127.0.0.1:7531'

export interface Health {
  ok: boolean
  version: string
  llm_available: boolean
  llm_provider: string | null
  llm_model: string | null
  skills_count: number
  tools: Record<string, boolean>
}

export interface SkillParam {
  name: string
  required?: boolean
  description?: string
  type?: string
  default?: string
}

export interface Skill {
  name: string
  description: string
  version?: string
  triggers: string[]
  examples: string[]
  parameters: SkillParam[]
  source?: string
}

// === 规则模式（旧）===

export interface Step {
  name: string
  type: string
  skipped?: boolean
  success?: boolean
  output?: string
  error?: string
  duration?: number
  needs_confirm?: boolean
  confirm_message?: string
  confirm_decision?: string
}

export interface ChatResult {
  success: boolean
  final_message: string
  steps: Step[]
  ctx: Record<string, unknown>
  dry_run?: boolean
}

export interface Intent {
  skill_name: string | null
  params: Record<string, string>
  source: string
  confidence: number
  explanation: string
  matched: boolean
}

// === Agent 模式（v0.6+ 新增）===

export interface ToolCall {
  tool_name: string
  arguments: Record<string, unknown>
  success: boolean
  result_message: string
  error?: string
  details?: Record<string, unknown> | null
}

export interface ChatResponse {
  success: boolean
  // Agent 模式字段
  text?: string
  tool_calls?: ToolCall[]
  // 规则模式字段（兼容）
  intent?: Intent
  result?: ChatResult
  error?: string
}

export interface HistoryEntry {
  timestamp: string
  message: string
  skill: string
  success: boolean
}

// === 流式 Agent 事件（v0.7.9 新增）===

export interface ChatHistoryEntry {
  role: 'user' | 'assistant'
  content: string
}

export interface ToolCallRecord {
  name: string
  arguments: Record<string, unknown>
  success: boolean
  message: string
  details?: Record<string, unknown> | null
  error?: string
}

export type AgentStreamEvent =
  | { type: 'start'; tools_count: number }
  | { type: 'iteration'; n: number; max: number }
  | { type: 'text'; content: string }
  | { type: 'reasoning'; content: string }  // v0.8.20: LLM 思考链
  | { type: 'tool_call_start'; name: string; arguments: Record<string, unknown> }
  | { type: 'tool_call_end'; name: string; success: boolean; message: string; details?: Record<string, unknown> | null; error?: string }
  | { type: 'needs_confirm'; id: string; message: string; command: string; tool_name?: string; intent?: string; code?: string; command_text?: string }
  | { type: 'confirm_timeout'; id: string }  // v0.8.29: confirm 超时后关闭 ConfirmSheet
  | { type: 'done'; text: string; success: boolean; tool_calls: ToolCallRecord[]; error?: string }
  | { type: 'error'; message: string }

// === v0.8.20: 记忆系统类型（历史对话调取 + MemorySheet）===

export interface SessionSummary {
  session_id: string
  episode_count: number
  first_ts: number
  last_ts: number
  first_user_input: string
}

export interface EpisodeData {
  id: string
  timestamp: number
  user_input: string
  tool_calls: Array<{ name: string; arguments: Record<string, unknown>; success: boolean; error?: string }>
  success: boolean
  agent_response: string
  session_id: string
  duration: number
  reasoning?: string
  user_feedback?: string | null
}

export interface KnowledgePatternData {
  id: string
  keywords: string[]
  tool_chain: string[]
  success_count: number
  fail_count: number
  last_used: number
  created_at: number
  example_episode_id: string
}

export interface TrapData {
  id: number
  timestamp: number
  symptom: string
  root_cause: string
  solution: string
  status: string
  related_skills: string[]
  related_keywords: string[]
  occurrence_count: number
  fix_verified: boolean
  created_at: number
  updated_at: number
}

export interface MemoryStats {
  episodes_count?: number
  knowledge_patterns?: number
  total_interactions?: number
  success_rate?: number
  top_tools?: Array<{ name: string; count: number }>
  top_keywords?: Array<{ keyword: string; count: number }>
  [k: string]: unknown
}

// === 审计日志（v0.7.10 新增）===

export interface AuditEntry {
  ts: string
  timestamp?: number
  command: string
  safety_level: string
  success: boolean
  exit_code: number
  duration: number
  user_input?: string | null
  decision_reason?: string | null
  raw?: string  // 解析失败的原始行
}

export interface AuditResponse {
  entries: AuditEntry[]
  count: number
  log_file: string
}

// === LLM 配置（v0.7.1 新增）===

export interface ModelOption {
  id: string
  name: string
  tier: 'basic' | 'pro'
  is_free: boolean
  context_length: string
  description: string
}

export interface ModelPreset {
  id: string
  name: string
  provider: string
  api_base: string
  recommended_model: string
  models: ModelOption[]
  requires_api_key: boolean
  description: string
  homepage: string
  docs_note: string
}

export interface LLMConfig {
  enabled: boolean
  provider: string
  api_key_masked: string
  api_key_set: boolean
  api_base: string | null
  model: string
  temperature: number
  max_tokens: number
}

export interface LLMConfigUpdatePayload {
  enabled?: boolean
  provider?: string
  api_key?: string
  api_base?: string
  model?: string
  temperature?: number
  max_tokens?: number
}

// === 日志系统（v0.7.7 新增）===

export interface LogEntry {
  ts: string
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'
  level_no: number
  logger: string
  module: string
  line: number
  msg: string
  exc?: string
  extra?: Record<string, unknown>
}

export interface LogsResponse {
  entries: LogEntry[]
  count: number
  log_file: string
}

export interface LogLevelUpdate {
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BACKEND_URL}${path}`
  let lastError: Error | null = null
  // v0.8.23: 网络错误（连接拒绝）时自动重试 2 次，应对后端启动中 / 短暂中断
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const res = await fetch(url, {
        ...init,
        headers: {
          'Content-Type': 'application/json',
          ...(init?.headers || {}),
        },
      })
      if (!res.ok) {
        throw new Error(`API ${path} 失败：${res.status} ${res.statusText}`)
      }
      return res.json() as Promise<T>
    } catch (e) {
      lastError = e instanceof Error ? e : new Error(String(e))
      // 只有网络错误（TypeError: Failed to fetch）才重试，HTTP 错误码直接抛
      if (!(e instanceof TypeError) || attempt === 2) throw lastError
      await new Promise(r => setTimeout(r, 300 * (attempt + 1)))
    }
  }
  throw lastError!
}

export const api = {
  health: () => request<Health>('/api/health'),

  skills: () => request<Skill[]>('/api/skills'),

  skill: (name: string) => request<Skill>(`/api/skills/${name}`),

  parse: (message: string, no_llm = false) =>
    request<{ intent: Intent }>('/api/parse', {
      method: 'POST',
      body: JSON.stringify({ message, no_llm }),
    }),

  // Agent 模式（默认）
  // v0.8.20: 加 sessionId 参数，用于 episode 聚合 + 历史对话调取
  chat: (message: string, auto_confirm = false, dry_run = false, no_llm = false, history: ChatHistoryEntry[] = [], sessionId: string = '') =>
    request<ChatResponse>('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ message, auto_confirm, dry_run, no_llm, history, session_id: sessionId }),
    }),

  // 流式 Agent 模式：实时推送工具调用和结果（SSE）
  // 返回 async generator，逐个 yield AgentStreamEvent
  // v0.8.20: 加 sessionId 参数
  chatStream: async function* (
    message: string,
    history: ChatHistoryEntry[] = [],
    auto_confirm = false,
    dry_run = false,
    sessionId: string = '',
  ): AsyncGenerator<AgentStreamEvent> {
    // v0.8.23: fetch 连接拒绝时重试 2 次（后端启动中 / 短暂中断）
    let response: Response | null = null
    let lastError: Error | null = null
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        response = await fetch(`${BACKEND_URL}/api/chat/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message, history, auto_confirm, dry_run, session_id: sessionId }),
        })
        if (!response.ok || !response.body) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }
        break
      } catch (e) {
        lastError = e instanceof Error ? e : new Error(String(e))
        if (attempt < 2) {
          await new Promise(r => setTimeout(r, 500 * (attempt + 1)))
        }
      }
    }
    if (!response || !response.body) {
      throw lastError ?? new Error('chatStream 连接失败')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // 解析完整的 SSE 事件（以 \n\n 分隔）
      while (buffer.includes('\n\n')) {
        const idx = buffer.indexOf('\n\n')
        const eventStr = buffer.slice(0, idx).trim()
        buffer = buffer.slice(idx + 2)

        // 解析 "data: {...}" 格式
        if (eventStr.startsWith('data: ')) {
          const jsonStr = eventStr.slice(6)
          try {
            yield JSON.parse(jsonStr) as AgentStreamEvent
          } catch {
            // 跳过格式错误的事件
          }
        }
      }
    }
  },

  // 规则模式（兜底）
  chatRule: (message: string, auto_confirm = false, dry_run = false, no_llm = false) =>
    request<ChatResponse>('/api/chat/rule', {
      method: 'POST',
      body: JSON.stringify({ message, auto_confirm, dry_run, no_llm }),
    }),

  // v0.7.13 交互式 confirm：用户点击确认/取消后调用
  confirmChat: (confirm_id: string, decision: boolean) =>
    request<{ ok: boolean; error?: string }>('/api/chat/confirm', {
      method: 'POST',
      body: JSON.stringify({ confirm_id, decision }),
    }),

  history: (n = 20) =>
    request<{ entries: HistoryEntry[] }>(`/api/history?n=${n}`),

  // === v0.8.20: 记忆系统（历史对话调取 + MemorySheet）===

  // 列出所有会话（按 session_id 聚合，最近优先）
  memorySessions: (limit = 50) =>
    request<{ ok: boolean; sessions: SessionSummary[]; error?: string }>(`/api/memory/sessions?limit=${limit}`),

  // 获取某个会话的所有 episode（含 reasoning + tool_calls）
  memorySessionDetail: (sessionId: string) =>
    request<{ ok: boolean; session_id: string; episode_count: number; episodes: EpisodeData[]; error?: string }>(`/api/memory/sessions/${encodeURIComponent(sessionId)}`),

  // 获取所有知识库模式（用于 MemorySheet 知识库 tab）
  memoryKnowledge: () =>
    request<{ ok: boolean; patterns: KnowledgePatternData[]; count: number; error?: string }>('/api/memory/knowledge'),

  // 导出所有记忆数据（stats + preferences + traps，用于 MemorySheet 导出）
  memoryExport: () =>
    request<{ ok: boolean; stats: MemoryStats; preferences: Record<string, unknown>; traps: TrapData[]; exported_at: number; error?: string }>('/api/memory/export'),

  // 清空所有记忆（episodes + knowledge + preferences，保留 traps）— 用于 MemorySheet 初始化/重置
  memoryClear: () =>
    request<{ ok: boolean; message?: string; error?: string }>('/api/memory/clear', {
      method: 'DELETE',
    }),

  // === 审计日志（v0.7.10 结构化 + 过滤搜索）===

  audit: (
    n = 100,
    filters?: {
      success?: boolean
      safety?: 'white' | 'grey' | 'black' | 'unknown'
      q?: string
    },
  ) => {
    const params = new URLSearchParams({ n: String(n) })
    if (filters?.success !== undefined) params.set('success', String(filters.success))
    if (filters?.safety) params.set('safety', filters.safety)
    if (filters?.q) params.set('q', filters.q)
    return request<AuditResponse>(`/api/audit?${params.toString()}`)
  },

  auditExportUrl: () => `${BACKEND_URL}/api/audit/export`,

  auditClear: () =>
    request<{ ok: boolean; message?: string; error?: string }>('/api/audit', {
      method: 'DELETE',
    }),

  // === LLM 配置 ===

  listModelPresets: () =>
    request<{ presets: ModelPreset[] }>('/api/models/presets'),

  getLLMConfig: () =>
    request<LLMConfig>('/api/config/llm'),

  updateLLMConfig: (payload: LLMConfigUpdatePayload) =>
    request<{ ok: boolean; llm?: Partial<LLMConfig>; error?: string }>('/api/config/llm', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  applyPreset: (presetId: string, body?: { model_id?: string; api_base?: string }) =>
    request<{ ok: boolean; preset?: ModelPreset; llm?: Partial<LLMConfig>; error?: string }>(
      `/api/config/llm/preset/${presetId}`,
      { method: 'POST', body: JSON.stringify(body || {}) },
    ),

  // === 日志系统（v0.7.7）===

  logs: (n = 100, level?: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL') => {
    const params = new URLSearchParams({ n: String(n) })
    if (level) params.set('level', level)
    return request<LogsResponse>(`/api/logs?${params.toString()}`)
  },

  setLogLevel: (level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL') =>
    request<{ ok: boolean; level: string }>('/api/logs/level', {
      method: 'POST',
      body: JSON.stringify({ level }),
    }),

  logStreamUrl: () => `${BACKEND_URL}/api/logs/stream`,
}
