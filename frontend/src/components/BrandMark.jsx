/**
 * 品牌符号「感知涟漪」(Signal Ripple)
 * - 中心实心感知点 + 两道向上扩散、各留错位开口的同心弧
 * - 寓意：捕捉舆论信号、穿透信息茧房（未闭合的弧 = 持续传播、开放洞察）
 * - 单一颜色（继承 currentColor），深浅色由承载方反色方块统一控制
 */
export default function BrandMark({ size = 18, strokeWidth = 2, className }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <circle cx="12" cy="12" r="2" fill="currentColor" />
      <path
        d="M 17.2 12 A 5.2 5.2 0 1 1 12 6.8"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
      />
      <path
        d="M 12 3.4 A 8.6 8.6 0 1 1 3.4 12"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        opacity="0.55"
      />
    </svg>
  )
}
