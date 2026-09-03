import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout as AntLayout, Menu, Dropdown, Avatar, Space } from 'antd'
import {
  RadarChartOutlined,
  LogoutOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { useTheme } from '../theme'

const { Header, Sider, Content } = AntLayout

const menuItems = [
  { key: '/agent', icon: <RadarChartOutlined />, label: '跨平台分析台' },
]

function Layout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { dark } = useTheme()

  const handleLogout = () => {
    localStorage.removeItem('token')
    navigate('/login')
  }

  const userMenu = {
    items: [{ key: 'logout', icon: <LogoutOutlined />, label: '退出登录' }],
    onClick: ({ key }) => key === 'logout' && handleLogout(),
  }

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider
        width={224}
        theme={dark ? 'dark' : 'light'}
        className="ss-sider"
        style={{
          background: 'var(--bg-sider)',
          position: 'sticky',
          top: 0,
          height: '100vh',
          overflow: 'auto',
          zIndex: 20,
        }}
      >
        <div className="ss-brand">
          <div className="ss-brand__mark">
            <RadarChartOutlined />
          </div>
          <span className="ss-brand__name">Social Sense</span>
        </div>

        <Menu
          theme={dark ? 'dark' : 'light'}
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{
            background: 'transparent',
            borderInlineEnd: 'none',
            paddingTop: 6,
          }}
        />
      </Sider>

      <AntLayout>
        <Header className="ss-header">
          <div className="ss-header__loc">
            舆情分析台 <b>/ 多 AGENT 跨平台分析</b>
          </div>
          <Space size={14}>
            <Dropdown menu={userMenu} placement="bottomRight">
              <Space style={{ cursor: 'pointer', padding: '2px 4px' }}>
                <Avatar
                  size={28}
                  icon={<UserOutlined />}
                  style={{ background: 'var(--accent)', color: 'var(--accent-ink)', fontSize: 13 }}
                />
                <span className="ss-header__user">管理员</span>
              </Space>
            </Dropdown>
          </Space>
        </Header>

        <Content className="ss-content">
          <div className="page-enter" style={{ maxWidth: 1280, margin: '0 auto' }}>
            <Outlet />
          </div>
        </Content>
      </AntLayout>
    </AntLayout>
  )
}

export default Layout
