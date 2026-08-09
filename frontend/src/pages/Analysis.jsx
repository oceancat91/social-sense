import { useCallback, useEffect, useState } from 'react'
import { Row, Col, Card, Select, Radio, Table, Tag, message } from 'antd'
import { BarChartOutlined } from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import 'echarts-wordcloud'
import api from '../services/api'
import { PLATFORMS, SENTIMENTS, PLATFORM_OPTIONS, platformColor } from '../utils/platforms'
import { formatDate } from '../utils'

const CHART_TITLE = { fontSize: 15, fontWeight: 600 }
const TOOLTIP_BG = { backgroundColor: 'rgba(255,255,255,0.96)', borderColor: '#e8ecf3', textStyle: { color: '#333' } }

function Analysis() {
  const [platform, setPlatform] = useState('all')
  const [days, setDays] = useState(14)
  const [comparison, setComparison] = useState([])
  const [propagation, setPropagation] = useState(null)
  const [keywords, setKeywords] = useState([])
  const [hotContent, setHotContent] = useState([])
  const [loading, setLoading] = useState(true)

  const fetchAll = useCallback(() => {
    setLoading(true)
    const params = { platform: platform === 'all' ? undefined : platform, days }
    Promise.all([
      api.get('/analysis/platform-comparison'),
      api.get('/analysis/propagation', { params: { days } }),
      api.get('/analysis/keywords', { params: { ...params, top_k: 50 } }),
      api.get('/analysis/hot-content', { params: { ...params, limit: 10 } }),
    ])
      .then(([cp, pg, kw, hot]) => {
        setComparison(cp.data.data.items)
        setPropagation(pg.data.data)
        setKeywords(kw.data.data.keywords)
        setHotContent(hot.data.data.items)
      })
      .catch(() => message.error('分析数据加载失败'))
      .finally(() => setLoading(false))
  }, [platform, days])

  useEffect(() => { fetchAll() }, [fetchAll])

  // 跨平台情感分布堆叠图
  const sentimentBarOption = comparison.length > 0 && {
    title: { text: '各平台情感分布对比（情绪极化分析）', left: 'center', textStyle: CHART_TITLE },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, ...TOOLTIP_BG },
    legend: { bottom: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 8 },
    grid: { left: 50, right: 30, top: 50, bottom: 55 },
    xAxis: {
      type: 'category',
      data: comparison.map(c => PLATFORMS[c.platform]?.name || c.platform),
      axisLine: { lineStyle: { color: '#e8ecf3' } },
      axisLabel: { color: '#8a94a6' },
    },
    yAxis: {
      type: 'value',
      name: '数量',
      splitLine: { lineStyle: { color: '#f0f2f7' } },
      axisLabel: { color: '#8a94a6' },
    },
    series: ['positive', 'neutral', 'negative'].map(key => ({
      name: SENTIMENTS[key].name,
      type: 'bar',
      stack: 'sentiment',
      data: comparison.map(c => c[key]),
      itemStyle: { color: SENTIMENTS[key].color, borderRadius: key === 'negative' ? [0, 0, 6, 6] : 0 },
      barMaxWidth: 45,
    })),
  }

  // 传播溯源时间线：各平台声量曲线 + 首发标记
  const propagationOption = propagation && propagation.items.length > 0 && {
    title: { text: '跨平台传播路径（舆情溯源）', left: 'center', textStyle: CHART_TITLE },
    tooltip: { trigger: 'axis', ...TOOLTIP_BG },
    legend: { bottom: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 8 },
    grid: { left: 50, right: 30, top: 50, bottom: 55 },
    xAxis: {
      type: 'category',
      data: propagation.dates.map(d => d.slice(5)),
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#e8ecf3' } },
      axisLabel: { color: '#8a94a6' },
    },
    yAxis: {
      type: 'value',
      name: '日声量',
      splitLine: { lineStyle: { color: '#f0f2f7' } },
      axisLabel: { color: '#8a94a6' },
    },
    series: propagation.items.map(item => ({
      name: `${item.platform_name}（首发 +${item.delay_hours}h）`,
      type: 'line',
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2.5 },
      data: item.daily,
      color: platformColor(item.platform),
      markPoint: {
        data: [{
          coord: [item.first_seen ? item.first_seen.slice(5, 10) : 0, 0],
          value: '首发',
          itemStyle: { color: platformColor(item.platform) },
        }],
        symbolSize: 45,
        label: { fontSize: 10 },
      },
    })),
  }

  // 关键词词云
  const wordCloudOption = keywords.length > 0 && {
    title: { text: '高频关键词云', left: 'center', textStyle: CHART_TITLE },
    tooltip: { backgroundColor: 'rgba(255,255,255,0.96)', borderColor: '#e8ecf3' },
    series: [{
      type: 'wordCloud',
      shape: 'circle',
      sizeRange: [14, 55],
      rotationRange: [-30, 30],
      gridSize: 8,
      textStyle: {
        color: () => `rgb(${[Math.round(Math.random() * 160), Math.round(Math.random() * 160), Math.round(Math.random() * 160)].join(',')})`,
      },
      emphasis: { textStyle: { fontWeight: 'bold' } },
      data: keywords.map(k => ({ name: k.word, value: k.count })),
    }],
  }

  const hotColumns = [
    {
      title: '平台', dataIndex: 'platform', width: 90,
      render: p => <Tag color={platformColor(p)}>{PLATFORMS[p]?.name || p}</Tag>,
    },
    { title: '内容', dataIndex: 'content', ellipsis: true },
    { title: '作者', dataIndex: 'author', width: 140, ellipsis: true },
    {
      title: '情感', dataIndex: 'sentiment', width: 80,
      render: s => <Tag color={SENTIMENTS[s]?.color}>{SENTIMENTS[s]?.name || s}</Tag>,
    },
    { title: '点赞', dataIndex: 'like_count', width: 80, sorter: (a, b) => a.like_count - b.like_count },
    { title: '评论', dataIndex: 'comment_count', width: 80 },
    { title: '转发', dataIndex: 'share_count', width: 80 },
    { title: '发布时间', dataIndex: 'published_at', width: 170, render: t => formatDate(t) },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
        <h2 className="page-title">
          <BarChartOutlined style={{ color: 'var(--primary)' }} /> 跨平台舆情分析
        </h2>
        <div style={{ display: 'flex', gap: 12 }}>
          <Radio.Group value={days} onChange={e => setDays(e.target.value)} optionType="button" buttonStyle="solid">
            <Radio.Button value={7}>近 7 天</Radio.Button>
            <Radio.Button value={14}>近 14 天</Radio.Button>
          </Radio.Group>
          <Select
            value={platform}
            onChange={setPlatform}
            options={PLATFORM_OPTIONS}
            style={{ width: 130 }}
          />
        </div>
      </div>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={12} xs={24}>
          <Card loading={loading}>{sentimentBarOption && <ReactECharts option={sentimentBarOption} style={{ height: 360 }} />}</Card>
        </Col>
        <Col span={12} xs={24}>
          <Card loading={loading}>{wordCloudOption && <ReactECharts option={wordCloudOption} style={{ height: 360 }} />}</Card>
        </Col>
      </Row>

      <Card style={{ marginBottom: 16 }} loading={loading}>
        {propagationOption && <ReactECharts option={propagationOption} style={{ height: 380 }} />}
        {propagation && propagation.items.length > 0 && (
          <Table
            dataSource={propagation.items}
            rowKey="platform"
            pagination={false}
            size="small"
            columns={[
              {
                title: '平台', dataIndex: 'platform', width: 100,
                render: p => <Tag color={platformColor(p)}>{PLATFORMS[p]?.name || p}</Tag>,
              },
              { title: '首发时间', dataIndex: 'first_seen', render: t => formatDate(t) },
              {
                title: '传播延迟', dataIndex: 'delay_hours', width: 110,
                render: h => (h === 0 ? <Tag color="red">源头平台</Tag> : `+${h} 小时`),
              },
              { title: '峰值日期', dataIndex: 'peak_date', width: 120 },
              { title: '总声量', dataIndex: 'total', width: 100, sorter: (a, b) => a.total - b.total },
            ]}
          />
        )}
      </Card>

      <Card title="热门内容 TOP 10" loading={loading}>
        <Table dataSource={hotContent} columns={hotColumns} rowKey="id" pagination={false} />
      </Card>
    </div>
  )
}

export default Analysis
