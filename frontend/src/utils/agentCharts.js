/**
 * 多 Agent 跨平台报告的图表配置（ECharts option 工厂）。
 *
 * 数据来源均为 `GET /api/v1/agent/reports/:id` 返回的 result：
 *   - cross_platform.aligned.time_axis / z_series  -> 跨平台「对齐」时间序列
 *   - cross_platform.fusion.*                       -> 分歧 / 共振 / 茧房 / 分桶分歧
 *   - cross_platform.echo_chamber.*                 -> 茧房指数
 *
 * 对齐原则：z_series 是各平台在统一 time_axis 上的平台内 z-score，
 * 缺失桶为 null（ECharts 断点，不插值、不伪造），保证跨平台可比。
 *
 * 主题化：每个工厂的最后一个参数 dark（默认 false）控制文字/轴线/热力色，
 * 供跟随系统深浅主题的页面传入；平台系列色沿用平台品牌色（dark 下自动提亮）。
 */

import { PLATFORMS, platformColor, platformName } from './platforms'
import { SEMANTIC } from '../theme'

/** 立场五分类的展示元数据（与后端 contract.CANONICAL_STANCE 对齐） */
export const STANCE_META = {
  support: { name: '支持', color: '#15803D' },
  oppose: { name: '反对', color: '#B91C1C' },
  neutral: { name: '中立', color: '#8B9096' },
  mixed: { name: '混合', color: '#D97706' },
  unclear: { name: '不明', color: '#A8A19A' },
}

export const STANCE_ORDER = ['support', 'oppose', 'neutral', 'mixed', 'unclear']

const STANCE_DARK_COLOR = {
  support: '#3ECF8E',
  oppose: '#F26B5E',
  neutral: '#A5ACB3',
  mixed: '#F0A63F',
  unclear: '#6F7780',
}

/** 立场语义色（dark 下自动使用提亮变体） */
export function stanceColor(key, dark = false) {
  if (dark) return STANCE_DARK_COLOR[key] || STANCE_META[key]?.color || '#BFBFBF'
  return STANCE_META[key]?.color || '#BFBFBF'
}

function themePalette(dark) {
  return {
    text: dark ? '#EDF0F5' : '#191D25',
    label: dark ? '#A8B1C0' : '#4C5665',
    faint: dark ? '#7E8899' : '#5B6675',
    axisLine: dark ? '#313C53' : '#D6DAE1',
    splitLine: dark ? '#1A2030' : '#EEF0F4',
    tooltipBg: dark ? 'rgba(23,27,33,0.98)' : 'rgba(255,255,255,0.98)',
    tooltipBorder: dark ? '#313C53' : '#E6E9EE',
    tooltipText: dark ? '#EDF0F5' : '#191D25',
    heatmapTrack: dark ? '#0C0F16' : '#EEF0F4',
    dataZoomFiller: dark ? 'rgba(59,130,246,0.12)' : 'rgba(37,99,235,0.08)',
    dataZoomBorder: dark ? '#313C53' : '#D6DAE1',
    dataZoomBg: dark ? '#1A2030' : '#F0F2F5',
    labelOnHeat: dark ? '#0D0F12' : '#FFFFFF',
    accent: dark ? '#3B82F6' : '#2563EB',
    accentSoft: dark ? 'rgba(59,130,246,0.16)' : 'rgba(37,99,235,0.10)',
    success: SEMANTIC.success[dark ? 'dark' : 'light'],
    warning: SEMANTIC.warning[dark ? 'dark' : 'light'],
    danger: SEMANTIC.danger[dark ? 'dark' : 'light'],
    info: SEMANTIC.info[dark ? 'dark' : 'light'],
  }
}

const CHART_TITLE = (dark) => ({
  fontSize: 14,
  fontWeight: 600,
  color: themePalette(dark).text,
})
const AXIS_LABEL = (dark) => ({ color: themePalette(dark).faint })
const AXIS_LINE = (dark) => ({ lineStyle: { color: themePalette(dark).axisLine } })
const SPLIT_LINE = (dark) => ({ lineStyle: { color: themePalette(dark).splitLine } })
const tooltipStyle = (dark) => {
  const p = themePalette(dark)
  return {
    backgroundColor: p.tooltipBg,
    borderColor: p.tooltipBorder,
    textStyle: { color: p.tooltipText },
    extraCssText: 'box-shadow:0 6px 24px rgba(0,0,0,0.12);border-radius:8px;',
  }
}

/** 时间轴刻度显示：日粒度 -> MM-DD，小时粒度 -> MM-DD HH */
function tsTick(ts, granularity) {
  if (!ts) return ''
  const s = String(ts)
  if (granularity === 'hour') return s.slice(5, 10) + ' ' + (s.slice(11, 13) || '')
  return s.slice(5, 10)
}

/**
 * 茧房指数仪表盘。
 * @param {number} score 0~1
 */
export function echoGaugeOption(score, dark = false) {
  const v = Number(score ?? 0)
  const p = themePalette(dark)
  const low = p.success
  const mid = p.warning
  const high = p.danger
  const levelColor = v >= 0.5 ? high : v >= 0.25 ? mid : low
  return {
    series: [
      {
        type: 'gauge',
        min: 0,
        max: 1,
        radius: '92%',
        startAngle: 210,
        endAngle: -30,
        axisLine: {
          lineStyle: {
            width: 16,
            color: [
              [0.25, low],
              [0.5, mid],
              [1, high],
            ],
          },
        },
        pointer: { show: true, length: '60%', width: 4, itemStyle: { color: levelColor } },
        axisTick: { show: false },
        splitLine: {
          length: 9,
          lineStyle: { color: dark ? '#313C53' : '#D7DEE7', width: 2 },
        },
        axisLabel: {
          color: p.faint,
          fontSize: 10,
          distance: 16,
          formatter: (val) => val.toFixed(1),
        },
        anchor: { show: true, size: 8, itemStyle: { color: levelColor } },
        title: { show: true, offsetCenter: [0, '74%'], fontSize: 12, color: p.label },
        detail: {
          valueAnimation: true,
          formatter: (val) => (val * 100).toFixed(1) + '%',
          fontSize: 28,
          fontWeight: 700,
          color: levelColor,
          offsetCenter: [0, '40%'],
        },
        data: [{ value: v, name: '回声室指数' }],
      },
    ],
  }
}

/**
 * 跨平台「对齐」时间序列曲线：多平台在同一 time_axis 上的 z-score。
 */
export function alignedSeriesOption({
  timeAxis,
  zSeries,
  metric,
  title,
  yName,
  granularity = 'day',
  area = false,
}, dark = false) {
  const platforms = Object.keys(zSeries || {})
  if (!timeAxis?.length || !platforms.length) return null
  const p = themePalette(dark)

  return {
    title: { text: title, left: 'center', textStyle: CHART_TITLE(dark) },
    tooltip: {
      trigger: 'axis',
      ...tooltipStyle(dark),
      axisPointer: { type: 'line', lineStyle: { color: p.axisLine } },
    },
    legend: { bottom: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 8, type: 'scroll', textStyle: { color: p.label } },
    grid: { left: 48, right: 24, top: 56, bottom: 56 },
    dataZoom: [
      { type: 'inside', throttle: 50 },
      { type: 'slider', height: 16, bottom: 26, borderColor: p.dataZoomBorder, fillerColor: p.dataZoomFiller, backgroundColor: p.dataZoomBg },
    ],
    xAxis: {
      type: 'category',
      data: timeAxis.map((t) => tsTick(t, granularity)),
      boundaryGap: false,
      axisLine: AXIS_LINE(dark),
      axisLabel: { ...AXIS_LABEL(dark), hideOverlap: true },
    },
    yAxis: {
      type: 'value',
      name: yName || metric,
      nameTextStyle: { color: p.faint },
      splitLine: SPLIT_LINE(dark),
      axisLabel: AXIS_LABEL(dark),
      scale: true,
    },
    series: platforms.map((plat) => ({
      name: platformName(plat),
      type: 'line',
      smooth: true,
      symbol: 'none',
      large: true,
      sampling: 'lttb',
      connectNulls: false, // 空窗断点，不伪造观测
      lineStyle: { width: 2.2 },
      areaStyle: area ? { opacity: 0.12 } : undefined,
      emphasis: { focus: 'series' },
      color: platformColor(plat, dark),
      data: (zSeries[plat]?.[metric] || []).map((v) => (v == null ? null : Number(v))),
    })),
  }
}

/**
 * 各平台立场分布（100% 堆叠横向条）。
 */
export function stanceDistOption(stanceDist, dark = false) {
  const platforms = Object.keys(stanceDist || {})
  if (!platforms.length) return null
  const p = themePalette(dark)

  const semanticColor = (key) => {
    const base = STANCE_META[key]?.color
    if (!dark) return base
    return {
      support: '#34D399',
      oppose: '#F87171',
      neutral: '#8A95A5',
      mixed: '#F0A63F',
      unclear: '#65718A',
    }[key] || base
  }

  return {
    title: { text: '各平台立场分布（对齐对比）', left: 'center', textStyle: CHART_TITLE(dark) },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      ...tooltipStyle(dark),
      formatter: (params) => {
        const item = params[0]
        let html = `<b>${item?.name || ''}</b>`
        params.forEach((it) => {
          html += `<br/>${it.marker}${it.seriesName}: ${(it.value * 100).toFixed(1)}%`
        })
        return html
      },
    },
    legend: { bottom: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 8, textStyle: { color: p.label } },
    grid: { left: 52, right: 24, top: 44, bottom: 56 },
    xAxis: {
      type: 'value',
      max: 1,
      axisLabel: { ...AXIS_LABEL(dark), formatter: (val) => `${(val * 100).toFixed(0)}%` },
      splitLine: SPLIT_LINE(dark),
    },
    yAxis: {
      type: 'category',
      data: platforms.map(platformName),
      axisLine: AXIS_LINE(dark),
      axisLabel: AXIS_LABEL(dark),
    },
    series: STANCE_ORDER.map((key) => ({
      name: STANCE_META[key].name,
      type: 'bar',
      stack: 'stance',
      barMaxWidth: 22,
      itemStyle: { color: semanticColor(key) },
      data: platforms.map((plat) => Number(stanceDist[plat]?.[key] ?? 0)),
    })),
  }
}

/**
 * 平台声量共振矩阵（两两 Pearson 相关，对角线为 1）。
 */
export function corrMatrixOption(temporalCorr, platforms, dark = false) {
  if (!platforms?.length) return null
  const p = themePalette(dark)
  const n = platforms.length
  const map = {}
  for (const c of temporalCorr || []) {
    const [a, b] = c.pair || []
    map[`${a}|${b}`] = c.volume_corr
    map[`${b}|${a}`] = c.volume_corr
  }
  const data = []
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const pp = platforms[i]
      const q = platforms[j]
      const val = i === j ? 1 : map[`${pp}|${q}`]
      data.push([j, i, val == null ? '-' : Number(val)])
    }
  }
  const labels = platforms.map(platformName)

  return {
    title: { text: '平台声量共振（时间相关性）', left: 'center', textStyle: CHART_TITLE(dark) },
    tooltip: {
      position: 'top',
      ...tooltipStyle(dark),
      formatter: (params) => {
        const [x, y, v] = params.value
        if (v === '-') return `${labels[x]} × ${labels[y]}：数据不足`
        return `${labels[x]} × ${labels[y]}：<b>${Number(v).toFixed(3)}</b>`
      },
    },
    grid: { left: 56, right: 16, top: 44, bottom: 70 },
    xAxis: {
      type: 'category',
      data: labels,
      splitArea: { show: true, areaStyle: { color: [p.heatmapTrack, 'transparent'] } },
      axisLine: AXIS_LINE(dark),
      axisLabel: { ...AXIS_LABEL(dark), rotate: 30 },
    },
    yAxis: {
      type: 'category',
      data: labels,
      splitArea: { show: true, areaStyle: { color: [p.heatmapTrack, 'transparent'] } },
      axisLine: AXIS_LINE(dark),
      axisLabel: AXIS_LABEL(dark),
    },
    visualMap: {
      min: -1,
      max: 1,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 4,
      itemWidth: 12,
      textStyle: { color: p.faint },
      inRange: { color: [p.danger, p.heatmapTrack, p.success] },
    },
    series: [
      {
        type: 'heatmap',
        data,
        label: {
          show: true,
          fontSize: 11,
          color: dark ? '#A8B1C0' : '#4C5665',
          formatter: (params) => {
            const val = params.value[2]
            return val === '-' ? '' : Number(val).toFixed(2)
          },
        },
        itemStyle: {
          borderColor: dark ? '#0D0F12' : '#FFFFFF',
          borderWidth: 2,
          borderRadius: 4,
        },
        emphasis: { itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0,0,0,0.18)' } },
      },
    ],
  }
}

/**
 * 分桶跨平台情绪分歧时序。
 */
export function divergenceTimelineOption(perBucket, dark = false) {
  if (!perBucket?.length) return null
  const p = themePalette(dark)

  return {
    title: { text: '跨平台情绪分歧随时间扩散', left: 'center', textStyle: CHART_TITLE(dark) },
    tooltip: {
      trigger: 'axis',
      ...tooltipStyle(dark),
      formatter: (params) => {
        const item = params[0]
        const raw = perBucket[item?.dataIndex]
        return raw
          ? `时间 ${raw.ts.slice(0, 10)}<br/>情绪极差 <b>${Number(raw.sent_range).toFixed(4)}</b><br/>活跃平台 ${raw.active_platforms}`
          : ''
      },
    },
    grid: { left: 48, right: 24, top: 44, bottom: 56 },
    dataZoom: [
      { type: 'inside', throttle: 50 },
      { type: 'slider', height: 16, bottom: 26, borderColor: p.dataZoomBorder, fillerColor: p.dataZoomFiller, backgroundColor: p.dataZoomBg },
    ],
    xAxis: {
      type: 'category',
      data: perBucket.map((b) => b.ts.slice(5, 10)),
      boundaryGap: false,
      axisLine: AXIS_LINE(dark),
      axisLabel: { ...AXIS_LABEL(dark), hideOverlap: true },
    },
    yAxis: {
      type: 'value',
      name: '情绪极差',
      nameTextStyle: { color: p.faint },
      splitLine: SPLIT_LINE(dark),
      axisLabel: AXIS_LABEL(dark),
      scale: true,
    },
    series: [
      {
        name: '情绪极差',
        type: 'line',
        smooth: true,
        symbol: 'none',
        large: true,
        sampling: 'lttb',
        lineStyle: { width: 2.2, color: p.accent },
        areaStyle: { opacity: 0.14, color: p.accent },
        data: perBucket.map((b) => Number(b.sent_range)),
      },
    ],
  }
}

/** 平台完整信息（颜色/名称），供页面复用 */
export function platformMeta(code) {
  return PLATFORMS[code] || { name: code, color: '#666' }
}
