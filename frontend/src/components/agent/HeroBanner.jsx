import { useEffect, useRef, useState } from 'react'
import { Select, Button } from 'antd'
import { RefreshCw, Check } from 'lucide'
import MorphGlyph from '../MorphGlyph'

/**
 * 分析台 hero 区：大标题 + 副标题 + 报告选择器。
 * 背景氛围由页面级 AgentBackground 统一提供。
 *
 * 刷新按钮的图标在 RefreshCw 与 Check 之间由 morphicons 做真实形变，
 * 同一位置同时表达「正在拉取」与「已经是新的」，不需要额外的提示条。
 */
export default function HeroBanner({ selectedId, reportOptions, onSelect, onRefresh }) {
  const [done, setDone] = useState(false)
  const timer = useRef(0)

  useEffect(() => () => window.clearTimeout(timer.current), [])

  const handleRefresh = async () => {
    try {
      await onRefresh?.()
      setDone(true)
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(() => setDone(false), 1600)
    } catch {
      // 失败提示由上层 message 负责，图标保持原样
    }
  }

  return (
    <section className="ss-hero">
      <div className="ss-hero__copy">
        <h1>六大平台舆情，一屏看透</h1>
        <p>情绪分歧、声量共振、回声室强度，六个平台的变化一屏看清。</p>
      </div>
      <div className="ss-hero__side">
        <div className="ss-hero__controls">
          <Select
            style={{ flex: 1, minWidth: 220 }}
            placeholder="选择分析报告"
            value={selectedId}
            onChange={onSelect}
            options={reportOptions}
            showSearch
            optionFilterProp="label"
            notFoundContent="暂无报告"
          />
          <Button
            onClick={handleRefresh}
            icon={<MorphGlyph icon={done ? Check : RefreshCw} size={16} />}
          >
            刷新
          </Button>
        </div>
      </div>
    </section>
  )
}
