export default function LieflatChartFrame({
  title,
  subtitle,
  code,
  source,
  children,
  className = '',
}) {
  return (
    <figure className={`lieflat-chart ${className}`.trim()}>
      <header className="lieflat-chart__head">
        <div>
          <h3 className="lieflat-chart__title">{title}</h3>
          {subtitle && <p className="lieflat-chart__sub">{subtitle}</p>}
        </div>
        <span className="lieflat-chart__code">{code}</span>
      </header>
      <div className="lieflat-chart__plot">{children}</div>
      <figcaption className="lieflat-chart__source">{source}</figcaption>
    </figure>
  )
}
