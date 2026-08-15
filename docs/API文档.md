# Social Sense API 接口文档

## 基础信息

- **Base URL**: `http://localhost:5000/api/v1`
- **数据格式**: JSON
- **认证方式**: JWT Token（`Authorization: Bearer <token>`）

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

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | 是 | 用户名 |
| email | string | 是 | 邮箱 |
| password | string | 是 | 密码 |

### 1.2 用户登录

- **URL**: `POST /auth/login`

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
    "user": { "id": 1, "username": "admin" }
  }
}
```

## 2. 监控任务模块

### 2.1 获取支持的平台列表

- **URL**: `GET /tasks/platforms`
- **响应**: 6 大平台（weibo/douyin/xiaohongshu/bilibili/zhihu/kuaishou）的标识、名称与主题色。

### 2.2 创建监控任务

- **URL**: `POST /tasks`
- **请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| keywords | array | 是 | 监控关键词列表 |
| platform | string | 否 | 目标平台，默认 `all`（全平台） |
| days | int | 否 | 模拟事件回溯天数，默认 14 |
| auto_collect | bool | 否 | 是否自动启动采集，默认 true |

- **说明**: 创建后自动在后台执行"采集 → 清洗 → 情感分析 → 关键词提取 → 入库"管道，任务状态变为 `collecting`，完成后变为 `active`。

### 2.3 获取任务列表

- **URL**: `GET /tasks?page=1&page_size=10`

### 2.4 触发任务采集

- **URL**: `POST /tasks/<task_id>/collect`
- **说明**: 手动触发采集（后台执行）。任务正在采集中时返回 409。

### 2.5 删除任务

- **URL**: `DELETE /tasks/<task_id>`
- **说明**: 同时删除任务关联的全部舆情数据。

## 3. 舆情分析模块

所有分析接口支持以下通用查询参数：

| 参数 | 类型 | 说明 |
|------|------|------|
| task_id | int | 限定单个任务 |
| platform | string | 限定平台，默认全部 |
| days | int | 限定近 N 天数据 |

### 3.1 舆情总览

- **URL**: `GET /analysis/overview`
- **响应**: 数据总量、正/中/负情感数量、负面占比、平均情感分、各平台数据量分布。

### 3.2 跨平台对比

- **URL**: `GET /analysis/platform-comparison`
- **响应**: 各平台声量、情感分布、平均情感分、负面率、互动总量（用于情绪极化分析）。

### 3.3 声量与情感趋势

- **URL**: `GET /analysis/trend?days=14`
- **响应**: 日期序列、各平台日声量序列、每日情感分布。

### 3.4 高频关键词

- **URL**: `GET /analysis/keywords?top_k=50`
- **响应**: 关键词及出现频次（词云数据源）。

### 3.5 跨平台传播溯源

- **URL**: `GET /analysis/propagation?days=14`
- **响应**: 各平台首发时间、相对源头平台的传播延迟（小时）、峰值日期、日声量序列。

### 3.6 热门内容排行

- **URL**: `GET /analysis/hot-content?limit=10`
- **响应**: 按互动热度（点赞 + 评论×2 + 转发×3）排序的内容明细。

### 3.7 情感分析明细

- **URL**: `GET /analysis/sentiment?task_id=<id>`
- **响应**: 指定任务最近 100 条数据的情感分析结果。

### 3.8 热点话题

- **URL**: `GET /analysis/trending`
- **响应**: 基于高频关键词与互动热度聚合的话题榜。

## 4. 多 Agent 分析模块

> 跨平台多 Agent 架构：主控 Agent + 每平台一个 Agent，靠统一消息契约对齐、融合，输出跨平台终裁 CT 与「信息茧房指数」。引擎代码在 `agent/`（B 站单平台 Skill1–6）与 `multiagent/`（跨平台主控），由 `backend/app/services/agent_engine.py` 封装。

### 4.1 引擎状态

- **URL**: `GET /agent/status`
- **响应**: 引擎是否可用（`available`）与支持的平台列表。

### 4.2 创建跨平台分析任务

- **URL**: `POST /agent/analyze`
- **请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| keyword | string | 是 | 分析话题关键词 |
| platforms | array | 否 | 参与分析的平台列表；缺省时使用该用户已有数据覆盖的所有平台 |
| task_id | int | 否 | 限定数据来源为某个监控任务；缺省时使用该用户全部任务数据 |

- **说明**: 创建后后台执行「SentimentData → D_platform → Skill2–6 → 跨平台融合」，任务状态 `pending → running → success/partial/failed`。

### 4.3 获取分析报告列表

- **URL**: `GET /agent/reports?page=1&page_size=10`

### 4.4 获取分析报告详情

- **URL**: `GET /agent/reports/<report_id>`
- **响应 `data.result`** 包含:
  - `platform_reports[]`: 各平台的单平台报告（`D_ts`、立场分布、异常点、OT₁ 结论）
  - `cross_platform`: 跨平台终裁 CT（`CT_status`、`summary`、`claims[]`、`risk_flags[]`、`echo_chamber` 茧房指数、`calibration` CX 门禁）

> **数据源说明**：云端多 Agent 引擎不依赖真实 B 站爬虫/cookie，而是复用后端 `SentimentData`（已做情感分析）转成标准 `D_platform` 契约；未来接入真实采集器只需替换数据源转换层。未配置 `DEEPSEEK_API_KEY` 时，Skill5/6 结论与主控归纳自动降级为确定性规则，仍可跑通 Skill2–4 与跨平台融合。

## 5. 数据采集说明

当前阶段采集由多平台模拟数据源驱动（`scripts/seed_demo.py` / `scripts/crawl.py`），模拟热点事件在 6 大平台的完整生命周期与跨平台传播时序。真实平台采集器已在 `crawler_service.py` 预留接口，接入合规数据源后可按平台逐步替换。

情感分析默认使用 HuggingFace 预训练模型（`SENTIMENT_MODEL_NAME`），模型不可用或置信度不足时自动降级：预训练模型 → 词典分析（含否定词、程度副词处理）。
