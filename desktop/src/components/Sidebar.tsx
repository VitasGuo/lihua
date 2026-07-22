/**
 * Sidebar - 侧边栏
 *
 * 设计要点（v0.7.1 增强）：
 *   - 始终 mounted，通过 width + opacity transition 实现滑入/滑出双向动画
 *   - 主内容区配合收缩（width 0 → 288px 平滑过渡，flex layout 自动重排）
 *   - 宽度 280px（w-72），毛玻璃底色（bg-secondary/70 backdrop-blur-xl）
 *   - 内容固定宽度，外层 overflow-hidden 避免缩放期内容变形
 *   - 两个 tab：Skills / 历史
 *   - Skills 列表：name + description + 示例
 *   - 历史列表：消息 + 成功/失败图标 + 相对时间
 */

import { useState } from 'react'
import { CheckCircle2, Clock, MessageSquare, XCircle } from 'lucide-react'
import type { HistoryEntry, Skill } from '../api'

interface SidebarProps {
  open: boolean
  skills: Skill[]
  history: HistoryEntry[]
  onRefreshHistory: () => void
  onOpenHistorySheet: () => void  // v0.8.20: 打开完整对话历史 Sheet
}

type Tab = 'skills' | 'history'

export function Sidebar({ open, skills, history, onRefreshHistory, onOpenHistorySheet }: SidebarProps) {
  const [tab, setTab] = useState<Tab>('skills')

  return (
    <aside
      className={[
        'flex flex-col',
        'bg-bg-secondary/70 backdrop-blur-xl',
        'border-l border-border-default',
        'overflow-hidden',
        'transition-[width,opacity] duration-base ease-out-soft',
        open ? 'w-72 opacity-100' : 'w-0 opacity-0',
      ].join(' ')}
      aria-hidden={!open}
    >
      {/* 内容固定宽度，避免缩放期变形 */}
      <div className="w-72 h-full flex flex-col">
        {/* Tab 切换 */}
        <div className="flex border-b border-border-soft">
          <TabButton active={tab === 'skills'} onClick={() => setTab('skills')}>
            Skills
            <span className="ml-1.5 text-xs text-text-tertiary">{skills.length}</span>
          </TabButton>
          <TabButton
            active={tab === 'history'}
            onClick={() => {
              setTab('history')
              onRefreshHistory()
            }}
          >
            历史
          </TabButton>
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto p-2.5">
          {tab === 'skills' ? (
            <SkillsList skills={skills} />
          ) : (
            <>
              {/* v0.8.20: 查看完整对话历史入口（按 session_id 聚合的 episode 历史） */}
              <button
                onClick={onOpenHistorySheet}
                className="w-full mb-2 px-2.5 py-2 rounded-md bg-accent-soft text-accent text-sm hover:bg-accent-soft/70 transition-all duration-fast ease-out-soft flex items-center gap-1.5 cjk-spacing"
              >
                <MessageSquare size={13} strokeWidth={2} />
                查看完整对话历史
              </button>
              <HistoryList history={history} />
            </>
          )}
        </div>
      </div>
    </aside>
  )
}

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
        'flex-1 py-3 text-sm',
        'transition-all duration-fast ease-out-soft',
        'border-b-2',
        active
          ? 'text-accent border-accent font-medium'
          : 'text-text-secondary border-transparent hover:text-text-primary hover:bg-bg-tertiary/30',
      ].join(' ')}
    >
      {children}
    </button>
  )
}

function SkillsList({ skills }: { skills: Skill[] }) {
  if (skills.length === 0) {
    return (
      <div className="text-text-tertiary text-sm text-center mt-8 cjk-spacing">
        暂无 Skills
      </div>
    )
  }
  return (
    <div className="space-y-0.5">
      {skills.map(s => (
        <div
          key={s.name}
          className="px-2.5 py-2 rounded-md hover:bg-bg-tertiary/50 cursor-default transition-all duration-fast ease-out-soft"
        >
          <div className="text-sm text-text-primary font-medium">{s.name}</div>
          <div className="text-xs text-text-secondary mt-0.5 leading-relaxed cjk-spacing">
            {s.description}
          </div>
          {s.examples.length > 0 && (
            <div className="text-xs text-text-tertiary mt-1 cjk-spacing">
              <span className="text-text-tertiary/80">例：</span>
              {s.examples[0]}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function HistoryList({ history }: { history: HistoryEntry[] }) {
  if (history.length === 0) {
    return (
      <div className="text-text-tertiary text-sm text-center mt-8 cjk-spacing">
        暂无历史
      </div>
    )
  }
  return (
    <div className="space-y-0.5">
      {history.slice().reverse().map((h, i) => (
        <div
          key={i}
          className="px-2.5 py-2 rounded-md hover:bg-bg-tertiary/50 cursor-default transition-all duration-fast ease-out-soft"
        >
          <div className="text-sm text-text-primary truncate cjk-spacing">{h.message}</div>
          <div className="flex items-center gap-1.5 mt-1">
            {h.success ? (
              <CheckCircle2 size={11} className="text-accent" strokeWidth={2} />
            ) : (
              <XCircle size={11} className="text-danger" strokeWidth={2} />
            )}
            <span className={`text-xs ${h.success ? 'text-accent' : 'text-danger'}`}>
              {h.success ? '成功' : '失败'}
            </span>
            {h.timestamp && (
              <span className="text-xs text-text-tertiary flex items-center gap-0.5 ml-auto">
                <Clock size={10} strokeWidth={1.5} />
                {formatTime(h.timestamp)}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts)
    const now = new Date()
    const diff = now.getTime() - d.getTime()
    const min = Math.floor(diff / 60000)
    if (min < 1) return '刚刚'
    if (min < 60) return `${min}分钟前`
    const hour = Math.floor(min / 60)
    if (hour < 24) return `${hour}小时前`
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  } catch {
    return ''
  }
}
