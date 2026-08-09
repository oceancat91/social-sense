import { useEffect, useRef, useState } from 'react'
import { Table, Button, Modal, Form, Input, Select, message, Tag, Popconfirm, Space, Card } from 'antd'
import { UnorderedListOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import api from '../services/api'
import { PLATFORM_OPTIONS, platformColor } from '../utils/platforms'
import { formatDate } from '../utils'

const STATUS_MAP = {
  active: { text: '运行中', color: 'green' },
  collecting: { text: '采集中', color: 'processing' },
  paused: { text: '已暂停', color: 'default' },
}

function Tasks() {
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [form] = Form.useForm()
  const pollTimer = useRef(null)

  const fetchTasks = async () => {
    setLoading(true)
    try {
      const res = await api.get('/tasks', { params: { page_size: 100 } })
      setTasks(res.data.data.tasks)
    } catch {
      message.error('获取任务列表失败')
    } finally {
      setLoading(false)
    }
  }

  // 有任务处于"采集中"状态时轮询刷新
  useEffect(() => {
    const collecting = tasks.some(t => t.status === 'collecting')
    if (collecting && !pollTimer.current) {
      pollTimer.current = setInterval(fetchTasks, 3000)
    } else if (!collecting && pollTimer.current) {
      clearInterval(pollTimer.current)
      pollTimer.current = null
    }
  }, [tasks])

  useEffect(() => {
    fetchTasks()
    return () => pollTimer.current && clearInterval(pollTimer.current)
  }, [])

  const handleCreate = async () => {
    const values = await form.validateFields()
    values.keywords = values.keywords.split(/[,，]/).map(k => k.trim()).filter(Boolean)
    await api.post('/tasks', values)
    message.success('任务创建成功，数据采集中')
    setModalVisible(false)
    form.resetFields()
    fetchTasks()
  }

  const handleCollect = async (taskId) => {
    try {
      await api.post(`/tasks/${taskId}/collect`)
      message.success('采集已启动')
      fetchTasks()
    } catch (err) {
      message.warning(err.response?.data?.message || '启动失败')
    }
  }

  const handleDelete = async (taskId) => {
    await api.delete(`/tasks/${taskId}`)
    message.success('删除成功')
    fetchTasks()
  }

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '关键词', dataIndex: 'keywords', key: 'keywords' },
    {
      title: '平台', dataIndex: 'platform', key: 'platform', width: 110,
      render: p => (p === 'all'
        ? <Tag color="purple">全部平台</Tag>
        : <Tag color={platformColor(p)}>{PLATFORM_OPTIONS.find(o => o.value === p)?.label || p}</Tag>),
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: s => <Tag color={STATUS_MAP[s]?.color}>{STATUS_MAP[s]?.text || s}</Tag>,
    },
    { title: '数据量', dataIndex: 'data_count', key: 'data_count', width: 90 },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180, render: t => formatDate(t) },
    {
      title: '操作', key: 'action', width: 180,
      render: (_, record) => (
        <Space>
          <Button
            size="small"
            icon={<ReloadOutlined />}
            disabled={record.status === 'collecting'}
            onClick={() => handleCollect(record.id)}
          >
            重新采集
          </Button>
          <Popconfirm title="删除任务及其全部数据？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
        <h2 className="page-title">
          <UnorderedListOutlined style={{ color: 'var(--primary)' }} /> 监控任务
        </h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalVisible(true)}>
          新建任务
        </Button>
      </div>
      <Card>
        <Table dataSource={tasks} columns={columns} rowKey="id" loading={loading} />
      </Card>
      <Modal title="新建监控任务" open={modalVisible} onOk={handleCreate} onCancel={() => setModalVisible(false)}>
        <Form form={form} layout="vertical">
          <Form.Item
            label="事件关键词（多个用逗号分隔）"
            name="keywords"
            rules={[{ required: true, message: '请输入关键词' }]}
          >
            <Input placeholder="如：校园食品安全" />
          </Form.Item>
          <Form.Item label="目标平台" name="platform" initialValue="all">
            <Select options={PLATFORM_OPTIONS} />
          </Form.Item>
          <Form.Item label="模拟事件时间跨度（天）" name="days" initialValue={14}>
            <Select options={[{ value: 7, label: '7 天' }, { value: 14, label: '14 天' }, { value: 30, label: '30 天' }]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Tasks
