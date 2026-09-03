import React from 'react'
import ReactDOM from 'react-dom/client'
import { App as AntApp } from 'antd'
import App from './App'
import ThemeGate from './theme'
import '@fontsource-variable/inter'
import '@fontsource-variable/jetbrains-mono'
import './styles/global.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ThemeGate>
      <AntApp>
        <App />
      </AntApp>
    </ThemeGate>
  </React.StrictMode>
)
