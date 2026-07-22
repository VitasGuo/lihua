/**
 * WelcomeScreen - 空状态欢迎屏
 *
 * 设计要点：
 *   - 居中布局，上下大留白（py-12）
 *   - 顶部：56px 狸花猫 logo（绿色描边，rounded-xl 18px 圆角）
 *   - 中间：思源宋体欢迎语（text-2xl 28px）+ 副标题（text-sm 灰色）
 *   - 底部：快捷动作卡片，2 列网格，max-w 480px（适配 720 窗口）
 *   - 整体使用 message-in 入场动画
 *   - 快捷动作带前缀图标（Sparkles），增强视觉层次
 *
 * v0.8.5 改造：LLM 未配置时显示醒目引导卡片
 *   - 检测 health.llm_available === false
 *   - 在快捷动作上方显示警告色引导卡片 + "配置模型"按钮
 *   - 新用户第一次打开应用就能看到清晰的引导，而不是技术性错误
 */

import { AlertCircle, Sparkles } from 'lucide-react'
import type { Health } from '../api'
import { LihuaLogo } from './LihuaLogo'

interface WelcomeScreenProps {
  onQuickAction: (text: string) => void
  /** v0.8.5: 传入 health 状态，用于检测 LLM 是否已配置 */
  health?: Health | null
  /** v0.8.5: 打开模型设置的回调 */
  onOpenModelSettings?: () => void
}

// 快捷动作（按使用频率排序，常用在前）
const QUICK_ACTIONS: { label: string; hint: string }[] = [
  { label: '装个思源黑体', hint: '安装字体' },
  { label: '切换到 fcitx5', hint: '输入法' },
  { label: '清一下垃圾', hint: '系统清理' },
  { label: '没声音了', hint: '故障排查' },
  { label: '电脑怎么这么卡啊', hint: '性能优化' },
  { label: '磁盘满了', hint: '空间清理' },
]

export function WelcomeScreen({ onQuickAction, health, onOpenModelSettings }: WelcomeScreenProps) {
  // v0.8.5: 检测 LLM 是否已配置
  const llmNotConfigured = health !== null && health !== undefined && !health.llm_available

  return (
    <div className="flex-1 h-full flex flex-col items-center justify-center px-10 py-10 message-in overflow-y-auto">
      {/* Logo */}
      <div className="mb-5">
        <div className="w-14 h-14 rounded-xl flex items-center justify-center bg-accent-soft border border-accent/25 shadow-sm">
          <LihuaLogo className="text-accent" size={30} />
        </div>
      </div>

      {/* 欢迎语 */}
      <h1 className="font-serif text-2xl text-text-primary tracking-wide mb-1.5">
        想得多，做得少，事半功倍
      </h1>
      <p className="text-sm text-text-secondary mb-8 text-center max-w-xs leading-relaxed cjk-spacing">
        AI 系统管家，让普通用户也能省心用 Linux
      </p>

      {/* v0.8.5: LLM 未配置时的醒目引导卡片 */}
      {llmNotConfigured && (
        <div className="w-full max-w-[480px] mb-4 px-4 py-3 rounded-xl bg-warn/10 border border-warn/30 flex items-start gap-3">
          <AlertCircle size={18} className="text-warn shrink-0 mt-0.5" strokeWidth={2} />
          <div className="flex-1">
            <div className="text-sm text-text-primary font-medium cjk-spacing">
              需要先配置 AI 模型
            </div>
            <div className="text-xs text-text-secondary mt-0.5 leading-relaxed cjk-spacing">
              Lihua 需要 AI 模型才能理解你的需求并执行任务。点击下方按钮配置模型后即可开始使用。
            </div>
            {onOpenModelSettings && (
              <button
                onClick={onOpenModelSettings}
                className={[
                  'mt-2 px-3 py-1.5 rounded-lg',
                  'text-xs font-medium text-white',
                  'bg-accent hover:bg-accent-hover',
                  'transition-all duration-fast ease-out-soft',
                  'cjk-spacing',
                ].join(' ')}
              >
                配置模型
              </button>
            )}
          </div>
        </div>
      )}

      {/* 快捷动作 */}
      <div className="w-full max-w-[480px]">
        <div className="flex items-center gap-1.5 text-xs text-text-tertiary mb-2.5 px-1 tracking-wider">
          <Sparkles size={11} strokeWidth={1.5} />
          <span>试试这些</span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {QUICK_ACTIONS.map(action => (
            <button
              key={action.label}
              onClick={() => onQuickAction(action.label)}
              className={[
                'text-left',
                'px-4 py-2.5',
                'rounded-lg',
                'bg-bg-secondary/40 hover:bg-bg-tertiary/70',
                'border border-border-soft hover:border-accent/40',
                'text-sm text-text-secondary hover:text-text-primary',
                'transition-all duration-base ease-out-soft',
                'hover:-translate-y-0.5 hover:shadow-md',
                'active:translate-y-0 active:scale-[0.98]',
                'cjk-spacing',
                'group',
              ].join(' ')}
            >
              <div className="text-text-primary/90 group-hover:text-text-primary">
                {action.label}
              </div>
              <div className="text-xs text-text-tertiary mt-0.5">{action.hint}</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
