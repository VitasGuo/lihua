/**
 * HistorySheet - 历史对话查看（v0.8.20）
 *
 * 只读查看按 session_id 聚合的历史会话：
 *   - 左侧：会话列表（first_user_input + episode_count + 相对时间）
 *   - 右侧：选中会话的 episode 列表（user_input + reasoning + agent_response + tool_calls 简要）
 *
 * 数据来源：
 *   - GET /api/memory/sessions         会话列表
 *   - GET /api/memory/sessions/{id}    某会话的所有 episode
 *
 * 设计要点：
 *   - 只读：无任何编辑操作（避免误改记忆）
 *   - 复用 ModelSheet/AuditSheet 的 closing 动画模式（T045）
 *   - Esc 键 / 点击遮罩 / 关闭按钮三种关闭路径都走退出动画
 *   - 思考链（reasoning）默认折叠，点击展开（避免占空间过多）
 */

import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  Brain,
  CheckCircle2,
  ChevronDown,
  Clock,
  Loader2,
  MessageSquare,
  RefreshCw,
  X,
  XCircle,
} from 'lucide-react'
import type { SessionSummary, EpisodeData } from '../api'
import { api } from '../api'
import { IconButton } from './IconButton'

interface HistorySheetProps {
  open: boolean
  onClose: () => void
}

const EXIT_ANIM_MS = 150

export function HistorySheet({ open, onClose }: HistorySheetProps) {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [selectedId, setSelectedId] = useState<string>('')
  const [episodes, setEpisodes] = useState<EpisodeData[]>([])
  const [loadingSessions, setLoadingSessions] = useState(false)
  const [loadingEpisodes, setLoadingEpisodes] = useState(false)
  const [expandedReasoning, setExpandedReasoning] = useState<Set<string>>(new Set())
  const [closing, setClosing] = useState(false)
  const prevOpenRef = useRef(false)
  const shouldRender = open || closing

  // 退出动画
  useEffect(() => {
    const prevOpen = prevOpenRef.current
    prevOpenRef.current = open
    if (open) {
      setClosing(false)
    } else if (prevOpen) {
      setClosing(true)
      const t = setTimeout(() => setClosing(false), EXIT_ANIM_MS)
      return () => clearTimeout(t)
    }
  }, [open])

  // 拉取会话列表
  const fetchSessions = async () => {
    setLoadingSessions(true)
    try {
      const res = await api.memorySessions(50)
      if (res.ok) {
        const list = res.sessions || []
        setSessions(list)
        // 默认选中第一条（用 functional update 避免 stale closure）
        if (list.length > 0) {
          setSelectedId(prev => prev || list[0].session_id)
        }
      }
    } catch {
      // 静默
    } finally {
      setLoadingSessions(false)
    }
  }

  // open 变 true 时拉取会话列表
  useEffect(() => {
    if (open) {
      fetchSessions()
    }
  }, [open])

  // 选中会话变化时拉取 episode 列表
  useEffect(() => {
    if (!open || !selectedId) return
    setLoadingEpisodes(true)
    setEpisodes([])
    api.memorySessionDetail(selectedId)
      .then(res => {
        if (res.ok) setEpisodes(res.episodes || [])
      })
      .catch(() => {})
      .finally(() => setLoadingEpisodes(false))
  }, [open, selectedId])

  // Esc 关闭
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!shouldRender) return null

  const toggleReasoning = (epId: string) => {
    setExpandedReasoning(prev => {
      const next = new Set(prev)
      if (next.has(epId)) next.delete(epId)
      else next.add(epId)
      return next
    })
  }

  return createPortal(
    <div
      className={[
        'fixed inset-0 z-40 flex flex-col',
        'bg-black/40 backdrop-blur-sm',
        closing ? 'animate-fade-out' : 'animate-fade-in',
      ].join(' ')}
      style={{ animationDuration: `${EXIT_ANIM_MS}ms` }}
      onClick={e => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        className={[
          'mx-auto my-auto w-full max-w-[860px] h-[80vh]',
          'bg-bg-secondary border border-border-default rounded-2xl shadow-popover',
          'flex flex-col overflow-hidden',
          closing ? 'animate-fade-out' : 'animate-slide-up',
        ].join(' ')}
        style={{ animationDuration: `${EXIT_ANIM_MS}ms` }}
        onClick={e => e.stopPropagation()}
      >
        {/* 顶部栏 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-soft">
          <div className="flex items-center gap-2 text-text-primary">
            <MessageSquare size={16} className="text-accent" />
            <span className="text-sm font-medium cjk-spacing">历史对话</span>
            <span className="text-xs text-text-tertiary">·</span>
            <span className="text-xs text-text-tertiary">{sessions.length} 个会话</span>
          </div>
          <div className="flex items-center gap-1">
            <IconButton onClick={fetchSessions} title="刷新">
              <RefreshCw size={14} className={loadingSessions ? 'animate-spin' : ''} />
            </IconButton>
            <IconButton onClick={onClose} title="关闭">
              <X size={14} />
            </IconButton>
          </div>
        </div>

        {/* 左右分栏 */}
        <div className="flex-1 flex overflow-hidden">
          {/* 左侧：会话列表 */}
          <div className="w-64 border-r border-border-soft flex flex-col overflow-hidden">
            <div className="px-3 py-2 text-[10px] text-text-tertiary uppercase tracking-wider border-b border-border-soft cjk-spacing">
              会话
            </div>
            <div className="flex-1 overflow-y-auto">
              {loadingSessions ? (
                <div className="flex items-center justify-center h-full text-text-tertiary">
                  <Loader2 size={16} className="animate-spin" />
                </div>
              ) : sessions.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-text-tertiary text-xs gap-2 cjk-spacing">
                  <MessageSquare size={24} className="text-text-tertiary/40" />
                  <span>暂无历史会话</span>
                </div>
              ) : (
                <div className="py-1">
                  {sessions.map(s => (
                    <button
                      key={s.session_id}
                      onClick={() => setSelectedId(s.session_id)}
                      className={[
                        'w-full text-left px-3 py-2 transition-all duration-fast ease-out-soft',
                        selectedId === s.session_id
                          ? 'bg-accent-soft/60 border-l-2 border-accent'
                          : 'border-l-2 border-transparent hover:bg-bg-tertiary/40',
                      ].join(' ')}
                    >
                      <div className="text-xs text-text-primary truncate cjk-spacing">
                        {s.first_user_input || '(空消息)'}
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-[10px] text-text-tertiary">
                          {s.episode_count} 轮
                        </span>
                        <span className="text-[10px] text-text-tertiary flex items-center gap-0.5">
                          <Clock size={9} strokeWidth={1.5} />
                          {formatRelTime(s.last_ts)}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* 右侧：episode 列表 */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {loadingEpisodes ? (
              <div className="flex items-center justify-center h-full text-text-tertiary">
                <Loader2 size={16} className="animate-spin" />
              </div>
            ) : episodes.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-text-tertiary text-xs gap-2 cjk-spacing">
                <MessageSquare size={24} className="text-text-tertiary/40" />
                <span>{selectedId ? '该会话无记录' : '选择左侧会话查看详情'}</span>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto p-3 space-y-3">
                {episodes.map(ep => {
                  const expanded = expandedReasoning.has(ep.id)
                  return (
                    <div
                      key={ep.id}
                      className="rounded-md border border-border-soft bg-bg-tertiary/30 overflow-hidden"
                    >
                      {/* 用户输入 */}
                      <div className="px-3 py-2 border-b border-border-soft/60">
                        <div className="text-[10px] text-text-tertiary mb-0.5 cjk-spacing">用户</div>
                        <div className="text-sm text-text-primary cjk-spacing whitespace-pre-wrap">
                          {ep.user_input}
                        </div>
                      </div>

                      {/* 思考链（如果有，折叠展示） */}
                      {ep.reasoning && (
                        <div className="px-3 py-2 border-b border-border-soft/60">
                          <button
                            onClick={() => toggleReasoning(ep.id)}
                            className="flex items-center gap-1.5 text-[11px] text-text-tertiary hover:text-text-secondary transition-colors"
                          >
                            <Brain size={11} strokeWidth={1.8} />
                            <span className="cjk-spacing">思考链</span>
                            <ChevronDown
                              size={11}
                              className={`transition-transform ${expanded ? 'rotate-180' : ''}`}
                            />
                          </button>
                          {expanded && (
                            <div className="mt-1.5 text-xs text-text-secondary italic leading-relaxed whitespace-pre-wrap cjk-spacing pl-4 border-l border-border-soft">
                              {ep.reasoning}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Agent 回复 */}
                      {ep.agent_response && (
                        <div className="px-3 py-2 border-b border-border-soft/60">
                          <div className="text-[10px] text-text-tertiary mb-0.5 cjk-spacing">狸花</div>
                          <div className="text-sm text-text-secondary cjk-spacing whitespace-pre-wrap">
                            {ep.agent_response}
                          </div>
                        </div>
                      )}

                      {/* 工具调用简要 */}
                      {ep.tool_calls && ep.tool_calls.length > 0 && (
                        <div className="px-3 py-2 flex items-center gap-2 text-[10px] text-text-tertiary">
                          <span className="cjk-spacing">
                            工具调用 {ep.tool_calls.length} 次
                          </span>
                          <span className="flex items-center gap-1">
                            {ep.tool_calls.every(t => t.success) ? (
                              <CheckCircle2 size={10} className="text-accent" strokeWidth={2} />
                            ) : (
                              <XCircle size={10} className="text-danger" strokeWidth={2} />
                            )}
                            <span className={ep.tool_calls.every(t => t.success) ? 'text-accent' : 'text-danger'}>
                              {ep.tool_calls.filter(t => t.success).length}/{ep.tool_calls.length} 成功
                            </span>
                          </span>
                          <span className="ml-auto flex items-center gap-0.5">
                            <Clock size={9} strokeWidth={1.5} />
                            {ep.duration.toFixed(2)}s
                          </span>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  )
}

/** 格式化相对时间（时间戳 → "刚刚 / N分钟前 / N小时前 / 月日"） */
function formatRelTime(ts: number): string {
  try {
    const diff = Date.now() - ts * 1000
    const min = Math.floor(diff / 60000)
    if (min < 1) return '刚刚'
    if (min < 60) return `${min}分钟前`
    const hour = Math.floor(min / 60)
    if (hour < 24) return `${hour}小时前`
    const day = Math.floor(hour / 24)
    if (day < 7) return `${day}天前`
    const d = new Date(ts * 1000)
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  } catch {
    return ''
  }
}
