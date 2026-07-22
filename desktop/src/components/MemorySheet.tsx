/**
 * MemorySheet - 记忆管理面板（v0.8.20）
 *
 * 用户权利入口：让用户能查看 / 导出 / 清空 agent 的记忆数据。
 *
 * 4 个 tab：
 *   1. 统计：episodes_count / knowledge_patterns / success_rate / top_tools / top_keywords
 *   2. 对话历史：跳转入口 → 打开 HistorySheet 查看完整对话
 *   3. 知识库：KnowledgePattern 列表（keywords + tool_chain + 成功率进度条）
 *   4. 踩坑记录：Trap 列表（编号 + symptom + status 徽章 + 点击展开根因/方案）
 *
 * 底部操作：
 *   - 导出：调 /api/memory/export 下载 JSON
 *   - 清空：二次确认 → /api/memory/clear（保留 traps）
 *
 * 数据来源：
 *   - GET /api/memory/export     stats + preferences + traps
 *   - GET /api/memory/knowledge  知识库 patterns
 *   - DELETE /api/memory/clear   清空
 *
 * 设计要点：
 *   - 复用 ModelSheet/AuditSheet 的 closing 动画模式（T045）
 *   - 只读查看 + 清空重置，不编辑单个 pattern/preference（决策 8）
 *   - Esc 键 / 点击遮罩 / 关闭按钮三种关闭路径都走退出动画
 */

import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  Database,
  Download,
  ExternalLink,
  Lightbulb,
  Loader2,
  Trash2,
  Wrench,
  X,
} from 'lucide-react'
import type { KnowledgePatternData, TrapData, MemoryStats } from '../api'
import { api } from '../api'
import { IconButton } from './IconButton'

interface MemorySheetProps {
  open: boolean
  onClose: () => void
  onOpenHistorySheet: () => void  // 跳转到 HistorySheet
}

type Tab = 'stats' | 'history' | 'knowledge' | 'traps'

const EXIT_ANIM_MS = 150

export function MemorySheet({ open, onClose, onOpenHistorySheet }: MemorySheetProps) {
  const [tab, setTab] = useState<Tab>('stats')
  const [stats, setStats] = useState<MemoryStats | null>(null)
  const [traps, setTraps] = useState<TrapData[]>([])
  const [knowledge, setKnowledge] = useState<KnowledgePatternData[]>([])
  const [loading, setLoading] = useState(false)
  const [confirmingClear, setConfirmingClear] = useState(false)
  const [clearing, setClearing] = useState(false)
  const [expandedTrap, setExpandedTrap] = useState<number | null>(null)
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

  // 拉取数据（stats + traps 一起从 export 接口取；knowledge 单独取）
  const fetchAll = async () => {
    setLoading(true)
    try {
      const [exportRes, knowledgeRes] = await Promise.all([
        api.memoryExport(),
        api.memoryKnowledge(),
      ])
      if (exportRes.ok) {
        setStats(exportRes.stats)
        setTraps(exportRes.traps || [])
      }
      if (knowledgeRes.ok) {
        setKnowledge(knowledgeRes.patterns || [])
      }
    } catch {
      // 静默
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) fetchAll()
  }, [open])

  // Esc 关闭
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (confirmingClear) setConfirmingClear(false)
        else onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose, confirmingClear])

  // 导出 JSON
  const handleExport = async () => {
    try {
      const res = await api.memoryExport()
      if (!res.ok) return
      const blob = new Blob([JSON.stringify(res, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `lihua-memory-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      // 静默
    }
  }

  // 清空
  const handleClear = async () => {
    setClearing(true)
    try {
      const res = await api.memoryClear()
      if (res.ok) {
        setConfirmingClear(false)
        await fetchAll()
      }
    } catch {
      // 静默
    } finally {
      setClearing(false)
    }
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
            <Database size={16} className="text-accent" />
            <span className="text-sm font-medium cjk-spacing">记忆管理</span>
          </div>
          <div className="flex items-center gap-1">
            <IconButton onClick={fetchAll} title="刷新">
              <Loader2 size={14} className={loading ? 'animate-spin' : ''} />
            </IconButton>
            <IconButton onClick={onClose} title="关闭">
              <X size={14} />
            </IconButton>
          </div>
        </div>

        {/* Tab 切换 */}
        <div className="flex border-b border-border-soft">
          <TabButton active={tab === 'stats'} onClick={() => setTab('stats')}>统计</TabButton>
          <TabButton active={tab === 'history'} onClick={() => setTab('history')}>对话历史</TabButton>
          <TabButton active={tab === 'knowledge'} onClick={() => setTab('knowledge')}>
            知识库
            <span className="ml-1 text-[10px] text-text-tertiary">{knowledge.length}</span>
          </TabButton>
          <TabButton active={tab === 'traps'} onClick={() => setTab('traps')}>
            踩坑
            <span className="ml-1 text-[10px] text-text-tertiary">{traps.length}</span>
          </TabButton>
        </div>

        {/* 内容区 */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center h-full text-text-tertiary">
              <Loader2 size={20} className="animate-spin" />
            </div>
          ) : tab === 'stats' ? (
            <StatsPanel stats={stats} />
          ) : tab === 'history' ? (
            <HistoryEntryPanel onOpenHistorySheet={onOpenHistorySheet} />
          ) : tab === 'knowledge' ? (
            <KnowledgePanel patterns={knowledge} />
          ) : (
            <TrapsPanel
              traps={traps}
              expandedTrap={expandedTrap}
              onToggle={setExpandedTrap}
            />
          )}
        </div>

        {/* 底部操作栏 */}
        <div className="flex items-center justify-between px-4 py-2.5 border-t border-border-soft">
          <button
            onClick={handleExport}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs text-text-secondary hover:text-text-primary hover:bg-bg-tertiary/50 transition-all duration-fast ease-out-soft cjk-spacing"
          >
            <Download size={12} strokeWidth={1.8} />
            导出 JSON
          </button>
          {confirmingClear ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-danger cjk-spacing flex items-center gap-1">
                <AlertTriangle size={11} />
                确认清空所有记忆？（保留踩坑记录）
              </span>
              <button
                onClick={handleClear}
                disabled={clearing}
                className="px-2.5 py-1 rounded-md bg-danger text-white text-xs hover:bg-danger/90 transition-all cjk-spacing disabled:opacity-50"
              >
                {clearing ? '清空中...' : '确认清空'}
              </button>
              <button
                onClick={() => setConfirmingClear(false)}
                className="px-2.5 py-1 rounded-md text-text-secondary text-xs hover:bg-bg-tertiary/50 transition-all cjk-spacing"
              >
                取消
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmingClear(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs text-danger hover:bg-danger/10 transition-all duration-fast ease-out-soft cjk-spacing"
            >
              <Trash2 size={12} strokeWidth={1.8} />
              清空记忆
            </button>
          )}
        </div>
      </div>
    </div>,
    document.body,
  )
}

// ─── Tab 按钮 ──────────────────────────────────────────────

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={[
        'flex-1 py-2.5 text-xs',
        'transition-all duration-fast ease-out-soft',
        'border-b-2 cjk-spacing',
        active
          ? 'text-accent border-accent font-medium'
          : 'text-text-secondary border-transparent hover:text-text-primary hover:bg-bg-tertiary/30',
      ].join(' ')}
    >
      {children}
    </button>
  )
}

// ─── 统计面板 ──────────────────────────────────────────────

function StatsPanel({ stats }: { stats: MemoryStats | null }) {
  if (!stats) {
    return (
      <div className="text-text-tertiary text-xs text-center mt-8 cjk-spacing">
        暂无统计数据
      </div>
    )
  }
  const episodes = stats.episodes_count ?? 0
  const patterns = stats.knowledge_patterns ?? 0
  const successRate = stats.success_rate ?? 0
  const topTools = (stats.top_tools as Array<{ name: string; count: number }>) || []
  const topKeywords = (stats.top_keywords as Array<{ keyword: string; count: number }>) || []

  return (
    <div className="space-y-4">
      {/* 关键数字 */}
      <div className="grid grid-cols-3 gap-3">
        <StatCard label="情景记忆" value={episodes} unit="条" />
        <StatCard label="知识模式" value={patterns} unit="条" />
        <StatCard label="成功率" value={(successRate * 100).toFixed(1)} unit="%" />
      </div>

      {/* Top 工具 */}
      {topTools.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 text-xs text-text-tertiary mb-2 cjk-spacing">
            <Wrench size={11} strokeWidth={1.8} />
            常用工具 Top 5
          </div>
          <div className="space-y-1.5">
            {topTools.slice(0, 5).map((t, i) => {
              const max = topTools[0]?.count || 1
              return (
                <div key={i} className="flex items-center gap-2">
                  <span className="text-xs text-text-secondary w-32 truncate font-mono">{t.name}</span>
                  <div className="flex-1 h-1.5 bg-bg-tertiary/50 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-accent/60 rounded-full transition-all"
                      style={{ width: `${(t.count / max) * 100}%` }}
                    />
                  </div>
                  <span className="text-[10px] text-text-tertiary w-8 text-right">{t.count}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Top 关键词 */}
      {topKeywords.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 text-xs text-text-tertiary mb-2 cjk-spacing">
            <Lightbulb size={11} strokeWidth={1.8} />
            常见关键词 Top 5
          </div>
          <div className="flex flex-wrap gap-1.5">
            {topKeywords.slice(0, 10).map((k, i) => (
              <span
                key={i}
                className="px-2 py-0.5 rounded text-[10px] bg-bg-tertiary/50 text-text-secondary cjk-spacing"
              >
                {k.keyword} <span className="text-text-tertiary">·{k.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {episodes === 0 && patterns === 0 && (
        <div className="text-text-tertiary text-xs text-center mt-8 cjk-spacing">
          记忆系统还未积累数据，多和狸花聊几句吧～
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, unit }: { label: string; value: number | string; unit: string }) {
  return (
    <div className="rounded-lg border border-border-soft bg-bg-tertiary/30 p-3">
      <div className="text-[10px] text-text-tertiary mb-1 cjk-spacing">{label}</div>
      <div className="flex items-baseline gap-1">
        <span className="text-xl font-medium text-text-primary">{value}</span>
        <span className="text-[10px] text-text-tertiary">{unit}</span>
      </div>
    </div>
  )
}

// ─── 对话历史入口面板 ──────────────────────────────────────

function HistoryEntryPanel({ onOpenHistorySheet }: { onOpenHistorySheet: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center gap-3">
      <div className="w-12 h-12 rounded-full bg-accent-soft flex items-center justify-center">
        <Brain size={20} className="text-accent" strokeWidth={1.8} />
      </div>
      <div>
        <div className="text-sm text-text-primary mb-1 cjk-spacing">完整对话历史</div>
        <div className="text-xs text-text-tertiary cjk-spacing">
          查看按会话聚合的所有交互记录（含思考链 + 工具调用）
        </div>
      </div>
      <button
        onClick={onOpenHistorySheet}
        className="flex items-center gap-1.5 px-4 py-2 rounded-md bg-accent text-white text-sm hover:bg-accent/90 transition-all duration-fast ease-out-soft cjk-spacing"
      >
        查看完整对话历史
        <ExternalLink size={12} strokeWidth={1.8} />
      </button>
    </div>
  )
}

// ─── 知识库面板 ────────────────────────────────────────────

function KnowledgePanel({ patterns }: { patterns: KnowledgePatternData[] }) {
  if (patterns.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-text-tertiary text-xs gap-2 cjk-spacing">
        <Database size={24} className="text-text-tertiary/40" />
        <span>暂无知识库模式</span>
      </div>
    )
  }
  return (
    <div className="space-y-2">
      {patterns.map(p => {
        const total = p.success_count + p.fail_count
        const rate = total > 0 ? (p.success_count / total) * 100 : 0
        return (
          <div
            key={p.id}
            className="rounded-md border border-border-soft bg-bg-tertiary/30 p-2.5"
          >
            <div className="flex flex-wrap gap-1 mb-1.5">
              {p.keywords.map((kw, i) => (
                <span
                  key={i}
                  className="px-1.5 py-0.5 rounded text-[10px] bg-bg-tertiary/60 text-text-secondary cjk-spacing"
                >
                  {kw}
                </span>
              ))}
            </div>
            <div className="flex items-center gap-1.5 text-[10px] text-text-tertiary mb-1.5">
              <Wrench size={9} strokeWidth={1.5} />
              <span className="font-mono">{p.tool_chain.join(' → ')}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1.5 bg-bg-tertiary/50 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${rate >= 80 ? 'bg-accent/60' : rate >= 50 ? 'bg-yellow-400/60' : 'bg-danger/60'}`}
                  style={{ width: `${rate}%` }}
                />
              </div>
              <span className="text-[10px] text-text-tertiary">
                {p.success_count}/{total} · {rate.toFixed(0)}%
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ─── 踩坑记录面板 ──────────────────────────────────────────

function TrapsPanel({
  traps,
  expandedTrap,
  onToggle,
}: {
  traps: TrapData[]
  expandedTrap: number | null
  onToggle: (id: number | null) => void
}) {
  if (traps.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-text-tertiary text-xs gap-2 cjk-spacing">
        <AlertTriangle size={24} className="text-text-tertiary/40" />
        <span>暂无踩坑记录</span>
      </div>
    )
  }
  return (
    <div className="space-y-1.5">
      {traps.map(t => {
        const expanded = expandedTrap === t.id
        const statusMeta = getTrapStatusMeta(t.status)
        return (
          <div
            key={t.id}
            className="rounded-md border border-border-soft bg-bg-tertiary/30 overflow-hidden"
          >
            <button
              onClick={() => onToggle(expanded ? null : t.id)}
              className="w-full text-left px-3 py-2 hover:bg-bg-tertiary/50 transition-all duration-fast ease-out-soft"
            >
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-text-tertiary font-mono">T{String(t.id).padStart(3, '0')}</span>
                <span className={`px-1.5 py-0.5 rounded text-[9px] ${statusMeta.color} cjk-spacing`}>
                  {statusMeta.label}
                </span>
                {t.fix_verified && (
                  <CheckCircle2 size={10} className="text-accent" strokeWidth={2} />
                )}
                <span className="text-xs text-text-primary truncate cjk-spacing flex-1">
                  {t.symptom || '(无现象描述)'}
                </span>
              </div>
            </button>
            {expanded && (
              <div className="px-3 py-2 border-t border-border-soft/60 space-y-2">
                {t.root_cause && (
                  <div>
                    <div className="text-[10px] text-text-tertiary mb-0.5 cjk-spacing">根因</div>
                    <div className="text-xs text-text-secondary cjk-spacing whitespace-pre-wrap pl-2 border-l border-border-soft">
                      {t.root_cause}
                    </div>
                  </div>
                )}
                {t.solution && (
                  <div>
                    <div className="text-[10px] text-text-tertiary mb-0.5 cjk-spacing">解决方案</div>
                    <div className="text-xs text-text-secondary cjk-spacing whitespace-pre-wrap pl-2 border-l border-accent/40">
                      {t.solution}
                    </div>
                  </div>
                )}
                {!t.root_cause && !t.solution && (
                  <div className="text-xs text-text-tertiary italic cjk-spacing">
                    尚未诊断根因和解决方案
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function getTrapStatusMeta(status: string): { color: string; label: string } {
  switch (status) {
    case 'open':
      return { color: 'text-danger bg-danger/10', label: '未修复' }
    case 'fixed':
      return { color: 'text-accent bg-accent/10', label: '已修复' }
    case 'workaround':
      return { color: 'text-yellow-400 bg-yellow-400/10', label: '已绕过' }
    default:
      return { color: 'text-text-tertiary bg-bg-tertiary', label: status }
  }
}
