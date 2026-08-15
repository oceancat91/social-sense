# Social Sense - 基于多源社交媒体协同的舆情溯源与辅助预测系统

<p align="center">
  <strong>跨平台舆情采集、NLP 情感分析、传播溯源与多维可视化</strong>
</p>

<p align="center">
  <a href="#项目简介">项目简介</a> •
  <a href="#功能特性">功能特性</a> •
  <a href="#技术架构">技术架构</a> •
  <a href="#快速开始">快速开始</a> •
  <a href="#项目结构">项目结构</a> •
  <a href="#贡献指南">贡献指南</a> •
  <a href="#团队成员">团队成员</a>
</p>

---

## 项目简介

Social Sense 是一个面向多平台社交媒体的舆情分析系统。针对抖音、微博、小红书、B 站、知乎、快手六大平台在用户结构、社区文化与推荐机制上的差异，系统对同一热点事件在不同平台的舆论走向、情绪倾向与传播路径进行跨平台协同分析，突破单平台舆情分析的"信息茧房"局限。本项目为大学生双创（创新创业）项目。

## 功能特性

### 第一阶段（当前）

- **多平台数据采集**：覆盖抖音/微博/小红书/B站/知乎/快手，统一"采集 → 清洗 → 分析 → 入库"处理管道（当前由模拟数据源驱动，真实采集器接口已预留）
- **数据清洗**：HTML/URL/@提及去噪、文本标准化、内容哈希去重
- **NLP 情感分析**：大模型优先（接入 DeepSeek 等 OpenAI 兼容 API，识别反讽与隐含情绪），其次 HuggingFace 预训练模型（DistilBERT，置信度阈值判定中性），最终兜底词典分析（含否定词、程度副词处理），逐级自动降级
- **跨平台多维分析**：
  - 各平台情感分布对比（情绪极化分析）
  - 声量生命周期趋势（曝光 → 发酵 → 峰值 → 平息）
  - 跨平台传播溯源（首发平台、传播延迟、峰值时间）
  - 高频关键词词云、热门内容排行、热点话题
- **可视化看板**：React + ECharts 的多维交互式仪表盘

### 后续规划

- 真实平台数据源接入（合规 API / 采集框架）
- 舆情趋势辅助预测（时序模型）
- 舆情预警与通知推送
- 自动生成舆情分析报告

## 多 Agent 架构（核心创新）

本项目以「多平台多 Agent」为架构主线，三大创新落点：

- **工程创新**：主控 Agent + 每平台一个 Agent 的层次化多 Agent 架构，靠统一消息契约（`PlatformReport`）解耦；单平台 Agent 用 LangGraph 编排 6 个原子 Skill。
- **学术创新**：Agent 内单个 Skill 的精准度——严格校准门禁（G1–G7）、多模态时序文本异常检测、BM25 知识增强等。
- **社会价值**：打破平台私域信息茧房——用可量化的「茧房指数」暴露同一话题在不同平台舆论场的立场/情绪/声量分裂。

```text
主控 Agent (multiagent/master.py)
   ▲  跨平台归纳 + CX1–CX5 门禁
   │  融合器 fuse.py（分歧度量 + 茧房指数）
   │  对齐器 align.py（时间轴对齐 + z-score 归一）
   ▲  PlatformReport × N（统一契约）
 B站Agent · 微博Agent · 抖音Agent · 小红书Agent ...
  （每个：Skill1采集清洗 → Skill2立场画像 → Skill3多模态分析
   → Skill4知识增强 → Skill5结论生成 → Skill6残差校准）
```

详见 [`agent/README.md`](agent/README.md) 与 [`multiagent/README.md`](multiagent/README.md)。

## 技术架构

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   前端展示    │     │   后端服务    │     │   数据存储    │
│  React/Vue   │◄───►│ Python/Flask │◄───►│  MySQL/Redis │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                    ┌──────┴──────┐
                    │  数据分析引擎  │
                    │ NLP / ML    │
                    └─────────────┘
```

### 技术栈

| 层级 | 技术选型 |
|------|---------|
| 前端 | React / Vue.js / ECharts |
| 后端 | Python / Flask / FastAPI |
| 数据库 | MySQL / Redis / MongoDB |
| 数据分析 | Pandas / Scikit-learn / Transformers |
| 部署 | Docker / Nginx |

## 快速开始

### 环境要求

- Python >= 3.9
- Node.js >= 16
- MySQL >= 8.0（可选，本地开发可用 SQLite 免安装）

### 安装步骤

1. **克隆项目**

```bash
git clone https://github.com/oceancat91/social-sense.git
cd social-sense
```

2. **安装后端依赖**

```bash
pip install -r backend/requirements.txt
# 可选：在 .env 中配置 LLM_API_KEY 启用大模型情感分析（效果最好）
# 可选：安装 PyTorch 以启用预训练情感模型（不装则自动降级为词典分析）
# pip install torch --index-url https://download.pytorch.org/whl/cpu
```

3. **安装前端依赖**

```bash
cd frontend
npm install
```

4. **配置环境变量**

```bash
cp .env.example .env
# 本地快速开发：设置 DB_DRIVER=sqlite 即可免装 MySQL
# 生产环境：设置 DB_DRIVER=mysql 并填写数据库连接信息
```

5. **初始化数据库并灌入演示数据**

```bash
python scripts/init_db.py      # 创建数据表与管理员账户（admin@social-sense.com / admin123）
python scripts/seed_demo.py    # 生成多平台演示舆情数据（约 400+ 条，含情感分析）
```

6. **启动开发服务器**

```bash
# 启动后端
python backend/run.py

# 启动前端（新终端）
cd frontend
npm run dev
```

访问 http://localhost:3000 ，使用管理员账户登录即可查看跨平台舆情看板与分析页面。

### 常用命令

```bash
# 命令行采集数据（全平台）
python scripts/crawl.py --keyword "人工智能" --platform all --days 14

# 运行后端测试
python -m pytest tests/test_backend -v
```

## 项目结构

```
social-sense/
├── README.md                 # 项目说明文档
├── LICENSE                   # 开源许可证
├── CONTRIBUTING.md           # 贡献指南
├── .gitignore                # Git 忽略配置
├── .env.example              # 环境变量示例
├── docker-compose.yml        # Docker 编排配置
├── docs/                     # 项目文档
│   ├── 需求文档.md            # 需求规格说明
│   ├── 设计文档.md            # 系统设计文档
│   ├── API文档.md             # 接口文档
│   └── 部署文档.md            # 部署指南
├── agent/                    # 单平台 Agent（B 站，Skill1–6 全链路 + LangGraph 编排）
│   ├── PlatformCrawler/      # Skill1 采集+清洗
│   ├── StanceProfiler/       # Skill2 立场画像
│   ├── MultimodalAnalyzer/   # Skill3 多模态时序文本分析
│   ├── KnowledgeAugmentor/   # Skill4 知识增强/RAG
│   ├── Conclusion/           # Skill5+6 结论生成与严格校准
│   ├── Agent/                # 全链路编排（agent.py + orchestrator.py）
│   └── dataset/              # 标准化数据集仓库
├── multiagent/               # 多平台多 Agent 架构（契约+对齐+融合+主控 Agent）
├── backend/                  # 后端代码
│   ├── app/                  # 应用主目录
│   │   ├── __init__.py       # 应用初始化
│   │   ├── config.py         # 配置文件
│   │   ├── models/           # 数据模型
│   │   ├── routes/           # 路由/接口
│   │   ├── services/         # 业务逻辑
│   │   └── utils/            # 工具函数
│   ├── requirements.txt      # Python 依赖
│   └── run.py                # 启动入口
├── frontend/                 # 前端代码
│   ├── public/               # 静态资源
│   ├── src/                  # 源代码
│   │   ├── components/       # 组件
│   │   ├── pages/            # 页面
│   │   ├── services/         # API 服务
│   │   ├── utils/            # 工具函数
│   │   └── App.jsx           # 根组件
│   ├── package.json          # Node 依赖
│   └── vite.config.js        # 构建配置
├── tests/                    # 测试代码
│   ├── test_backend/         # 后端测试
│   └── test_frontend/        # 前端测试
└── scripts/                  # 脚本工具
    ├── init_db.py            # 数据库初始化
    └── crawl.py              # 数据采集脚本
```

## 贡献指南

欢迎贡献代码！请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详细的贡献流程。

## 团队成员

| 姓名 | 角色 | 负责模块 |
|------|------|---------|
| 待补充 | 项目负责人 | 整体架构 |
| 待补充 | 前端开发 | 前端界面 |
| 待补充 | 后端开发 | 后端服务 |
| 待补充 | 数据分析 | 算法模型 |

## 许可证

本项目采用 [MIT](LICENSE) 许可证。
