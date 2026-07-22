/**
 * LogoSheet - 狸花猫图标自定义面板（v0.7.4 新增）
 *
 * 功能：
 *   1. 显示当前 logo 预览（emoji 或自定义图片）
 *   2. 上传自定义图片（FileReader → base64 → localStorage）
 *   3. 重置为默认 emoji 🐱
 *
 * 存储：
 *   - localStorage key: 'lihua:custom-logo'
 *   - 值：base64 data URL（如 'data:image/png;base64,...'）
 *
 * 限制：
 *   - 文件类型：image/*
 *   - 文件大小：< 500KB（避免 localStorage 爆掉）
 *   - 自动缩放预览（不修改原图）
 *
 * 动画：与 ModelSheet 一致（slide-up + fade-out 退出动画）
 */

import { useEffect, useRef, useState } from 'react'
import { ImagePlus, RotateCcw, Settings2, X } from 'lucide-react'
import { IconButton } from './IconButton'
import { LihuaLogo } from './LihuaLogo'

interface LogoSheetProps {
  open: boolean
  onClose: () => void
  customSrc: string | null
  onChange: (src: string | null) => void
}

const EXIT_ANIM_MS = 150
const MAX_FILE_SIZE = 500 * 1024 // 500KB
const STORAGE_KEY = 'lihua:custom-logo'

export function LogoSheet({ open, onClose, customSrc, onChange }: LogoSheetProps) {
  const [closing, setClosing] = useState(false)
  const [error, setError] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const prevOpenRef = useRef(false)

  const shouldRender = open || closing

  // 退出动画（与 ModelSheet 同逻辑）
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

  // ESC 关闭
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  if (!shouldRender) return null

  const handleClose = () => {
    if (closing) return
    setClosing(true)
    setTimeout(() => {
      onClose()
      setError('')
    }, EXIT_ANIM_MS)
  }

  // 处理文件选择
  const handleFile = (file: File) => {
    setError('')

    // 校验类型
    if (!file.type.startsWith('image/')) {
      setError('请选择图片文件（PNG / JPG / SVG 等）')
      return
    }

    // 校验大小
    if (file.size > MAX_FILE_SIZE) {
      const kb = Math.round(file.size / 1024)
      setError(`图片过大（${kb}KB），请选择小于 500KB 的图片`)
      return
    }

    // 读为 base64
    const reader = new FileReader()
    reader.onload = () => {
      const src = reader.result as string
      localStorage.setItem(STORAGE_KEY, src)
      onChange(src)
    }
    reader.onerror = () => setError('读取文件失败')
    reader.readAsDataURL(file)
  }

  // 重置为默认 emoji
  const handleReset = () => {
    localStorage.removeItem(STORAGE_KEY)
    onChange(null)
    setError('')
  }

  // 拖拽上传
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  const overlayAnim = closing ? 'animate-fade-out' : 'animate-fade-in'
  const sheetAnim = closing ? '' : 'animate-slide-up'

  return (
    <div
      className={`absolute inset-0 z-40 flex flex-col justify-end p-3 ${overlayAnim}`}
      style={{ background: 'rgba(0, 0, 0, 0.5)', backdropFilter: 'blur(6px)' }}
      onClick={handleClose}
    >
      <div
        className={`${sheetAnim} w-full bg-bg-secondary flex flex-col overflow-hidden rounded-2xl shadow-popover`}
        onClick={e => e.stopPropagation()}
        style={{ maxHeight: '90%' }}
      >
        {/* 顶部栏 */}
        <div className="h-12 px-5 flex items-center gap-2.5 border-b border-border-soft shrink-0">
          <div className="w-7 h-7 rounded-lg bg-accent-soft flex items-center justify-center">
            <Settings2 size={15} className="text-accent" strokeWidth={2} />
          </div>
          <h3 className="text-base font-medium text-text-primary flex-1 cjk-spacing">
            图标设置
          </h3>
          <IconButton onClick={handleClose} title="关闭" aria-label="关闭">
            <X size={16} />
          </IconButton>
        </div>

        {/* 主体内容 */}
        <div className="flex-1 overflow-y-auto px-5 py-5 space-y-5">
          {/* 当前预览 */}
          <div>
            <label className="block text-xs text-text-tertiary mb-2 tracking-wider cjk-spacing">
              当前图标
            </label>
            <div className="flex items-center gap-3 p-3 rounded-md bg-bg-primary border border-border-soft">
              <div className="w-12 h-12 rounded-lg bg-bg-tertiary/50 flex items-center justify-center shrink-0">
                <LihuaLogo size={32} customSrc={customSrc} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm text-text-primary cjk-spacing">
                  {customSrc ? '自定义图片' : '默认 emoji 🐱'}
                </div>
                <div className="text-xs text-text-tertiary mt-0.5 cjk-spacing">
                  {customSrc ? '点击「重置」恢复默认 emoji' : '系统 emoji，跟随主题'}
                </div>
              </div>
            </div>
          </div>

          {/* 上传区域 */}
          <div>
            <label className="block text-xs text-text-tertiary mb-2 tracking-wider cjk-spacing">
              上传自定义图片
            </label>
            <div
              onClick={() => fileInputRef.current?.click()}
              onDragOver={e => {
                e.preventDefault()
                setDragOver(true)
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              className={[
                'cursor-pointer rounded-md border-2 border-dashed p-6 text-center',
                'transition-colors duration-fast',
                dragOver
                  ? 'border-accent bg-accent-soft/20'
                  : 'border-border-default hover:border-border-strong hover:bg-bg-tertiary/30',
              ].join(' ')}
            >
              <ImagePlus
                size={24}
                className="text-text-tertiary mx-auto mb-2"
                strokeWidth={1.5}
              />
              <div className="text-sm text-text-secondary cjk-spacing">
                点击选择或拖拽图片到此处
              </div>
              <div className="text-xs text-text-tertiary mt-1 cjk-spacing">
                PNG / JPG / SVG · 最大 500KB
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={e => {
                  const file = e.target.files?.[0]
                  if (file) handleFile(file)
                  e.target.value = '' // 重置 input 允许重复选同一文件
                }}
                className="hidden"
              />
            </div>
          </div>

          {/* 错误提示 */}
          {error && (
            <div className="rounded-lg bg-danger-soft/30 border border-danger/30 px-3.5 py-2.5 text-sm text-danger cjk-spacing">
              {error}
            </div>
          )}

          {/* 重置按钮 */}
          {customSrc && (
            <button
              onClick={handleReset}
              className={[
                'w-full flex items-center justify-center gap-2',
                'px-4 py-2 rounded-md text-sm',
                'text-text-secondary border border-border-default',
                'hover:bg-bg-tertiary hover:text-text-primary',
                'transition-all duration-fast ease-out-soft',
              ].join(' ')}
            >
              <RotateCcw size={13} />
              <span className="cjk-spacing">重置为默认 emoji</span>
            </button>
          )}
        </div>

        {/* 底部按钮 */}
        <div className="px-5 py-3.5 border-t border-border-soft flex gap-2.5 justify-end shrink-0">
          <button
            onClick={handleClose}
            className="px-4 py-1.5 rounded-md text-sm font-medium text-white bg-accent hover:bg-accent-hover shadow-sm transition-all duration-fast ease-out-soft"
          >
            完成
          </button>
        </div>
      </div>
    </div>
  )
}
