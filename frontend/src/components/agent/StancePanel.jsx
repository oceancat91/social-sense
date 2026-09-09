import { Empty, Skeleton } from 'antd'
import ReactECharts from 'echarts-for-react'

/** 立场对齐（各平台立场分布堆叠）+ 声量共振（两两相关性矩阵），两列细分隔线 */
export default function StancePanel({ stanceOption, corrOption, loading }) {
  if (loading) {
    return <Skeleton active paragraph={{ rows: 8 }} title={false} />
  }
  return (
    <div className="split">
      <div className="split__col">
        {stanceOption
          ? <ReactECharts option={stanceOption} style={{ height: 320 }} />
          : <Empty />}
      </div>
      <div className="split__col">
        {corrOption
          ? <ReactECharts option={corrOption} style={{ height: 320 }} />
          : <Empty description="至少需两个平台方可计算共振" />}
      </div>
    </div>
  )
}
