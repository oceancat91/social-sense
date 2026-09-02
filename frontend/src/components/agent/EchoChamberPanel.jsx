import { Card, Empty } from 'antd'
import ReactECharts from 'echarts-for-react'
import { echoGaugeOption } from '../../utils/agentCharts'

/** 信息茧房指数仪表盘 */
export default function EchoChamberPanel({ echoScore, loading }) {
  return (
    <Card title="信息茧房指数" loading={loading}>
      {echoScore != null
        ? <ReactECharts option={echoGaugeOption(echoScore)} style={{ height: 240 }} />
        : <Empty />}
    </Card>
  )
}
