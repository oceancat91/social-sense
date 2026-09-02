import { Card, Statistic } from 'antd'

/** 通用统计卡片（带渐变图标） */
export default function StatCard({ title, value, suffix, color, icon, loading }) {
  return (
    <Card className="stat-card" loading={loading}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {icon && (
          <div style={{
            width: 44, height: 44, borderRadius: 10, background: color,
            color: '#fff', fontSize: 20, display: 'flex', alignItems: 'center',
            justifyContent: 'center', flexShrink: 0,
          }}>
            {icon}
          </div>
        )}
        <Statistic title={title} value={value} suffix={suffix} valueStyle={{ fontSize: 22 }} />
      </div>
    </Card>
  )
}
