import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Form,
  Input,
  Button,
  Tabs,
  App as AntApp,
} from 'antd'
import {
  RadarChartOutlined,
  UserOutlined,
  LockOutlined,
  MailOutlined,
} from '@ant-design/icons'
import api from '../services/api'

function Login() {
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState('login')
  const navigate = useNavigate()
  const { message, modal } = AntApp.useApp()
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
        navigate('/agent')
      }
    } catch (err) {
      const errorData = err.response?.data
      const msg = errorData?.message || '操作失败，请重试'

      if (errorData?.error_type === 'wrong_password') {
        modal.error({
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
    <div className="ss-login">
      <aside className="ss-login__radar">
        <div className="ss-login__brand">
          <span className="ss-brand__mark">
            <RadarChartOutlined />
          </span>
          <span>Social Sense</span>
        </div>

        <div className="ss-login__hero">
          <h1>
            跨平台舆情感知，<em>穿透信息茧房。</em>
          </h1>
          <p>
            多平台采集、立场画像与时间对齐融合，量化平台间的情绪分歧与回声室效应，
            让公开讨论真正可被观察。
          </p>
        </div>

        <div className="ss-login__foot">
          <span>BILIBILI</span>
          <span>WEIBO</span>
          <span>DOUYIN</span>
          <span>XHS</span>
          <span>ZHIHU</span>
          <span>KUAISHOU</span>
        </div>
      </aside>

      <div className="ss-login__side">
        <div className="ss-login__panel">
          <h2>{activeTab === 'login' ? '接入情报台' : '创建账号'}</h2>
          <p className="sub">
            {activeTab === 'login' ? 'AUTH / LOGIN' : 'AUTH / REGISTER'}
          </p>

          <Form form={form} layout="vertical" onFinish={onFinish} autoComplete="off">
            <Tabs
              activeKey={activeTab}
              onChange={(key) => {
                setActiveTab(key)
                if (key === 'login') form.resetFields(['username'])
              }}
              items={[
                {
                  key: 'login',
                  label: '登录',
                  children: (
                    <>
                      <Form.Item label="邮箱" name="email" rules={[{ required: true, message: '请输入邮箱' }]}>
                        <Input prefix={<MailOutlined className="field-prefix" />} placeholder="请输入邮箱" size="large" />
                      </Form.Item>
                      <Form.Item label="密码" name="password" rules={[{ required: true, message: '请输入密码' }]}>
                        <Input.Password prefix={<LockOutlined className="field-prefix" />} placeholder="请输入密码" size="large" />
                      </Form.Item>
                      <Form.Item style={{ marginBottom: 0, marginTop: 26 }}>
                        <Button type="primary" htmlType="submit" loading={loading} block size="large">
                          进入分析台
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
                        <Input prefix={<UserOutlined className="field-prefix" />} placeholder="请输入用户名" size="large" />
                      </Form.Item>
                      <Form.Item label="邮箱" name="email" rules={[{ required: true, message: '请输入邮箱' }]}>
                        <Input prefix={<MailOutlined className="field-prefix" />} placeholder="请输入邮箱" size="large" />
                      </Form.Item>
                      <Form.Item label="密码" name="password" rules={[{ required: true, message: '请输入密码' }, { min: 6, message: '密码至少 6 位' }]}>
                        <Input.Password prefix={<LockOutlined className="field-prefix" />} placeholder="请输入密码（至少 6 位）" size="large" />
                      </Form.Item>
                      <Form.Item style={{ marginBottom: 0, marginTop: 26 }}>
                        <Button type="primary" htmlType="submit" loading={loading} block size="large">
                          注册并继续
                        </Button>
                      </Form.Item>
                    </>
                  ),
                },
              ]}
            />
          </Form>
        </div>
      </div>
    </div>
  )
}

export default Login
