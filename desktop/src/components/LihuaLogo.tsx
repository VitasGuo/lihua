/**
 * 狸花猫 Logo（v0.7.4 emoji 版）
 *
 * 设计理念（v0.7.4 教训）：
 *   - 用户原话「狸花猫的图标甚至不如第一版的 emoji」
 *   - v0.7.0-v0.7.3 自绘 SVG 失败 3 次（几何猫头 → 盾形脸 → 圆润版）
 *   - v0.7.4 放弃自绘，用系统 emoji 🐱（每家平台都有成熟设计）
 *   - 同时支持用户自定义图片（base64 存 localStorage）
 *
 * 渲染优先级：
 *   1. customSrc（用户上传的图片 URL，base64 或 blob）
 *   2. 默认 emoji 🐱（用 system emoji 字体渲染，跟随主题色）
 *
 * 使用方式：
 *   <LihuaLogo size={18} />                              // 默认 emoji
 *   <LihuaLogo size={18} customSrc="data:..." />         // 自定义图片
 *   <LihuaLogo size={18} onClick={...} />                // 可点击
 */

interface LihuaLogoProps {
  size?: number
  customSrc?: string | null
  className?: string
  onClick?: () => void
}

// 默认 emoji（系统字体渲染，跟随系统主题）
const DEFAULT_EMOJI = '🐱'

export function LihuaLogo({
  size = 18,
  customSrc,
  className = '',
  onClick,
}: LihuaLogoProps) {
  // 自定义图片：用 <img> 渲染
  if (customSrc) {
    return (
      <img
        src={customSrc}
        alt="狸花猫"
        width={size}
        height={size}
        onClick={onClick}
        className={`object-contain select-none ${onClick ? 'cursor-pointer' : ''} ${className}`}
        style={{ width: size, height: size }}
        draggable={false}
      />
    )
  }

  // 默认 emoji：用 <span> 渲染（系统 emoji 字体）
  return (
    <span
      onClick={onClick}
      aria-label="狸花猫"
      role={onClick ? 'button' : undefined}
      className={[
        'inline-flex items-center justify-center leading-none select-none',
        onClick ? 'cursor-pointer' : '',
        className,
      ].join(' ')}
      style={{
        fontSize: `${size}px`,
        width: size,
        height: size,
        lineHeight: 1,
      }}
    >
      {DEFAULT_EMOJI}
    </span>
  )
}
