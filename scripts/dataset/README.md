# 外部数据集工具

这些工具面向**不纳入仓库**的外部 CSV。所有输入、输出目录均由参数提供，命令不会修改源文件。

## 准备

| 命令 | 作用 |
| --- | --- |
| `python -m scripts.dataset.prepare.merge_sources --help` | 合并分散的 B 站、微博和小红书清洗文件，并复制抖音/快手源文件 |
| `python -m scripts.dataset.prepare.clean_analysis --src RAW --dst CLEANED` | 输出统一 18 列分析字段集和 `all_cleaned.csv` |
| `python -m scripts.dataset.prepare.clean_minimal --src RAW --dst CLEANED` | 输出只含 `platform,time,text` 的轻量分析集 |

两种清洗命令服务于不同下游 schema，输出目录不可混用。

## 只读诊断

| 命令 | 作用 |
| --- | --- |
| `python -m scripts.dataset.diagnostics.schema --src RAW` | 检查字段、记录数、时间范围和基础质量指标 |
| `python -m scripts.dataset.diagnostics.health --src RAW` | 汇总空值、时间解析和三元组重复情况 |
| `python -m scripts.dataset.diagnostics.duplicates --src RAW` | 分析各平台的投影重复与整行重复 |
| `python -m scripts.dataset.diagnostics.kuaishou_duplicates --input RAW/kuaishou.csv` | 定位快手重复组中发生变化的字段 |
| `python -m scripts.dataset.diagnostics.verify_minimal --src CLEANED` | 校验轻量三列输出的格式、空值和重复 |
