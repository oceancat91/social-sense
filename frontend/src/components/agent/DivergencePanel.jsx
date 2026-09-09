import { Empty, Table, Skeleton } from 'antd'
import ReactECharts from 'echarts-for-react'
import SoftTag from './SoftTag'
import LieflatChartFrame from './LieflatChartFrame'

const gatesColumns = [
  { title: '门禁', dataIndex: 'gate', width: 90 },
  {
    title: '结果',
    dataIndex: 'pass',
    width: 96,
    render: (pass) => (
      <SoftTag color={pass ? 'var(--success)' : 'var(--danger)'}>
        {pass ? '通过' : '未通过'}
      </SoftTag>
    ),
  },
  { title: '说明', dataIndex: 'note' },
]

/** 分歧扩散（分桶情绪极差时序）+ 跨平台校准门禁（CX1-CX5），两列细分隔线 */
export default function DivergencePanel({ divergenceOption, calib, loading }) {
  if (loading) {
    return <Skeleton active paragraph={{ rows: 8 }} title={false} />
  }
  return (
    <div className="split">
      <div className="split__col">
        <LieflatChartFrame
          title="情绪分歧沿时间形成可见峰值"
          subtitle="每根垂线代表一个分歧时桶 / 顶点连接只呈现观测顺序"
          code="L3 BARCODE LOLLIPOP"
          source="SENTIMENT RANGE / SOCIAL SENSE REPORT / CUSTOM BLUE"
        >
          {divergenceOption
            ? <ReactECharts option={divergenceOption} style={{ height: 320 }} />
            : <Empty description="无分桶分歧数据" />}
        </LieflatChartFrame>
      </div>
      <div className="split__col">
        <div className="gates">
          <div className="gates__title">跨平台校准门禁（CX1-CX5）</div>
          <Table
            dataSource={calib.gates || []}
            columns={gatesColumns}
            rowKey="gate"
            size="small"
            pagination={false}
            footer={() => (
              <SoftTag color={calib.all_pass ? 'var(--success)' : 'var(--danger)'}>
                {calib.all_pass ? '全部通过' : '存在未通过门禁'}
              </SoftTag>
            )}
          />
        </div>
      </div>
    </div>
  )
}
