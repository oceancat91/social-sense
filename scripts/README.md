# 脚本导航

脚本按职责分组，所有命令均应在仓库根目录执行。需要后端应用的脚本会自行定位 `backend/`，不依赖当前工作目录的偶然路径。

| 目录 | 命令 | 用途 |
| --- | --- | --- |
| `bootstrap/` | `python scripts/bootstrap/init_db.py` | 创建数据表和管理员账户 |
| `bootstrap/` | `python scripts/bootstrap/seed_demo.py` | 写入可重复执行的演示舆情任务（本地；容器内请用 `backend/scripts/seed_demo.py`） |
| `operations/` | `python scripts/operations/crawl.py --keyword …` | 运行采集、清洗、情感分析与入库管道 |
| `operations/` | `python scripts/operations/verify_api.py` | 验证已启动的分析 API |
| `dataset/` | `python -m scripts.dataset.prepare.clean_analysis --help` | 外部 CSV 整理、质量检查和结果校验 |

数据集工具的输入与输出位置均通过命令行参数指定，避免把个人计算机路径写入版本库。完整说明见 [`dataset/README.md`](dataset/README.md)。
