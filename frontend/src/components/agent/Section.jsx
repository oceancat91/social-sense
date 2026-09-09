import { useEffect, useRef } from 'react'

/**
 * 统一区域分割组件：序号 + 标题 + 滚动 draw-in 细分隔线。
 * 进入视口时 `.is-drawn` 触发分隔线从左到右延伸（scroll-driven reveal）。
 */
export default function Section({ index, title, desc, extra, children, className = '', style }) {
  const ref = useRef(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (typeof IntersectionObserver === 'undefined') {
      el.classList.add('is-drawn')
      return
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add('is-drawn')
            io.unobserve(e.target)
          }
        })
      },
      { threshold: 0.05 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])

  return (
    <section ref={ref} className={`section ${className}`} style={style}>
      <header className="section__head">
        {index && <span className="section__index">{index}</span>}
        <h2 className="section__title">{title}</h2>
        {desc && <span className="section__desc">{desc}</span>}
        {extra && <span className="section__extra">{extra}</span>}
      </header>
      <div className="section__body">{children}</div>
    </section>
  )
}
