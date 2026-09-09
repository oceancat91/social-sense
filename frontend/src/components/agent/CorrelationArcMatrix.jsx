import { useMemo, useState } from 'react'
import { platformName } from '../../utils/platforms'
import { LIEFLAT } from './lieflatTheme'

function shadeFor(value) {
  const index = Math.min(
    LIEFLAT.RAMP.length - 1,
    Math.floor(Math.abs(value) * LIEFLAT.RAMP.length),
  )
  return LIEFLAT.RAMP[index]
}

/**
 * L4 Arc Matrix。
 * 每行是一条平台关系弧，圆面积编码 |Pearson r|；实心为正相关，空心为负相关。
 */
export default function CorrelationArcMatrix({ temporalCorr, platforms }) {
  const [replay, setReplay] = useState(0)
  const lookup = useMemo(() => {
    const map = {}
    for (const item of temporalCorr || []) {
      const [a, b] = item.pair || []
      map[`${a}|${b}`] = item.volume_corr
      map[`${b}|${a}`] = item.volume_corr
    }
    return map
  }, [temporalCorr])

  if (!platforms?.length) return null

  const width = 640
  const height = Math.max(300, 106 + platforms.length * 62)
  const xStart = 178
  const xEnd = 588
  const xAt = (index) => platforms.length === 1
    ? (xStart + xEnd) / 2
    : xStart + index / (platforms.length - 1) * (xEnd - xStart)
  const arcLift = (index) => platforms.length <= 1
    ? 0
    : -15 * Math.sin(Math.PI * index / (platforms.length - 1))

  return (
    <svg
      key={replay}
      className="correlation-arc"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="平台两两声量相关性弧形矩阵"
      tabIndex="0"
      onClick={() => setReplay(value => value + 1)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') setReplay(value => value + 1)
      }}
    >
      {platforms.map((platform, rowIndex) => {
        const baseY = 92 + rowIndex * 58
        const path = platforms
          .map((_, columnIndex) =>
            `${columnIndex === 0 ? 'M' : 'L'} ${xAt(columnIndex)} ${baseY + arcLift(columnIndex)}`)
          .join(' ')

        return (
          <g key={platform}>
            <path
              d={path}
              fill="none"
              stroke={LIEFLAT.GRID}
              strokeWidth="1.4"
              className="lieflat-draw"
              pathLength="1"
              style={{ animationDelay: `${rowIndex * 0.08}s` }}
            />
            <text
              x="142"
              y={baseY + 4}
              textAnchor="end"
              fill={LIEFLAT.LAB}
              fontSize="12"
              fontWeight="700"
            >
              {platformName(platform)}
            </text>
            {platforms.map((peer, columnIndex) => {
              const isSelf = platform === peer
              const raw = isSelf ? null : lookup[`${platform}|${peer}`]
              const value = raw == null ? null : Number(raw)
              const x = xAt(columnIndex)
              const y = baseY + arcLift(columnIndex)

              if (isSelf) {
                return (
                  <g key={peer}>
                    <circle cx={x} cy={y} r="5" fill={LIEFLAT.BG} stroke={LIEFLAT.FLOOR} strokeWidth="1.5" />
                    <circle cx={x} cy={y} r="1.6" fill={LIEFLAT.FAINT} />
                  </g>
                )
              }

              if (value == null || Number.isNaN(value)) {
                return <circle key={peer} cx={x} cy={y} r="1.5" fill={LIEFLAT.FAINT} />
              }

              const radius = 4 + Math.sqrt(Math.abs(value)) * 16
              const positive = value >= 0
              return (
                <g key={peer} className="lieflat-pop" style={{ animationDelay: `${0.15 + rowIndex * 0.08 + columnIndex * 0.035}s` }}>
                  <circle
                    cx={x}
                    cy={y}
                    r={radius}
                    fill={positive ? shadeFor(value) : LIEFLAT.BG}
                    stroke={positive ? LIEFLAT.HERO : LIEFLAT.DATA}
                    strokeWidth={positive ? 1 : 2}
                    strokeDasharray={positive ? undefined : '3 3'}
                  >
                    <title>{`${platformName(platform)} × ${platformName(peer)} / r=${value.toFixed(3)}`}</title>
                  </circle>
                  <text
                    x={x}
                    y={y + 4}
                    textAnchor="middle"
                    fill={LIEFLAT.TXT}
                    stroke={LIEFLAT.HALO}
                    strokeWidth="3"
                    paintOrder="stroke"
                    fontSize="11"
                    fontWeight="800"
                  >
                    {value.toFixed(2)}
                  </text>
                </g>
              )
            })}
          </g>
        )
      })}

      {platforms.map((platform, index) => {
        const x = xAt(index)
        const y = 50 + arcLift(index)
        return (
          <text
            key={platform}
            x={x}
            y={y}
            textAnchor="middle"
            fill={LIEFLAT.MUT}
            fontSize="11"
            fontWeight="700"
          >
            {platformName(platform)}
          </text>
        )
      })}

      <text
        x={width / 2}
        y={height - 18}
        textAnchor="middle"
        fill={LIEFLAT.FAINT}
        fontSize="10.5"
        fontWeight="600"
        letterSpacing=".08em"
      >
        圆面积 = |r| / 实心 = 正相关 / 空心 = 负相关 / 小圆 = 自身
      </text>
    </svg>
  )
}
