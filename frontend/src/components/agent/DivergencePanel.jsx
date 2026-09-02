import { Row, Col, Card, Empty, Table, Tag } from 'antd'
import ReactECharts from 'echarts-for-react'

const gatesColumns = [
  { title: '门禁', dataIndex: 'gate', width: 80 },
  {
    title: '结果', dataIndex: 'pass', width: 90,
    render: pass => <Tag color={pass ? 'success' : 'error'}>{pass ? '通过' : '未通过'}</Tag>,
  },
  { title: '说明', dataIndex: 'note' },
]

/** 分歧扩散（分桶情绪极差时序）+ 跨平台校准门禁（CX1–CX5） */
export default function DivergencePanel({ divergenceOption, calib, loading }) {
  return (
    <Row gutter={16} style={{ marginBottom: 16 }}>
      <Col span={12} xs={24}>
        <Card loading={loading}>
          {divergenceOption ? <ReactECharts option={divergenceOption} style={{ height: 320 }} /> : <Empty description="无分桶分歧数据" />}
        </Card>
      </Col>
      <Col span={12} xs={24}>
        <Card title="跨平台校准门禁（CX1–CX5）" loading={loading}>
          <Table
            dataSource={calib.gates || []}
            columns={gatesColumns}
            rowKey="gate"
            size="small"
            pagination={false}
            footer={() => (
              <Tag color={(calib.all_pass ? 'success' : 'error')} style={{ marginTop: 4 }}>
                {calib.all_pass ? '全部通过' : '存在未通过门禁'}
              </Tag>
            )}
          />
        </Card>
      </Col>
    </Row>
  )
}
