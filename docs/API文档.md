# Social Sense API 接口文档

## 基础信息

- **Base URL**: `http://localhost:5000/api/v1`
- **数据格式**: JSON
- **认证方式**: JWT Token

## 通用响应格式

```json
{
  "code": 200,
  "message": "操作成功",
  "data": {}
}
```

## 1. 用户模块

### 1.1 用户注册

- **URL**: `POST /auth/register`
- **请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | 是 | 用户名 |
| email | string | 是 | 邮箱 |
| password | string | 是 | 密码 |

- **响应示例**:

```json
{
  "code": 200,
  "message": "注册成功",
  "data": {
    "user_id": 1,
    "username": "testuser"
  }
}
```

### 1.2 用户登录

- **URL**: `POST /auth/login`
- **请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| email | string | 是 | 邮箱 |
| password | string | 是 | 密码 |

- **响应示例**:

```json
{
  "code": 200,
  "message": "登录成功",
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "user": {
      "id": 1,
      "username": "testuser"
    }
  }
}
```

## 2. 监控任务模块

### 2.1 创建监控任务

- **URL**: `POST /tasks`
- **请求头**: `Authorization: Bearer <token>`
- **请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| keywords | array | 是 | 监控关键词列表 |
| platform | string | 是 | 目标平台 |

### 2.2 获取任务列表

- **URL**: `GET /tasks`
- **请求头**: `Authorization: Bearer <token>`
- **查询参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页数量，默认 10 |

## 3. 舆情分析模块

### 3.1 获取舆情概览

- **URL**: `GET /analysis/overview`
- **请求头**: `Authorization: Bearer <token>`

### 3.2 获取情感分析结果

- **URL**: `GET /analysis/sentiment`
- **请求头**: `Authorization: Bearer <token>`
- **查询参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| task_id | int | 是 | 任务 ID |
| start_date | string | 否 | 开始日期 |
| end_date | string | 否 | 结束日期 |

### 3.3 获取热点话题

- **URL**: `GET /analysis/trending`
- **请求头**: `Authorization: Bearer <token>`
