import { Card, Alert } from 'antd'
import { platformName } from '../../utils/platforms'

/** 主控 Agent 归纳结论：summary + 风险提示 + 可验证断言 */
export default function ConclusionPanel({ ct, loading }) {
  return (
    <Card title="跨平台结论（主控 Agent 归纳）" loading={loading}>
      <p style={{ fontSize: 14, lineHeight: 1.8, color: '#3a4356' }}>{ct.summary || '-'}</p>
      <div style={{ margin: '12px 0' }}>
        {ct.risk_flags?.map((r, i) => (
          <Alert key={i} type={i === 0 ? 'warning' : 'info'} showIcon message={r}
            style={{ marginBottom: 8 }} />
        ))}
      </div>
      <div style={{ fontWeight: 600, margin: '8px 0 4px' }}>可验证断言（claims）</div>
      <div style={{ maxHeight: 200, overflow: 'auto' }}>
        {ct.claims?.map((c, i) => (
          <div key={i} style={{ padding: '6px 0', borderBottom: '1px solid #f0f2f7', fontSize: 13 }}>
            <span style={{ color: '#5b6472' }}>· {c.text}</span>
            <span style={{ color: '#8a94a6', marginLeft: 8 }}>
              [{c.platforms?.map(platformName).join('、')}]
            </span>
          </div>
        ))}
      </div>
    </Card>
  )
}
