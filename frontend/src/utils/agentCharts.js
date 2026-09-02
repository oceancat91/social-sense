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
 */

import { PLATFORMS, platformColor, platformName } from './platforms'

/** 立场五分类的展示元数据（与后端 contract.CANONICAL_STANCE 对齐） */
export const STANCE_META = {
  support: { name: '支持', color: '#52C41A' },
  oppose: { name: '反对', color: '#F5222D' },
  neutral: { name: '中立', color: '#8C8C8C' },
  mixed: { name: '混合', color: '#FA8C16' },
  unclear: { name: '不明', color: '#BFBFBF' },
}

export const STANCE_ORDER = ['support', 'oppose', 'neutral', 'mixed', 'unclear']

const CHART_TITLE = { fontSize: 15, fontWeight: 600 }
const TOOLTIP_BG = {
  backgroundColor: 'rgba(255,255,255,0.96)',
  borderColor: '#e8ecf3',
  textStyle: { color: '#333' },
}
const AXIS_LABEL = { color: '#8a94a6' }
const AXIS_LINE = { lineStyle: { color: '#e8ecf3' } }
const SPLIT_LINE = { lineStyle: { color: '#f0f2f7' } }

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
export function echoGaugeOption(score) {
  const v = Number(score ?? 0)
  const levelColor = v >= 0.5 ? '#F5222D' : v >= 0.25 ? '#FA8C16' : '#0e9f6e'
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
            width: 18,
            color: [
              [0.25, '#0e9f6e'],
              [0.5, '#FA8C16'],
              [1, '#F5222D'],
            ],
          },
        },
        pointer: { show: true, length: '62%', width: 5, itemStyle: { color: levelColor } },
        axisTick: { show: false },
        splitLine: { length: 10, lineStyle: { color: '#e8ecf3', width: 2 } },
        axisLabel: {
          color: '#8a94a6',
          fontSize: 10,
          distance: 18,
          formatter: val => val.toFixed(1),
        },
        anchor: { show: true, size: 10, itemStyle: { color: levelColor } },
        title: { show: true, offsetCenter: [0, '72%'], fontSize: 13, color: '#5b6472' },
        detail: {
          valueAnimation: true,
          formatter: val => (val * 100).toFixed(1) + '%',
          fontSize: 30,
          fontWeight: 700,
          color: levelColor,
          offsetCenter: [0, '38%'],
        },
        data: [{ value: v, name: '信息茧房指数' }],
      },
    ],
  }
}

/**
 * 跨平台「对齐」时间序列曲线：多平台在同一 time_axis 上的 z-score。
 * @param {object} opts
 * @param {string[]} opts.timeAxis
 * @param {object} opts.zSeries  { platform: { metric: [number|null] } }
 * @param {string} opts.metric   指标键（volume / sent_mean / controversy ...）
 * @param {string} opts.title
 * @param {string} opts.yName
 * @param {string} opts.granularity
 * @param {boolean} opts.area
 */
export function alignedSeriesOption({
  timeAxis,
  zSeries,
  metric,
  title,
  yName,
  granularity = 'day',
  area = false,
}) {
  const platforms = Object.keys(zSeries || {})
  if (!timeAxis?.length || !platforms.length) return null

  return {
    title: { text: title, left: 'center', textStyle: CHART_TITLE },
    tooltip: {
      trigger: 'axis',
      ...TOOLTIP_BG,
      axisPointer: { type: 'line', lineStyle: { color: '#c8cfdb' } },
    },
    legend: { bottom: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 8, type: 'scroll' },
    grid: { left: 48, right: 24, top: 56, bottom: 56 },
    dataZoom: [
      { type: 'inside', throttle: 50 },
      { type: 'slider', height: 18, bottom: 26, borderColor: '#e8ecf3', fillerColor: 'rgba(26,115,232,0.08)' },
    ],
    xAxis: {
      type: 'category',
      data: timeAxis.map(t => tsTick(t, granularity)),
      boundaryGap: false,
      axisLine: AXIS_LINE,
      axisLabel: { ...AXIS_LABEL, hideOverlap: true },
    },
    yAxis: {
      type: 'value',
      name: yName || metric,
      nameTextStyle: { color: '#8a94a6' },
      splitLine: SPLIT_LINE,
      axisLabel: AXIS_LABEL,
      scale: true,
    },
    series: platforms.map(p => ({
      name: platformName(p),
      type: 'line',
      smooth: true,
      symbol: 'none',
      large: true,
      sampling: 'lttb',
      connectNulls: false, // 空窗断点，不伪造观测
      lineStyle: { width: 2.2 },
      areaStyle: area ? { opacity: 0.12 } : undefined,
      emphasis: { focus: 'series' },
      color: platformColor(p),
      data: (zSeries[p]?.[metric] || []).map(v => (v == null ? null : Number(v))),
    })),
  }
}

/**
 * 各平台立场分布（100% 堆叠横向条，直观对比「立场对齐」）。
 * @param {object} stanceDist { platform: { support: r, oppose: r, ... } }
 */
export function stanceDistOption(stanceDist) {
  const platforms = Object.keys(stanceDist || {})
  if (!platforms.length) return null

  return {
    title: { text: '各平台立场分布（对齐对比）', left: 'center', textStyle: CHART_TITLE },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      ...TOOLTIP_BG,
      formatter: params => {
        const p = params[0]
        let html = `<b>${p?.name || ''}</b>`
        params.forEach(it => {
          html += `<br/>${it.marker}${it.seriesName}: ${(it.value * 100).toFixed(1)}%`
        })
        return html
      },
    },
    legend: { bottom: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 8 },
    grid: { left: 52, right: 24, top: 44, bottom: 56 },
    xAxis: {
      type: 'value',
      max: 1,
      axisLabel: { ...AXIS_LABEL, formatter: v => `${(v * 100).toFixed(0)}%` },
      splitLine: SPLIT_LINE,
    },
    yAxis: {
      type: 'category',
      data: platforms.map(platformName),
      axisLine: AXIS_LINE,
      axisLabel: AXIS_LABEL,
    },
    series: STANCE_ORDER.map(key => ({
      name: STANCE_META[key].name,
      type: 'bar',
      stack: 'stance',
      barMaxWidth: 26,
      itemStyle: { color: STANCE_META[key].color },
      data: platforms.map(p => Number(stanceDist[p]?.[key] ?? 0)),
    })),
  }
}

/**
 * 平台声量共振矩阵（两两 Pearson 相关，对角线为 1）。
 * @param {Array} temporalCorr [{ pair: [a,b], volume_corr: number|null }]
 * @param {string[]} platforms
 */
export function corrMatrixOption(temporalCorr, platforms) {
  if (!platforms?.length) return null
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
      const p = platforms[i]
      const q = platforms[j]
      const v = i === j ? 1 : map[`${p}|${q}`]
      data.push([j, i, v == null ? '-' : Number(v)])
    }
  }
  const labels = platforms.map(platformName)

  return {
    title: { text: '平台声量共振（时间相关性）', left: 'center', textStyle: CHART_TITLE },
    tooltip: {
      position: 'top',
      ...TOOLTIP_BG,
      formatter: params => {
        const [x, y, v] = params.value
        if (v === '-') return `${labels[x]} × ${labels[y]}：数据不足`
        return `${labels[x]} × ${labels[y]}：<b>${Number(v).toFixed(3)}</b>`
      },
    },
    grid: { left: 56, right: 16, top: 44, bottom: 66 },
    xAxis: {
      type: 'category',
      data: labels,
      splitArea: { show: true },
      axisLine: AXIS_LINE,
      axisLabel: { ...AXIS_LABEL, rotate: 30 },
    },
    yAxis: {
      type: 'category',
      data: labels,
      splitArea: { show: true },
      axisLine: AXIS_LINE,
      axisLabel: AXIS_LABEL,
    },
    visualMap: {
      min: -1,
      max: 1,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 4,
      itemWidth: 12,
      textStyle: { color: '#8a94a6' },
      inRange: { color: ['#d4380d', '#f5f6f8', '#1a73e8'] },
    },
    series: [
      {
        type: 'heatmap',
        data,
        label: {
          show: true,
          fontSize: 11,
          color: '#1f2733',
          formatter: params => {
            const v = params.value[2]
            return v === '-' ? '' : Number(v).toFixed(2)
          },
        },
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        emphasis: { itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0,0,0,0.2)' } },
      },
    ],
  }
}

/**
 * 分桶跨平台情绪分歧时序（sent_range 随时间变化，揭示分歧如何扩散）。
 * @param {Array} perBucket [{ ts, active_platforms, sent_range }]
 */
export function divergenceTimelineOption(perBucket) {
  if (!perBucket?.length) return null
  return {
    title: { text: '跨平台情绪分歧随时间扩散', left: 'center', textStyle: CHART_TITLE },
    tooltip: {
      trigger: 'axis',
      ...TOOLTIP_BG,
      formatter: params => {
        const p = params[0]
        const raw = perBucket[p?.dataIndex]
        return raw
          ? `时间 ${raw.ts.slice(0, 10)}<br/>情绪极差 <b>${Number(raw.sent_range).toFixed(4)}</b><br/>活跃平台 ${raw.active_platforms}`
          : ''
      },
    },
    grid: { left: 48, right: 24, top: 44, bottom: 56 },
    dataZoom: [
      { type: 'inside', throttle: 50 },
      { type: 'slider', height: 18, bottom: 26, borderColor: '#e8ecf3', fillerColor: 'rgba(26,115,232,0.08)' },
    ],
    xAxis: {
      type: 'category',
      data: perBucket.map(b => b.ts.slice(5, 10)),
      boundaryGap: false,
      axisLine: AXIS_LINE,
      axisLabel: { ...AXIS_LABEL, hideOverlap: true },
    },
    yAxis: {
      type: 'value',
      name: '情绪极差',
      nameTextStyle: { color: '#8a94a6' },
      splitLine: SPLIT_LINE,
      axisLabel: AXIS_LABEL,
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
        lineStyle: { width: 2.2, color: '#673ab7' },
        areaStyle: { opacity: 0.15, color: '#673ab7' },
        data: perBucket.map(b => Number(b.sent_range)),
      },
    ],
  }
}

/** 平台完整信息（颜色/名称），供页面复用 */
export function platformMeta(code) {
  return PLATFORMS[code] || { name: code, color: '#666' }
}
