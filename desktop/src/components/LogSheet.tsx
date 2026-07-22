/**
 * LogSheet - 日志查看面板（v0.7.8）
 *
 * 复用 v0.7.7 日志系统 API：
 *   - GET /api/logs?n=100&level=INFO  查询最近 N 条
 *   - GET /api/logs/stream            SSE 实时推送
 *   - POST /api/logs/level            运行时调整级别
 *
 * 功能：
 *   1. 实时日志流（EventSource 监听 /api/logs/stream）
 *   2. 级别筛选（全部 / DEBUG / INFO / WARNING / ERROR / CRITICAL）
 *   3. 搜索（按消息内容或 logger 名过滤）
 *   4. 暂停 / 继续实时流
 *   5. 运行时级别调整（DEBUG / INFO / WARNING / ERROR）
 *   6. 清空当前视图
 *
 * 布局：
 *   ┌─ 顶部栏：标题 + 暂停/继续 + 关闭 ──────────┐
 *   ├─ 工具栏：级别筛选 + 搜索框 + 条数 ─────────┤
 *   ├─ 日志列表（flex-1，自动滚动到最新）────────┤
 *   └─ 底部栏：运行时级别 dropdown + 清空 + 路径 ┘
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { createPortal } from 'react-dom'
import {
  Check,
  ChevronDown,
  Pause,
  Play,
  Search,
  Terminal,
  Trash2,
  X,
} from 'lucide-react'
import type { LogEntry } from '../api'
import { api } from '../api'
import { IconButton } from './IconButton'

interface LogSheetProps {
  open: boolean
  onClose: () => void
}

type LevelFilter = 'ALL' | 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'

const LEVEL_FILTERS: LevelFilter[] = ['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'text-cyan-400 bg-cyan-400/10',
  INFO: 'text-green-400 bg-green-400/10',
  WARNING: 'text-yellow-400 bg-yellow-400/10',
  ERROR: 'text-red-400 bg-red-400/10',
  CRITICAL: 'text-purple-400 bg-purple-400/10',
}

const RUNTIME_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR'] as const
const EXIT_ANIM_MS = 150
const MAX_ENTRIES = 500 // 前端最多保留 500 条，防止内存爆炸

export function LogSheet({ open, onClose }: LogSheetProps) {
  const [entries, setEntries] = useState<LogEntry[]>([])
  const [levelFilter, setLevelFilter] = useState<LevelFilter>('ALL')
  const [search, setSearch] = useState('')
  const [paused, setPaused] = useState(false)
  const [runtimeLevel, setRuntimeLevel] = useState<string>('INFO')
  const [logFilePath, setLogFilePath] = useState('')
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [dropdownPos, setDropdownPos] = useState<{ top: number; left: number; width: number } | null>(null)
  const [closing, setClosing] = useState(false)

  const dropdownRef = useRef<HTMLDivElement>(null)
  const dropdownListRef = useRef<HTMLDivElement>(null)
  const listEndRef = useRef<HTMLDivElement>(null)
  const prevOpenRef = useRef(false)
  const eventSourceRef = useRef<EventSource | null>(null)
  // paused 用 ref，避免 toggle 时重建 EventSource 连接
  const pausedRef = useRef(false)
  useEffect(() => {
    pausedRef.current = paused
  }, [paused])

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

  // 打开时：拉取历史日志 + 启动 SSE + 查询当前级别
  useEffect(() => {
    if (!open) return

    api.logs(100).then(res => {
      setEntries(res.entries)
      setLogFilePath(res.log_file)
    }).catch(() => {})

    // 查询当前运行时级别（从 health 推断不了，直接读 config）
    // 这里用一个简单的方式：默认 INFO，用户调整后更新
    setRuntimeLevel('INFO')

    // 启动 SSE
    const es = new EventSource(api.logStreamUrl())
    eventSourceRef.current = es
    es.onmessage = ev => {
      if (pausedRef.current) return
      try {
        const entry: LogEntry = JSON.parse(ev.data)
        setEntries(prev => {
          const next = [...prev, entry]
          if (next.length > MAX_ENTRIES) {
            return next.slice(next.length - MAX_ENTRIES)
          }
          return next
        })
      } catch {
        // 忽略解析错误
      }
    }
    es.onerror = () => {
      // EventSource 会自动重连，不需要手动处理
    }

    return () => {
      es.close()
      eventSourceRef.current = null
    }
  }, [open])

  // 自动滚动到最新
  useEffect(() => {
    if (!paused && listEndRef.current) {
      listEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [entries, paused])

  // 点击外部关闭下拉
  useEffect(() => {
    if (!dropdownOpen) return
    const onClick = (e: MouseEvent) => {
      const target = e.target as Node
      if (dropdownRef.current?.contains(target)) return
      if (dropdownListRef.current?.contains(target)) return
      setDropdownOpen(false)
    }
    const onScroll = () => setDropdownOpen(false)
    document.addEventListener('mousedown', onClick)
    window.addEventListener('scroll', onScroll, true)
    return () => {
      document.removeEventListener('mousedown', onClick)
      window.removeEventListener('scroll', onScroll, true)
    }
  }, [dropdownOpen])

  const handleToggleDropdown = () => {
    if (dropdownOpen) {
      setDropdownOpen(false)
      return
    }
    if (dropdownRef.current) {
      const rect = dropdownRef.current.getBoundingClientRect()
      setDropdownPos({ top: rect.bottom + 4, left: rect.left, width: rect.width })
      setDropdownOpen(true)
    }
  }

  const handleSetRuntimeLevel = async (level: string) => {
    setDropdownOpen(false)
    try {
      await api.setLogLevel(level as 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR')
      setRuntimeLevel(level)
    } catch {
      // 忽略错误
    }
  }

  const handleClear = () => {
    setEntries([])
  }

  // 过滤日志
  const filtered = entries.filter(e => {
    if (levelFilter !== 'ALL' && e.level !== levelFilter) return false
    if (search) {
      const q = search.toLowerCase()
      if (!e.msg.toLowerCase().includes(q) && !e.logger.toLowerCase().includes(q)) {
        return false
      }
    }
    return true
  })

  if (!shouldRender) return null

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
          'mx-auto my-auto w-full max-w-[680px] h-[80vh]',
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
            <Terminal size={16} className="text-accent" />
            <span className="text-sm font-medium cjk-spacing">日志查看</span>
            <span className="text-xs text-text-tertiary">·</span>
            <span className="text-xs text-text-tertiary">{filtered.length} 条</span>
          </div>
          <div className="flex items-center gap-1">
            <IconButton
              onClick={() => setPaused(p => !p)}
              title={paused ? '继续实时流' : '暂停实时流'}
            >
              {paused ? <Play size={14} /> : <Pause size={14} />}
            </IconButton>
            <IconButton onClick={onClose} title="关闭">
              <X size={14} />
            </IconButton>
          </div>
        </div>

        {/* 工具栏：级别筛选 + 搜索 */}
        <div className="flex items-center gap-2 px-4 py-2 border-b border-border-soft">
          <div className="flex items-center gap-0.5 bg-bg-tertiary/40 rounded-md p-0.5">
            {LEVEL_FILTERS.map(lv => (
              <button
                key={lv}
                onClick={() => setLevelFilter(lv)}
                className={[
                  'px-2 py-1 rounded text-[10px] font-medium transition-all',
                  levelFilter === lv
                    ? 'bg-bg-secondary text-text-primary shadow-sm'
                    : 'text-text-tertiary hover:text-text-secondary',
                ].join(' ')}
              >
                {lv === 'ALL' ? '全部' : lv}
              </button>
            ))}
          </div>
          <div className="flex-1 flex items-center gap-1.5 px-2 py-1 bg-bg-tertiary/40 rounded-md">
            <Search size={12} className="text-text-tertiary" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="搜索消息或 logger..."
              className="flex-1 bg-transparent text-xs text-text-primary placeholder:text-text-tertiary outline-none"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="text-text-tertiary hover:text-text-secondary"
              >
                <X size={12} />
              </button>
            )}
          </div>
        </div>

        {/* 日志列表 */}
        <div className="flex-1 overflow-y-auto font-mono text-[11px] leading-relaxed">
          {filtered.length === 0 ? (
            <div className="flex items-center justify-center h-full text-text-tertiary text-xs cjk-spacing">
              暂无日志
            </div>
          ) : (
            <div className="py-1">
              {filtered.map((e, i) => (
                <div
                  key={`${e.ts}-${i}`}
                  className="flex items-start gap-2 px-3 py-1 hover:bg-bg-tertiary/30 transition-colors"
                >
                  <span className="text-text-tertiary shrink-0 tabular-nums">
                    {e.ts.slice(11)}
                  </span>
                  <span
                    className={[
                      'shrink-0 px-1 rounded text-[9px] font-bold tracking-wide',
                      LEVEL_COLORS[e.level] || 'text-text-tertiary bg-bg-tertiary',
                    ].join(' ')}
                  >
                    {e.level}
                  </span>
                  <span className="text-text-secondary shrink-0 max-w-[120px] truncate">
                    [{e.logger.replace('lihua.', '')}]
                  </span>
                  <span className="text-text-primary break-all">
                    {e.msg}
                  </span>
                </div>
              ))}
              <div ref={listEndRef} />
            </div>
          )}
        </div>

        {/* 底部栏：运行时级别 + 清空 + 路径 */}
        <div className="flex items-center justify-between px-4 py-2 border-t border-border-soft text-xs">
          <div className="flex items-center gap-2">
            <span className="text-text-tertiary cjk-spacing">运行时级别</span>
            <div ref={dropdownRef} className="relative">
              <button
                onClick={handleToggleDropdown}
                className="flex items-center gap-1 px-2 py-1 rounded bg-bg-tertiary/50 hover:bg-bg-tertiary text-text-secondary transition-colors"
              >
                <span className="font-mono">{runtimeLevel}</span>
                <ChevronDown
                  size={10}
                  className={`transition-transform ${dropdownOpen ? 'rotate-180' : ''}`}
                />
              </button>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleClear}
              className="flex items-center gap-1 px-2 py-1 rounded text-text-tertiary hover:text-text-secondary hover:bg-bg-tertiary/40 transition-all"
              title="清空当前视图（不影响后端缓冲区）"
            >
              <Trash2 size={11} />
              <span className="cjk-spacing">清空</span>
            </button>
            {logFilePath && (
              <span className="text-text-tertiary/60 font-mono text-[10px] truncate max-w-[200px]" title={logFilePath}>
                {logFilePath}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* 运行时级别下拉（Portal 到 body，避免 overflow 裁剪） */}
      {dropdownOpen && dropdownPos && createPortal(
        <div
          ref={dropdownListRef}
          className="bg-bg-secondary border border-border-default rounded-md shadow-popover overflow-hidden animate-fade-in"
          style={{
            position: 'fixed',
            top: dropdownPos.top,
            left: dropdownPos.left,
            width: dropdownPos.width,
            zIndex: 9999,
            animationDuration: '100ms',
          }}
        >
          <div className="py-1">
            {RUNTIME_LEVELS.map(lv => (
              <button
                key={lv}
                onClick={() => handleSetRuntimeLevel(lv)}
                className={[
                  'w-full flex items-center justify-between px-3 py-1.5 text-xs transition-colors',
                  runtimeLevel === lv
                    ? 'bg-accent-soft text-accent'
                    : 'text-text-secondary hover:bg-bg-tertiary/50',
                ].join(' ')}
              >
                <span className="font-mono">{lv}</span>
                {runtimeLevel === lv && <Check size={12} />}
              </button>
            ))}
          </div>
        </div>,
        document.body,
      )}
    </div>,
    document.body,
  )
}
