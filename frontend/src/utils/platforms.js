/** 平台与情感展示常量（与后端 app/constants.py 保持一致） */

export const PLATFORMS = {
  weibo: { name: '微博', color: '#E6162D' },
  douyin: { name: '抖音', color: '#161823' },
  xiaohongshu: { name: '小红书', color: '#FF2442' },
  bilibili: { name: 'B站', color: '#FB7299' },
  zhihu: { name: '知乎', color: '#0066FF' },
  kuaishou: { name: '快手', color: '#FF4906' },
}

export const SENTIMENTS = {
  positive: { name: '正面', color: '#52C41A' },
  neutral: { name: '中性', color: '#8C8C8C' },
  negative: { name: '负面', color: '#F5222D' },
}

export const PLATFORM_OPTIONS = [
  { value: 'all', label: '全部平台' },
  ...Object.entries(PLATFORMS).map(([value, p]) => ({ value, label: p.name })),
]

export function platformName(code) {
  return PLATFORMS[code]?.name || code
}

export function platformColor(code) {
  return PLATFORMS[code]?.color || '#666'
}
