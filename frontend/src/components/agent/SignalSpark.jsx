/**
 * 指标 sparkline：一条极简面积折线，配末端脉冲点。
 * 纯 SVG 视觉资产，用于在简洁指标旁表达趋势，避免堆叠完整图表。
 * @param {number[]} values 归一化 0~1 数值序列
 */
export default function SignalSpark({ values = [], width = 96, height = 30 }) {
  if (!values || values.length < 2) return null
  const n = values.length
  const pad = 3
  const step = (width - pad * 2) / (n - 1)
  const max = Math.max(...values) || 1
  const min = Math.min(...values)
  const range = max - min || 1
  const px = (i) => pad + i * step
  const py = (v) => height - pad - ((v - min) / range) * (height - pad * 2)

  const line = values.map((v, i) => `${i === 0 ? 'M' : 'L'} ${px(i).toFixed(1)} ${py(v).toFixed(1)}`).join(' ')
  const area = `${line} L ${px(n - 1).toFixed(1)} ${height - pad} L ${px(0).toFixed(1)} ${height - pad} Z`
  const lastX = px(n - 1)
  const lastY = py(values[n - 1])

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="signal-spark" aria-hidden="true">
      <defs>
        <linearGradient id="spark-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.28" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#spark-fill)" />
      <path d={line} fill="none" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className="signal-spark__line" />
      <circle cx={lastX} cy={lastY} r="2.6" fill="var(--accent)" className="signal-spark__dot" />
    </svg>
  )
}
