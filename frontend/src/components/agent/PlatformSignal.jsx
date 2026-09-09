import { useEffect, useRef, useState } from 'react'
import { platformColor, platformName } from '../../utils/platforms'

/**
 * 平台信号条：各平台声量强度水平条，进入视口后逐条注入 + 脉冲末端点。
 * 纯 CSS/SVG 视觉资产，用「信号强度」隐喻各平台声量，呼应品牌信号主题。
 *
 * @param {Array<{platform: string, level: number}>} items level 归一化 0~1
 */
export default function PlatformSignal({ items = [] }) {
  const ref = useRef(null)
  const [on, setOn] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el || typeof IntersectionObserver === 'undefined') { setOn(true); return }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) { setOn(true); io.unobserve(e.target) }
        })
      },
      { threshold: 0.4 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])

  if (!items?.length) return null

  return (
    <div className={`platform-signal ${on ? 'is-on' : ''}`} ref={ref}>
      {items.map((it, i) => {
        const level = Math.max(0, Math.min(1, Number(it.level) || 0))
        return (
          <div className="platform-signal__row" key={it.platform || i}>
            <span className="platform-signal__name" style={{ color: platformColor(it.platform) }}>
              {platformName(it.platform)}
            </span>
            <div className="platform-signal__track">
              <div
                className="platform-signal__fill"
                style={{
                  '--fill': `${(level * 100).toFixed(1)}%`,
                  '--delay': `${i * 90}ms`,
                  background: platformColor(it.platform),
                }}
              />
            </div>
            <span className="platform-signal__val tnum">
              {(level * 100).toFixed(0)}
            </span>
          </div>
        )
      })}
    </div>
  )
}
