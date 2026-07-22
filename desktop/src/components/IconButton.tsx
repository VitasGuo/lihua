/**
 * IconButton - macOS 风格图标按钮
 *
 * 设计要点（v0.7.1 动效增强）：
 *   - 8×8 padding（32×32 总尺寸）
 *   - 默认态：透明背景 + 灰色图标
 *   - hover：浅灰背景 + 主色文字 + scale(1.05) 微放大
 *   - active：scale(0.94) 明确按压反馈
 *   - 焦点环：3px 半透明绿色光环
 *   - 圆角 8px（rounded-lg）
 *   - 支持 hoverDanger 变体（hover 变红，用于关闭按钮）
 *   - transition duration-fast (150ms) + ease-out-soft
 */

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'

type Variant = 'default' | 'hoverDanger'

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode
  variant?: Variant
  /** 按钮尺寸 px，默认 32（即 w-8 h-8） */
  size?: number
  /** tooltip 文本 */
  title?: string
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  function IconButton(
    { children, variant = 'default', size = 32, title, className = '', ...rest },
    ref,
  ) {
    const baseCls = [
      'inline-flex items-center justify-center',
      'rounded-lg',
      'transition-all duration-fast ease-out-soft',
      'text-text-secondary',
      'hover:scale-105 active:scale-95',
      'focus-visible:outline-none focus-visible:shadow-focus',
      'disabled:opacity-40 disabled:cursor-not-allowed disabled:pointer-events-none disabled:hover:scale-100',
    ].join(' ')

    const hoverCls =
      variant === 'hoverDanger'
        ? 'hover:bg-danger-soft hover:text-danger'
        : 'hover:bg-bg-tertiary hover:text-text-primary'

    const style = { width: size, height: size }

    return (
      <button
        ref={ref}
        title={title}
        className={`${baseCls} ${hoverCls} ${className}`}
        style={style}
        {...rest}
      >
        {children}
      </button>
    )
  },
)
