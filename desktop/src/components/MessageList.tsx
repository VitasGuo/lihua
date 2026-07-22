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
  // v0.8.27: 'smooth' → 'auto'，避免平滑滚动与手动滚动冲突导致卡顿
  useEffect(() => {
    if (isAutoScrollRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'auto', block: 'end' })
    }
  }, [messages])

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto overflow-x-hidden px-6 py-6 overscroll-contain"
      // v0.8.31: 只保留 translateZ(0) 提升合成层
      //   v0.8.28 加的 will-change:scroll-position 会预分配整个可滚动区域的 GPU 缓冲区
      //   消息多时 GPU 内存耗尽 → Wayland display 连接断开 → 窗口黑屏
      //   translateZ(0) 足够提升合成层，不需要 will-change 预分配
      style={{ transform: 'translateZ(0)' }}
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
