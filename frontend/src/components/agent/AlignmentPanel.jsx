import { Empty, Skeleton } from 'antd'
import LieflatChartFrame from './LieflatChartFrame'
import AlignedBarcodeChart from './AlignedBarcodeChart'
import SentimentRidgeline from './SentimentRidgeline'

/** 长时序改为窗口峰值条码，情绪改为分组分布脊线。 */
export default function AlignmentPanel({ aligned, isSingle, loading }) {
  if (loading) {
    return <Skeleton active paragraph={{ rows: 8 }} title={false} />
  }
  return (
    <div>
      {isSingle && (
        <div className="note">
          <span className="note__tag">提示</span>
          当前只有单一平台的数据，跨平台对比暂时做不了。
        </div>
      )}
      <LieflatChartFrame
        className="chart-block"
        title="同一件事，各平台的热度并不同步"
        subtitle="谁先火、谁在跟，一根根看得很清楚。"
        code="跨平台热度"
        source="Social Sense · 跨平台声量"
      >
        {aligned?.time_axis?.length && Object.keys(aligned?.z_series || {}).length
          ? <AlignedBarcodeChart timeAxis={aligned.time_axis} zSeries={aligned.z_series} />
          : <Empty description="暂无可用数据" />}
      </LieflatChartFrame>
      <LieflatChartFrame
        className="chart-block"
        title="每个平台的情绪重心，落在不同位置"
        subtitle="山脊越高，说明该平台的情绪越集中。"
        code="情绪分布"
        source="Social Sense · 情绪分布"
      >
        {Object.keys(aligned?.z_series || {}).length
          ? <SentimentRidgeline zSeries={aligned.z_series} />
          : <Empty description="暂无可用数据" />}
      </LieflatChartFrame>
    </div>
  )
}
