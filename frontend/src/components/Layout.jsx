import { Outlet, useNavigate } from 'react-router-dom'
import { Layout as AntLayout, Dropdown } from 'antd'
import BrandMark from './BrandMark'
import NoiseOverlay from './agent/NoiseOverlay'
import AgentBackground from './agent/AgentBackground'

const { Header, Content } = AntLayout

function Layout() {
  const navigate = useNavigate()

  const handleLogout = () => {
    localStorage.removeItem('token')
    navigate('/login')
  }

  const userMenu = {
    items: [{ key: 'logout', label: '退出登录' }],
    onClick: ({ key }) => key === 'logout' && handleLogout(),
  }

  return (
    <>
      <AgentBackground />
      <NoiseOverlay />
      <AntLayout className="ss-app-shell">
        <Header className="ss-header">
          <div className="ss-header__inner">
            <a href="https://socialsense.cn/" className="ss-brand">
              <span className="ss-brand__mark">
                <BrandMark size={25} />
              </span>
              <span className="ss-brand__name">Social Sense</span>
            </a>

            <Dropdown menu={userMenu} placement="bottomRight" trigger={['click']}>
              <button type="button" className="ss-user-menu" aria-label="打开管理员菜单">
                管理员
              </button>
            </Dropdown>
          </div>
        </Header>

        <Content className="ss-content">
          <div className="page-enter ss-page-frame">
            <Outlet />
          </div>
        </Content>
      </AntLayout>
    </>
  )
}

export default Layout
