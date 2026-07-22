/**
 * Lihua 狸花猫 - Tailwind 配置
 *
 * 设计语言：macOS Sequoia 暗色模式 + Lihua 品牌色
 * 设计原则：
 *   1. 不用纯黑（#000），用带轻微蓝调的深灰，模拟 macOS 暗色模式「活性背景」
 *   2. 中性色走 9 阶灰阶，层次清晰
 *   3. 品牌色保留绿，但用 macOS System Green #30D158（比 emerald 更亮更现代）
 *   4. 边框用 rgba 三阶（soft/default/strong），而非一刀切 white/10
 *   5. 圆角分层级（6/10/14/18/24），而非一刀切 2xl
 *   6. 间距走 8 点栅格
 *   7. 字号略大于 Tailwind 默认（正文 15px，对标 macOS 系统正文）
 */

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // === 背景层（从深到浅，模拟毛玻璃层次）===
        bg: {
          DEFAULT: 'var(--bg-primary)',      // #1C1C1E 最深层（侧边栏底）
          primary: 'var(--bg-primary)',      // #1C1C1E
          secondary: 'var(--bg-secondary)',  // #2C2C2E 卡片层
          tertiary: 'var(--bg-tertiary)',    // #3A3A3C hover 层
          elevated: 'var(--bg-elevated)',    // #48484A 按下/选中层
          input: 'var(--bg-input)',          // 输入框底
          window: 'var(--bg-window)',        // 窗口毛玻璃底色
        },
        // === 文字（3 阶 + 2 辅助）===
        text: {
          DEFAULT: 'var(--text-primary)',    // #F5F5F7 主文字
          primary: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',// #AEAEB2 次要文字
          tertiary: 'var(--text-tertiary)',  // #636366 占位/禁用
          dim: 'var(--text-secondary)',      // 别名（兼容旧代码）
          muted: 'var(--text-tertiary)',     // 别名（兼容旧代码）
        },
        // === 品牌色（macOS System Green）===
        accent: {
          DEFAULT: 'var(--accent)',          // #30D158
          hover: 'var(--accent-hover)',      // #28B34A
          soft: 'var(--accent-soft)',        // rgba(48,209,88,0.18)
        },
        // === 功能色（macOS 系统色板）===
        danger: {
          DEFAULT: 'var(--color-red)',       // #FF453A
          soft: 'rgba(255, 69, 58, 0.18)',
        },
        warn: {
          DEFAULT: 'var(--color-orange)',    // #FF9F0A
          soft: 'rgba(255, 159, 10, 0.18)',
        },
        info: {
          DEFAULT: 'var(--color-blue)',      // #0A84FF
          soft: 'rgba(10, 132, 255, 0.18)',
        },
        purple: {
          DEFAULT: 'var(--color-purple)',    // #BF5AF2
        },
        // === 边框（三阶透明度）===
        border: {
          soft: 'var(--border-soft)',        // rgba(255,255,255,0.06)
          DEFAULT: 'var(--border-default)',  // rgba(255,255,255,0.10)
          strong: 'var(--border-strong)',    // rgba(255,255,255,0.18)
        },
      },
      fontFamily: {
        sans: [
          '"Source Han Sans SC"',
          '"思源黑体"',
          '"PingFang SC"',
          'system-ui',
          '-apple-system',
          'sans-serif',
        ],
        mono: ['"JetBrains Mono"', '"SF Mono"', '"Menlo"', 'monospace'],
        serif: ['"Source Han Serif SC"', '"思源宋体"', 'serif'],
      },
      fontSize: {
        // macOS 风格字号阶梯
        'xs': ['11px', { lineHeight: '1.4' }],
        'sm': ['13px', { lineHeight: '1.45' }],
        'base': ['15px', { lineHeight: '1.5' }],   // 主正文
        'lg': ['17px', { lineHeight: '1.4' }],     // 输入框、标题
        'xl': ['22px', { lineHeight: '1.3' }],     // 欢迎语
        '2xl': ['28px', { lineHeight: '1.25' }],
      },
      spacing: {
        // 8 点栅格
        '0.5': '2px',
        '1': '4px',
        '1.5': '6px',
        '2': '8px',
        '3': '12px',
        '4': '16px',
        '5': '20px',
        '6': '24px',
        '8': '32px',
        '10': '40px',
        '12': '48px',
      },
      borderRadius: {
        // 分层级圆角
        'sm': '6px',
        'md': '10px',
        'lg': '14px',
        'xl': '18px',
        '2xl': '24px',
      },
      boxShadow: {
        'window': '0 24px 80px rgba(0, 0, 0, 0.55), 0 8px 24px rgba(0, 0, 0, 0.4)',
        'card': '0 2px 8px rgba(0, 0, 0, 0.2)',
        'popover': '0 12px 40px rgba(0, 0, 0, 0.5)',
        'focus': '0 0 0 3px rgba(48, 209, 88, 0.35)',
        'inner-light': 'inset 0 1px 0 rgba(255, 255, 255, 0.06)',
      },
      transitionTimingFunction: {
        'out-soft': 'cubic-bezier(0.16, 1, 0.3, 1)',
        'in-out-soft': 'cubic-bezier(0.65, 0, 0.35, 1)',
        'spring': 'cubic-bezier(0.34, 1.56, 0.64, 1)',
      },
      transitionDuration: {
        'fast': '120ms',
        'base': '200ms',
        'slow': '320ms',
      },
      animation: {
        'fade-in': 'fade-in 200ms cubic-bezier(0.16, 1, 0.3, 1)',
        'fade-out': 'fade-out 150ms cubic-bezier(0.65, 0, 0.35, 1)',
        'slide-down': 'slide-down 280ms cubic-bezier(0.16, 1, 0.3, 1)',
        'slide-up': 'slide-up 240ms cubic-bezier(0.16, 1, 0.3, 1)',
        'slide-right': 'slide-right 240ms cubic-bezier(0.16, 1, 0.3, 1)',
        'scale-in': 'scale-in 200ms cubic-bezier(0.34, 1.56, 0.64, 1)',
        'pulse-soft': 'pulse-soft 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'shimmer': 'shimmer 2.5s linear infinite',
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'fade-out': {
          '0%': { opacity: '1' },
          '100%': { opacity: '0' },
        },
        'slide-down': {
          '0%': { opacity: '0', transform: 'translateY(-12px) scale(0.98)' },
          '100%': { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        'slide-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-right': {
          '0%': { opacity: '0', transform: 'translateX(-12px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        'scale-in': {
          '0%': { opacity: '0', transform: 'scale(0.96)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        'pulse-soft': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5' },
        },
        'shimmer': {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
    },
  },
  plugins: [],
}
