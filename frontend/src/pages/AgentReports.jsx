import { useCallback, useEffect, useMemo, useState } from 'react'
import { Empty, App as AntApp } from 'antd'
import api from '../services/api'
import { platformName } from '../utils/platforms'
import { formatDate } from '../utils'
import { useDarkMode } from '../theme'
import {
  alignedSeriesOption,
  stanceDistOption,
  corrMatrixOption,
  divergenceTimelineOption,
} from '../utils/agentCharts'
import HeroBanner from '../components/agent/HeroBanner'
import Reveal from '../components/agent/Reveal'
import Section from '../components/agent/Section'
import ReportOverview from '../components/agent/ReportOverview'
import ConclusionPanel from '../components/agent/ConclusionPanel'
import AlignmentPanel from '../components/agent/AlignmentPanel'
import StancePanel from '../components/agent/StancePanel'
import DivergencePanel from '../components/agent/DivergencePanel'

/**
 * 多 Agent 跨平台分析页（薄容器）：
 * 仅负责数据获取、状态管理与图表 option 组装，具体展示拆分为
 * components/agent/ 下各职责单一的面板模块。
 * 视觉上与 landing 首页同源：hero 区 + 细分隔线分区 + 信号涟漪资产 + stagger 入场，
 * 避免卡片/便当盒堆叠。
 */
function AgentReports() {
  const dark = useDarkMode()
  const { message } = AntApp.useApp()
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
  }, [message])

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
  }, [message])

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
    }, dark),
    [hasResult, aligned, ct.granularity, dark],
  )
  const sentimentOption = useMemo(
    () => hasResult && alignedSeriesOption({
      timeAxis: aligned.time_axis,
      zSeries: aligned.z_series,
      metric: 'sent_mean',
      title: '跨平台情绪均值对齐（z-score）',
      yName: '情绪 z-score',
      granularity: ct.granularity,
    }, dark),
    [hasResult, aligned, ct.granularity, dark],
  )
  const stanceOption = useMemo(() => stanceDistOption(fusion.stance_dist, dark), [fusion.stance_dist, dark])
  const corrOption = useMemo(
    () => corrMatrixOption(fusion.temporal_corr, platforms, dark),
    [fusion.temporal_corr, platforms, dark],
  )
  const divergenceOption = useMemo(
    () => divergenceTimelineOption(fusion.per_bucket_divergence, dark),
    [fusion.per_bucket_divergence, dark],
  )

  const reportOptions = reports.map(r => ({
    value: r.id,
    label: `#${r.id} / ${r.keyword}（${(r.platforms || []).map(platformName).join('/')}）/ ${formatDate(r.created_at)}`,
  }))

  const isSingle = ct.scope === 'single_platform' || platforms.length < 2

  return (
    <div>
      <Reveal>
        <HeroBanner
          selectedId={selectedId}
          reportOptions={reportOptions}
          onSelect={setSelectedId}
          onRefresh={fetchReports}
        />
      </Reveal>

      {!hasResult ? (
        <div className="section">
          <Empty description={detail?.status === 'failed'
            ? `分析失败：${detail?.error || '未知错误'}`
            : '暂无可展示的报告。'} />
        </div>
      ) : (
        <>
          <Reveal delay={60}>
            <Section index="01" title="概览" desc="关键词 / 回声室 / 共振 / 立场">
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
            </Section>
          </Reveal>

          <Reveal delay={110}>
            <Section index="02" title="跨平台结论" desc="主控 Agent 归纳">
              <ConclusionPanel ct={ct} loading={loading} />
            </Section>
          </Reveal>

          <Reveal delay={150}>
            <Section index="03" title="对齐呈现" desc="统一时间轴">
              <AlignmentPanel
                volumeOption={volumeOption}
                sentimentOption={sentimentOption}
                isSingle={isSingle}
                loading={loading}
              />
            </Section>
          </Reveal>

          <Reveal delay={190}>
            <Section index="04" title="立场与共振" desc="分布 / 相关性">
              <StancePanel stanceOption={stanceOption} corrOption={corrOption} loading={loading} />
            </Section>
          </Reveal>

          <Reveal delay={230}>
            <Section index="05" title="分歧与门禁" desc="扩散 / 校准">
              <DivergencePanel divergenceOption={divergenceOption} calib={calib} loading={loading} />
            </Section>
          </Reveal>
        </>
      )}
    </div>
  )
}

export default AgentReports
