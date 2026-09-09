import { useMemo, useState } from 'react'
import { platformName } from '../../utils/platforms'
import { LIEFLAT } from './lieflatTheme'

const BIN_COUNT = 56

function quantile(sorted, ratio) {
  if (!sorted.length) return 0
  const index = (sorted.length - 1) * ratio
  const lower = Math.floor(index)
  const upper = Math.ceil(index)
  if (lower === upper) return sorted[lower]
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (index - lower)
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b)
  return quantile(sorted, 0.5)
}

function distribution(values, low, high) {
  const bins = Array(BIN_COUNT).fill(0)
  const span = high - low || 1
  for (const value of values) {
    const index = Math.max(
      0,
      Math.min(BIN_COUNT - 1, Math.floor((value - low) / span * BIN_COUNT)),
    )
    bins[index] += 1
  }
  return bins.map((value, index) => {
    const prev = bins[Math.max(0, index - 1)]
    const next = bins[Math.min(BIN_COUNT - 1, index + 1)]
    return prev * 0.25 + value * 0.5 + next * 0.25
  })
}

/**
 * L19 Ridgeline。
 * 将情绪 z-score 从长时序改为平台分组分布，展示日常区间与偏移，而非再放一条拖拽折线。
 */
export default function SentimentRidgeline({ zSeries, metric = 'sent_mean' }) {
  const [replay, setReplay] = useState(0)
  const prepared = useMemo(() => {
    const groups = Object.keys(zSeries || {}).map((platform) => ({
      platform,
      values: (zSeries[platform]?.[metric] || [])
        .filter(value => value != null && !Number.isNaN(Number(value)))
        .map(Number),
    })).filter(group => group.values.length)
    const all = groups.flatMap(group => group.values).sort((a, b) => a - b)
    const low = quantile(all, 0.01)
    const high = quantile(all, 0.99)
    return {
      low,
      high,
      groups: groups.map(group => ({
        ...group,
        density: distribution(group.values, low, high),
        median: median(group.values),
      })),
    }
  }, [zSeries, metric])

  if (!prepared.groups.length) return null

  const width = 960
  const left = 116
  const right = 34
  const rowHeight = 94
  const height = 72 + prepared.groups.length * rowHeight
  const plotWidth = width - left - right
  const xAt = (index) => left + index / (BIN_COUNT - 1) * plotWidth
  const mapValue = (value) => left + (value - prepared.low) / (prepared.high - prepared.low || 1) * plotWidth

  return (
    <svg
      key={replay}
      className="sentiment-ridge"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="各平台情绪 z-score 分布脊线"
      tabIndex="0"
      onClick={() => setReplay(value => value + 1)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') setReplay(value => value + 1)
      }}
    >
      {prepared.groups.map((group, groupIndex) => {
        const baseline = 70 + groupIndex * rowHeight
        const color = LIEFLAT.SERIES[groupIndex % LIEFLAT.SERIES.length]
        const maxDensity = Math.max(...group.density, 1)
        const points = group.density.map((density, index) => ({
          x: xAt(index),
          y: baseline - density / maxDensity * 56,
        }))
        const path = points
          .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`)
          .join(' ')
        const peakIndex = group.density.indexOf(maxDensity)
        const peak = points[peakIndex]
        const peakValue = prepared.low + peakIndex / (BIN_COUNT - 1) * (prepared.high - prepared.low)
        const medianX = mapValue(group.median)

        return (
          <g key={group.platform}>
            {points.filter((_, index) => index % 2 === 0).map((point, index) => (
              <line
                key={index}
                x1={point.x}
                x2={point.x}
                y1={baseline}
                y2={point.y}
                stroke={color}
                strokeWidth="1"
                opacity="0.85"
                className="lieflat-stem"
                pathLength="1"
                style={{ animationDelay: `${groupIndex * 0.1 + index * 0.007}s` }}
              />
            ))}
            <path
              d={path}
              fill="none"
              stroke={color}
              strokeWidth="1.8"
              className="lieflat-draw"
              pathLength="1"
              style={{ animationDelay: `${0.12 + groupIndex * 0.1}s` }}
            >
              <title>
                {`${platformName(group.platform)} / ${group.values.length.toLocaleString()} 个有效时桶 / 中位数 ${group.median.toFixed(2)}`}
              </title>
            </path>
            <line
              x1={left}
              x2={width - right}
              y1={baseline}
              y2={baseline}
              stroke={LIEFLAT.GRID}
              strokeWidth="1"
            />
            <line
              x1={medianX}
              x2={medianX}
              y1={baseline - 60}
              y2={baseline + 4}
              stroke={LIEFLAT.FAINT}
              strokeWidth="1"
              strokeDasharray="2 4"
            />
            <circle cx={peak.x} cy={peak.y} r="3.4" fill={color} className="lieflat-pop" />
            <text
              x={peak.x + 8}
              y={peak.y + 3}
              fill={LIEFLAT.TXT}
              stroke={LIEFLAT.HALO}
              strokeWidth="3"
              paintOrder="stroke"
              fontSize="9"
              fontWeight="800"
            >
              {peakValue.toFixed(1)}
            </text>
            <text
              x={left - 16}
              y={baseline - 3}
              textAnchor="end"
              fill={LIEFLAT.LAB}
              fontSize="12"
              fontWeight="700"
            >
              {platformName(group.platform)}
            </text>
          </g>
        )
      })}

      {[0, 0.5, 1].map((ratio) => {
        const x = left + ratio * plotWidth
        const value = prepared.low + ratio * (prepared.high - prepared.low)
        return (
          <g key={ratio}>
            <line x1={x} x2={x} y1={height - 34} y2={height - 28} stroke={LIEFLAT.FLOOR} />
            <text
              x={x}
              y={height - 14}
              textAnchor={ratio === 0 ? 'start' : ratio === 1 ? 'end' : 'middle'}
              fill={LIEFLAT.MUT}
              fontSize="9"
              fontWeight="600"
            >
              {value.toFixed(1)}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
