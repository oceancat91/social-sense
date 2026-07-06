import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Form, Input, Button, Card, message } from 'antd'
import api from '../services/api'

function Login() {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const onFinish = async (values) => {
    setLoading(true)
    try {
      const res = await api.post('/auth/login', values)
      localStorage.setItem('token', res.data.data.token)
      message.success('登录成功')
      navigate('/dashboard')
    } catch {
      message.error('登录失败，请检查邮箱和密码')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f0f2f5' }}>
      <Card title="Social Sense 登录" style={{ width: 400 }}>
        <Form layout="vertical" onFinish={onFinish}>
          <Form.Item label="邮箱" name="email" rules={[{ required: true, message: '请输入邮箱' }]}>
            <Input placeholder="请输入邮箱" />
          </Form.Item>
          <Form.Item label="密码" name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password placeholder="请输入密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}

export default Login
