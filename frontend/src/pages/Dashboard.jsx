import { useEffect, useState } from 'react'
import { Row, Col, Card, Statistic, message } from 'antd'
import {
  DatabaseOutlined,
  AppstoreOutlined,
  WarningOutlined,
  SmileOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import api from '../services/api'
import { PLATFORMS, SENTIMENTS, platformColor } from '../utils/platforms'

const STAT_CARDS = [
  { key: 'total', title: '舆情数据总量', icon: <DatabaseOutlined />, bg: 'linear-gradient(135deg,#1a73e8,#4d9dff)' },
  { key: 'platform_count', title: '覆盖平台数', icon: <AppstoreOutlined />, bg: 'linear-gradient(135deg,#673ab7,#9c6bff)' },
  { key: 'negative_ratio', title: '负面舆情占比', icon: <WarningOutlined />, bg: 'linear-gradient(135deg,#d4380d,#ff8a4d)' },
  { key: 'avg_score', title: '平均情感得分', icon: <SmileOutlined />, bg: 'linear-gradient(135deg,#0e9f6e,#3ecf96)' },
]

function Dashboard() {
  const [overview, setOverview] = useState(null)
  const [trend, setTrend] = useState(null)
  const [comparison, setComparison] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.get('/analysis/overview'),
      api.get('/analysis/trend', { params: { days: 14 } }),
      api.get('/analysis/platform-comparison'),
    ])
      .then(([ov, tr, cp]) => {
        setOverview(ov.data.data)
        setTrend(tr.data.data)
        setComparison(cp.data.data.items)
      })
      .catch(() => message.error('数据加载失败'))
      .finally(() => setLoading(false))
  }, [])

  const trendOption = trend && {
    title: { text: '多平台声量趋势（近 14 天）', left: 'center', textStyle: { fontSize: 15, fontWeight: 600 } },
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(255,255,255,0.96)', borderColor: '#e8ecf3', textStyle: { color: '#333' } },
    legend: { bottom: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 8 },
    grid: { left: 50, right: 30, top: 50, bottom: 55 },
    xAxis: {
      type: 'category',
      data: trend.dates.map(d => d.slice(5)),
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#e8ecf3' } },
      axisLabel: { color: '#8a94a6' },
    },
    yAxis: {
      type: 'value',
      name: '声量',
      splitLine: { lineStyle: { color: '#f0f2f7' } },
      axisLabel: { color: '#8a94a6' },
    },
    series: trend.platforms.map(p => ({
      name: p.platform_name,
      type: 'line',
      stack: 'total',
      smooth: true,
      symbol: 'none',
      areaStyle: { opacity: 0.25 },
      emphasis: { focus: 'series' },
      lineStyle: { width: 2.5 },
      data: p.data,
      color: platformColor(p.platform),
    })),
  }

  const pieOption = overview && {
    title: { text: '情感分布', left: 'center', textStyle: { fontSize: 15, fontWeight: 600 } },
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)', backgroundColor: 'rgba(255,255,255,0.96)', borderColor: '#e8ecf3' },
    legend: { bottom: 0, icon: 'circle', itemWidth: 10, itemHeight: 10 },
    series: [{
      type: 'pie',
      radius: ['42%', '68%'],
      center: ['50%', '52%'],
      itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
      label: { show: false },
      emphasis: {
        itemStyle: { shadowBlur: 16, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.2)' },
        label: { show: true, fontWeight: 600, formatter: '{b}\n{c} ({d}%)' },
      },
      data: [
        { value: overview.positive, name: '正面', itemStyle: { color: SENTIMENTS.positive.color } },
        { value: overview.negative, name: '负面', itemStyle: { color: SENTIMENTS.negative.color } },
        { value: overview.neutral, name: '中性', itemStyle: { color: SENTIMENTS.neutral.color } },
      ],
    }],
  }

  const barOption = comparison.length > 0 && {
    title: { text: '各平台声量与负面占比', left: 'center', textStyle: { fontSize: 15, fontWeight: 600 } },
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(255,255,255,0.96)', borderColor: '#e8ecf3' },
    legend: { bottom: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 8 },
    grid: { left: 60, right: 60, top: 50, bottom: 55 },
    xAxis: {
      type: 'category',
      data: comparison.map(c => PLATFORMS[c.platform]?.name || c.platform),
      axisLine: { lineStyle: { color: '#e8ecf3' } },
      axisLabel: { color: '#8a94a6' },
    },
    yAxis: [
      {
        type: 'value',
        name: '声量',
        splitLine: { lineStyle: { color: '#f0f2f7' } },
        axisLabel: { color: '#8a94a6' },
      },
      {
        type: 'value',
        name: '负面占比',
        max: 1,
        splitLine: { show: false },
        axisLabel: { formatter: v => `${v * 100}%`, color: SENTIMENTS.negative.color },
      },
    ],
    series: [
      {
        name: '声量',
        type: 'bar',
        data: comparison.map(c => ({
          value: c.total,
          itemStyle: {
            color: platformColor(c.platform),
            opacity: 0.85,
            borderRadius: [6, 6, 0, 0],
          },
        })),
        barMaxWidth: 40,
      },
      {
        name: '负面占比',
        type: 'line',
        yAxisIndex: 1,
        data: comparison.map(c => c.negative_ratio),
        smooth: true,
        symbol: 'circle',
        symbolSize: 7,
        itemStyle: { color: SENTIMENTS.negative.color },
        lineStyle: { width: 2.5 },
      },
    ],
  }

  const cardValues = {
    total: { value: overview?.total ?? '-', suffix: '' },
    platform_count: { value: overview?.platform_count ?? '-', suffix: '/ 6' },
    negative_ratio: {
      value: overview ? (overview.negative_ratio * 100).toFixed(1) : '-',
      suffix: '%',
    },
    avg_score: { value: overview?.avg_score ?? '-', suffix: '' },
  }

  return (
    <div>
      <h2 className="page-title" style={{ marginBottom: 24 }}>
        <DatabaseOutlined style={{ color: 'var(--primary)' }} /> 跨平台舆情看板
      </h2>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        {STAT_CARDS.map(card => {
          const v = cardValues[card.key]
          const isNegative = card.key === 'negative_ratio'
          const isScore = card.key === 'avg_score'
          const scoreColor = overview?.avg_score >= 0 ? '#0e9f6e' : '#d4380d'
          return (
            <Col span={6} xs={12} key={card.key}>
              <Card className="stat-card" loading={loading}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                  <div style={{
                    width: 48,
                    height: 48,
                    borderRadius: 12,
                    background: card.bg,
                    color: '#fff',
                    fontSize: 22,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                    boxShadow: '0 6px 16px rgba(16,42,100,0.18)',
                  }}>
                    {card.icon}
                  </div>
                  <Statistic
                    title={card.title}
                    value={v.value}
                    suffix={v.suffix}
                    valueStyle={{
                      color: isNegative ? SENTIMENTS.negative.color : (isScore ? scoreColor : '#1f2733'),
                    }}
                  />
                </div>
              </Card>
            </Col>
          )
        })}
      </Row>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={16} xs={24}>
          <Card loading={loading}>{trendOption && <ReactECharts option={trendOption} style={{ height: 380 }} />}</Card>
        </Col>
        <Col span={8} xs={24}>
          <Card loading={loading}>{pieOption && <ReactECharts option={pieOption} style={{ height: 380 }} />}</Card>
        </Col>
      </Row>
      <Card loading={loading}>{barOption && <ReactECharts option={barOption} style={{ height: 340 }} />}</Card>
    </div>
  )
}

export default Dashboard
