import { Empty, Skeleton } from 'antd'
import ReactECharts from 'echarts-for-react'

/** 跨平台对齐呈现：统一时间轴上的声量/情绪 z-score 曲线（缺失断点不插值，无卡片盒） */
export default function AlignmentPanel({ volumeOption, sentimentOption, isSingle, loading }) {
  if (loading) {
    return <Skeleton active paragraph={{ rows: 8 }} title={false} />
  }
  return (
    <div>
      {isSingle && (
        <div className="note">
          <span className="note__tag">提示</span>
          当前为单平台分析，跨平台对齐图仅展示该平台自身时序。
        </div>
      )}
      <div className="chart-block">
        <div className="chart-block__title">
          跨平台声量对齐（z-score，统一时间轴）
          <span className="chart-block__meta">缺失断点不插值</span>
        </div>
        {volumeOption
          ? <ReactECharts option={volumeOption} style={{ height: 340 }} />
          : <Empty description="无可对齐的时序数据" />}
      </div>
      <div className="chart-block">
        <div className="chart-block__title">跨平台情绪均值对齐（z-score）</div>
        {sentimentOption
          ? <ReactECharts option={sentimentOption} style={{ height: 320 }} />
          : <Empty description="无情绪时序数据" />}
      </div>
    </div>
  )
}
