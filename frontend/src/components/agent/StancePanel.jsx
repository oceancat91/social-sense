import { Empty, Skeleton } from 'antd'
import LieflatChartFrame from './LieflatChartFrame'
import StanceField from './StanceField'
import CorrelationArcMatrix from './CorrelationArcMatrix'

/** L14 立场单位场 + L4 弧形关系矩阵 */
export default function StancePanel({ stanceDist, temporalCorr, platforms, loading }) {
  if (loading) {
    return <Skeleton active paragraph={{ rows: 8 }} title={false} />
  }
  return (
    <div className="split">
      <div className="split__col">
        <LieflatChartFrame
          title="沉默的大多数，才是舆论的底色"
          subtitle="每个平台拆成 100 个点，一点代表 1%。"
          code="立场构成"
          source="Social Sense · 立场分布"
        >
          {Object.keys(stanceDist || {}).length
            ? <StanceField stanceDist={stanceDist} />
            : <Empty />}
        </LieflatChartFrame>
      </div>
      <div className="split__col">
        <LieflatChartFrame
          title="哪些平台在同声，哪些在背离"
          subtitle="圆越大共振越强，实心为同向，空心为反向。"
          code="共振关系"
          source="Social Sense · 跨平台共振"
        >
          {platforms?.length
            ? <CorrelationArcMatrix temporalCorr={temporalCorr} platforms={platforms} />
            : <Empty description="至少需要两个平台才能比较共振" />}
        </LieflatChartFrame>
      </div>
    </div>
  )
}
