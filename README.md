# Social Sense

跨平台社交媒体舆情采集、分析与可视化系统。项目将平台侧数据整理为统一契约，再通过单平台 Agent 与跨平台 Agent 分析立场、情绪、传播节奏及信息茧房风险。

## 仓库导航

| 目录 | 职责 |
| --- | --- |
| `backend/` | Flask API、数据模型和业务服务（含 `forecast_service` 预测适配） |
| `frontend/` | Three.js 三维档案终端（TypeScript + Vite） |
| `landing/` | Next.js 项目介绍页 |
| `agent/` | 单平台 Agent 的采集、画像、分析、增强与结论流水线 |
| `multiagent/` | 跨平台报告契约、对齐、融合与主控归纳 |
| `social_forecast/` | 时序预测 + 异常归因模型（checkpoint / 推理 / DeepSeek 报告）；详见 [`social_forecast/README.md`](social_forecast/README.md) |
| `workflow/` | 端到端流水线（异常 → 预测 → LLM）；详见 [`workflow/forecast_ai/README.md`](workflow/forecast_ai/README.md) |
| `result/` | 预测模型的决策口径实验报告与图表；详见 [`result/README.md`](result/README.md) |
| `config/` | 本地环境变量配置与示例；详见 [`config/README.md`](config/README.md) |
| `scripts/` | 可直接执行的初始化、运维和数据集工具；详见 [`scripts/README.md`](scripts/README.md) |
| `docs/` | 产品、架构、API 与部署文档；详见 [`docs/README.md`](docs/README.md) |
| `deploy/` | Docker、Nginx 与云部署辅助文件 |
| `tests/` | 后端与 Agent 回归测试 |

## 快速开始

要求：Python 3.9+、Node.js 18+。MySQL 可选；本地开发可在 `config/.env` 中设置 `DB_DRIVER=sqlite`。

> **先建虚拟环境，再用它装依赖。** 下面所有 `python` / `pip` 命令都假定你已经激活了虚拟环境；
> 没激活的话，裸 `python` 会落到系统解释器上，缺包报错会很难查（尤其是预测功能要的 torch，
> 体积大、很容易只装在某个环境里）。

```bash
# 建虚拟环境（只需一次）
python -m venv .venv

# 激活：Windows PowerShell        .venv\Scripts\Activate.ps1
#       Windows cmd               .venv\Scripts\activate.bat
#       macOS / Linux             source .venv/bin/activate
```

激活后提示符前面会出现 `(.venv)`。**不想激活也行**，把下面的 `python` 换成解释器的完整路径即可：
Windows 是 `.venv\Scripts\python.exe`，macOS / Linux 是 `.venv/bin/python`。

```bash
cp config/.env.example config/.env
pip install -r backend/requirements.txt

# 预测功能需要额外的重依赖（torch / matplotlib / scipy / scikit-learn 等）
# 不跑预测的话这行可以跳过
pip install -r social_forecast/requirements.txt

npm --prefix frontend install

python scripts/bootstrap/init_db.py
python scripts/bootstrap/seed_demo.py

python backend/run.py
# 新终端
npm --prefix frontend run dev
```

依赖分两份是**故意的**：`backend/requirements.txt` 是后端跑起来的最小集，
`social_forecast/requirements.txt` 只有预测功能才需要（torch 一个就上 GB），
不跑预测的部署不必装。

默认打开 `http://localhost:3000/app/`，管理员账户为
`admin@social-sense.com` / `admin123`。

**热度预测仪表盘**（模型权重不进版本库，需先按
[`social_forecast/README.md`](social_forecast/README.md) 准备 checkpoint）：

```text
http://localhost:5000/forecast
```

API：`/api/v1/forecast/status`、`/dashboard-data`、`/predict`、`/report`。

> 这是全项目唯一不加 JWT 的业务接口（仪表盘是独立静态页，`dashboard.js` 不带 token，
> 直接加 `@jwt_required` 会让页面变空白）。**线上由 nginx 层用 HTTP Basic 密码保护**，
> 账号密码用 `sudo bash deploy/setup-forecast-auth.sh` 生成，详见
> [`docs/部署文档.md`](docs/部署文档.md) 的「正式域名双站点部署」一节。

项目介绍页可另行运行：

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
python -m pytest -c tests/pytest.ini tests/test_backend -v

# 整理外部 CSV 为分析数据集（显式指定输入、输出路径）
python -m scripts.dataset.prepare.clean_analysis --src path/to/raw --dst path/to/cleaned

# 时序预测 + AI 归因端到端工作流（需先有 checkpoint；--template-llm 表示不调 DeepSeek）
python -u workflow/forecast_ai/run_workflow.py --template-llm

# 重算预测模型的实验报告与图表
python -u result/build_report.py
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

提交规范与开发约定见 [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md)。本项目使用 [MIT License](docs/LICENSE)。
