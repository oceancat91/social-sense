/**
 * 格式化日期时间
 */
export function formatDate(dateStr) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN')
}

/**
 * 检查用户是否已登录
 */
export function isAuthenticated() {
  return !!localStorage.getItem('token')
}
