# Social Sense

跨平台社交媒体舆情采集、分析与可视化系统。项目将平台侧数据整理为统一契约，再通过单平台 Agent 与跨平台 Agent 分析立场、情绪、传播节奏及信息茧房风险。

## 仓库导航

| 目录 | 职责 |
| --- | --- |
| `backend/` | Flask API、数据模型和业务服务 |
| `frontend/` | Three.js 三维档案终端（TypeScript + Vite） |
| `landing/` | Next.js 项目介绍页 |
| `agent/` | 单平台 Agent 的采集、画像、分析、增强与结论流水线 |
| `multiagent/` | 跨平台报告契约、对齐、融合与主控归纳 |
| `scripts/` | 可直接执行的初始化、运维和数据集工具；详见 [`scripts/README.md`](scripts/README.md) |
| `docs/` | 产品、架构、API 与部署文档；详见 [`docs/README.md`](docs/README.md) |
| `deploy/` | Docker、Nginx 与云部署辅助文件 |
| `tests/` | 后端与 Agent 回归测试 |

## 快速开始

要求：Python 3.9+、Node.js 18+。MySQL 可选；本地开发可在 `.env` 中设置 `DB_DRIVER=sqlite`。

```bash
cp .env.example .env
pip install -r backend/requirements.txt
npm --prefix frontend install

python scripts/bootstrap/init_db.py
python scripts/bootstrap/seed_demo.py

python backend/run.py
# 新终端
npm --prefix frontend run dev
```

默认打开 `http://localhost:3000/app/`，管理员账户为
`admin@social-sense.com` / `admin123`。项目介绍页可另行运行：

```bash
npm --prefix landing install
npm --prefix landing run dev
```

## 常用命令

```bash
# 采集、清洗、情感分析并入库
python scripts/operations/crawl.py --keyword "人工智能" --platform all --days 14

# 验证已启动的分析 API
python scripts/operations/verify_api.py

# 后端测试
python -m pytest tests/test_backend -v

# 整理外部 CSV 为分析数据集（显式指定输入、输出路径）
python -m scripts.dataset.prepare.clean_analysis --src path/to/raw --dst path/to/cleaned
```

## 架构概览

```text
Three.js 档案终端 / Next.js 介绍页
             │
        Flask API
             │
单平台 Agent（采集 → 画像 → 多模态分析 → 校准）
             │ PlatformReport × N
跨平台 Agent（对齐 → 融合 → 主控归纳）
```

关于数据契约、Agent 门禁和部署方式，请从 [`docs/README.md`](docs/README.md) 进入对应文档。

## 贡献与许可

提交规范与开发约定见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。本项目使用 [MIT License](LICENSE)。
