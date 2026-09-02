import { Row, Col, Card, Tag, Space, Progress, Tooltip } from 'antd'
import { SafetyCertificateOutlined, ClusterOutlined } from '@ant-design/icons'
import { platformColor, platformName } from '../../utils/platforms'
import { STANCE_META } from '../../utils/agentCharts'
import StatCard from './StatCard'
import { REPORT_STATUS, CT_STATUS } from './constants'

/** 报告概览：元信息 + 茧房指数/声量共振统计 + 茧房三分量 + 各平台主导立场 */
export default function ReportOverview({
  detail, ct, platforms, echoScore, components, dominant, fusion, loading,
}) {
  const echoColor = echoScore >= 0.5
    ? 'linear-gradient(135deg,#d4380d,#ff8a4d)'
    : echoScore >= 0.25
      ? 'linear-gradient(135deg,#fa8c16,#ffc53d)'
      : 'linear-gradient(135deg,#0e9f6e,#3ecf96)'

  return (
    <Row gutter={16} style={{ marginBottom: 16 }}>
      <Col span={8} xs={24}>
        <Card loading={loading} style={{ height: '100%' }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontSize: 16, fontWeight: 700 }}>{ct.keyword || '-'}</span>
            <Tag color="blue">{REPORT_STATUS[detail?.status]?.text || detail?.status}</Tag>
            <Tag color={CT_STATUS[ct.CT_status]?.color}>{CT_STATUS[ct.CT_status]?.text || ct.CT_status}</Tag>
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {platforms.map(p => (
              <Tag key={p} color={platformColor(p)}>{platformName(p)}</Tag>
            ))}
          </div>
          <div style={{ color: '#8a94a6', fontSize: 12, marginTop: 8 }}>
            时间范围：{ct.time_range ? `${(ct.time_range.start || '').slice(0, 10)} ~ ${(ct.time_range.end || '').slice(0, 10)}` : '-'}
            {' '}· 粒度：{ct.granularity}
          </div>
        </Card>
      </Col>
      <Col span={8} xs={24}>
        <StatCard title="信息茧房指数" loading={loading}
          value={echoScore != null ? (echoScore * 100).toFixed(1) : '-'} suffix="%"
          color={echoColor}
          icon={<SafetyCertificateOutlined />} />
        <StatCard title="声量共振" loading={loading}
          value={fusion.mean_volume_corr != null ? Number(fusion.mean_volume_corr).toFixed(3) : '-'}
          suffix=""
          color="linear-gradient(135deg,#673ab7,#9c6bff)"
          icon={<ClusterOutlined />} />
      </Col>
      <Col span={8} xs={24}>
        <Card loading={loading} style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>茧房三分量</div>
          <Space direction="vertical" style={{ width: '100%' }} size={4}>
            <Progress percent={Math.round((components.stance ?? 0) * 100)} size="small"
              format={p => `立场分歧 ${p}%`} strokeColor="#FA8C16" />
            <Progress percent={Math.round((components.sentiment ?? 0) * 100)} size="small"
              format={p => `情绪分歧 ${p}%`} strokeColor="#F5222D" />
            <Progress percent={Math.round((components.corr ?? 0) * 100)} size="small"
              format={p => `声量失振 ${p}%`} strokeColor="#673ab7" />
          </Space>
        </Card>
        <Card loading={loading}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>各平台主导立场</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {platforms.map(p => (
              <Tooltip key={p} title={platformName(p)}>
                <Tag color={STANCE_META[dominant[p]]?.color || '#d9d9d9'}>
                  {platformName(p)} · {STANCE_META[dominant[p]]?.name || '不明'}
                </Tag>
              </Tooltip>
            ))}
          </div>
        </Card>
      </Col>
    </Row>
  )
}
