import { MorphIcon } from 'morphicons/react'

/**
 * 分析台唯一图标出口。
 *
 * 图标数据来自 `lucide`（数据包，非组件包），形变由 morphicons 完成：
 * 两个图形之间的旋转由数学推导，不需要手工声明 rotate，也不需要
 * AnimatePresence / from-to 配对。改 icon 属性即触发形变。
 *
 * 替代原先的 @ant-design/icons 与内联 SVG 图标，使两端视觉语言一致。
 */
export default function MorphGlyph({
  icon,
  size = 18,
  strokeWidth = 2,
  className,
  style,
  ...rest
}) {
  return (
    <MorphIcon
      icon={icon}
      size={size}
      strokeWidth={strokeWidth}
      className={className}
      style={style}
      reducedMotion="user"
      {...rest}
    />
  )
}
