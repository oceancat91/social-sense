import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Tasks from './pages/Tasks'
import Analysis from './pages/Analysis'

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="tasks" element={<Tasks />} />
          <Route path="analysis" element={<Analysis />} />
        </Route>
      </Routes>
    </Router>
  )
}

export default App
