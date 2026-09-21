/**
 * 多 Agent 跨平台报告的 ECharts option。
 *
 * 数据来源均为 `GET /api/v1/agent/reports/:id` 返回的 result：
 * 当前仅保留分桶情绪分歧；其余图型已迁移到 Lieflat SVG 原语。
 *
 * 主题化仍接受 dark 参数以维持调用契约，但页面固定使用浅色 custom 色板。
 */

import { PLATFORMS } from './platforms'
import { LIEFLAT } from '../components/agent/lieflatTheme'

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

function themePalette() {
  return {
    faint: LIEFLAT.MUT,
    axisLine: LIEFLAT.FLOOR,
    splitLine: LIEFLAT.GRID,
    tooltipBg: LIEFLAT.BG,
    tooltipBorder: LIEFLAT.FLOOR,
    tooltipText: LIEFLAT.TXT,
    accent: LIEFLAT.HERO,
  }
}

const AXIS_LABEL = (dark) => ({ color: themePalette(dark).faint })
const AXIS_LINE = (dark) => ({ lineStyle: { color: themePalette(dark).axisLine } })
const SPLIT_LINE = (dark) => ({ lineStyle: { color: themePalette(dark).splitLine } })
const tooltipStyle = (dark) => {
  const p = themePalette(dark)
  return {
    backgroundColor: p.tooltipBg,
    borderColor: p.tooltipBorder,
    textStyle: { color: p.tooltipText },
    extraCssText: 'border-radius:4px;',
  }
}

/**
 * 分桶跨平台情绪分歧时序。
 */
export function divergenceTimelineOption(perBucket, dark = false) {
  if (!perBucket?.length) return null
  const p = themePalette(dark)
  const values = perBucket.map((bucket) => Number(bucket.sent_range))

  return {
    animationDuration: 900,
    animationEasing: 'quarticOut',
    tooltip: {
      trigger: 'axis',
      ...tooltipStyle(dark),
      formatter: (params) => {
        const item = params[0]
        const raw = perBucket[item?.dataIndex]
        return raw
          ? `时间 ${raw.ts.slice(0, 10)}<br/>分歧幅度 <b>${Number(raw.sent_range).toFixed(4)}</b><br/>参与平台 ${raw.active_platforms}`
          : ''
      },
    },
    grid: { left: 48, right: 24, top: 18, bottom: 34 },
    xAxis: {
      type: 'category',
      data: perBucket.map((b) => b.ts.slice(5, 10)),
      boundaryGap: false,
      axisLine: AXIS_LINE(dark),
      axisLabel: { ...AXIS_LABEL(dark), hideOverlap: true },
    },
    yAxis: {
      type: 'value',
      name: '分歧幅度',
      nameTextStyle: { color: p.faint },
      splitLine: SPLIT_LINE(dark),
      axisLabel: AXIS_LABEL(dark),
      scale: true,
    },
    series: [
      {
        name: '分歧柱',
        type: 'bar',
        barWidth: 1.4,
        silent: true,
        itemStyle: { color: LIEFLAT.DATA2, opacity: 0.85 },
        data: values,
      },
      {
        name: '分歧幅度',
        type: 'line',
        smooth: false,
        symbol: 'none',
        large: true,
        sampling: 'lttb',
        lineStyle: { width: 1.8, color: p.accent },
        data: values,
      },
    ],
  }
}

/** 平台完整信息（颜色/名称），供页面复用 */
export function platformMeta(code) {
  return PLATFORMS[code] || { name: code, color: '#666' }
}
