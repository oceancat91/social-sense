import { Row, Col, Card, Alert, Empty } from 'antd'
import { ThunderboltOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'

/** 跨平台对齐呈现：统一时间轴上的声量/情绪 z-score 曲线（缺失断点不插值） */
export default function AlignmentPanel({ volumeOption, sentimentOption, isSingle, loading }) {
  return (
    <>
      <Card
        title={<span><ThunderboltOutlined style={{ color: 'var(--primary)' }} /> 跨平台对齐呈现（统一时间轴，缺失断点不插值）</span>}
        style={{ marginBottom: 16 }}
        loading={loading}
      >
        {isSingle && (
          <Alert type="info" showIcon message="当前为单平台分析，跨平台对齐图仅展示该平台自身时序。" style={{ marginBottom: 12 }} />
        )}
        {volumeOption ? <ReactECharts option={volumeOption} style={{ height: 340 }} /> : <Empty description="无可对齐的时序数据" />}
      </Card>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={24} xs={24}>
          <Card loading={loading}>
            {sentimentOption ? <ReactECharts option={sentimentOption} style={{ height: 320 }} /> : <Empty description="无情绪时序数据" />}
          </Card>
        </Col>
      </Row>
    </>
  )
}
