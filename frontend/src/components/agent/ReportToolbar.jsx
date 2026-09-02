import { Select, Button, Space } from 'antd'
import { RobotOutlined, ReloadOutlined } from '@ant-design/icons'

/** 顶部报告工具栏：标题 + 报告选择器 + 刷新 */
export default function ReportToolbar({ selectedId, reportOptions, onSelect, onRefresh }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
      <h2 className="page-title">
        <RobotOutlined style={{ color: 'var(--primary)' }} /> 多 Agent 跨平台分析
      </h2>
      <Space wrap>
        <Select
          style={{ minWidth: 360 }}
          placeholder="选择分析报告"
          value={selectedId}
          onChange={onSelect}
          options={reportOptions}
          showSearch
          optionFilterProp="label"
          notFoundContent="暂无报告"
        />
        <Button icon={<ReloadOutlined />} onClick={onRefresh}>刷新</Button>
      </Space>
    </div>
  )
}
