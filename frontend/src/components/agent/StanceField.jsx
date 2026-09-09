import { platformName } from '../../utils/platforms'
import { STANCE_META, STANCE_ORDER } from '../../utils/agentCharts'
import { LIEFLAT } from './lieflatTheme'

const COLORS = [
  LIEFLAT.HERO,
  LIEFLAT.TXT,
  LIEFLAT.DATA2,
  LIEFLAT.FAINT_DATA,
  LIEFLAT.QUIET,
]

function allocateHundred(values) {
  const safe = values.map((value) => Math.max(0, Number(value) || 0))
  const total = safe.reduce((sum, value) => sum + value, 0)
  if (!total) return safe.map(() => 0)

  const exact = safe.map((value) => (value / total) * 100)
  const result = exact.map(Math.floor)
  let remaining = 100 - result.reduce((sum, value) => sum + value, 0)
  const order = exact
    .map((value, index) => ({ index, fraction: value - Math.floor(value) }))
    .sort((a, b) => b.fraction - a.fraction)

  for (let index = 0; index < remaining; index += 1) {
    result[order[index % order.length].index] += 1
  }
  return result
}

/**
 * L14 Hundred Field 的多平台适配。
 * 每个平台严格分解为 100 个单位点，颜色之外仍通过图例和 tooltip 传达立场。
 */
export default function StanceField({ stanceDist }) {
  const platforms = Object.keys(stanceDist || {})
  if (!platforms.length) return null

  const columns = Math.min(platforms.length, 3)
  const rows = Math.ceil(platforms.length / columns)
  const width = 900
  const cellWidth = width / columns
  const rowHeight = 228
  const height = rows * rowHeight + 62

  return (
    <svg
      className="stance-field"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="各平台立场百分比单位场，每个点代表一个百分点"
    >
      {platforms.map((platform, platformIndex) => {
        const values = STANCE_ORDER.map((key) => stanceDist[platform]?.[key] || 0)
        const counts = allocateHundred(values)
        const column = platformIndex % columns
        const row = Math.floor(platformIndex / columns)
        const originX = column * cellWidth + (cellWidth - 126) / 2
        const originY = row * rowHeight + 58
        const cumulative = counts.reduce((list, count) => {
          list.push((list.at(-1) || 0) + count)
          return list
        }, [])

        return (
          <g key={platform}>
            <text
              x={column * cellWidth + cellWidth / 2}
              y={row * rowHeight + 28}
              textAnchor="middle"
              fill={LIEFLAT.TXT}
              fontSize="18"
              fontWeight="700"
            >
              {platformName(platform)}
            </text>
            {Array.from({ length: 100 }, (_, pointIndex) => {
              const stanceIndex = cumulative.findIndex((limit) => pointIndex < limit)
              const resolvedIndex = stanceIndex < 0 ? STANCE_ORDER.length - 1 : stanceIndex
              const key = STANCE_ORDER[resolvedIndex]
              const x = originX + (pointIndex % 10) * 14
              const y = originY + Math.floor(pointIndex / 10) * 14
              return (
                <circle
                  key={pointIndex}
                  cx={x}
                  cy={y}
                  r="4.1"
                  fill={COLORS[resolvedIndex]}
                  stroke={resolvedIndex === 4 ? LIEFLAT.FLOOR : 'none'}
                  strokeWidth="1"
                  className="lieflat-dot"
                  style={{ animationDelay: `${platformIndex * 0.08 + pointIndex * 0.004}s` }}
                >
                  <title>
                    {`${platformName(platform)} / ${STANCE_META[key].name} / 第 ${pointIndex + 1} 个百分点`}
                  </title>
                </circle>
              )
            })}
          </g>
        )
      })}

      {STANCE_ORDER.map((key, index) => (
        <g key={key} transform={`translate(${96 + index * 150} ${height - 24})`}>
          <circle cx="0" cy="0" r="4" fill={COLORS[index]} stroke={index === 4 ? LIEFLAT.FLOOR : 'none'} />
          <text x="11" y="4" fill={LIEFLAT.MUT} fontSize="11" fontWeight="600">
            {STANCE_META[key].name}
          </text>
        </g>
      ))}
    </svg>
  )
}
