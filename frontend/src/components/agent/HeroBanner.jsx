import { Select, Button } from 'antd'

/**
 * 分析台 hero 区：大标题 + 副标题 + 报告选择器。
 * 背景氛围由页面级 AgentBackground 统一提供。
 */

export default function HeroBanner({ selectedId, reportOptions, onSelect, onRefresh }) {
  return (
    <section className="ss-hero">
      <div className="ss-hero__copy">
        <h1>跨平台多 Agent 舆情分析</h1>
        <p>六平台实时采集，统一时间轴与口径，量化情绪分歧、声量共振与回声室强度。</p>
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
          <Button onClick={onRefresh}>刷新</Button>
        </div>
      </div>
    </section>
  )
}
