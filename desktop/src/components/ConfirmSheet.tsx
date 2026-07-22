/**
 * ConfirmSheet - 灰名单确认弹窗（macOS Sheet 风格）
 *
 * 设计要点：
 *   - 从顶部滑下（slide-down 动画），而非中央 fade-in
 *   - 弹窗底色 bg-secondary + 强阴影 shadow-popover
 *   - 圆角 18px（rounded-xl）
 *   - 标题左侧 SVG ShieldCheck 图标（绿色安全底，非橙色警示）
 *   - 操作内容用卡片包裹（bg-primary/60），让用户清楚知道执行什么
 *   - 主操作按钮（确认）绿色实心，次要按钮（取消）灰色边框
 *   - 底部辅助说明：灰名单任务需要确认 · 命令原文不展示
 *   - 点击背景不关闭（避免误触），必须显式点击按钮或按 Esc
 *   - autoFocus 默认在取消按钮（防误回车确认）
 *
 * v0.8.4 改造：支持结构化字段（toolName / intent / code / commandText），
 * 让 confirm 弹窗能分别展示"意图说明"和"代码/命令"，而不是把 ```python
 * 标记和"命令："前缀当纯文本展示。
 * - run_python：意图卡片 + Python 代码块（带 Code 图标 + 等宽字体 + 深色背景）
 * - run_shell：意图卡片 + 命令块（带 Terminal 图标 + 等宽字体 + 深色背景）
 * - file_op / 默认：纯文本展示（保持旧行为）
 */

import { useEffect } from 'react'
import { Code, ShieldCheck, Terminal, X } from 'lucide-react'
import { IconButton } from './IconButton'

interface ConfirmSheetProps {
  messages: string[]
  /** v0.8.4: 工具名，决定展示样式 */
  toolName?: string
  /** v0.8.4: LLM 给的中文意图说明 */
  intent?: string
  /** v0.8.4: run_python 的代码内容 */
  code?: string
  /** v0.8.4: run_shell 的命令内容 */
  commandText?: string
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmSheet({
  messages,
  toolName,
  intent,
  code,
  commandText,
  onConfirm,
  onCancel,
}: ConfirmSheetProps) {
  // Esc 取消
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCancel])

  // v0.8.4: 判断是否走结构化展示路径
  const isRunPython = toolName === 'run_python' && Boolean(code)
  const isRunShell = toolName === 'run_shell' && Boolean(commandText)
  // 文件操作或默认：走纯文本 messages 展示
  const useStructured = isRunPython || isRunShell

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-16 px-4"
      style={{ background: 'rgba(0, 0, 0, 0.55)', backdropFilter: 'blur(8px)' }}
      onClick={onCancel}
    >
      <div
        className="animate-slide-down w-full max-w-lg bg-bg-secondary border border-border-default rounded-xl shadow-popover overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* 顶部栏 */}
        <div className="flex items-center gap-2.5 px-5 py-4 border-b border-border-soft">
          <div className="w-8 h-8 rounded-lg bg-accent-soft flex items-center justify-center">
            <ShieldCheck size={18} className="text-accent" strokeWidth={2} />
          </div>
          <h3 className="text-base font-semibold text-text-primary flex-1 cjk-spacing">
            需要你的确认
          </h3>
          <IconButton onClick={onCancel} title="取消" aria-label="取消">
            <X size={16} />
          </IconButton>
        </div>

        {/* 内容 */}
        <div className="px-5 py-4 space-y-2.5">
          {useStructured ? (
            <>
              {/* v0.8.4: 结构化展示——意图 + 代码块/命令块 */}
              <p className="text-sm text-text-secondary leading-relaxed cjk-spacing">
                {isRunPython ? '即将执行以下 Python 代码：' : '即将执行以下命令：'}
              </p>

              {/* 意图说明卡片 */}
              {intent && (
                <div className="px-3 py-2.5 rounded-lg bg-bg-primary/60 border border-border-soft">
                  <div className="text-[10px] tracking-wider text-text-tertiary mb-1">意图</div>
                  <p className="text-sm text-text-primary leading-relaxed cjk-spacing">
                    {intent}
                  </p>
                </div>
              )}

              {/* run_python 代码块 */}
              {isRunPython && (
                <div className="rounded-lg overflow-hidden border border-border-default">
                  <div className="flex items-center gap-1.5 px-3 py-1.5 bg-bg-tertiary/80 border-b border-border-soft">
                    <Code size={12} className="text-accent" strokeWidth={1.5} />
                    <span className="text-[10px] tracking-wider text-text-tertiary">
                      Python 代码{code && code.length > 500 ? `（${code.length} 字符）` : ''}
                    </span>
                  </div>
                  <pre className="font-mono text-xs text-text-secondary whitespace-pre-wrap break-all leading-relaxed bg-[#1e1e2e] text-[#cdd6f4] px-3 py-2.5 max-h-60 overflow-y-auto">
                    {code}
                  </pre>
                </div>
              )}

              {/* run_shell 命令块 */}
              {isRunShell && (
                <div className="rounded-lg overflow-hidden border border-border-default">
                  <div className="flex items-center gap-1.5 px-3 py-1.5 bg-bg-tertiary/80 border-b border-border-soft">
                    <Terminal size={12} className="text-accent" strokeWidth={1.5} />
                    <span className="text-[10px] tracking-wider text-text-tertiary">命令</span>
                  </div>
                  <pre className="font-mono text-xs text-text-secondary whitespace-pre-wrap break-all leading-relaxed bg-[#1e1e2e] text-[#cdd6f4] px-3 py-2.5 max-h-40 overflow-y-auto">
                    {commandText}
                  </pre>
                </div>
              )}
            </>
          ) : (
            <>
              {/* 旧路径：纯文本 messages 展示（文件操作 / skill / 兼容旧前端） */}
              <p className="text-sm text-text-secondary leading-relaxed cjk-spacing">
                即将执行以下操作：
              </p>

              <div className="space-y-2">
                {messages.length === 0 ? (
                  <div className="px-3 py-2.5 rounded-lg bg-bg-primary/60 border border-border-soft text-sm text-text-secondary cjk-spacing">
                    即将执行需要管理员权限的操作
                  </div>
                ) : (
                  messages.map((m, i) => (
                    <div
                      key={i}
                      className="px-3 py-2.5 rounded-lg bg-bg-primary/60 border border-border-soft"
                    >
                      <p className="text-sm text-text-primary leading-relaxed cjk-spacing whitespace-pre-wrap break-all">
                        {m}
                      </p>
                    </div>
                  ))
                )}
              </div>
            </>
          )}

          <p className="text-xs text-text-tertiary leading-relaxed mt-1 cjk-spacing">
            {useStructured
              ? (isRunPython
                  ? 'Python 代码能力很强，请确认代码内容后再执行。'
                  : '这条命令会修改你的系统，请确认后再执行。')
              : '这个操作会修改你的系统，需要你确认才会执行。'}
          </p>
        </div>

        {/* 按钮区 */}
        <div className="px-5 py-4 border-t border-border-soft flex gap-2.5 justify-end">
          <button
            onClick={onCancel}
            autoFocus
            className={[
              'px-5 py-2 rounded-lg',
              'text-sm text-text-secondary',
              'border border-border-default',
              'hover:bg-bg-tertiary hover:text-text-primary',
              'transition-all duration-fast ease-out-soft',
            ].join(' ')}
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            className={[
              'px-5 py-2 rounded-lg',
              'text-sm font-medium text-white',
              'bg-accent hover:bg-accent-hover',
              'shadow-sm',
              'transition-all duration-fast ease-out-soft',
            ].join(' ')}
          >
            确认执行
          </button>
        </div>
      </div>
    </div>
  )
}
