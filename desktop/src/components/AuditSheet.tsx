/**
 * AuditSheet - 审计日志面板（v0.7.10）
 *
 * 复用 v0.7.10 后端审计 API：
 *   - GET    /api/audit?n=100&success=true&safety=white&q=keyword  查询 + 过滤
 *   - GET    /api/audit/export                                      下载完整文件
 *   - DELETE /api/audit                                             备份后清空
 *
 * 功能：
 *   1. 结构化列表：时间 + ✓/✗ + safety 颜色标签 + 命令 + duration + exit_code
 *   2. 过滤：成功 / 失败 / 全部 + safety 级别（白/灰/黑/未知）
 *   3. 搜索：按命令或 user_input 关键词
 *   4. 导出：调用后端导出接口（浏览器下载完整日志文件）
 *   5. 清空：二次确认后清空（后端会先备份）
 *
 * 布局：
 *   ┌─ 顶部栏：标题 + 条数 + 刷新 + 关闭 ─────────────┐
 *   ├─ 工具栏：成功状态 + safety 级别 + 搜索框 ──────┤
 *   ├─ 审计列表（flex-1，倒序显示，最新在顶部）──────┤
 *   └─ 底部栏：导出 + 清空（二次确认） + 路径 ────────┘
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { createPortal } from 'react-dom'
import {
  AlertTriangle,
  Check,
  Download,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  X,
  XCircle,
} from 'lucide-react'
import type { AuditEntry, AuditResponse } from '../api'
import { api } from '../api'
import { IconButton } from './IconButton'

interface AuditSheetProps {
  open: boolean
  onClose: () => void
}

type SuccessFilter = 'ALL' | 'OK' | 'FAIL'
type SafetyFilter = 'ALL' | 'white' | 'grey' | 'black' | 'unknown'

const SUCCESS_FILTERS: { value: SuccessFilter; label: string }[] = [
  { value: 'ALL', label: '全部' },
  { value: 'OK', label: '成功' },
  { value: 'FAIL', label: '失败' },
]

const SAFETY_FILTERS: { value: SafetyFilter; label: string }[] = [
  { value: 'ALL', label: '全部' },
  { value: 'white', label: '白名单' },
  { value: 'grey', label: '灰名单' },
  { value: 'black', label: '黑名单' },
  { value: 'unknown', label: '未知' },
]

const SAFETY_META: Record<string, { color: string; label: string; Icon: typeof Shield }> = {
  white: { color: 'text-green-400 bg-green-400/10', label: '白', Icon: ShieldCheck },
  grey: { color: 'text-yellow-400 bg-yellow-400/10', label: '灰', Icon: Shield },
  black: { color: 'text-red-400 bg-red-400/10', label: '黑', Icon: ShieldAlert },
  unknown: { color: 'text-text-tertiary bg-bg-tertiary', label: '?', Icon: Shield },
}

const EXIT_ANIM_MS = 150
const DEFAULT_PAGE_SIZE = 200

export function AuditSheet({ open, onClose }: AuditSheetProps) {
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [logFilePath, setLogFilePath] = useState('')
  const [successFilter, setSuccessFilter] = useState<SuccessFilter>('ALL')
  const [safetyFilter, setSafetyFilter] = useState<SafetyFilter>('ALL')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [confirmingClear, setConfirmingClear] = useState(false)
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

  // 拉取审计数据
  const fetchAudit = useCallback(async () => {
    setLoading(true)
    try {
      const filters: {
        success?: boolean
        safety?: 'white' | 'grey' | 'black' | 'unknown'
        q?: string
      } = {}
      if (successFilter !== 'ALL') filters.success = successFilter === 'OK'
      if (safetyFilter !== 'ALL') filters.safety = safetyFilter
      if (search.trim()) filters.q = search.trim()
      const res: AuditResponse = await api.audit(DEFAULT_PAGE_SIZE, filters)
      setEntries(res.entries)
      setTotalCount(res.count)
      setLogFilePath(res.log_file)
    } catch {
      // 静默
    } finally {
      setLoading(false)
    }
  }, [successFilter, safetyFilter, search])

  // 打开时 + 过滤条件变化时拉取
  useEffect(() => {
    if (!open) return
    fetchAudit()
  }, [open, fetchAudit])

  // 搜索防抖
  useEffect(() => {
    if (!open) return
    const t = setTimeout(() => fetchAudit(), 250)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search])

  const handleExport = () => {
    window.open(api.auditExportUrl(), '_blank')
  }

  const handleClearRequest = () => {
    setConfirmingClear(true)
  }

  const handleClearConfirm = async () => {
    setConfirmingClear(false)
    try {
      await api.auditClear()
      await fetchAudit()
    } catch {
      // 静默
    }
  }

  const handleClearCancel = () => {
    setConfirmingClear(false)
  }

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
          'mx-auto my-auto w-full max-w-[760px] h-[80vh]',
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
            <Shield size={16} className="text-accent" />
            <span className="text-sm font-medium cjk-spacing">审计日志</span>
            <span className="text-xs text-text-tertiary">·</span>
            <span className="text-xs text-text-tertiary">{totalCount} 条</span>
          </div>
          <div className="flex items-center gap-1">
            <IconButton onClick={fetchAudit} title="刷新">
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            </IconButton>
            <IconButton onClick={onClose} title="关闭">
              <X size={14} />
            </IconButton>
          </div>
        </div>

        {/* 工具栏：成功状态 + safety 级别 + 搜索 */}
        <div className="flex items-center gap-2 px-4 py-2 border-b border-border-soft">
          {/* 成功状态筛选 */}
          <div className="flex items-center gap-0.5 bg-bg-tertiary/40 rounded-md p-0.5">
            {SUCCESS_FILTERS.map(f => (
              <button
                key={f.value}
                onClick={() => setSuccessFilter(f.value)}
                className={[
                  'px-2 py-1 rounded text-[10px] font-medium transition-all cjk-spacing',
                  successFilter === f.value
                    ? 'bg-bg-secondary text-text-primary shadow-sm'
                    : 'text-text-tertiary hover:text-text-secondary',
                ].join(' ')}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* safety 级别筛选 */}
          <div className="flex items-center gap-0.5 bg-bg-tertiary/40 rounded-md p-0.5">
            {SAFETY_FILTERS.map(f => (
              <button
                key={f.value}
                onClick={() => setSafetyFilter(f.value)}
                className={[
                  'px-2 py-1 rounded text-[10px] font-medium transition-all cjk-spacing',
                  safetyFilter === f.value
                    ? 'bg-bg-secondary text-text-primary shadow-sm'
                    : 'text-text-tertiary hover:text-text-secondary',
                ].join(' ')}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* 搜索框 */}
          <div className="flex-1 flex items-center gap-1.5 px-2 py-1 bg-bg-tertiary/40 rounded-md">
            <Search size={12} className="text-text-tertiary" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="搜索命令或用户输入..."
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

        {/* 审计列表 */}
        <div className="flex-1 overflow-y-auto font-mono text-[11px] leading-relaxed">
          {entries.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-text-tertiary text-xs gap-2 cjk-spacing">
              <Shield size={24} className="text-text-tertiary/40" />
              <span>暂无审计记录</span>
            </div>
          ) : (
            <div className="py-1">
              {entries.map((e, i) => {
                const safety = SAFETY_META[e.safety_level] || SAFETY_META.unknown
                const SafetyIcon = safety.Icon
                const hasRaw = Boolean(e.raw)
                return (
                  <div
                    key={`${e.ts}-${i}`}
                    className="flex items-start gap-2 px-3 py-1.5 hover:bg-bg-tertiary/30 transition-colors border-b border-border-soft/40"
                  >
                    {/* 时间 */}
                    <span className="text-text-tertiary shrink-0 tabular-nums">
                      {e.ts.slice(5)}
                    </span>

                    {/* 成功/失败 */}
                    {e.success ? (
                      <Check size={11} className="text-green-400 shrink-0 mt-0.5" />
                    ) : (
                      <XCircle size={11} className="text-red-400 shrink-0 mt-0.5" />
                    )}

                    {/* safety 标签 */}
                    <span
                      className={[
                        'shrink-0 px-1 py-0 rounded text-[9px] font-bold tracking-wide flex items-center gap-0.5',
                        safety.color,
                      ].join(' ')}
                      title={`safety=${e.safety_level}`}
                    >
                      <SafetyIcon size={9} />
                      {safety.label}
                    </span>

                    {/* 命令 + 元数据 */}
                    <div className="flex-1 min-w-0">
                      <div className="text-text-primary break-all">
                        {e.command || e.raw || '(空)'}
                      </div>
                      <div className="flex items-center gap-3 mt-0.5 text-[10px] text-text-tertiary">
                        <span>exit={e.exit_code}</span>
                        <span>{e.duration?.toFixed(2)}s</span>
                        {e.user_input && (
                          <span className="truncate max-w-[200px]" title={e.user_input}>
                            输入: {e.user_input}
                          </span>
                        )}
                        {e.decision_reason && (
                          <span className="truncate max-w-[260px] text-text-tertiary/70" title={e.decision_reason}>
                            原因: {e.decision_reason}
                          </span>
                        )}
                        {hasRaw && (
                          <span className="text-yellow-500/70 flex items-center gap-0.5">
                            <AlertTriangle size={9} />
                            旧格式
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* 底部栏：导出 + 清空 + 路径 */}
        <div className="flex items-center justify-between px-4 py-2 border-t border-border-soft text-xs">
          <div className="flex items-center gap-2">
            {!confirmingClear ? (
              <>
                <button
                  onClick={handleExport}
                  className="flex items-center gap-1 px-2 py-1 rounded text-text-secondary hover:text-text-primary hover:bg-bg-tertiary/40 transition-all cjk-spacing"
                  title="下载完整审计日志文件"
                >
                  <Download size={11} />
                  <span>导出</span>
                </button>
                <button
                  onClick={handleClearRequest}
                  className="flex items-center gap-1 px-2 py-1 rounded text-text-tertiary hover:text-red-400 hover:bg-red-400/10 transition-all cjk-spacing"
                  title="备份后清空审计日志"
                >
                  <Trash2 size={11} />
                  <span>清空</span>
                </button>
              </>
            ) : (
              <div className="flex items-center gap-2 cjk-spacing">
                <AlertTriangle size={11} className="text-yellow-400" />
                <span className="text-yellow-400">确认清空？后端会先备份</span>
                <button
                  onClick={handleClearConfirm}
                  className="px-2 py-0.5 rounded bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
                >
                  确认
                </button>
                <button
                  onClick={handleClearCancel}
                  className="px-2 py-0.5 rounded text-text-tertiary hover:text-text-secondary hover:bg-bg-tertiary/40 transition-colors"
                >
                  取消
                </button>
              </div>
            )}
          </div>
          {logFilePath && (
            <span
              className="text-text-tertiary/60 font-mono text-[10px] truncate max-w-[260px]"
              title={logFilePath}
            >
              {logFilePath}
            </span>
          )}
        </div>
      </div>
    </div>,
    document.body,
  )
}
