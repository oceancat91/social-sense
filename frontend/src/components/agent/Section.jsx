/**
 * 统一区域分割组件：仅用标题、说明和留白建立层级。
 */
export default function Section({ title, desc, extra, children, className = '', style }) {
  return (
    <section className={`section ${className}`} style={style}>
      <header className="section__head">
        <div>
          <h2 className="section__title">{title}</h2>
          {desc && <p className="section__desc">{desc}</p>}
        </div>
        {extra && <span className="section__extra">{extra}</span>}
      </header>
      <div className="section__body">{children}</div>
    </section>
  )
}
