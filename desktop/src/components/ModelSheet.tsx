/**
 * ModelSheet - LLM 模型选择面板（v0.7.4 极简版）
 *
 * v0.7.4 关键修复：
 *   1. 自绘下拉菜单（替代原生 <select>）→ 修复 Tauri WebView 下白底白字问题
 *   2. 退出动画（先 fade-out 再 unmount）→ 修复「退出有残影」问题
 *   3. ESC 键 / 点击遮罩 / 关闭按钮三种关闭路径都走退出动画
 *
 * 极简结构（v0.7.3 沿用）：
 *   1. 厂商 segmented control（6 个按钮一字排开）
 *   2. 模型下拉（自绘，默认该厂商 pro 旗舰）
 *   3. API Key 输入（带显隐 + 获取链接）
 *   4. 能力下限警告条（黄色，固定底部）
 *   5. 保存按钮
 */

import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ExternalLink,
  Eye,
  EyeOff,
  Loader2,
  Settings2,
  X,
} from 'lucide-react'
import type { LLMConfig, ModelPreset } from '../api'
import { api } from '../api'
import { IconButton } from './IconButton'

interface ModelSheetProps {
  open: boolean
  onClose: () => void
  onSaved: () => void
}

// 能力下限警告（静态，不依赖 API）
const MIN_RECOMMENDED_WARNING =
  '不建议使用能力低于 DeepSeek V4 Flash 的模型，否则 Agent 可能无法正确调用工具'

// 退出动画时长（与 animate-fade-out 一致）
const EXIT_ANIM_MS = 150

export function ModelSheet({ open, onClose, onSaved }: ModelSheetProps) {
  const [presets, setPresets] = useState<ModelPreset[]>([])
  const [config, setConfig] = useState<LLMConfig | null>(null)
  const [selectedPresetId, setSelectedPresetId] = useState<string>('')
  const [selectedModelId, setSelectedModelId] = useState<string>('')
  const [apiKey, setApiKey] = useState('')
  // v0.8.21: 按 provider 存储 key，切换厂商时保存/恢复
  const [apiKeysByPreset, setApiKeysByPreset] = useState<Record<string, string>>({})
  const [showKey, setShowKey] = useState(false)
  const [customApiBase, setCustomApiBase] = useState('')
  const [customModel, setCustomModel] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [successMsg, setSuccessMsg] = useState('')

  // 退出动画状态：open=false 时先 closing=true 播退出动画，动画结束再真正 unmount
  const [closing, setClosing] = useState(false)
  // 模型下拉展开状态 + 位置（v0.7.6: Portal 方案，脱离父容器 overflow 裁剪）
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false)
  const [dropdownPos, setDropdownPos] = useState<{ top: number; left: number; width: number } | null>(null)
  const modelDropdownRef = useRef<HTMLDivElement>(null)
  const modelDropdownListRef = useRef<HTMLDivElement>(null)
  // 跟踪上一次的 open 状态，避免初始 mount 时误触发退出动画
  const prevOpenRef = useRef(false)

  // 真正的"是否渲染"：open 或 closing 时都渲染
  const shouldRender = open || closing

  // 监听 open 变化：仅当从 true→false 时触发退出动画
  useEffect(() => {
    const prevOpen = prevOpenRef.current
    prevOpenRef.current = open

    if (open) {
      // 打开：重置退出状态
      setClosing(false)
    } else if (prevOpen) {
      // 从开变关：触发退出动画
      setClosing(true)
      const t = setTimeout(() => setClosing(false), EXIT_ANIM_MS)
      return () => clearTimeout(t)
    }
  }, [open])

  // 加载预设 + 当前配置
  useEffect(() => {
    if (!open) return
    Promise.all([api.listModelPresets(), api.getLLMConfig()])
      .then(([presetRes, cfg]) => {
        setPresets(presetRes.presets)
        setConfig(cfg)
        const matched = presetRes.presets.find(
          p => p.api_base && cfg.api_base && p.api_base === cfg.api_base,
        )
        const presetId = matched?.id || 'custom'
        setSelectedPresetId(presetId)
        const preset = matched || presetRes.presets.find(p => p.id === 'custom')
        if (preset && preset.models.some(m => m.id === cfg.model)) {
          setSelectedModelId(cfg.model || '')
        } else if (preset) {
          setSelectedModelId(preset.recommended_model || cfg.model || '')
        }
        if (!matched) {
          setCustomApiBase(cfg.api_base || '')
          setCustomModel(cfg.model || '')
        }
      })
      .catch(e => setError(e.message))
  }, [open])

  // Esc 关闭（走退出动画）
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (modelDropdownOpen) {
          setModelDropdownOpen(false)
        } else {
          handleClose()
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, modelDropdownOpen])

  // 点击模型下拉外部关闭（含 Portal 里的列表）
  // v0.8.26: 增加 data-dropdown-list 属性 closest() fallback，
  //   不依赖 ref.contains() 对 Portal 节点的捕获（Tauri WebKitGTK 下更健壮）
  useEffect(() => {
    if (!modelDropdownOpen) return
    const onClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      const inTrigger = modelDropdownRef.current?.contains(target)
      const inList = modelDropdownListRef.current?.contains(target)
      // Fallback: data 属性检测（Portal 渲染到 body，ref 偶发未挂载时兜底）
      const inListFallback = target.closest('[data-dropdown-list]')
      if (!inTrigger && !inList && !inListFallback) {
        setModelDropdownOpen(false)
      }
    }
    window.addEventListener('mousedown', onClick)
    return () => window.removeEventListener('mousedown', onClick)
  }, [modelDropdownOpen])

  // 滚动或窗口大小变化时关闭下拉（避免位置错乱）
  useEffect(() => {
    if (!modelDropdownOpen) return
    const onClose = () => setModelDropdownOpen(false)
    window.addEventListener('scroll', onClose, false)
    window.addEventListener('resize', onClose)
    return () => {
      window.removeEventListener('scroll', onClose, false)
      window.removeEventListener('resize', onClose)
    }
  }, [modelDropdownOpen])

  // 切换模型下拉：计算位置后展开
  const handleToggleDropdown = () => {
    if (modelDropdownOpen) {
      setModelDropdownOpen(false)
      return
    }
    if (modelDropdownRef.current) {
      const rect = modelDropdownRef.current.getBoundingClientRect()
      setDropdownPos({
        top: rect.bottom + 4,
        left: rect.left,
        width: rect.width,
      })
      setModelDropdownOpen(true)
    }
  }

  // 关闭流程：先播退出动画再调 onClose
  const handleClose = () => {
    if (closing) return
    setClosing(true)
    setTimeout(() => {
      onClose()
      // 重置临时状态
      setError('')
      setSuccessMsg('')
      setModelDropdownOpen(false)
    }, EXIT_ANIM_MS)
  }

  if (!shouldRender) return null

  const selectedPreset = presets.find(p => p.id === selectedPresetId)

  const handleSelectPreset = (preset: ModelPreset) => {
    // v0.8.21: 保存当前 provider 的 key，恢复目标 provider 的 key
    if (selectedPresetId) {
      setApiKeysByPreset(prev => ({ ...prev, [selectedPresetId]: apiKey }))
    }
    setSelectedPresetId(preset.id)
    setError('')
    setSuccessMsg('')
    setSelectedModelId(preset.recommended_model || '')
    setModelDropdownOpen(false)
    setApiKey(apiKeysByPreset[preset.id] || '')
    // v0.8.21: 切到 custom 时不覆盖 customApiBase/customModel，保留之前输入的值
  }

  const handleSave = async () => {
    if (!selectedPreset) return
    setSaving(true)
    setError('')
    setSuccessMsg('')
    try {
      const body: { model_id?: string; api_base?: string } = {}
      if (selectedPreset.id === 'custom') {
        if (customApiBase.trim()) body.api_base = customApiBase.trim()
        if (customModel.trim()) body.model_id = customModel.trim()
      } else if (selectedModelId) {
        body.model_id = selectedModelId
      }
      const presetRes = await api.applyPreset(selectedPreset.id, body)
      if (!presetRes.ok) {
        throw new Error(presetRes.error || '应用预设失败')
      }

      if (apiKey.trim()) {
        const res = await api.updateLLMConfig({ api_key: apiKey.trim() })
        if (!res.ok) {
          throw new Error(res.error || '更新 API Key 失败')
        }
      }

      if (!config?.enabled) {
        const res = await api.updateLLMConfig({ enabled: true })
        if (!res.ok) {
          throw new Error(res.error || '启用 LLM 失败')
        }
      }

      const modelLabel =
        selectedPreset.id === 'custom'
          ? customModel || '自定义模型'
          : selectedPreset.models.find(m => m.id === selectedModelId)?.name ||
            selectedModelId

      setSuccessMsg(`已切换到 ${selectedPreset.name} · ${modelLabel}`)
      setApiKey('')
      // v0.8.21: 清空已保存 provider 的临时 key（已持久化到后端）
      setApiKeysByPreset(prev => {
        const next = { ...prev }
        delete next[selectedPresetId]
        return next
      })
      setTimeout(() => {
        onSaved()
        handleClose()
      }, 800)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  // 选中模型对象
  const selectedModel = selectedPreset?.models.find(m => m.id === selectedModelId)

  // 容器动画类
  const overlayAnim = closing
    ? 'animate-fade-out'
    : 'animate-fade-in'
  const sheetAnim = closing ? '' : 'animate-slide-up'

  return (
    <div
      className={`absolute inset-0 z-40 flex flex-col justify-end p-3 ${overlayAnim}`}
      style={{ background: 'rgba(0, 0, 0, 0.5)', backdropFilter: 'blur(6px)' }}
      // v0.8.26: 只在点击遮罩本身时关闭，不依赖 React 合成事件冒泡
      //   （Portal 渲染到 body 的子元素 click 在某些 WebView 下冒泡路径异常）
      onClick={e => {
        if (e.target === e.currentTarget) handleClose()
      }}
    >
      <div
        className={`${sheetAnim} w-full bg-bg-secondary flex flex-col rounded-2xl shadow-popover`}
        style={{ maxHeight: '90%' }}
      >
        {/* 顶部栏 */}
        <div className="h-12 px-5 flex items-center gap-2.5 border-b border-border-soft shrink-0 rounded-t-2xl">
          <div className="w-7 h-7 rounded-lg bg-accent-soft flex items-center justify-center">
            <Settings2 size={15} className="text-accent" strokeWidth={2} />
          </div>
          <h3 className="text-base font-medium text-text-primary flex-1 cjk-spacing">
            模型设置
          </h3>
          <IconButton onClick={handleClose} title="关闭" aria-label="关闭">
            <X size={16} />
          </IconButton>
        </div>

        {/* 主体内容 */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {/* 厂商 segmented control */}
          <div>
            <label className="block text-xs text-text-tertiary mb-2 tracking-wider cjk-spacing">
              厂商
            </label>
            <div className="flex flex-wrap gap-1.5">
              {presets.map(preset => {
                const active = selectedPresetId === preset.id
                return (
                  <button
                    key={preset.id}
                    onClick={() => handleSelectPreset(preset)}
                    className={[
                      'px-3 py-1.5 rounded-md text-xs font-medium',
                      'transition-all duration-fast ease-out-soft',
                      'active:scale-95',
                      active
                        ? 'bg-accent text-white shadow-sm'
                        : 'bg-bg-tertiary/50 text-text-secondary hover:bg-bg-tertiary hover:text-text-primary',
                    ].join(' ')}
                  >
                    {preset.name}
                  </button>
                )
              })}
            </div>
          </div>

          {/* 模型选择 / 自定义输入 */}
          {selectedPreset && (
            <div className="expand-in">
              {selectedPreset.id === 'custom' ? (
                <div className="space-y-3">
                  <Field label="API Base">
                    <input
                      type="text"
                      value={customApiBase}
                      onChange={e => setCustomApiBase(e.target.value)}
                      placeholder="https://your-endpoint.com/v1"
                      className="w-full bg-bg-primary border border-border-soft rounded-md px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary outline-none focus:border-accent/40 transition-colors font-mono"
                    />
                  </Field>
                  <Field label="模型名">
                    <input
                      type="text"
                      value={customModel}
                      onChange={e => setCustomModel(e.target.value)}
                      placeholder="deepseek-v4-flash / gpt-4o-mini / ..."
                      className="w-full bg-bg-primary border border-border-soft rounded-md px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary outline-none focus:border-accent/40 transition-colors font-mono"
                    />
                  </Field>
                </div>
              ) : (
                <Field label="模型">
                  {/* 自绘下拉菜单（v0.7.6: Portal 渲染到 body，脱离父容器 overflow 裁剪） */}
                  <div className="relative" ref={modelDropdownRef}>
                    <button
                      type="button"
                      onClick={handleToggleDropdown}
                      className={[
                        'w-full flex items-center justify-between',
                        'bg-bg-primary border border-border-soft rounded-md',
                        'px-3 py-2 text-sm text-text-primary',
                        'outline-none focus:border-accent/40 transition-colors',
                        'cursor-pointer cjk-spacing',
                      ].join(' ')}
                    >
                      <span className={selectedModel ? '' : 'text-text-tertiary'}>
                        {selectedModel
                          ? `${selectedModel.name}${selectedModel.tier === 'pro' ? '（旗舰）' : ''}${selectedModel.is_free ? ' · 免费' : ''}`
                          : '请选择模型'}
                      </span>
                      <ChevronDown
                        size={14}
                        className={`text-text-tertiary transition-transform duration-fast ${modelDropdownOpen ? 'rotate-180' : ''}`}
                      />
                    </button>
                  </div>
                  {/* 模型描述 */}
                  {selectedModel?.description && (
                    <p className="text-xs text-text-tertiary mt-1.5 leading-relaxed cjk-spacing">
                      {selectedModel.description}
                    </p>
                  )}
                </Field>
              )}
            </div>
          )}

          {/* API Key */}
          <Field label="API Key">
            <div className="relative">
              <input
                type={showKey ? 'text' : 'password'}
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                placeholder={
                  config?.api_key_set
                    ? `已设置 ${config.api_key_masked}（留空不改）`
                    : 'sk-...'
                }
                className="w-full bg-bg-primary border border-border-soft rounded-md px-3 py-2 pr-9 text-sm text-text-primary placeholder:text-text-tertiary outline-none focus:border-accent/40 transition-colors font-mono"
              />
              <button
                onClick={() => setShowKey(!showKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-text-tertiary hover:text-text-primary transition-colors"
                aria-label={showKey ? '隐藏' : '显示'}
              >
                {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
            {selectedPreset?.homepage && (
              <a
                href={selectedPreset.homepage}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 mt-1.5 text-xs text-accent hover:text-accent-hover transition-colors"
              >
                <span>获取 API Key</span>
                <ExternalLink size={11} strokeWidth={1.5} />
              </a>
            )}
          </Field>

          {/* 错误提示 */}
          {error && (
            <div className="rounded-lg bg-danger-soft/30 border border-danger/30 px-3.5 py-2.5 text-sm text-danger cjk-spacing">
              {error}
            </div>
          )}

          {/* 成功提示 */}
          {successMsg && (
            <div className="rounded-lg bg-accent-soft/30 border border-accent/30 px-3.5 py-2.5 text-sm text-accent cjk-spacing">
              {successMsg}
            </div>
          )}
        </div>

        {/* 能力下限警告条 */}
        <div className="px-5 py-2.5 border-t border-border-soft bg-warn-soft/10 flex items-start gap-2 shrink-0">
          <AlertTriangle
            size={13}
            className="text-warn shrink-0 mt-0.5"
            strokeWidth={2}
          />
          <p className="text-xs text-text-secondary leading-relaxed cjk-spacing">
            {MIN_RECOMMENDED_WARNING}
          </p>
        </div>

        {/* 底部按钮 */}
        <div className="px-5 py-3.5 border-t border-border-soft flex gap-2.5 justify-end shrink-0">
          <button
            onClick={handleClose}
            className="px-4 py-1.5 rounded-md text-sm text-text-secondary border border-border-default hover:bg-bg-tertiary hover:text-text-primary transition-all duration-fast ease-out-soft"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !selectedPreset}
            className="px-4 py-1.5 rounded-md text-sm font-medium text-white bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed shadow-sm transition-all duration-fast ease-out-soft flex items-center gap-1.5"
          >
            {saving ? (
              <>
                <Loader2 size={13} className="animate-spin" />
                保存中
              </>
            ) : (
              '保存'
            )}
          </button>
        </div>
      </div>

      {/* v0.7.6: 模型下拉列表用 Portal 渲染到 body，脱离父容器 overflow 裁剪 */}
      {/* v0.8.26: data-dropdown-list 标记，供 window mousedown 监听器 closest() 识别 */}
      {modelDropdownOpen &&
        dropdownPos &&
        selectedPreset &&
        selectedPreset.id !== 'custom' &&
        createPortal(
          <div
            ref={modelDropdownListRef}
            data-dropdown-list
            className="bg-bg-secondary border border-border-default rounded-md shadow-popover overflow-hidden animate-fade-in"
            style={{
              position: 'fixed',
              top: dropdownPos.top,
              left: dropdownPos.left,
              width: dropdownPos.width,
              zIndex: 9999,
              animationDuration: '100ms',
            }}
            onMouseDown={e => e.stopPropagation()}
            onClick={e => e.stopPropagation()}
          >
            <div className="max-h-60 overflow-y-auto py-1">
              {selectedPreset.models.map(model => {
                const active = model.id === selectedModelId
                return (
                  <button
                    key={model.id}
                    type="button"
                    onMouseDown={e => e.stopPropagation()}
                    onClick={() => {
                      setSelectedModelId(model.id)
                      setModelDropdownOpen(false)
                    }}
                    className={[
                      'w-full flex items-center justify-between gap-2',
                      'px-3 py-2 text-left text-sm',
                      'transition-colors duration-fast',
                      active
                        ? 'bg-accent-soft text-accent'
                        : 'text-text-primary hover:bg-bg-tertiary',
                    ].join(' ')}
                  >
                    <span className="flex items-center gap-2 cjk-spacing">
                      <span>{model.name}</span>
                      {model.tier === 'pro' && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent-soft text-accent font-medium">
                          旗舰
                        </span>
                      )}
                      {model.is_free && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-info-soft text-info font-medium">
                          免费
                        </span>
                      )}
                    </span>
                    {active && <Check size={13} className="text-accent" />}
                  </button>
                )
              })}
            </div>
          </div>,
          document.body,
        )}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs text-text-tertiary mb-1.5 tracking-wider cjk-spacing">
        {label}
      </label>
      {children}
    </div>
  )
}
