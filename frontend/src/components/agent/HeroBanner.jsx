import { Select, Button } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'

/**
 * 分析台 hero 区：大标题 + 副标题 + 信号雷达视觉资产 + 报告选择器。
 * 扁平化处理：无圆角/边框/阴影，仅底部细分隔线。
 * 动效：氛围光晕漂移（glow drift）+ 雷达扫描线 + live 脉冲点 + 涟漪呼吸。
 */

function SignalRadar() {
  return (
    <svg
      className="ss-hero__field"
      viewBox="0 0 200 120"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      focusable="false"
    >
      {/* 同心刻度弧（雷达距离环） */}
      <circle cx="100" cy="104" r="24" stroke="var(--accent)" strokeOpacity="0.1" strokeWidth="1" fill="none" />
      <circle cx="100" cy="104" r="42" stroke="var(--accent)" strokeOpacity="0.08" strokeWidth="1" fill="none" />
      <circle cx="100" cy="104" r="60" stroke="var(--accent)" strokeOpacity="0.06" strokeWidth="1" fill="none" />
      {/* 底部基线 */}
      <line x1="16" y1="104" x2="184" y2="104" stroke="var(--accent)" strokeOpacity="0.16" strokeWidth="1" />
      {/* 中心感知点 */}
      <circle cx="100" cy="104" r="3" fill="var(--accent)" />
      {/* 三道向上扩散的信号涟漪 */}
      <path d="M 76 104 A 24 24 0 0 1 124 104" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" className="ss-hero__arc ss-hero__arc--1" />
      <path d="M 58 104 A 42 42 0 0 1 142 104" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" opacity="0.6" className="ss-hero__arc ss-hero__arc--2" />
      <path d="M 40 104 A 60 60 0 0 1 160 104" stroke="var(--accent)" strokeWidth="1.2" strokeLinecap="round" opacity="0.32" className="ss-hero__arc ss-hero__arc--3" />
      {/* 雷达扫描线（旋转） */}
      <g className="ss-hero__sweep">
        <line x1="100" y1="104" x2="100" y2="44" stroke="var(--accent)" strokeWidth="1.2" strokeLinecap="round" opacity="0.5" />
        <circle cx="100" cy="46" r="2.4" fill="var(--accent)" opacity="0.9" />
      </g>
    </svg>
  )
}

export default function HeroBanner({ selectedId, reportOptions, onSelect, onRefresh }) {
  return (
    <section className="ss-hero">
      <div className="ss-hero__glow" aria-hidden="true" />
      <div className="ss-hero__copy">
        <div className="ss-hero__eyebrow">
          <span className="live-dot" />
          SOCIAL SENSE / AGENT DESK
        </div>
        <h1>跨平台多 Agent 舆情分析</h1>
        <p>六平台实时采集，统一时间轴与口径，量化情绪分歧、声量共振与回声室强度。</p>
      </div>
      <div className="ss-hero__side">
        <SignalRadar />
        <div className="ss-hero__controls">
          <Select
            style={{ flex: 1, minWidth: 220 }}
            placeholder="选择分析报告"
            value={selectedId}
            onChange={onSelect}
            options={reportOptions}
            showSearch
            optionFilterProp="label"
            notFoundContent="暂无报告"
          />
          <Button icon={<ReloadOutlined />} onClick={onRefresh}>刷新</Button>
        </div>
      </div>
    </section>
  )
}
