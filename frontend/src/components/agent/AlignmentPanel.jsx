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
          当前为单平台分析，跨平台对齐图仅展示该平台自身时序。
        </div>
      )}
      <LieflatChartFrame
        className="chart-block"
        title="声量在平台之间呈现长周期错峰"
        subtitle="每根发丝代表等宽时间窗内的绝对峰值 / 最多 96 窗 / 缺失保持空白"
        code="L3 BARCODE LOLLIPOP"
        source="ALIGNED VOLUME / SOCIAL SENSE REPORT / CUSTOM BLUE"
      >
        {aligned?.time_axis?.length && Object.keys(aligned?.z_series || {}).length
          ? <AlignedBarcodeChart timeAxis={aligned.time_axis} zSeries={aligned.z_series} />
          : <Empty description="无可对齐的时序数据" />}
      </LieflatChartFrame>
      <LieflatChartFrame
        className="chart-block"
        title="各平台情绪集中区间并不相同"
        subtitle="每道山脊代表一个平台 / 横轴裁切至 1% 至 99% 分位且尾部并入两端 / 虚线为中位数"
        code="L19 RIDGELINE"
        source="ALIGNED SENTIMENT / SOCIAL SENSE REPORT / CUSTOM BLUE"
      >
        {Object.keys(aligned?.z_series || {}).length
          ? <SentimentRidgeline zSeries={aligned.z_series} />
          : <Empty description="无情绪时序数据" />}
      </LieflatChartFrame>
    </div>
  )
}
