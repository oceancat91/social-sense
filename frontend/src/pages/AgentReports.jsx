import { useCallback, useEffect, useMemo, useState } from 'react'
import { Row, Col, Card, Empty, message } from 'antd'
import api from '../services/api'
import { platformName } from '../utils/platforms'
import { formatDate } from '../utils'
import {
  alignedSeriesOption,
  stanceDistOption,
  corrMatrixOption,
  divergenceTimelineOption,
} from '../utils/agentCharts'
import ReportToolbar from '../components/agent/ReportToolbar'
import ReportOverview from '../components/agent/ReportOverview'
import EchoChamberPanel from '../components/agent/EchoChamberPanel'
import ConclusionPanel from '../components/agent/ConclusionPanel'
import AlignmentPanel from '../components/agent/AlignmentPanel'
import StancePanel from '../components/agent/StancePanel'
import DivergencePanel from '../components/agent/DivergencePanel'

/**
 * 多 Agent 跨平台分析页（薄容器）：
 * 仅负责数据获取、状态管理与图表 option 组装，具体展示拆分为
 * components/agent/ 下各职责单一的面板模块。
 */
function AgentReports() {
  const [reports, setReports] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(false)

  const fetchReports = useCallback(async () => {
    try {
      const res = await api.get('/agent/reports', { params: { page_size: 100 } })
      const list = res.data.data.reports || []
      setReports(list)
      setSelectedId(prev => prev ?? list[0]?.id ?? null)
    } catch {
      message.error('获取分析报告列表失败')
    }
  }, [])

  const fetchDetail = useCallback(async (id) => {
    if (!id) { setDetail(null); return }
    setLoading(true)
    try {
      const res = await api.get(`/agent/reports/${id}`)
      setDetail(res.data.data)
    } catch {
      message.error('加载报告详情失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchReports() }, [fetchReports])

  useEffect(() => {
    if (selectedId) fetchDetail(selectedId)
  }, [selectedId, fetchDetail])

  // ---- 派生数据 ----
  const view = useMemo(() => {
    const result = detail?.result
    const ct = result?.cross_platform || {}
    const fusion = ct.fusion || {}
    const aligned = ct.aligned || {}
    const echo = ct.echo_chamber || {}
    const calib = ct.calibration || {}
    const platforms = ct.platforms || []
    return { result, ct, fusion, aligned, echo, calib, platforms }
  }, [detail])

  const { result, ct, fusion, aligned, echo, calib, platforms } = view

  const echoScore = echo.score ?? fusion.echo_chamber_score ?? 0
  const components = echo.components || fusion.echo_chamber_components || {}
  const dominant = fusion.dominant_stance || {}
  const hasResult = !!result

  // ---- 图表 option 组装 ----
  const volumeOption = useMemo(
    () => hasResult && alignedSeriesOption({
      timeAxis: aligned.time_axis,
      zSeries: aligned.z_series,
      metric: 'volume',
      title: '跨平台声量对齐（z-score，统一时间轴）',
      yName: '声量 z-score',
      granularity: ct.granularity,
      area: true,
    }),
    [hasResult, aligned, ct.granularity],
  )
  const sentimentOption = useMemo(
    () => hasResult && alignedSeriesOption({
      timeAxis: aligned.time_axis,
      zSeries: aligned.z_series,
      metric: 'sent_mean',
      title: '跨平台情绪均值对齐（z-score）',
      yName: '情绪 z-score',
      granularity: ct.granularity,
    }),
    [hasResult, aligned, ct.granularity],
  )
  const stanceOption = useMemo(() => stanceDistOption(fusion.stance_dist), [fusion.stance_dist])
  const corrOption = useMemo(() => corrMatrixOption(fusion.temporal_corr, platforms), [fusion.temporal_corr, platforms])
  const divergenceOption = useMemo(() => divergenceTimelineOption(fusion.per_bucket_divergence), [fusion.per_bucket_divergence])

  const reportOptions = reports.map(r => ({
    value: r.id,
    label: `#${r.id} · ${r.keyword}（${(r.platforms || []).map(platformName).join('/')}）· ${formatDate(r.created_at)}`,
  }))

  const isSingle = ct.scope === 'single_platform' || platforms.length < 2

  return (
    <div>
      <ReportToolbar
        selectedId={selectedId}
        reportOptions={reportOptions}
        onSelect={setSelectedId}
        onRefresh={fetchReports}
      />

      {!hasResult ? (
        <Card>
          <Empty description={detail?.status === 'failed'
            ? `分析失败：${detail?.error || '未知错误'}`
            : '暂无可展示的报告。'} />
        </Card>
      ) : (
        <>
          <ReportOverview
            detail={detail}
            ct={ct}
            platforms={platforms}
            echoScore={echoScore}
            components={components}
            dominant={dominant}
            fusion={fusion}
            loading={loading}
          />

          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={8} xs={24}>
              <EchoChamberPanel echoScore={echoScore} loading={loading} />
            </Col>
            <Col span={16} xs={24}>
              <ConclusionPanel ct={ct} loading={loading} />
            </Col>
          </Row>

          <AlignmentPanel
            volumeOption={volumeOption}
            sentimentOption={sentimentOption}
            isSingle={isSingle}
            loading={loading}
          />
          <StancePanel stanceOption={stanceOption} corrOption={corrOption} loading={loading} />
          <DivergencePanel divergenceOption={divergenceOption} calib={calib} loading={loading} />
        </>
      )}
    </div>
  )
}

export default AgentReports
