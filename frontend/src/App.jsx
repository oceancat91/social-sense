import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Login from './pages/Login'
import AgentReports from './pages/AgentReports'
import { isAuthenticated } from './utils'

function ProtectedRoute({ children }) {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />
  }
  return children
}

function App() {
  return (
    <Router basename="/app">
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
    </Router>
  )
}

export default App
