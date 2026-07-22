/**
 * InputBar - 输入区
 *
 * 设计要点：
 *   - 独立毛玻璃圆角卡片（input-glass + rounded-xl 18px）
 *   - padding 对称：pt-3 pb-3，左右 px-4
 *   - 容器内：input + 圆形发送按钮（36×36）
 *   - 输入框文字 16px（text-base），避免过大
 *   - 发送按钮：圆形 36×36，绿色实心，禁用时灰底
 *   - 思考中：边框呼吸光晕（thinking class）+ Loader2 旋转
 *   - Enter 发送，IME 组合检测
 *   - 焦点环：3px 绿色光环（focus-within:shadow-focus）
 */

import { useEffect, useRef } from 'react'
import { ArrowUp, Loader2 } from 'lucide-react'

interface InputBarProps {
  value: string
  onChange: (v: string) => void
  onSend: () => void
  loading?: boolean
  placeholder?: string
  autoFocus?: boolean
}

export function InputBar({
  value,
  onChange,
  onSend,
  loading = false,
  placeholder = '告诉狸花猫你想做什么...',
  autoFocus = true,
}: InputBarProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (autoFocus) inputRef.current?.focus()
  }, [autoFocus])

  const canSend = value.trim().length > 0 && !loading

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Enter 发送（不带 Shift）
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      if (canSend) onSend()
    }
  }

  return (
    <div className="max-w-[640px] mx-auto w-full px-4 pt-3 pb-3">
      <div
        className={[
          'input-glass',
          'rounded-xl',
          'flex items-center gap-2',
          'pl-3 pr-1.5 py-1.5',
          'border',
          loading ? 'border-accent/30 thinking' : 'border-border-soft',
          'transition-colors duration-base ease-out-soft',
          'focus-within:border-accent/40',
          'focus-within:shadow-focus',
        ].join(' ')}
      >
        <input
          ref={inputRef}
          className={[
            'flex-1 bg-transparent',
            'py-2',
            'text-base leading-tight',
            'text-text-primary',
            'placeholder:text-text-tertiary',
            'outline-none',
            'cjk-spacing',
          ].join(' ')}
          placeholder={placeholder}
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          spellCheck={false}
          autoComplete="off"
        />

        {/* 发送按钮 / 加载指示器 */}
        {loading ? (
          <div
            className="w-9 h-9 rounded-full flex items-center justify-center bg-bg-tertiary/60 shrink-0"
            aria-label="思考中"
          >
            <Loader2 size={18} className="text-accent animate-spin" />
          </div>
        ) : (
          <button
            onClick={onSend}
            disabled={!canSend}
            aria-label="发送"
            title="Enter 发送"
            className={[
              'w-9 h-9 rounded-full',
              'flex items-center justify-center',
              'transition-all duration-fast ease-out-soft',
              'shrink-0',
              canSend
                ? 'bg-accent hover:bg-accent-hover text-white shadow-sm hover:shadow-md'
                : 'bg-bg-tertiary/40 text-text-tertiary cursor-not-allowed',
            ].join(' ')}
          >
            <ArrowUp size={18} strokeWidth={2.5} />
          </button>
        )}
      </div>
    </div>
  )
}
