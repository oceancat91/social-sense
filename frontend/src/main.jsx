import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import './styles/global.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#1a73e8',
          colorLink: '#1a73e8',
          borderRadius: 8,
          fontSize: 14,
        },
        components: {
          Card: { headerFontSize: 16, headerBg: 'transparent' },
          Layout: { bodyBg: '#eef1f7', headerBg: '#ffffff', headerHeight: 64 },
        },
      }}
    >
      <App />
    </ConfigProvider>
  </React.StrictMode>
)
