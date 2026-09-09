import { useEffect, useRef, useState } from 'react'

/**
 * 回声室指数「信号涟漪环」(Echo Signal Ring)
 * - 用品牌符号「感知涟漪」的闭合度隐喻茧房强度：弧越闭合茧房越强。
 * - 动效：雷达扫描线（旋转）+ 涟漪呼吸 + 数字 count-up + 值弧 dash 过渡。
 * - 纯 SVG 视觉资产，支持加载态与无数据态。
 */
export default function EchoSignal({ score, loading, size = 168 }) {
  const R = 76
  const C = 2 * Math.PI * R
  const ARC = 0.75
  const dash = C * ARC

  const v = typeof score === 'number' ? Math.max(0, Math.min(1, score)) : null

  // 数字 count-up
  const [disp, setDisp] = useState(v == null ? 0 : v)
  const fromRef = useRef(v == null ? 0 : v)
  useEffect(() => {
    const reduce = typeof window !== 'undefined'
      && window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches
    const to = v == null ? 0 : v
    if (reduce) { fromRef.current = to; setDisp(to); return }
    const from = fromRef.current
    if (from === to) return
    const start = performance.now()
    let raf = 0
    const tick = (now) => {
      const t = Math.min(1, (now - start) / 1100)
      const eased = 1 - Math.pow(1 - t, 3)
      const cur = from + (to - from) * eased
      setDisp(cur)
      if (t < 1) raf = requestAnimationFrame(tick)
      else fromRef.current = to
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [v])

  const tone =
    v == null
      ? 'var(--text-3)'
      : v >= 0.5
        ? 'var(--danger)'
        : v >= 0.25
          ? 'var(--warning)'
          : 'var(--success)'
  const label =
    v == null ? '待评估' : v >= 0.5 ? '强茧房' : v >= 0.25 ? '中度茧房' : '信号开放'
  const pct = v == null ? '—' : (disp * 100).toFixed(1)

  return (
    <div className="echo-signal" style={{ '--echo-tone': tone, width: size, height: size }}>
      <svg viewBox="0 0 200 200" width="100%" height="100%" aria-hidden="true">
        {/* 背景轨道弧 */}
        <circle
          cx="100" cy="100" r={R}
          fill="none" stroke="var(--border)" strokeWidth="14" strokeLinecap="round"
          strokeDasharray={`${dash} ${C}`} transform="rotate(135 100 100)"
        />
        {/* 前景值弧 */}
        {v != null && (
          <circle
            cx="100" cy="100" r={R}
            fill="none" stroke="var(--echo-tone)" strokeWidth="14" strokeLinecap="round"
            strokeDasharray={`${dash * v} ${C}`} transform="rotate(135 100 100)"
            className="echo-signal__value"
          />
        )}
        {/* 雷达扫描线（旋转） */}
        <g className="echo-signal__sweep">
          <line x1="100" y1="100" x2="100" y2={100 - R} stroke="var(--echo-tone)" strokeWidth="1.4" strokeLinecap="round" opacity="0.4" />
          <circle cx="100" cy={100 - R} r="2.6" fill="var(--echo-tone)" opacity="0.85" />
        </g>
        {/* 信号涟漪（装饰） */}
        <circle cx="100" cy="100" r={R - 22} fill="none" stroke="var(--accent)" strokeWidth="1.4" strokeLinecap="round" opacity="0.35" strokeDasharray="60 12" transform="rotate(20 100 100)" className="echo-signal__ripple" />
        <circle cx="100" cy="100" r={R + 20} fill="none" stroke="var(--accent)" strokeWidth="1" strokeLinecap="round" opacity="0.2" strokeDasharray="44 18" transform="rotate(-8 100 100)" className="echo-signal__ripple echo-signal__ripple--slow" />
        {/* 中心数字 */}
        <text x="100" y="96" textAnchor="middle" className="echo-signal__num" fill="var(--text-1)">
          {loading ? '· · ·' : pct}
        </text>
        <text x="100" y="114" textAnchor="middle" className="echo-signal__unit" fill="var(--text-3)">
          {loading ? '' : '%'}
        </text>
      </svg>
      <div className="echo-signal__label" style={{ color: tone }}>
        {loading ? '计算中' : label}
      </div>
    </div>
  )
}
