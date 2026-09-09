import { useEffect, useRef } from 'react'

/**
 * 滚动入场容器：进入视口时叠加 `.is-visible`，触发 CSS 的
 * fade + translateY 过渡。零依赖（IntersectionObserver），
 * 支持 `delay` 做 stagger；`prefers-reduced-motion` 下自动降级。
 */
export default function Reveal({ children, delay = 0, className = '', style }) {
  const ref = useRef(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (typeof IntersectionObserver === 'undefined') {
      el.classList.add('is-visible')
      return
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add('is-visible')
            io.unobserve(e.target)
          }
        })
      },
      { threshold: 0.08, rootMargin: '0px 0px -36px 0px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])

  return (
    <div
      ref={ref}
      className={`reveal ${className}`}
      style={{ '--reveal-delay': `${delay}ms`, ...style }}
    >
      {children}
    </div>
  )
}
