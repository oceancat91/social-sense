/** 平台与情感展示常量（与后端 app/constants.py 保持一致） */

/** 平台色：color 用于浅色；colorDark 为深色主题下的提亮变体，保证炭黑底可读 */
export const PLATFORMS = {
  weibo: { name: '微博', color: '#E6162D', colorDark: '#FF7A88' },
  douyin: { name: '抖音', color: '#1F2228', colorDark: '#9AA3AD' },
  xiaohongshu: { name: '小红书', color: '#FF2442', colorDark: '#FF5E75' },
  bilibili: { name: 'B站', color: '#FB7299', colorDark: '#FF8FB0' },
  zhihu: { name: '知乎', color: '#0066FF', colorDark: '#4D94FF' },
  kuaishou: { name: '快手', color: '#FF4906', colorDark: '#FF7848' },
}

export const SENTIMENTS = {
  positive: { name: '正面', color: '#15803D', colorDark: '#3ECF8E' },
  neutral: { name: '中性', color: '#8B9096', colorDark: '#A5ACB3' },
  negative: { name: '负面', color: '#B91C1C', colorDark: '#F26B5E' },
}

export const PLATFORM_OPTIONS = [
  { value: 'all', label: '全部平台' },
  ...Object.entries(PLATFORMS).map(([value, p]) => ({ value, label: p.name })),
]

export function platformName(code) {
  return PLATFORMS[code]?.name || code
}

/** 平台色（可指定 dark，深色下自动使用提亮变体） */
export function platformColor(code, dark = false) {
  const p = PLATFORMS[code]
  if (!p) return dark ? '#9AA3AD' : '#666'
  return dark ? p.colorDark || p.color : p.color
}

export function sentimentColor(code, dark = false) {
  const s = SENTIMENTS[code]
  if (!s) return dark ? '#A5ACB3' : '#8B9096'
  return dark ? s.colorDark || s.color : s.color
}
