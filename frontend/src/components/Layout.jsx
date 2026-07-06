import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout as AntLayout, Menu } from 'antd'

const { Header, Sider, Content } = AntLayout

const menuItems = [
  { key: '/dashboard', label: '数据看板' },
  { key: '/tasks', label: '监控任务' },
  { key: '/analysis', label: '舆情分析' },
]

function Layout() {
  const navigate = useNavigate()
  const location = useLocation()

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider>
        <div style={{ height: 64, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <h2 style={{ color: '#fff', margin: 0 }}>Social Sense</h2>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <AntLayout>
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h3>社交舆情感知平台</h3>
        </Header>
        <Content style={{ margin: 24, padding: 24, background: '#fff', borderRadius: 8 }}>
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  )
}

export default Layout
