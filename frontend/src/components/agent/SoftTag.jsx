import { useDarkMode } from '../../theme'

/**
 * 软底标签：强调色文字 + 同色 12% 底 + 细描边。
 * 自动随主题选择 light/dark 色，替代 antd 大色块 Tag。
 * color / colorDark 均为 CSS 色值；只传 color 时两端主题共用。
 */
export default function SoftTag({ color, colorDark, children, style }) {
  const dark = useDarkMode()
  const hex = dark ? colorDark || color : color
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '1px 8px',
        borderRadius: 6,
        fontSize: 12,
        lineHeight: '20px',
        whiteSpace: 'nowrap',
        color: hex,
        background: `color-mix(in srgb, ${hex} 12%, transparent)`,
        border: `1px solid color-mix(in srgb, ${hex} 30%, transparent)`,
        ...style,
      }}
    >
      {children}
    </span>
  )
}
