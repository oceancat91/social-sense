import { useEffect, useState } from 'react'
import { Table, Button, Modal, Form, Input, Select, message } from 'antd'
import api from '../services/api'

function Tasks() {
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [form] = Form.useForm()

  const fetchTasks = async () => {
    setLoading(true)
    try {
      const res = await api.get('/tasks')
      setTasks(res.data.data.tasks)
    } catch {
      message.error('获取任务列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchTasks() }, [])

  const handleCreate = async () => {
    const values = await form.validateFields()
    values.keywords = values.keywords.split(',').map(k => k.trim())
    await api.post('/tasks', values)
    message.success('任务创建成功')
    setModalVisible(false)
    form.resetFields()
    fetchTasks()
  }

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id' },
    { title: '关键词', dataIndex: 'keywords', key: 'keywords' },
    { title: '平台', dataIndex: 'platform', key: 'platform' },
    { title: '状态', dataIndex: 'status', key: 'status' },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at' },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2>监控任务</h2>
        <Button type="primary" onClick={() => setModalVisible(true)}>新建任务</Button>
      </div>
      <Table dataSource={tasks} columns={columns} rowKey="id" loading={loading} />
      <Modal title="新建监控任务" open={modalVisible} onOk={handleCreate} onCancel={() => setModalVisible(false)}>
        <Form form={form} layout="vertical">
          <Form.Item label="关键词（逗号分隔）" name="keywords" rules={[{ required: true }]}>
            <Input placeholder="如：人工智能,深度学习" />
          </Form.Item>
          <Form.Item label="平台" name="platform" initialValue="weibo">
            <Select options={[{ value: 'weibo', label: '微博' }, { value: 'zhihu', label: '知乎' }]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Tasks
