import { Outlet, useNavigate } from 'react-router-dom'
import { Layout as AntLayout, Dropdown } from 'antd'
import { useEffect, useState } from 'react'
import BrandMark from './BrandMark'
import NoiseOverlay from './agent/NoiseOverlay'
import AgentBackground from './agent/AgentBackground'

const { Content } = AntLayout

function Layout() {
  const navigate = useNavigate()
  const [lifted, setLifted] = useState(false)

  // 只记录离散的「已滚动」状态；模糊半径、底色、hairline 的连续过渡交给 CSS（合成层插值）。
  useEffect(() => {
    const onScroll = () => setLifted(window.scrollY > 16)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

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
        <header className="ss-header" data-lifted={lifted}>
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
        </header>

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
