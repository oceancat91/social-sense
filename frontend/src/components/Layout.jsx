import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout as AntLayout, Menu, Dropdown, Avatar, Space } from 'antd'
import {
  DashboardOutlined,
  UnorderedListOutlined,
  BarChartOutlined,
  RadarChartOutlined,
  LogoutOutlined,
  UserOutlined,
} from '@ant-design/icons'

const { Header, Sider, Content } = AntLayout

const menuItems = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '数据看板' },
  { key: '/tasks', icon: <UnorderedListOutlined />, label: '监控任务' },
  { key: '/analysis', icon: <BarChartOutlined />, label: '舆情分析' },
]

function Layout() {
  const navigate = useNavigate()
  const location = useLocation()

  const handleLogout = () => {
    localStorage.removeItem('token')
    navigate('/login')
  }

  const userMenu = {
    items: [
      { key: 'logout', icon: <LogoutOutlined />, label: '退出登录' },
    ],
    onClick: ({ key }) => key === 'logout' && handleLogout(),
  }

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider
        width={216}
        theme="light"
        style={{
          background: 'var(--sidebar-bg)',
          position: 'sticky',
          top: 0,
          height: '100vh',
          overflow: 'auto',
          boxShadow: '2px 0 16px rgba(13, 27, 62, 0.25)',
          zIndex: 10,
        }}
      >
        <div style={{
          height: 64,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 10,
          borderBottom: '1px solid rgba(255,255,255,0.1)',
        }}>
          <RadarChartOutlined style={{ fontSize: 26, color: '#5a8dff' }} />
          <div>
            <div style={{ color: '#fff', fontSize: 17, fontWeight: 700, lineHeight: 1.2 }}>Social Sense</div>
            <div style={{ color: 'rgba(255,255,255,0.55)', fontSize: 11, lineHeight: 1.4 }}>社交舆情感知平台</div>
          </div>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ background: 'transparent', borderInlineEnd: 'none', marginTop: 8 }}
        />
      </Sider>
      <AntLayout>
        <Header style={{
          background: '#fff',
          padding: '0 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          borderBottom: '1px solid #edf0f6',
          boxShadow: '0 1px 6px rgba(16, 42, 100, 0.04)',
        }}>
          <Dropdown menu={userMenu} placement="bottomRight">
            <Space style={{ cursor: 'pointer', padding: '0 8px' }}>
              <Avatar size={34} style={{ background: 'linear-gradient(135deg, #1a73e8, #6a3de8)' }} icon={<UserOutlined />} />
              <span style={{ fontWeight: 500, color: '#2b2f3a' }}>管理员</span>
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ margin: 24, padding: 24, background: 'transparent' }}>
          <div className="page-enter">
            <Outlet />
          </div>
        </Content>
      </AntLayout>
    </AntLayout>
  )
}

export default Layout
