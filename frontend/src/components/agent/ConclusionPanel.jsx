import { Skeleton } from 'antd'
import { ChevronRight } from 'lucide'
import { platformName } from '../../utils/platforms'
import MorphGlyph from '../MorphGlyph'

/** 主控 Agent 归纳结论：summary + 风险提示 + 可验证断言（简洁分区，无卡片盒） */
export default function ConclusionPanel({ ct, loading }) {
  if (loading) {
    return <Skeleton active paragraph={{ rows: 5 }} title={false} />
  }
  return (
    <div>
      <p style={{ fontSize: 14.5, lineHeight: 1.9, color: 'var(--text-1)', margin: 0 }}>{ct.summary || '-'}</p>

      {ct.risk_flags?.length > 0 && (
        <div className="risk-list">
          {ct.risk_flags.map((r, i) => (
            <div key={i} className="risk-item">
              <span className="risk-item__dot" style={{ background: i === 0 ? 'var(--warning)' : 'var(--accent)' }} />
              <span className="risk-item__text">{r}</span>
            </div>
          ))}
        </div>
      )}

      <div className="claims">
        <div className="claims__title">可验证的判断</div>
        {ct.claims?.map((c, i) => (
          <div key={i} className="claims__row">
            <span className="claims__mark"><MorphGlyph icon={ChevronRight} size={13} /></span>
            <span className="claims__text">{c.text}</span>
            <span className="claims__src">[{c.platforms?.map(platformName).join('、')}]</span>
          </div>
        ))}
        {!ct.claims?.length && <div style={{ color: 'var(--text-3)', fontSize: 13 }}>暂无判断</div>}
      </div>
    </div>
  )
}
