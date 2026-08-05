import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Form, Input, Button, Card, Tabs, Modal, message } from 'antd'
import api from '../services/api'

function Login() {
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('login')
  const navigate = useNavigate()
  const [form] = Form.useForm()

  const onFinish = async (values) => {
    setLoading(true)
    try {
      if (activeTab === 'register') {
        await api.post('/auth/register', values)
        message.success('注册成功，请登录')
        setActiveTab('login')
        form.resetFields(['username'])
      } else {
        const res = await api.post('/auth/login', values)
        localStorage.setItem('token', res.data.data.token)
        message.success('登录成功')
        navigate('/dashboard')
      }
    } catch (err) {
      const errorData = err.response?.data
      const msg = errorData?.message || '操作失败，请重试'

      if (errorData?.error_type === 'wrong_password') {
        Modal.error({
          title: '登录失败',
          content: '密码错误，请检查后重试',
          okText: '知道了',
        })
      } else if (errorData?.error_type === 'not_found') {
        setActiveTab('register')
        message.info('该邮箱尚未注册，请填写用户名完成注册')
      } else {
        message.error(msg)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f0f2f5' }}>
      <Card style={{ width: 420 }}>
        <div style={{ textAlign: 'center', marginBottom: 8 }}>
          <h2 style={{ margin: 0 }}>Social Sense</h2>
          <p style={{ color: '#999', margin: '4px 0 0' }}>社交舆情感知平台</p>
        </div>

        <Form form={form} layout="vertical" onFinish={onFinish} autoComplete="off">
          <Tabs
            activeKey={activeTab}
            onChange={(key) => {
              setActiveTab(key)
              if (key === 'login') form.resetFields(['username'])
            }}
            centered
            items={[
              {
                key: 'login',
                label: '登录',
                children: (
                  <>
                    <Form.Item label="邮箱" name="email" rules={[{ required: true, message: '请输入邮箱' }]}>
                      <Input placeholder="请输入邮箱" />
                    </Form.Item>
                    <Form.Item label="密码" name="password" rules={[{ required: true, message: '请输入密码' }]}>
                      <Input.Password placeholder="请输入密码" />
                    </Form.Item>
                    <Form.Item style={{ marginBottom: 0 }}>
                      <Button type="primary" htmlType="submit" loading={loading} block>
                        登录
                      </Button>
                    </Form.Item>
                  </>
                ),
              },
              {
                key: 'register',
                label: '注册',
                children: (
                  <>
                    <Form.Item label="用户名" name="username" rules={[{ required: true, message: '请输入用户名' }]}>
                      <Input placeholder="请输入用户名" />
                    </Form.Item>
                    <Form.Item label="邮箱" name="email" rules={[{ required: true, message: '请输入邮箱' }]}>
                      <Input placeholder="请输入邮箱" />
                    </Form.Item>
                    <Form.Item label="密码" name="password" rules={[{ required: true, message: '请输入密码' }, { min: 6, message: '密码至少 6 位' }]}>
                      <Input.Password placeholder="请输入密码（至少 6 位）" />
                    </Form.Item>
                    <Form.Item style={{ marginBottom: 0 }}>
                      <Button type="primary" htmlType="submit" loading={loading} block>
                        注册
                      </Button>
                    </Form.Item>
                  </>
                ),
              },
            ]}
          />
        </Form>
      </Card>
    </div>
  )
}

export default Login
