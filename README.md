# Social Sense - 社交舆情感知平台

<p align="center">
  <strong>基于大数据与人工智能的社交媒体舆情分析系统</strong>
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

Social Sense 是一个面向社交媒体的舆情感知与分析平台，旨在帮助用户实时监控、分析和可视化社交网络上的舆论动态。本项目为大学生双创（创新创业）项目。

## 功能特性

- **数据采集**：支持多平台社交媒体数据抓取与整合
- **情感分析**：基于 NLP 技术的文本情感倾向分析
- **热点追踪**：实时发现和追踪社交网络热点话题
- **可视化看板**：直观的数据可视化仪表盘
- **预警通知**：舆情异常波动预警与推送
- **报告生成**：自动生成舆情分析报告

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
- MySQL >= 8.0
- Redis >= 6.0

### 安装步骤

1. **克隆项目**

```bash
git clone https://github.com/oceancat91/social-sense.git
cd social-sense
```

2. **安装后端依赖**

```bash
cd backend
pip install -r requirements.txt
```

3. **安装前端依赖**

```bash
cd frontend
npm install
```

4. **配置环境变量**

```bash
cp .env.example .env
# 编辑 .env 文件，填入必要的配置信息
```

5. **启动开发服务器**

```bash
# 启动后端
cd backend
python run.py

# 启动前端（新终端）
cd frontend
npm run dev
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
