import axios from 'axios'

// VITE_API_BASE_URL 由构建时注入，开发环境留空走 Vite proxy
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    // 401 未授权 / 422 token 过期或无效（flask-jwt-extended 对过期 token 默认返回 422）
    // 两者都应视为登录态失效，清除本地 token 并跳转登录页重新登录。
    const status = error.response?.status
    if (status === 401 || status === 422) {
      localStorage.removeItem('token')
      window.location.href = '/app/login'
    }
    return Promise.reject(error)
  }
)

export default api
