import { useEffect, useRef, useState } from 'react'
import { LIEFLAT } from './lieflatTheme'

/** F11 Tick Gauge：用 100 根刻度编码回声室指数。 */
export default function EchoSignal({ score, loading, size = 190 }) {
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

  const label =
    v == null ? '待评估' : v >= 0.5 ? '强茧房' : v >= 0.25 ? '中度茧房' : '信号开放'
  const pct = v == null ? '-' : (disp * 100).toFixed(1)
  const goal = v == null ? 0 : Math.round(v * 100)
  const cx = 100
  const cy = 116
  const radius = 70
  const start = -195
  const sweep = 210
  const polar = (r, angle) => {
    const rad = angle * Math.PI / 180
    return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)]
  }
  const tipAngle = start + goal / 100 * sweep
  const [tipX, tipY] = polar(radius + 15, tipAngle)

  return (
    <div className="echo-signal" style={{ width: size }}>
      <svg viewBox="0 24 200 125" width="100%" aria-hidden="true">
        {Array.from({ length: 100 }, (_, index) => {
          const angle = start + index / 100 * sweep
          const inked = index < goal
          const length = inked ? 10 + ((index * 7) % 5) : 4 + ((index * 3) % 3)
          const [x1, y1] = polar(radius, angle)
          const [x2, y2] = polar(radius + length, angle)
          return (
            <line
              key={index}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke={inked ? LIEFLAT.HERO : LIEFLAT.FLOOR}
              strokeWidth={inked ? 1.35 : 0.75}
              className="echo-signal__tick"
              style={{ animationDelay: `${index * 0.009}s` }}
            />
          )
        })}
        {[25, 50, 75, 100].map((milestone) => {
          const angle = start + milestone / 100 * sweep
          const [dotX, dotY] = polar(radius - 5, angle)
          const [textX, textY] = polar(radius - 15, angle)
          return (
            <g key={milestone}>
              <circle cx={dotX} cy={dotY} r="1.1" fill={LIEFLAT.FAINT} />
              <text x={textX} y={textY + 2} textAnchor="middle" fontSize="6.5" fill={LIEFLAT.FAINT}>
                {milestone}
              </text>
            </g>
          )
        })}
        {v != null && (
          <circle cx={tipX} cy={tipY} r="2.5" fill={LIEFLAT.HERO} className="echo-signal__tip" />
        )}
        <text x="100" y="113" textAnchor="middle" className="echo-signal__num" fill={LIEFLAT.TXT}>
          {loading ? '· · ·' : pct}
        </text>
        <text x="100" y="130" textAnchor="middle" className="echo-signal__unit" fill={LIEFLAT.MUT}>
          {loading ? '' : '%'}
        </text>
      </svg>
      <div className="echo-signal__label" style={{ color: LIEFLAT.DATA }}>
        {loading ? '计算中' : label}
      </div>
    </div>
  )
}
