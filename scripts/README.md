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

## 不在本目录的脚本

时序预测 + AI 归因的端到端流水线在 `workflow/forecast_ai/`，模型训练/导出/推理在 `social_forecast/scripts/`：

```bash
# 端到端：异常检测 → 预测 → LLM 归因报告（--template-llm 表示不调 DeepSeek）
python -u workflow/forecast_ai/run_workflow.py --template-llm

# 重算实验报告与图表
python -u result/build_report.py
```

说明：[`../workflow/forecast_ai/README.md`](../workflow/forecast_ai/README.md) ·
[`../social_forecast/README.md`](../social_forecast/README.md)。
