import { lazy, Suspense } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { Spin } from 'antd'
import Layout from './components/Layout'
import { isAuthenticated } from './utils'

// 页面按路由懒加载：图表依赖（echarts）只在进入分析台时下载，不阻塞首屏。
const Login = lazy(() => import('./pages/Login'))
const AgentReports = lazy(() => import('./pages/AgentReports'))

function RouteFallback() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '96px 0' }}>
      <Spin />
    </div>
  )
}

function ProtectedRoute({ children }) {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />
  }
  return children
}

function App() {
  return (
    <Router basename="/app">
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/login" element={
            isAuthenticated() ? <Navigate to="/agent" replace /> : <Login />
          } />
          <Route path="/" element={
            <ProtectedRoute><Layout /></ProtectedRoute>
          }>
            <Route index element={<Navigate to="/agent" replace />} />
            <Route path="agent" element={<AgentReports />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </Router>
  )
}

export default App
