import { useMemo, useState } from 'react'
import { platformName } from '../../utils/platforms'
import { LIEFLAT } from './lieflatTheme'

const MAX_STEMS = 96

function formatTick(value) {
  if (!value) return ''
  const text = String(value)
  return text.length >= 10 ? text.slice(0, 10) : text
}

function bucketPeaks(timeAxis, values) {
  if (!timeAxis?.length) return []
  const bucketSize = Math.max(1, Math.ceil(timeAxis.length / MAX_STEMS))
  const buckets = []
  for (let start = 0; start < timeAxis.length; start += bucketSize) {
    const end = Math.min(timeAxis.length, start + bucketSize)
    let chosen = null
    for (let index = start; index < end; index += 1) {
      const value = values?.[index]
      if (value == null || Number.isNaN(Number(value))) continue
      if (!chosen || Math.abs(Number(value)) > Math.abs(chosen.value)) {
        chosen = { value: Number(value), timestamp: timeAxis[index] }
      }
    }
    buckets.push(chosen || { value: null, timestamp: timeAxis[start] })
  }
  return buckets
}

/**
 * L3 Barcode Lollipop 的多平台小多图适配。
 * 长序列按同宽时间窗折叠，每根发丝只编码该窗内绝对峰值，不显示拖拽区间。
 */
export default function AlignedBarcodeChart({ timeAxis, zSeries, metric = 'volume' }) {
  const [replay, setReplay] = useState(0)
  const rows = useMemo(
    () => Object.keys(zSeries || {}).map((platform) => ({
      platform,
      buckets: bucketPeaks(timeAxis, zSeries[platform]?.[metric] || []),
    })),
    [timeAxis, zSeries, metric],
  )

  if (!rows.length || !timeAxis?.length) return null

  const width = 960
  const left = 92
  const right = 28
  const rowHeight = 90
  const height = 70 + rows.length * rowHeight
  const plotWidth = width - left - right
  const maxAbs = Math.max(
    2,
    ...rows.flatMap(row => row.buckets.map(item => Math.abs(item.value || 0))),
  )

  return (
    <svg
      key={replay}
      className="aligned-barcode"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="跨平台声量窗口峰值条码图"
      tabIndex="0"
      onClick={() => setReplay(value => value + 1)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') setReplay(value => value + 1)
      }}
    >
      {rows.map((row, rowIndex) => {
        const baseline = 56 + rowIndex * rowHeight
        const color = LIEFLAT.SERIES[rowIndex % LIEFLAT.SERIES.length]
        const peak = row.buckets.reduce((best, item, index) =>
          Math.abs(item.value || 0) > Math.abs(best.item?.value || 0)
            ? { item, index }
            : best,
        { item: null, index: 0 })

        return (
          <g key={row.platform}>
            <text
              x={left - 16}
              y={baseline + 4}
              textAnchor="end"
              fill={LIEFLAT.LAB}
              fontSize="12"
              fontWeight="700"
            >
              {platformName(row.platform)}
            </text>
            <line
              x1={left}
              x2={width - right}
              y1={baseline}
              y2={baseline}
              stroke={LIEFLAT.GRID}
              strokeWidth="1"
            />
            {row.buckets.map((item, index) => {
              const x = row.buckets.length === 1
                ? left + plotWidth / 2
                : left + index / (row.buckets.length - 1) * plotWidth
              if (item.value == null) {
                return <circle key={index} cx={x} cy={baseline} r="1" fill={LIEFLAT.FAINT} />
              }
              const y = baseline - item.value / maxAbs * 34
              const isPeak = index === peak.index
              return (
                <g key={index}>
                  <line
                    x1={x}
                    x2={x}
                    y1={baseline}
                    y2={y}
                    stroke={color}
                    strokeWidth={isPeak ? 2 : 1.1}
                    opacity={isPeak ? 1 : 0.86}
                    className="lieflat-stem"
                    pathLength="1"
                    style={{ animationDelay: `${rowIndex * 0.08 + index * 0.004}s` }}
                  />
                  <circle
                    cx={x}
                    cy={y}
                    r={isPeak ? 3.6 : 1.9}
                    fill={item.value >= 0 ? color : LIEFLAT.BG}
                    stroke={color}
                    strokeWidth="1.2"
                    className="lieflat-pop"
                    style={{ animationDelay: `${0.15 + rowIndex * 0.08 + index * 0.004}s` }}
                  >
                    <title>
                      {`${platformName(row.platform)} / ${formatTick(item.timestamp)} / 窗口绝对峰值 ${item.value.toFixed(2)}`}
                    </title>
                  </circle>
                  {isPeak && (
                    <text
                      x={x}
                      y={y - 8}
                      textAnchor="middle"
                      fill={LIEFLAT.TXT}
                      stroke={LIEFLAT.HALO}
                      strokeWidth="3"
                      paintOrder="stroke"
                      fontSize="9"
                      fontWeight="800"
                    >
                      {item.value.toFixed(1)}
                    </text>
                  )}
                </g>
              )
            })}
          </g>
        )
      })}

      {[0, 0.5, 1].map((ratio) => {
        const index = Math.min(timeAxis.length - 1, Math.round((timeAxis.length - 1) * ratio))
        const x = left + ratio * plotWidth
        return (
          <g key={ratio}>
            <line x1={x} x2={x} y1={height - 36} y2={height - 30} stroke={LIEFLAT.FLOOR} />
            <text
              x={x}
              y={height - 16}
              textAnchor={ratio === 0 ? 'start' : ratio === 1 ? 'end' : 'middle'}
              fill={LIEFLAT.MUT}
              fontSize="9"
              fontWeight="600"
            >
              {formatTick(timeAxis[index])}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
