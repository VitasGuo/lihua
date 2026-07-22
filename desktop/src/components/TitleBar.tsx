/**
 * TitleBar - 顶部标题栏
 *
 * 设计要点（v0.8.19 更新）：
 *   - 高度 48px（h-12），data-tauri-drag-region 可拖动
 *   - 左侧：18px 狸花猫 logo（可点击打开图标设置）+ 「狸花猫」标题
 *   - 右侧按钮组（从左到右）：
 *       1. 新会话（SquarePen）— 清空当前对话
 *       2. 侧栏切换（PanelLeftClose/Open）
 *       3. 最小化（Minus）
 *       4. 最大化/还原（Maximize2 / Minimize2，根据 isMaximized 切换）
 *       5. 关闭（X，hoverDanger）— 隐藏到托盘
 *   - Logo 支持 customSrc（用户自定义图片）
 *   - 双击标题栏触发 Tauri 默认最大化/还原（data-tauri-drag-region 自带）
 */

import { Maximize2, Minimize2, Minus, PanelLeftClose, PanelLeftOpen, SquarePen, X } from 'lucide-react'
import { IconButton } from './IconButton'
import { LihuaLogo } from './LihuaLogo'

interface TitleBarProps {
  sidebarOpen: boolean
  onToggleSidebar: () => void
  onHide: () => void
  /** v0.8.19: 新会话按钮回调 */
  onNewChat: () => void
  /** v0.8.19: 最小化按钮回调 */
  onMinimize: () => void
  /** v0.8.19: 最大化/还原按钮回调 */
  onToggleMaximize: () => void
  /** v0.8.19: 当前是否最大化（控制图标切换） */
  isMaximized: boolean
  customLogoSrc?: string | null
  onLogoClick?: () => void
}

export function TitleBar({
  sidebarOpen,
  onToggleSidebar,
  onHide,
  onNewChat,
  onMinimize,
  onToggleMaximize,
  isMaximized,
  customLogoSrc,
  onLogoClick,
}: TitleBarProps) {
  return (
    <div
      data-tauri-drag-region
      className="h-12 px-5 flex items-center gap-2.5 border-b border-border-default select-none"
    >
      {/* Logo（可点击打开图标设置） */}
      <LihuaLogo
        size={18}
        customSrc={customLogoSrc}
        onClick={onLogoClick}
        className="rounded p-0.5 hover:bg-bg-tertiary/30 transition-colors duration-fast"
      />

      {/* 标题 */}
      <span
        data-tauri-drag-region
        className="text-base font-medium text-text-primary tracking-tight cjk-spacing"
      >
        狸花猫
      </span>

      <div data-tauri-drag-region className="flex-1" />

      {/* 新会话 */}
      <IconButton
        onClick={onNewChat}
        title="新会话"
        aria-label="新会话"
      >
        <SquarePen size={16} strokeWidth={2} />
      </IconButton>

      {/* 侧栏切换 */}
      <IconButton
        onClick={onToggleSidebar}
        title={sidebarOpen ? '关闭侧边栏' : '打开侧边栏'}
        aria-label={sidebarOpen ? '关闭侧边栏' : '打开侧边栏'}
      >
        {sidebarOpen ? <PanelLeftClose size={17} /> : <PanelLeftOpen size={17} />}
      </IconButton>

      {/* 最小化 */}
      <IconButton
        onClick={onMinimize}
        title="最小化"
        aria-label="最小化"
      >
        <Minus size={16} strokeWidth={2} />
      </IconButton>

      {/* 最大化 / 还原 */}
      <IconButton
        onClick={onToggleMaximize}
        title={isMaximized ? '还原' : '最大化'}
        aria-label={isMaximized ? '还原' : '最大化'}
      >
        {isMaximized ? <Minimize2 size={15} strokeWidth={2} /> : <Maximize2 size={15} strokeWidth={2} />}
      </IconButton>

      {/* 关闭（隐藏到托盘） */}
      <IconButton onClick={onHide} title="关闭" variant="hoverDanger" aria-label="关闭">
        <X size={17} strokeWidth={2} />
      </IconButton>
    </div>
  )
}
