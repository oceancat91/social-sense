import { Empty, Table, Skeleton } from 'antd'
import ReactEChartsCore from 'echarts-for-react/lib/core'
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import SoftTag from './SoftTag'
import LieflatChartFrame from './LieflatChartFrame'

// 按需注册：本面板只画「分歧柱 + 分歧折线」，无需整包 echarts（约 1 MB -> 约 0.3 MB）。
echarts.use([BarChart, LineChart, GridComponent, TooltipComponent, CanvasRenderer])

const gatesColumns = [
  { title: '校验项', dataIndex: 'gate', width: 90 },
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

/** 分歧扩散（分桶分歧回一线时序）+ 可信校验，两列细分隔线 */
export default function DivergencePanel({ divergenceOption, calib, loading }) {
  if (loading) {
    return <Skeleton active paragraph={{ rows: 8 }} title={false} />
  }
  return (
    <div className="split">
      <div className="split__col">
        <LieflatChartFrame
          title="分歧在哪些时刻集中爆发"
          subtitle="每一根竖线代表一个时间点，越高分歧越大。"
          code="分歧强度"
          source="Social Sense · 情绪分歧"
        >
          {divergenceOption
            ? <ReactEChartsCore echarts={echarts} option={divergenceOption} style={{ height: 320 }} />
            : <Empty description="暂无可用数据" />}
        </LieflatChartFrame>
      </div>
      <div className="split__col">
        <div className="gates">
          <div className="gates__title">可信校验</div>
          <Table
            dataSource={calib.gates || []}
            columns={gatesColumns}
            rowKey="gate"
            size="small"
            pagination={false}
            footer={() => (
              <SoftTag color={calib.all_pass ? 'var(--success)' : 'var(--danger)'}>
                {calib.all_pass ? '全部通过' : '有项目未通过'}
              </SoftTag>
            )}
          />
        </div>
      </div>
    </div>
  )
}
