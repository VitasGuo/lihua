/**
 * MessageBubble - 消息气泡
 *
 * 设计要点：
 *
 * 用户消息（右对齐）：
 *   - 淡绿底（accent-soft + /25 透明度叠加）+ 1px 绿色边框（accent/30）
 *   - 圆角 14px（rounded-lg），统一圆角
 *   - 最大宽 75%
 *   - 文字 text-base (15px)，主文字色
 *   - padding: px-4 py-2.5（与助手消息对齐）
 *
 * 助手消息（左对齐，毛玻璃卡片）：
 *   - 卡片底色（card-glass + bg-secondary 叠加，比窗口底深一阶）
 *   - 圆角 14px
 *   - 最大宽 92%（留出右侧呼吸空间）
 *   - 文字 text-base (15px)，主文字色
 *   - 思考中：用 thinking-dots 替代三个点
 *   - 工具调用：默认折叠（ToolCallCard）
 *   - 错误态：红色边框 + 红色文字
 *
 * 关键变化（vs v0.6）：
 *   - 去掉 intent.source / confidence / params 工程师信息
 *   - 去掉 ✓✗⊘ 文字符号，用 SVG 图标
 *   - 助手消息从「灰色方块」改为「毛玻璃卡片 + 深一阶底色」
 *   - 用户消息从「实心绿 + 圆角不对称」改为「淡绿底 + 统一圆角」
 *   - 两条消息 padding 统一，视觉对齐
 */

import { memo } from 'react'
import { AlertCircle, Brain, Loader2 } from 'lucide-react'
import type { Message } from '../types'
import { ToolCallCard } from './ToolCallCard'

interface MessageBubbleProps {
  msg: Message
}

// v0.8.28: React.memo 避免滚动时 App state 变化导致所有消息重渲染
export const MessageBubble = memo(function MessageBubble({ msg }: MessageBubbleProps) {
  // v0.8.27: content-visibility: auto 让浏览器跳过屏幕外消息的渲染
  //   搭配 contain-intrinsic-size 提供预估高度，避免滚动条跳动
  //   流式消息（streaming）不加，避免内容更新时被跳过
  const lazyStyle = msg.streaming
    ? undefined
    : { contentVisibility: 'auto' as const, containIntrinsicSize: '120px' }

  // === 用户消息 ===
  if (msg.role === 'user') {
    return (
      <div className="flex justify-end message-in" style={lazyStyle}>
      <div
          className={[
            'max-w-[75%]',
            'px-4 py-2.5',
            'rounded-lg',
            'bg-accent/25',
            'border border-accent/30',
            'text-base text-text-primary',
            'leading-relaxed',
            'cjk-spacing',
            'break-words',
          ].join(' ')}
        >
          {msg.content}
        </div>
      </div>
    )
  }

  // === 助手消息 ===
  const hasError = msg.error || (msg.result && msg.result.success === false)
  const hasToolCalls = (msg.tool_calls && msg.tool_calls.length > 0) ||
    (msg.result && msg.result.steps && msg.result.steps.some(s => !s.skipped))
  const hasContent = Boolean(msg.content)
  const isStreaming = msg.streaming
  // 思考中：loading 且没有内容也没有工具调用且没有 currentTool
  const isThinking = msg.loading && !hasContent && !hasToolCalls && !msg.currentTool

  return (
    <div className="flex justify-start message-in" style={lazyStyle}>
      <div
        className={[
          'max-w-[92%]',
          'px-4 py-2.5',
          'rounded-lg',
          'card-glass',
          hasError
            ? 'border border-danger/35'
            : 'border border-border-soft',
          'text-base text-text-primary',
          'leading-relaxed',
          'cjk-spacing',
          'break-words',
        ].join(' ')}
      >
        {/* 思考中（无任何内容时） */}
        {isThinking ? (
          <div className="text-text-secondary text-base flex items-center gap-1.5 py-0.5">
            <span>思考中</span>
            <span className="thinking-dots inline-flex">
              <span>.</span>
              <span>.</span>
              <span>.</span>
            </span>
          </div>
        ) : (
          <>
            {/* 错误提示 */}
            {hasError && msg.error && (
              <div className="flex items-start gap-2 mb-2 text-danger">
                <AlertCircle size={15} strokeWidth={2} className="shrink-0 mt-0.5" />
                <span className="text-sm">{msg.error}</span>
              </div>
            )}

            {/* v0.8.20: LLM 思考链（默认展开，Brain 图标 + 浅色斜体） */}
            {msg.reasoning && (
              <div className="mb-2 p-2.5 rounded-md bg-bg-tertiary/40 border border-border-soft">
                <div className="flex items-center gap-1.5 text-xs text-text-tertiary mb-1.5">
                  <Brain size={12} strokeWidth={1.8} />
                  <span className="cjk-spacing">思考链</span>
                </div>
                <div className="text-xs text-text-secondary italic leading-relaxed whitespace-pre-wrap cjk-spacing">
                  {msg.reasoning}
                </div>
              </div>
            )}

            {/* 主回复内容（流式时也显示，实时更新） */}
            {hasContent && (
              <p className="text-text-primary whitespace-pre-wrap">{msg.content}</p>
            )}

            {/* 工具调用过程（流式时也显示，实时追加） */}
            {hasToolCalls && (
              <ToolCallCard
                toolCalls={msg.tool_calls}
                steps={msg.result?.steps}
                streaming={isStreaming}
              />
            )}

            {/* 正在执行工具（流式中） */}
            {isStreaming && msg.currentTool && !hasContent && (
              <div className="flex items-center gap-1.5 text-text-secondary text-sm py-0.5">
                <Loader2 size={13} className="animate-spin" />
                <span className="cjk-spacing">正在执行 {msg.currentTool}...</span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
})
