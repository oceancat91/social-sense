import { Card, Empty } from 'antd'
import ReactECharts from 'echarts-for-react'
import { echoGaugeOption } from '../../utils/agentCharts'
import { useDarkMode } from '../../theme'

/** 回声室指数仪表盘 */
export default function EchoChamberPanel({ echoScore, loading }) {
  const dark = useDarkMode()
  return (
    <Card title="回声室指数" loading={loading}>
      {echoScore != null
        ? <ReactECharts option={echoGaugeOption(echoScore, dark)} style={{ height: 240 }} />
        : <Empty />}
    </Card>
  )
}
