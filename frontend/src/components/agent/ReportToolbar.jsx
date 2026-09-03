import { Select, Button, Space } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'

/** 顶部报告工具栏：标题 + 报告选择器 + 刷新 */
export default function ReportToolbar({ selectedId, reportOptions, onSelect, onRefresh }) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: 20,
      flexWrap: 'wrap',
      gap: 12,
    }}>
      <h2 className="page-title">
        <span className="page-title-mark" />
        跨平台多 Agent 舆情分析
      </h2>
      <Space wrap>
        <Select
          style={{ minWidth: 380 }}
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
