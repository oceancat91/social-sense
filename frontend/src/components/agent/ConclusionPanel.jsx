import { Card, Alert } from 'antd'
import { platformName } from '../../utils/platforms'

/** 主控 Agent 归纳结论：summary + 风险提示 + 可验证断言 */
export default function ConclusionPanel({ ct, loading }) {
  return (
    <Card title="跨平台结论（主控 Agent 归纳）" loading={loading}>
      <p style={{ fontSize: 14.5, lineHeight: 1.9, color: 'var(--text-1)' }}>{ct.summary || '-'}</p>
      <div style={{ margin: '12px 0' }}>
        {ct.risk_flags?.map((r, i) => (
          <Alert
            key={i}
            type={i === 0 ? 'warning' : 'info'}
            showIcon
            message={r}
            style={{ marginBottom: 8 }}
          />
        ))}
      </div>
      <div style={{ fontWeight: 600, fontSize: 14, margin: '8px 0 4px' }}>可验证断言（claims）</div>
      <div style={{ maxHeight: 208, overflow: 'auto', marginTop: 6 }}>
        {ct.claims?.map((c, i) => (
          <div
            key={i}
            style={{
              padding: '8px 2px',
              borderTop: i === 0 ? '1px solid var(--border-faint)' : 'none',
              borderBottom: '1px solid var(--border-faint)',
              fontSize: 13,
              display: 'flex',
              alignItems: 'baseline',
              gap: 8,
            }}
          >
            <span style={{ color: 'var(--accent)', flexShrink: 0 }}>›</span>
            <span style={{ color: 'var(--text-2)' }}>{c.text}</span>
            <span style={{ color: 'var(--text-3)', marginLeft: 'auto', whiteSpace: 'nowrap', fontSize: 12 }}>
              [{c.platforms?.map(platformName).join('、')}]
            </span>
          </div>
        ))}
        {!ct.claims?.length && <div style={{ color: 'var(--text-3)', fontSize: 13 }}>无断言</div>}
      </div>
    </Card>
  )
}
