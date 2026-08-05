import { useEffect, useState } from 'react'
import { Row, Col, Card, Statistic, message } from 'antd'
import ReactECharts from 'echarts-for-react'
import api from '../services/api'
import { PLATFORMS, SENTIMENTS, platformColor } from '../utils/platforms'

function Dashboard() {
  const [overview, setOverview] = useState(null)
  const [trend, setTrend] = useState(null)
  const [comparison, setComparison] = useState([])

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
  }, [])

  const trendOption = trend && {
    title: { text: '多平台声量趋势（近 14 天）', left: 'center' },
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0 },
    grid: { left: 50, right: 30, top: 50, bottom: 50 },
    xAxis: {
      type: 'category',
      data: trend.dates.map(d => d.slice(5)),
      boundaryGap: false,
    },
    yAxis: { type: 'value', name: '声量' },
    series: trend.platforms.map(p => ({
      name: p.platform_name,
      type: 'line',
      stack: 'total',
      areaStyle: { opacity: 0.3 },
      emphasis: { focus: 'series' },
      smooth: true,
      data: p.data,
      color: platformColor(p.platform),
    })),
  }

  const pieOption = overview && {
    title: { text: '情感分布', left: 'center' },
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0 },
    series: [{
      type: 'pie',
      radius: ['40%', '65%'],
      center: ['50%', '55%'],
      data: [
        { value: overview.positive, name: '正面', itemStyle: { color: SENTIMENTS.positive.color } },
        { value: overview.negative, name: '负面', itemStyle: { color: SENTIMENTS.negative.color } },
        { value: overview.neutral, name: '中性', itemStyle: { color: SENTIMENTS.neutral.color } },
      ],
      emphasis: { itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.3)' } },
    }],
  }

  const barOption = comparison.length > 0 && {
    title: { text: '各平台声量与负面占比', left: 'center' },
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0 },
    grid: { left: 60, right: 60, top: 50, bottom: 50 },
    xAxis: {
      type: 'category',
      data: comparison.map(c => PLATFORMS[c.platform]?.name || c.platform),
    },
    yAxis: [
      { type: 'value', name: '声量' },
      { type: 'value', name: '负面占比', max: 1, axisLabel: { formatter: v => `${v * 100}%` } },
    ],
    series: [
      {
        name: '声量',
        type: 'bar',
        data: comparison.map(c => ({
          value: c.total,
          itemStyle: { color: platformColor(c.platform), opacity: 0.85 },
        })),
        barMaxWidth: 40,
      },
      {
        name: '负面占比',
        type: 'line',
        yAxisIndex: 1,
        data: comparison.map(c => c.negative_ratio),
        itemStyle: { color: SENTIMENTS.negative.color },
        smooth: true,
      },
    ],
  }

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>跨平台舆情看板</h2>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card><Statistic title="舆情数据总量" value={overview?.total ?? '-'} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="覆盖平台数" value={overview?.platform_count ?? '-'} suffix="/ 6" /></Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="负面舆情占比"
              value={overview ? (overview.negative_ratio * 100).toFixed(1) : '-'}
              suffix="%"
              valueStyle={{ color: SENTIMENTS.negative.color }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="平均情感得分"
              value={overview?.avg_score ?? '-'}
              valueStyle={{ color: overview?.avg_score >= 0 ? SENTIMENTS.positive.color : SENTIMENTS.negative.color }}
            />
          </Card>
        </Col>
      </Row>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={16}>
          <Card>{trendOption && <ReactECharts option={trendOption} style={{ height: 380 }} />}</Card>
        </Col>
        <Col span={8}>
          <Card>{pieOption && <ReactECharts option={pieOption} style={{ height: 380 }} />}</Card>
        </Col>
      </Row>
      <Card>{barOption && <ReactECharts option={barOption} style={{ height: 340 }} />}</Card>
    </div>
  )
}

export default Dashboard
