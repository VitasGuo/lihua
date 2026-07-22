/**
 * MessageList - 对话流容器
 *
 * 设计要点：
 *   - 大留白：px-6 py-6（24px）
 *   - 消息间距：space-y-6（24px，比 v0.6 的 space-y-3 翻倍）
 *   - 自动滚动到底部（用户上滚时暂停）
 *   - 滚动条 4px 极简风
 *   - 空消息列表时不渲染（由 WelcomeScreen 接管）
 */

import { useEffect, useRef } from 'react'
import type { Message } from '../types'
import { MessageBubble } from './MessageBubble'

interface MessageListProps {
  messages: Message[]
}

export function MessageList({ messages }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const isAutoScrollRef = useRef(true)

  // 监听用户是否手动滚动（避免抢夺滚动控制）
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = container
      const atBottom = scrollHeight - scrollTop - clientHeight < 60
      isAutoScrollRef.current = atBottom
    }

    container.addEventListener('scroll', handleScroll, { passive: true })
    return () => container.removeEventListener('scroll', handleScroll)
  }, [])

  // 新消息到达时自动滚动到底部
  useEffect(() => {
    if (isAutoScrollRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [messages])

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto overflow-x-hidden px-6 py-6"
    >
      <div className="max-w-[640px] mx-auto space-y-6">
        {messages.map(m => (
          <MessageBubble key={m.id} msg={m} />
        ))}
      </div>
      <div ref={bottomRef} />
    </div>
  )
}
