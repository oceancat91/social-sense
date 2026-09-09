import { Skeleton } from 'antd'
import { platformName } from '../../utils/platforms'
import { STANCE_META } from '../../utils/agentCharts'
import EchoSignal from './EchoSignal'
import CountUp from './CountUp'
import { REPORT_STATUS, CT_STATUS } from './constants'
import { LIEFLAT } from './lieflatTheme'

function EchoBand({ label, percent, shade }) {
  const filled = Math.round(percent / 5)
  return (
    <div className="echo-band">
      <span className="echo-band__label">{label}</span>
      <span className="echo-band__ticks" aria-hidden="true">
        {Array.from({ length: 20 }, (_, index) => (
          <span
            key={index}
            className="echo-band__tick"
            style={{ backgroundColor: index < filled ? shade : LIEFLAT.TRACK }}
          />
        ))}
      </span>
      <span className="echo-band__value tnum">
        {percent}%
      </span>
    </div>
  )
}

/**
 * 报告概览：分析对象与数据读数两级分区。
 * 区域依靠底色和留白组织，不使用连续分隔线。
 */
export default function ReportOverview({
  detail, ct, platforms, echoScore, components, dominant, fusion, loading,
}) {
  const statusMeta = REPORT_STATUS[detail?.status] || { text: detail?.status, color: 'default' }
  const ctMeta = CT_STATUS[ct.CT_status] || { text: ct.CT_status, color: 'default' }
  const timeRange = ct.time_range
    ? `${(ct.time_range.start || '').slice(0, 10)} 至 ${(ct.time_range.end || '').slice(0, 10)}`
    : '-'

  return (
    <div className="overview">
      <section className="overview-key" aria-label="分析对象">
        {loading ? (
          <Skeleton active paragraph={{ rows: 5 }} title={false} />
        ) : (
          <>
            <div className="overview-key__label">分析对象</div>
            <h3 className="overview-key__title">{ct.keyword || '-'}</h3>
            <dl className="overview-key__facts">
              <div className="overview-key__fact overview-key__fact--wide">
                <dt>覆盖平台</dt>
                <dd className="overview-key__platforms">
                  {platforms.map((p) => (
                    <span key={p}>{platformName(p)}</span>
                  ))}
                </dd>
              </div>
              <div className="overview-key__fact">
                <dt>运行状态</dt>
                <dd>{statusMeta.text || '-'} / {ctMeta.text || '-'}</dd>
              </div>
              <div className="overview-key__fact">
                <dt>数据粒度</dt>
                <dd>{ct.granularity || '-'}</dd>
              </div>
              <div className="overview-key__fact overview-key__fact--wide">
                <dt>时间范围</dt>
                <dd>{timeRange}</dd>
              </div>
            </dl>
          </>
        )}
      </section>

      <div className="overview__signals">
        <section className="overview-echo" aria-label="回声室指数">
          <div className="overview-echo__title">回声室指数</div>
          <div className="overview-echo__ring">
            <EchoSignal score={echoScore} loading={loading} />
          </div>
        </section>

        <section className="overview-measures" aria-label="共振构成">
          {loading ? (
            <Skeleton active paragraph={{ rows: 5 }} title={false} />
          ) : (
            <div className="overview-stats">
              <div className="metric">
                <div className="metric__label">声量共振</div>
                <div className="metric__value">
                  {fusion.mean_volume_corr != null
                    ? <CountUp value={Number(fusion.mean_volume_corr)} decimals={3} />
                    : '-'}
                </div>
              </div>

              <div className="overview-stats__block">
                <div className="overview-stats__label">回声室三分量</div>
                <div className="echo-band-list">
                  <EchoBand label="立场分歧" percent={Math.round((components.stance ?? 0) * 100)} shade={LIEFLAT.HERO} />
                  <EchoBand label="情绪分歧" percent={Math.round((components.sentiment ?? 0) * 100)} shade={LIEFLAT.DATA} />
                  <EchoBand label="声量失振" percent={Math.round((components.corr ?? 0) * 100)} shade={LIEFLAT.DATA2} />
                </div>
                <div className="overview-stats__source">L15 BALLOT TALLY / 每格 5%</div>
              </div>

              <div className="overview-stats__block">
                <div className="overview-stats__label">各平台主导立场</div>
                <ul className="overview-platforms">
                  {platforms.map((p) => (
                    <li key={p}>
                      <span>{platformName(p)}</span>
                      <strong>{STANCE_META[dominant[p]]?.name || '不明'}</strong>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
