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
          title="中立讨论占据多数平台"
          subtitle="每个平台严格拆成 100 个单位点 / 一点代表 1%"
          code="L14 HUNDRED FIELD"
          source="STANCE DISTRIBUTION / SOCIAL SENSE REPORT / CUSTOM BLUE"
        >
          {Object.keys(stanceDist || {}).length
            ? <StanceField stanceDist={stanceDist} />
            : <Empty />}
        </LieflatChartFrame>
      </div>
      <div className="split__col">
        <LieflatChartFrame
          title="共振关系沿平台弧线展开"
          subtitle="圆面积编码相关强度 / 实心为正相关 / 空心为负相关"
          code="L4 ARC MATRIX"
          source="TEMPORAL CORRELATION / SOCIAL SENSE REPORT / CUSTOM BLUE"
        >
          {platforms?.length
            ? <CorrelationArcMatrix temporalCorr={temporalCorr} platforms={platforms} />
            : <Empty description="至少需两个平台方可计算共振" />}
        </LieflatChartFrame>
      </div>
    </div>
  )
}
