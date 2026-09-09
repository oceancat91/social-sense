import { useEffect, useRef, useState } from 'react'

/**
 * 数字滚动（count-up）：从上一值 easeOutCubic 缓动到当前值。
 * 尊重 prefers-reduced-motion（直接跳变），输出 tabular-nums。
 */
export default function CountUp({ value, duration = 1000, decimals = 0, className = '', style }) {
  const [display, setDisplay] = useState(value ?? 0)
  const fromRef = useRef(value ?? 0)
  const rafRef = useRef(0)

  useEffect(() => {
    const reduce = typeof window !== 'undefined'
      && window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches
    const to = typeof value === 'number' ? value : 0
    if (reduce) {
      fromRef.current = to
      setDisplay(to)
      return
    }
    const from = fromRef.current
    if (from === to) return
    const start = performance.now()
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      const cur = from + (to - from) * eased
      setDisplay(cur)
      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick)
      } else {
        fromRef.current = to
      }
    }
    cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [value, duration])

  return (
    <span className={`tnum ${className}`} style={style}>
      {(typeof display === 'number' ? display : 0).toFixed(decimals)}
    </span>
  )
}
