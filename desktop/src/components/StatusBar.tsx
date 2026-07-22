/**
 * StatusBar - 底部状态栏
 *
 * 设计要点（v0.8.19 增强）：
 *   - 高度 36px（h-9），底部 pb-1.5 内缩 6px 安全区
 *     防止点击底栏按钮误触窗口边缘的 resize handle
 *   - 左侧：LLM 状态点 + 模型名 + ChevronRight 图标（点击打开模型设置）
 *   - 右侧：kbd 快捷键提示
 *   - 状态点呼吸光晕动画（在线时）
 *   - 模型名 hover 时变亮 + 显示 ChevronRight
 */

import { ChevronRight, Shield, Terminal } from 'lucide-react'
import type { Health } from '../api'

interface StatusBarProps {
  health: Health | null
  showEscHint?: boolean
  onOpenModelSettings?: () => void
  onOpenLog?: () => void
  onOpenAudit?: () => void
}

export function StatusBar({ health, showEscHint = false, onOpenModelSettings, onOpenLog, onOpenAudit }: StatusBarProps) {
  let dotColor = 'bg-warn'
  let statusText = '连接后端中...'
  let available = false

  if (health) {
    if (health.llm_available) {
      dotColor = 'bg-accent'
      statusText = health.llm_model || 'LLM 已连接'
      available = true
    } else {
      dotColor = 'bg-text-tertiary'
      statusText = '未启用 LLM · 点击设置'
    }
  }

  return (
    <div className="h-9 px-5 pb-1.5 flex items-center justify-between border-t border-border-soft text-xs text-text-tertiary select-none">
      {/* 左侧：LLM 状态（可点击打开模型设置） */}
      <button
        onClick={onOpenModelSettings}
        disabled={!onOpenModelSettings}
        className={[
          'flex items-center gap-1.5',
          'transition-all duration-fast ease-out-soft',
          onOpenModelSettings
            ? 'hover:text-text-primary cursor-pointer -mx-1 px-1 py-0.5 rounded'
            : 'cursor-default',
        ].join(' ')}
        title={onOpenModelSettings ? '点击切换模型' : undefined}
      >
        <span className={`w-2 h-2 rounded-full ${dotColor} ${available ? 'animate-pulse-soft' : ''}`} />
        <span className="cjk-spacing max-w-[200px] truncate">{statusText}</span>
        {onOpenModelSettings && (
          <ChevronRight size={11} strokeWidth={1.5} className="text-text-tertiary/70" />
        )}
      </button>

      {/* 右侧：审计 + 日志按钮 + 操作提示 */}
      <div className="flex items-center gap-3 cjk-spacing">
        {onOpenAudit && (
          <button
            onClick={onOpenAudit}
            className="flex items-center gap-1 text-text-tertiary hover:text-text-secondary transition-colors -mx-1 px-1 py-0.5 rounded"
            title="审计日志"
          >
            <Shield size={12} strokeWidth={1.5} />
          </button>
        )}
        {onOpenLog && (
          <button
            onClick={onOpenLog}
            className="flex items-center gap-1 text-text-tertiary hover:text-text-secondary transition-colors -mx-1 px-1 py-0.5 rounded"
            title="查看日志"
          >
            <Terminal size={12} strokeWidth={1.5} />
          </button>
        )}
        {showEscHint && (
          <span className="flex items-center gap-1">
            <kbd className="font-mono text-text-secondary px-1.5 py-0.5 rounded border border-border-soft bg-bg-secondary/60 text-[10px]">
              Esc
            </kbd>
            <span>取消</span>
          </span>
        )}
        <span className="flex items-center gap-1">
          <kbd className="font-mono text-text-secondary px-1.5 py-0.5 rounded border border-border-soft bg-bg-secondary/60 text-[10px]">
            Enter
          </kbd>
          <span>发送</span>
        </span>
      </div>
    </div>
  )
}
