import { Space, Progress, Tooltip, Skeleton } from 'antd'
import { ClusterOutlined } from '@ant-design/icons'
import { platformColor, platformName } from '../../utils/platforms'
import { STANCE_META, stanceColor } from '../../utils/agentCharts'
import SoftTag from './SoftTag'
import EchoSignal from './EchoSignal'
import CountUp from './CountUp'
import { REPORT_STATUS, CT_STATUS } from './constants'

function EchoBand({ label, percent, tone }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <span style={{ width: 8, height: 8, borderRadius: 4, flexShrink: 0, background: tone }} />
      <span style={{ fontSize: 13, color: 'var(--text-2)', flex: 1, minWidth: 0 }}>{label}</span>
      <Progress percent={percent} size="small" showInfo={false} strokeColor={tone} style={{ width: 90 }} />
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

const DARK_STATUS_TONE = {
  success: '#3ECF8E',
  processing: '#60A5FA',
  warning: '#F0A63F',
  error: '#F26B5E',
  default: '#A5ACB3',
}

function ReportStatusChip({ text, color, dark }) {
  const tone = dark ? DARK_STATUS_TONE[color] : STATUS_TONE[color]
  return <SoftTag color={tone || (dark ? '#A5ACB3' : 'var(--text-3)')}>{text}</SoftTag>
}

/**
 * 报告概览：三列细分隔线分栏（无卡片盒）。
 * 左 = 深色关键词块（直角、无边框阴影），中 = 回声室指数涟漪环，
 * 右 = 声量共振 + 回声室三分量 + 各平台主导立场。
 */
export default function ReportOverview({
  detail, ct, platforms, echoScore, components, dominant, fusion, loading,
}) {
  const statusMeta = REPORT_STATUS[detail?.status] || { text: detail?.status, color: 'default' }
  const ctMeta = CT_STATUS[ct.CT_status] || { text: ct.CT_status, color: 'default' }

  return (
    <div className="overview">
      {/* 深色关键词块 */}
      <div className="overview__col">
        <div className="overview-key">
          {loading ? (
            <Skeleton active paragraph={{ rows: 3 }} title={false} />
          ) : (
            <>
              <div className="overview-key__label">ANALYSIS TARGET</div>
              <div className="overview-key__title">{ct.keyword || '-'}</div>
              <div className="overview-key__tags">
                {platforms.map((p) => (
                  <SoftTag key={p} color={platformColor(p, true)}>
                    {platformName(p)}
                  </SoftTag>
                ))}
              </div>
              <div className="overview-key__status">
                <ReportStatusChip text={statusMeta.text} color={statusMeta.color} dark />
                <ReportStatusChip text={ctMeta.text} color={ctMeta.color} dark />
              </div>
              <div className="overview-key__meta">
                时间范围：{ct.time_range
                  ? `${(ct.time_range.start || '').slice(0, 10)} ~ ${(ct.time_range.end || '').slice(0, 10)}`
                  : '-'}
                <span style={{ margin: '0 6px' }}>/</span>粒度：{ct.granularity}
              </div>
            </>
          )}
        </div>
      </div>

      {/* 回声室指数涟漪环 */}
      <div className="overview__col overview__echo">
        <div className="overview-echo__title">回声室指数</div>
        <div className="overview-echo__ring">
          <EchoSignal score={echoScore} loading={loading} />
        </div>
        <div className="overview-echo__hint">弧越闭合 / 茧房越强</div>
      </div>

      {/* 声量共振 + 三分量 + 主导立场 */}
      <div className="overview__col">
        {loading ? (
          <Skeleton active paragraph={{ rows: 5 }} title={false} />
        ) : (
          <div className="overview-stats">
            <div className="metric">
              <div className="metric__icon">
                <ClusterOutlined />
              </div>
              <div className="metric__main">
                <div className="metric__label">声量共振</div>
                <div className="metric__value">
                  {fusion.mean_volume_corr != null
                    ? <CountUp value={Number(fusion.mean_volume_corr)} decimals={3} />
                    : '-'}
                </div>
              </div>
            </div>

            <div className="overview-stats__block">
              <div className="overview-stats__label">回声室三分量</div>
              <Space direction="vertical" size={10} style={{ width: '100%' }}>
                <EchoBand label="立场分歧" percent={Math.round((components.stance ?? 0) * 100)} tone="var(--warning)" />
                <EchoBand label="情绪分歧" percent={Math.round((components.sentiment ?? 0) * 100)} tone="var(--danger)" />
                <EchoBand label="声量失振" percent={Math.round((components.corr ?? 0) * 100)} tone="var(--accent)" />
              </Space>
            </div>

            <div className="overview-stats__block">
              <div className="overview-stats__label">各平台主导立场</div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {platforms.map((p) => (
                  <Tooltip key={p} title={platformName(p)}>
                    <SoftTag
                      color={stanceColor(dominant[p], false)}
                      colorDark={stanceColor(dominant[p], true)}
                    >
                      {platformName(p)} / {STANCE_META[dominant[p]]?.name || '不明'}
                    </SoftTag>
                  </Tooltip>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
