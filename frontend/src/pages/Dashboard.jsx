import { useEffect, useState } from 'react'
import { Row, Col, Card, Statistic } from 'antd'
import ReactECharts from 'echarts-for-react'
import api from '../services/api'

function Dashboard() {
  const [overview, setOverview] = useState({ total: 0, positive: 0, negative: 0, neutral: 0 })

  useEffect(() => {
    api.get('/analysis/overview')
      .then(res => setOverview(res.data.data))
      .catch(() => {})
  }, [])

  const pieOption = {
    title: { text: '情感分布', left: 'center' },
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie',
      radius: '60%',
      data: [
        { value: overview.positive, name: '正面' },
        { value: overview.negative, name: '负面' },
        { value: overview.neutral, name: '中性' },
      ],
      emphasis: { itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0, 0, 0, 0.5)' } }
    }]
  }

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>数据看板</h2>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}><Card><Statistic title="数据总量" value={overview.total} /></Card></Col>
        <Col span={6}><Card><Statistic title="正面舆情" value={overview.positive} valueStyle={{ color: '#3f8600' }} /></Card></Col>
        <Col span={6}><Card><Statistic title="负面舆情" value={overview.negative} valueStyle={{ color: '#cf1322' }} /></Card></Col>
        <Col span={6}><Card><Statistic title="中性舆情" value={overview.neutral} valueStyle={{ color: '#999' }} /></Card></Col>
      </Row>
      <Card>
        <ReactECharts option={pieOption} style={{ height: 400 }} />
      </Card>
    </div>
  )
}

export default Dashboard
