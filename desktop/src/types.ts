// 类型定义
//
// 后端 API 类型统一从 api.ts 导出，避免双源不一致。
// 这里只保留前端独有的 UI 状态类型。

export type {
  Health,
  SkillParam,
  Skill,
  Step,
  ChatResult,
  Intent,
  ToolCall,
  ChatResponse,
  HistoryEntry,
} from './api'

// 前端 UI 状态用到的消息类型
export interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  loading?: boolean
  // Agent 模式字段
  text?: string
  tool_calls?: import('./api').ToolCall[]
  // 规则模式字段（兼容）
  intent?: import('./api').Intent
  result?: import('./api').ChatResult
  // 标记
  isAgent?: boolean
  error?: string
  // 流式状态（v0.7.9）
  streaming?: boolean
  iteration?: number
  // 当前正在执行的工具名（用于 UI 显示 "正在执行 X..."）
  currentTool?: string
  // v0.8.20: LLM 思考链（reasoning_content），MessageBubble 默认展开渲染
  reasoning?: string
}

// 待确认的请求
export interface ConfirmPending {
  // 规则模式（旧）：用 message 重新发送带 auto_confirm=true
  message?: string
  response?: import('./api').ChatResponse
  // Agent 模式（v0.7.13）：用 confirm_id 调 /api/chat/confirm
  confirmId?: string
  confirmMessage?: string  // 展示给用户的确认文案（纯文本，兼容旧路径）
  // v0.8.4：结构化字段，让 ConfirmSheet 能分别展示意图和代码/命令
  toolName?: string  // 'run_python' | 'run_shell' | 'file_op' | undefined
  intent?: string    // LLM 给的中文意图说明
  code?: string      // run_python 的代码内容
  commandText?: string  // run_shell 的命令内容
}
