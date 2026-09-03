import { Card, Statistic } from 'antd'

const TONES = {
  accent: 'var(--accent)',
  success: 'var(--success)',
  warning: 'var(--warning)',
  danger: 'var(--danger)',
}

/**
 * 通用统计卡。tone 控制顶部强调条与图标色，
 * 不加整块渐变背景，避免堆叠的“彩色卡片墙”。
 */
export default function StatCard({ title, value, suffix, tone = 'accent', icon, loading }) {
  const color = TONES[tone] || TONES.accent
  return (
    <Card
      className="stat-card"
      loading={loading}
      style={{ '--card-accent': color }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: 8,
            flexShrink: 0,
            display: 'grid',
            placeItems: 'center',
            fontSize: 18,
            color,
            background: 'color-mix(in srgb, var(--card-accent) 12%, transparent)',
          }}
        >
          {icon}
        </div>
        <Statistic
          title={title}
          value={value}
          suffix={suffix}
          valueStyle={{ fontSize: 24, fontWeight: 650, color: 'var(--text-1)' }}
        />
      </div>
    </Card>
  )
}
