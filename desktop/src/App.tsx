/**
 * App - 主浮窗应用
 *
 * v0.7.0 重构：
 *   - macOS Sequoia 暗色风 + 毛玻璃层次
 *   - 默认走 LLM Agent 模式（后端 /api/chat 已支持）
 *   - 工具调用过程默认折叠（ToolCallCard）
 *   - 灰名单确认弹窗用 Sheet 风格（从顶部滑下）
 *   - 去掉浮动小球相关逻辑
 *   - 去掉 intent.source/confidence/params 工程师视角信息
 *
 * 布局：
 *   ┌─ TitleBar (48px) ─────────────────────┐
 *   ├─ MessageList (flex-1) ──┬─ Sidebar ──┤
 *   │                         │   (280px)   │
 *   ├─ InputBar (auto) ───────┴─────────────┤
 *   └─ StatusBar (28px) ────────────────────┘
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { invoke } from '@tauri-apps/api/core'
import { getVersion } from '@tauri-apps/api/app'
import { listen } from '@tauri-apps/api/event'
import type { Health, Skill, ChatResponse, HistoryEntry, ChatHistoryEntry } from './api'
import { api } from './api'
import type { Message, ConfirmPending } from './types'

import { TitleBar } from './components/TitleBar'
import { MessageList } from './components/MessageList'
import { InputBar } from './components/InputBar'
import { StatusBar } from './components/StatusBar'
import { Sidebar } from './components/Sidebar'
import { WelcomeScreen } from './components/WelcomeScreen'
import { ConfirmSheet } from './components/ConfirmSheet'
import { ModelSheet } from './components/ModelSheet'
import { LogoSheet } from './components/LogoSheet'
import { LogSheet } from './components/LogSheet'
import { AuditSheet } from './components/AuditSheet'
import { MemorySheet } from './components/MemorySheet'  // v0.8.20: 记忆管理
import { HistorySheet } from './components/HistorySheet'  // v0.8.20: 历史对话

// localStorage key（与 LogoSheet 同步）
const LOGO_STORAGE_KEY = 'lihua:custom-logo'

function App() {
  // v0.8.20: session_id 用于 episode 聚合 + localStorage 分键持久化
  // 首次启动或 localStorage 无当前 session 时生成新 id；有则恢复上次未结束的 session
  const [sessionId, setSessionId] = useState<string>(() => {
    try {
      const saved = localStorage.getItem('lihua:current-session')
      if (saved && localStorage.getItem(`lihua:messages:${saved}`)) {
        return saved
      }
    } catch {}
    const newId = `s_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    try { localStorage.setItem('lihua:current-session', newId) } catch {}
    return newId
  })
  // v0.8.20: messages 启动时从 localStorage 按 session_id 恢复（避免重启丢失上下文）
  const [messages, setMessages] = useState<Message[]>(() => {
    try {
      const sid = localStorage.getItem('lihua:current-session')
      if (sid) {
        const saved = localStorage.getItem(`lihua:messages:${sid}`)
        if (saved) return JSON.parse(saved) as Message[]
      }
    } catch {}
    return []
  })
  const [input, setInput] = useState('')
  const [health, setHealth] = useState<Health | null>(null)
  const [skills, setSkills] = useState<Skill[]>([])
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [confirmPending, setConfirmPending] = useState<ConfirmPending | null>(null)
  const [modelSheetOpen, setModelSheetOpen] = useState(false)
  const [logoSheetOpen, setLogoSheetOpen] = useState(false)
  const [logSheetOpen, setLogSheetOpen] = useState(false)
  const [auditSheetOpen, setAuditSheetOpen] = useState(false)
  const [memorySheetOpen, setMemorySheetOpen] = useState(false)  // v0.8.20: 记忆管理
  const [historySheetOpen, setHistorySheetOpen] = useState(false)  // v0.8.20: 历史对话
  // v0.7.15: 后端版本不匹配警告（后端没重启时提示用户）
  const [versionMismatch, setVersionMismatch] = useState(false)
  // v0.8.19: 窗口是否最大化（用于 TitleBar 最大化/还原图标切换）
  const [isMaximized, setIsMaximized] = useState(false)
  // 自定义 logo（从 localStorage 读取，支持用户上传图片）
  const [customLogoSrc, setCustomLogoSrc] = useState<string | null>(() => {
    try {
      return localStorage.getItem(LOGO_STORAGE_KEY)
    } catch {
      return null
    }
  })

  // messages ref：让 send 回调能读到最新 messages 构建 history，避免 stale closure
  const messagesRef = useRef<Message[]>([])
  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  // v0.8.20: messages 按 session_id 持久化到 localStorage（分键存储避免单键超 5MB 配额）
  useEffect(() => {
    try {
      localStorage.setItem(`lihua:messages:${sessionId}`, JSON.stringify(messages))
    } catch {
      // 配额超限时只保留最近 20 条重试
      try {
        const trimmed = messages.slice(-20)
        localStorage.setItem(`lihua:messages:${sessionId}`, JSON.stringify(trimmed))
      } catch {}
    }
  }, [messages, sessionId])

  // v0.8.20: SSE 重试计数（中断后自动重试 1 次，避免无限重试）
  const retryCountRef = useRef(0)

  // 初始化：轮询健康状态直到后端就绪（v0.8.23：解决启动时后端未就绪导致 Connection refused）
  useEffect(() => {
    let cancelled = false
    const pollHealth = async () => {
      for (let i = 0; i < 30; i++) {  // 最多 15 秒（30 × 500ms）
        if (cancelled) return
        try {
          const h = await api.health()
          if (cancelled) return
          setHealth(h)
          api.skills().then(setSkills).catch(() => {})
          api.history().then(r => setHistory(r.entries)).catch(() => {})
          return
        } catch {
          await new Promise(r => setTimeout(r, 500))
        }
      }
    }
    pollHealth()
    return () => { cancelled = true }
  }, [])

  // v0.7.15: 检查前后端版本号是否匹配（后端没重启时提示用户）
  useEffect(() => {
    let cancelled = false
    Promise.all([getVersion(), api.health()]).then(([feVersion, h]) => {
      if (cancelled) return
      // 后端 version 格式 "0.7.14a0"，前端 getVersion() 格式 "0.7.14"
      // 对比时去掉 alpha 后缀（a0/b0/rc0 等）
      const beVersion = h.version.replace(/[a-z]\d*$/, '')
      if (feVersion !== beVersion) {
        setVersionMismatch(true)
        console.warn(`版本不匹配：前端 ${feVersion} / 后端 ${h.version}（后端需重启）`)
      }
    }).catch(() => {})
    return () => { cancelled = true }
  }, [health?.version])

  // 监听后端就绪事件 + 托盘菜单事件
  useEffect(() => {
    const backendReadyP = listen('backend-ready', () => {
      api.health().then(setHealth).catch(() => {})
      api.skills().then(setSkills).catch(() => {})
    })
    const newChatP = listen('new-chat', () => {
      // v0.8.20: 生成新 session_id 并同步到 localStorage，清空 messages
      const newId = `s_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
      try { localStorage.setItem('lihua:current-session', newId) } catch {}
      setSessionId(newId)
      setMessages([])
      setInput('')
    })
    const openHistoryP = listen('open-history', () => {
      setSidebarOpen(true)
      api.history().then(r => setHistory(r.entries)).catch(() => {})
    })
    // v0.7.4: 监听托盘「设置」菜单项 → 打开 ModelSheet
    const openSettingsP = listen('open-settings', () => {
      setModelSheetOpen(true)
    })
    // v0.7.10: 监听托盘「审计日志」菜单项 → 打开独立 AuditSheet
    const openAuditP = listen('open-audit', () => {
      setAuditSheetOpen(true)
    })
    // v0.8.20: 监听托盘「记忆管理」菜单项 → 打开 MemorySheet
    const openMemoryP = listen('open-memory', () => {
      setMemorySheetOpen(true)
    })

    return () => {
      backendReadyP.then(fn => fn())
      newChatP.then(fn => fn())
      openHistoryP.then(fn => fn())
      openSettingsP.then(fn => fn())
      openAuditP.then(fn => fn())
      openMemoryP.then(fn => fn())
    }
  }, [])

  // v0.8.19: 监听窗口最大化状态变化（用于 TitleBar 最大化/还原图标切换）
  // 动态 import 避免非 Tauri 环境报错
  useEffect(() => {
    let unlistenFn: (() => void) | null = null
    import('@tauri-apps/api/window')
      .then(({ getCurrentWindow }) => {
        const win = getCurrentWindow()
        win.isMaximized().then(setIsMaximized).catch(() => {})
        win.onResized(() => {
          win.isMaximized().then(setIsMaximized).catch(() => {})
        }).then(fn => {
          unlistenFn = fn
        })
      })
      .catch(() => {
        // 非 Tauri 环境（如浏览器开发）忽略
      })
    return () => {
      unlistenFn?.()
    }
  }, [])

  // 发送消息（v0.7.9：流式 SSE，实时显示 Agent 思考和工具调用）
  const send = useCallback(
    async (text: string, autoConfirm = false) => {
      if (!text.trim() || loading) return
      // v0.8.20: 每次发送重置重试计数
      retryCountRef.current = 0

      // v0.8.23: 后端未就绪时（health === null）不调 chatStream，避免 Connection refused
      if (!health) {
        const userText = text.trim()
        setInput('')
        setMessages(prev => [
          ...prev,
          { id: Date.now(), role: 'user', content: userText },
          {
            id: Date.now() + 1,
            role: 'assistant',
            content: '',
            error: '后端正在启动中，请稍等几秒后重试...',
            isAgent: true,
          },
        ])
        return
      }

      // v0.8.5: LLM 未配置时不调用后端，直接显示友好提示
      // 避免用户看到技术性错误（如 502/连接失败），引导去配置模型
      if (!health.llm_available) {
        const userText = text.trim()
        setInput('')
        const userMsgId = Date.now()
        const assistantMsgId = Date.now() + 1
        setMessages(prev => [
          ...prev,
          { id: userMsgId, role: 'user', content: userText },
          {
            id: assistantMsgId,
            role: 'assistant',
            content: '',
            error: '还没配置 AI 模型哦～请先点击底部的"配置模型"按钮设置模型后再开始对话。',
          },
        ])
        return
      }

      const userText = text.trim()
      setInput('')

      // 从已有消息构建对话历史（多轮上下文）
      // v0.8.23: 优化串台问题——缩短到 10 条 + 过滤 UI 边框字符 + 过滤过长 assistant 消息
      //   旧逻辑取最近 20 条所有消息，话题切换时旧消息干扰 LLM 注意力，且用户粘贴旧 UI 输出会混入
      const UI_BORDER_CHARS = /[╭╰╮╯│┃━┅]/
      const history: ChatHistoryEntry[] = messagesRef.current
        .filter(m => !m.error && (m.role === 'user' || (m.role === 'assistant' && (m.content || m.text))))
        .map(m => ({
          role: m.role,
          content: m.content || m.text || '',
        }))
        .filter(m => {
          if (!m.content) return false
          // 过滤包含 UI 边框字符的消息（用户粘贴了旧 UI 输出，非真实对话）
          if (UI_BORDER_CHARS.test(m.content)) return false
          // 过滤过长的 assistant 消息（>800 字的诊断报告进 history 会干扰 LLM 注意力）
          if (m.role === 'assistant' && m.content.length > 800) return false
          return true
        })
        .slice(-10)  // v0.8.23: 从 20 条缩到 10 条，减少旧话题干扰

      const userMsgId = Date.now()
      const assistantMsgId = Date.now() + 1
      setMessages(prev => [
        ...prev,
        { id: userMsgId, role: 'user', content: userText },
        {
          id: assistantMsgId,
          role: 'assistant',
          content: '',
          loading: true,
          streaming: true,
          isAgent: true,
        },
      ])
      setLoading(true)

      // 更新最后一条消息的 helper
      const updateLast = (updater: (m: Message) => Message) => {
        setMessages(prev => {
          const copy = [...prev]
          copy[copy.length - 1] = updater(copy[copy.length - 1])
          return copy
        })
      }

      // v0.8.20: chatStream 消费抽成内联函数，支持 SSE 中断后重试（不重复添加 user message）
      const runStream = async () => {
        for await (const event of api.chatStream(userText, history, autoConfirm, false, sessionId)) {
          switch (event.type) {
            case 'start':
              // Agent 已启动
              break

            case 'iteration':
              updateLast(m => ({ ...m, iteration: event.n }))
              break

            case 'text':
              updateLast(m => ({ ...m, content: event.content, text: event.content }))
              break

            case 'reasoning':
              // v0.8.20: LLM 思考链（reasoning_content），实时更新到 message
              updateLast(m => ({ ...m, reasoning: event.content }))
              break

            case 'tool_call_start':
              updateLast(m => ({
                ...m,
                tool_calls: [
                  ...(m.tool_calls || []),
                  {
                    tool_name: event.name,
                    arguments: event.arguments,
                    success: false,
                    result_message: '',
                  },
                ],
                currentTool: event.name,
              }))
              break

            case 'tool_call_end': {
              // 更新最后一个 tool_call 的结果
              updateLast(m => {
                const tcs = [...(m.tool_calls || [])]
                const lastIdx = tcs.length - 1
                if (lastIdx >= 0) {
                  tcs[lastIdx] = {
                    ...tcs[lastIdx],
                    success: event.success,
                    result_message: event.message || '',
                    error: event.error,
                    details: event.details,
                  }
                }
                return { ...m, tool_calls: tcs, currentTool: undefined }
              })
              break
            }

            case 'needs_confirm': {
              // v0.7.13：Agent 遇到灰名单操作，弹 ConfirmSheet
              // 后端 confirm_cb 阻塞等待 /api/chat/confirm 响应
              // v0.8.4：传递结构化字段（toolName / intent / code / commandText）让 ConfirmSheet 富文本展示
              setConfirmPending({
                confirmId: event.id,
                confirmMessage: event.message,
                toolName: event.tool_name,
                intent: event.intent,
                code: event.code,
                commandText: event.command_text,
              })
              break
            }

            case 'confirm_timeout': {
              // v0.8.29: confirm 超时后后端推送此事件，关闭旧 ConfirmSheet
              //   避免 ConfirmSheet 一直显示已失效的确认请求
              setConfirmPending(null)
              break
            }

            case 'done':
              updateLast(m => ({
                ...m,
                loading: false,
                streaming: false,
                content: event.text || (event.success ? '完成' : '未能完成'),
                text: event.text,
                // v0.8.20: 保留已收到的 reasoning（done 事件不带 reasoning，不应覆盖）
                reasoning: m.reasoning,
                tool_calls: event.tool_calls?.map(tc => ({
                  tool_name: tc.name,
                  arguments: tc.arguments,
                  success: tc.success,
                  result_message: tc.message,
                  error: tc.error,
                  details: tc.details,
                })) || m.tool_calls,
                iteration: undefined,
                currentTool: undefined,
                error: event.error,
                isAgent: true,
              }))
              break

            case 'error':
              updateLast(m => ({
                ...m,
                loading: false,
                streaming: false,
                content: '',
                error: event.message,
                currentTool: undefined,
              }))
              break
          }
        }

        // v0.7.13：旧的"灰名单被拒绝 → 弹确认框"兜底已删除
        // Agent 模式现在完全由 needs_confirm 事件触发交互式 confirm
        // 规则模式（chatRule）仍用旧式 setConfirmPending（在 _chat_via_rule 路径里）

        // 刷新历史和健康状态
        api.history().then(r => setHistory(r.entries)).catch(() => {})
        api.health().then(setHealth).catch(() => {})
      }

      try {
        await runStream()
      } catch (e) {
        // v0.8.9: SSE 流断开时检测后端是否在重启（self_restart 会导致后端短暂不可用）
        // v0.8.20: 改进——非 LLM 错误时先自动重试 1 次（显示"🔄 正在重连..."），重试失败再走 3 秒检测
        const errMsg = e instanceof Error ? e.message : String(e)

        // v0.8.20: SSE 中断自动重试 1 次（非 LLM 错误且未重试过）
        if (retryCountRef.current < 1 && !errMsg.includes('LLM 调用失败')) {
          retryCountRef.current++
          updateLast(m => ({
            ...m,
            loading: true,
            streaming: true,
            content: '',
            error: '🔄 正在重连...',
            currentTool: undefined,
          }))
          await new Promise(r => setTimeout(r, 1500))
          try {
            // 重试前清掉重连提示
            updateLast(m => ({ ...m, error: undefined }))
            await runStream()
            setLoading(false)
            return  // 重试成功
          } catch {
            // 重试也失败，继续走下面的 3 秒检测逻辑
          }
        }

        // 原 3 秒后端检测逻辑（重试失败 / LLM 错误 / 已重试过）
        updateLast(m => ({
          ...m,
          loading: false,
          streaming: false,
          content: '',
          error: `连接中断（可能是后端重启中），3 秒后自动检测恢复...`,
          currentTool: undefined,
        }))
        setTimeout(() => {
          api.health().then(h => {
            setHealth(h)
            updateLast(m => ({
              ...m,
              loading: false,
              streaming: false,
              error: undefined,
              content: '✅ 后端已重启恢复，可以继续对话了。',
              currentTool: undefined,
            }))
          }).catch(() => {
            // 后端还没恢复，显示原始错误
            updateLast(m => ({
              ...m,
              loading: false,
              streaming: false,
              content: '',
              error: `连接失败：${errMsg}。如果刚执行了 self_restart，请等几秒后重试。`,
              currentTool: undefined,
            }))
          })
        }, 3000)
      }
      setLoading(false)
    },
    [loading, health, sessionId],
  )

  const handleConfirm = async (confirmed: boolean) => {
    if (!confirmPending) return
    // v0.7.13：Agent 模式（有 confirmId）→ 调 /api/chat/confirm
    //          规则模式（无 confirmId）→ 重新发送 message 带 auto_confirm=true
    if (confirmPending.confirmId) {
      const confirmId = confirmPending.confirmId
      setConfirmPending(null)
      console.log('[confirm] 用户点击', confirmed ? '确认' : '取消', 'confirmId=', confirmId)
      try {
        const result = await api.confirmChat(confirmId, confirmed)
        console.log('[confirm] 后端响应', result)
        // v0.8.5 修复：后端返回 ok:false（confirm_id 不匹配或已过期）→ 给用户错误反馈
        // 之前 bug：用户点击确认后弹窗消失，但后端没收到，60 秒后提示"用户取消"，用户困惑
        if (!result.ok) {
          console.warn('[confirm] 后端拒绝：', result.error)
          setMessages(prev => [...prev, {
            id: Date.now(),
            role: 'assistant',
            content: '',
            error: `确认未生效：${result.error || 'confirm_id 不匹配或已过期'}`,
            isAgent: true,
          }])
        }
      } catch (e) {
        console.error('[confirm] 调用失败:', e)
        // v0.8.5 修复：fetch 失败（网络/CSP/后端没启动）→ 给用户错误反馈
        const errMsg = e instanceof Error ? e.message : String(e)
        setMessages(prev => [...prev, {
          id: Date.now(),
          role: 'assistant',
          content: '',
          error: `确认请求失败：${errMsg}`,
          isAgent: true,
        }])
      }
    } else {
      const text = confirmPending.message || ''
      setConfirmPending(null)
      if (confirmed && text) {
        await send(text, true)
      }
    }
  }

  // 隐藏主窗口到托盘
  const hideToTray = useCallback(async () => {
    try {
      await invoke('cmd_hide_main')
    } catch (e) {
      console.error('隐藏窗口失败:', e)
    }
  }, [])

  // v0.8.19: 最小化主窗口
  const minimizeWindow = useCallback(async () => {
    try {
      await invoke('cmd_minimize')
    } catch (e) {
      console.error('最小化窗口失败:', e)
    }
  }, [])

  // v0.8.19: 切换最大化/还原
  const toggleMaximize = useCallback(async () => {
    try {
      await invoke('cmd_toggle_maximize')
    } catch (e) {
      console.error('切换最大化失败:', e)
    }
  }, [])

  // v0.8.19: 新会话（清空当前对话 + 输入框）
  // v0.8.20: 生成新 session_id 并同步到 localStorage
  const handleNewChat = useCallback(() => {
    const newId = `s_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    try { localStorage.setItem('lihua:current-session', newId) } catch {}
    setSessionId(newId)
    setMessages([])
    setInput('')
  }, [])

  // Esc 键：有确认弹窗→取消；无→隐藏窗口
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (confirmPending) {
          handleConfirm(false)
        } else {
          hideToTray()
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [confirmPending, hideToTray])

  // 待确认的消息列表
  // v0.7.13：Agent 模式用 confirmMessage，规则模式用 response.result.steps
  const confirmMessages: string[] = confirmPending
    ? (confirmPending.confirmMessage
        ? [confirmPending.confirmMessage]
        : (confirmPending.response?.result?.steps
            ?.filter(s => s.needs_confirm)
            .map(s => s.confirm_message)
            .filter((m): m is string => Boolean(m)) || []))
    : []

  return (
    // v0.7.5: 去掉外层 p-3，让 window-glass 占满整个窗口
    //   Wayland 下窗口本身是矩形不透明，p-3 留白会显示为黑色矩形破坏圆角
    //   让 window-glass 占满窗口后，rounded-2xl 圆角直接贴窗口边缘
    //   vignette 内阴影跟随 border-radius 裁剪，视觉上圆角内是精致的
    //   圆角外区域：用 CSS mask-image 让 .window-glass 圆角外完全不渲染
    //   配合窗口 transparent:true，让圆角外的黑色也被裁掉（Wayland 不完全生效，但 X11 会生效）
    <div className="h-screen w-full window-outer">
      <div className="window-appear window-glass w-full h-full flex flex-col overflow-hidden">
        <TitleBar
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
          onHide={hideToTray}
          onNewChat={handleNewChat}
          onMinimize={minimizeWindow}
          onToggleMaximize={toggleMaximize}
          isMaximized={isMaximized}
          customLogoSrc={customLogoSrc}
          onLogoClick={() => setLogoSheetOpen(true)}
        />

        <div className="flex-1 flex overflow-hidden">
          {messages.length === 0 ? (
            <WelcomeScreen
              onQuickAction={s => send(s)}
              health={health}
              onOpenModelSettings={() => setModelSheetOpen(true)}
            />
          ) : (
            <MessageList messages={messages} />
          )}

          {/* v0.7.15: 后端版本不匹配警告 */}
          {versionMismatch && (
            <div className="absolute top-2 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-lg bg-amber-500/90 text-white text-xs shadow-lg backdrop-blur-sm flex items-center gap-2 animate-in fade-in slide-in-from-top-2 duration-300">
              <span>⚠️</span>
              <span>后端服务版本不匹配，请重启应用以加载新功能</span>
              <button
                onClick={() => setVersionMismatch(false)}
                className="ml-2 hover:bg-white/20 rounded px-1.5 py-0.5 transition-colors"
              >
                ✕
              </button>
            </div>
          )}

          <Sidebar
            open={sidebarOpen}
            skills={skills}
            history={history}
            onRefreshHistory={() =>
              api.history().then(r => setHistory(r.entries)).catch(() => {})
            }
            onOpenHistorySheet={() => setHistorySheetOpen(true)}
          />
        </div>

        <InputBar
          value={input}
          onChange={setInput}
          onSend={() => send(input)}
          loading={loading}
        />

        <StatusBar
          health={health}
          showEscHint={Boolean(confirmPending)}
          onOpenModelSettings={() => setModelSheetOpen(true)}
          onOpenLog={() => setLogSheetOpen(true)}
          onOpenAudit={() => setAuditSheetOpen(true)}
        />
      </div>

      {confirmPending && (
        <ConfirmSheet
          messages={confirmMessages}
          toolName={confirmPending.toolName}
          intent={confirmPending.intent}
          code={confirmPending.code}
          commandText={confirmPending.commandText}
          onConfirm={() => handleConfirm(true)}
          onCancel={() => handleConfirm(false)}
        />
      )}

      <ModelSheet
        open={modelSheetOpen}
        onClose={() => setModelSheetOpen(false)}
        onSaved={() => {
          // 保存后刷新 health 显示新模型
          api.health().then(setHealth).catch(() => {})
        }}
      />

      <LogoSheet
        open={logoSheetOpen}
        onClose={() => setLogoSheetOpen(false)}
        customSrc={customLogoSrc}
        onChange={src => setCustomLogoSrc(src)}
      />

      <LogSheet
        open={logSheetOpen}
        onClose={() => setLogSheetOpen(false)}
      />

      <AuditSheet
        open={auditSheetOpen}
        onClose={() => setAuditSheetOpen(false)}
      />

      {/* v0.8.20: 记忆管理（托盘菜单"记忆管理"打开）+ 历史对话（只读查看） */}
      <MemorySheet
        open={memorySheetOpen}
        onClose={() => setMemorySheetOpen(false)}
        onOpenHistorySheet={() => {
          setMemorySheetOpen(false)
          setHistorySheetOpen(true)
        }}
      />
      <HistorySheet
        open={historySheetOpen}
        onClose={() => setHistorySheetOpen(false)}
      />
    </div>
  )
}

export default App
