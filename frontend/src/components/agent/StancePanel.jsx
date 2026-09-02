import { Row, Col, Card, Empty } from 'antd'
import ReactECharts from 'echarts-for-react'

/** 立场对齐（各平台立场分布堆叠）+ 声量共振（两两相关性矩阵） */
export default function StancePanel({ stanceOption, corrOption, loading }) {
  return (
    <Row gutter={16} style={{ marginBottom: 16 }}>
      <Col span={12} xs={24}>
        <Card loading={loading}>
          {stanceOption ? <ReactECharts option={stanceOption} style={{ height: 320 }} /> : <Empty />}
        </Card>
      </Col>
      <Col span={12} xs={24}>
        <Card loading={loading}>
          {corrOption ? <ReactECharts option={corrOption} style={{ height: 320 }} /> : <Empty description="至少需两个平台方可计算共振" />}
        </Card>
      </Col>
    </Row>
  )
}
