import { useCallback, useEffect, useMemo, useState } from 'react'
import { Empty, App as AntApp } from 'antd'
import api from '../services/api'
import { platformName } from '../utils/platforms'
import { formatDate } from '../utils'
import { useDarkMode } from '../theme'
import {
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

  // ---- ECharts 仅保留分歧时序；其余图表使用 Lieflat SVG 原语 ----
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
            <Section title="概览" desc="一眼掌握全局">
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
            <Section title="跨平台结论" desc="AI 归纳的核心判断">
              <ConclusionPanel ct={ct} loading={loading} />
            </Section>
          </Reveal>

          <Reveal delay={150}>
            <Section title="节奏对齐" desc="谁先火，谁在跟">
              <AlignmentPanel
                aligned={aligned}
                isSingle={isSingle}
                loading={loading}
              />
            </Section>
          </Reveal>

          <Reveal delay={190}>
            <Section title="立场与共振" desc="谁在同声，谁在分化">
              <StancePanel
                stanceDist={fusion.stance_dist}
                temporalCorr={fusion.temporal_corr}
                platforms={platforms}
                loading={loading}
              />
            </Section>
          </Reveal>

          <Reveal delay={230}>
            <Section title="分歧与校验" desc="分歧在哪爆发，结论是否可信">
              <DivergencePanel divergenceOption={divergenceOption} calib={calib} loading={loading} />
            </Section>
          </Reveal>
        </>
      )}
    </div>
  )
}

export default AgentReports
