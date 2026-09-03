import { Row, Col, Card, Space, Progress, Tooltip } from 'antd'
import { SafetyCertificateOutlined, ClusterOutlined } from '@ant-design/icons'
import { platformColor, platformName } from '../../utils/platforms'
import { STANCE_META, stanceColor } from '../../utils/agentCharts'
import StatCard from './StatCard'
import SoftTag from './SoftTag'
import { REPORT_STATUS, CT_STATUS } from './constants'

function EchoBand({ label, percent, tone }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: 4,
          flexShrink: 0,
          background: tone,
        }}
      />
      <span style={{ fontSize: 13, color: 'var(--text-2)', flex: 1, minWidth: 0 }}>{label}</span>
      <Progress
        percent={percent}
        size="small"
        showInfo={false}
        strokeColor={tone}
        style={{ width: 90 }}
      />
      <span className="tnum" style={{ fontSize: 13, color: 'var(--text-1)', minWidth: 44, textAlign: 'right' }}>
        {percent}%
      </span>
    </div>
  )
}

const STATUS_TONE = {
  success: 'var(--success)',
  processing: 'var(--accent)',
  warning: 'var(--warning)',
  error: 'var(--danger)',
  default: 'var(--text-3)',
}

function ReportStatusChip({ text, color }) {
  return <SoftTag color={STATUS_TONE[color] || 'var(--text-3)'}>{text}</SoftTag>
}

/** 报告概览：元信息 + 回声室指数/声量共振 + 三分量 + 各平台主导立场 */
export default function ReportOverview({
  detail, ct, platforms, echoScore, components, dominant, fusion, loading,
}) {
  const statusMeta = REPORT_STATUS[detail?.status] || { text: detail?.status, color: 'default' }
  const ctMeta = CT_STATUS[ct.CT_status] || { text: ct.CT_status, color: 'default' }

  return (
    <Row gutter={16} style={{ marginBottom: 16 }}>
      <Col span={8} xs={24}>
        <Card loading={loading} style={{ height: '100%' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ fontSize: 20, fontWeight: 650, letterSpacing: '-0.02em' }}>
              {ct.keyword || '-'}
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {platforms.map((p) => (
                <SoftTag key={p} color={platformColor(p, false)} colorDark={platformColor(p, true)}>
                  {platformName(p)}
                </SoftTag>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 2 }}>
              <ReportStatusChip text={statusMeta.text} color={statusMeta.color} />
              <ReportStatusChip text={ctMeta.text} color={ctMeta.color} />
            </div>
            <div style={{ color: 'var(--text-3)', fontSize: 12.5, borderTop: '1px solid var(--border-faint)', paddingTop: 10 }}>
              时间范围：{ct.time_range
                ? `${(ct.time_range.start || '').slice(0, 10)} ~ ${(ct.time_range.end || '').slice(0, 10)}`
                : '-'}
              <span style={{ margin: '0 6px' }}>·</span>粒度：{ct.granularity}
            </div>
          </div>
        </Card>
      </Col>

      <Col span={8} xs={24}>
        <StatCard
          title="回声室指数"
          loading={loading}
          value={echoScore != null ? (echoScore * 100).toFixed(1) : '-'}
          suffix="%"
          tone={echoScore >= 0.5 ? 'danger' : echoScore >= 0.25 ? 'warning' : 'success'}
          icon={<SafetyCertificateOutlined />}
        />
        <StatCard
          title="声量共振"
          loading={loading}
          value={fusion.mean_volume_corr != null ? Number(fusion.mean_volume_corr).toFixed(3) : '-'}
          tone="accent"
          icon={<ClusterOutlined />}
        />
      </Col>

      <Col span={8} xs={24}>
        <Card loading={loading} style={{ height: '100%' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 10 }}>回声室三分量</div>
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                <EchoBand label="立场分歧" percent={Math.round((components.stance ?? 0) * 100)} tone="var(--warning)" />
                <EchoBand label="情绪分歧" percent={Math.round((components.sentiment ?? 0) * 100)} tone="var(--danger)" />
                <EchoBand label="声量失振" percent={Math.round((components.corr ?? 0) * 100)} tone="var(--accent)" />
              </Space>
            </div>
            <div style={{ borderTop: '1px solid var(--border-faint)', paddingTop: 12 }}>
              <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 10 }}>各平台主导立场</div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {platforms.map((p) => (
                  <Tooltip key={p} title={platformName(p)}>
                    <SoftTag
                      color={stanceColor(dominant[p], false)}
                      colorDark={stanceColor(dominant[p], true)}
                    >
                      {platformName(p)} · {STANCE_META[dominant[p]]?.name || '不明'}
                    </SoftTag>
                  </Tooltip>
                ))}
              </div>
            </div>
          </div>
        </Card>
      </Col>
    </Row>
  )
}
