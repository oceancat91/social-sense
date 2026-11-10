# 页面与证据对应表

所有路径相对仓库根目录。主讲 1–12 页；13–18 页为问答备份，不计入 360 秒。这里的证据索引与引用放在独立文件，PPT 备注只保留可口述讲稿。

| 输出页 | 模板源页 | 核心信息 | 证据入口 | 讲述边界 | 秒 |
|---:|---:|---|---|---|---:|
| 1 | 1 | SocialSense 项目、五人团队、指导教师 | 用户汇报表与创新训练立项书；`docs/midterm_20261029/sources/` | 日期为 2026 年 11 月，不预填具体场次或编号 | 15 |
| 2 | 6 | 平台口径、结论核验、预测评价、传播关系问题 | `multiagent/align.py`、`fuse.py`、`master.py`；P01/P02/P09 | 是研究问题，不是已完成需求调研的统计结果 | 25 |
| 3 | 5 | 五项任务的中期状态 | `agent/`、`multiagent/`、`social_forecast/`、`frontend/`；立项书 | 四条主线为原型状态；语义事件对齐和 GNN 溯源未宣称完成 | 35 |
| 4 | 9 | 以 PlatformReport 连接模块 | `agent/agent/orchestrator.py`、`multiagent/contract.py`、`backend/app/`、`frontend/src/` | 架构图不等于线上全链路验收；预测为旁路 | 35 |
| 5 | 12 | G1–G7、CX1–CX5 校准 | `agent/Conclusion/calib/gates.py`、`multiagent/master.py` | 规则是局部一致性检查，关键证据仍需人工核查 | 35 |
| 6 | 10 | T/S/C/R、专属编码、数值路由、可选文本 | `social_forecast/models/rep_moe.py`、`layers/rep_fusion.py`、`Mamba_block.py` | 按真实 forward 说明，不把借鉴方法写成首创 | 40 |
| 7 | 18 | 数值 MSE、方向、尖峰、数值包 | `social_forecast/results/retrain_20261019/deployment_verification.json` | with_text=False；MSE 高于持续值；文件体积不等于内存 | 40 |
| 8 | 20 | 档案入口实际界面 | `docs/midterm_20261029/evidence/local_archive.png`、`local_capture.json` | 本地仓库、内置档案数据；不证明线上实时采集 | 35 |
| 9 | 16 | 证据约束、分量设计、行为验证、人工复核 | C03/C06/C07/C08/C12/C13；P03–P10 | 项目特色定位为任务组合与可核验设计 | 25 |
| 10 | 17 | 五位成员职责与科研训练 | 原汇报表/立项书；修订后的分工与心得 | 为团队任务安排，不虚构第三方评价或奖项 | 25 |
| 11 | 26 | 至 2027.06 的三阶段计划与预算 | 立项书；`RESEARCH_WORKFLOW.md`；`RESEARCH_CONSTRAINTS.md` | 后续验收均为计划；7500 元为申报预算 | 35 |
| 12 | 27 | 阶段结论与进入问答 | 3–11 页的归纳 | 已有研究原型；后续补验证和溯源 | 15 |
| 13 | 18 副本 | 时间切分、两类阈值、混淆矩阵 | 同 7；`scripts/verify_forecast_checkpoint.py` | 测试分位数为回溯标签；重叠窗不独立 | 备份 |
| 14 | 15 | 文献—代码—未验证边界 | `research/READING_NOTES.md`、`CODE_EVIDENCE.md` | 方法依据不自动转化为性能证明 | 备份 |
| 15 | 21 | 档案详情与可核查字段 | `evidence/local_detail.png`、前端详情代码 | 展示的是存档案例；界面数据量不是预测实验规模 | 备份 |
| 16 | 13 | 原预算科目与核账事项 | 创新训练立项书；原汇报表调剂建议 | 不把拟调整 2200 元等写成已审批或实支 | 备份 |
| 17 | 25 | 六项后续风险与验收 | 工作流和约束文件 | 有明确记录才将状态改为完成 | 备份 |
| 18 | 23 | 10 篇文献与证据入口 | `research/acquisition.json`、研读笔记、代码审计 | 指定 Scholar 入口访问受限已留痕，未声称完成系统综述 | 备份 |

## 图表的数据出处

- 第 7 页原生柱状图：持续值 1.5246421099、数值路径 1.8885908127，来自独立验证 JSON 的 `numeric_holdout_metrics`。图中保留 3 位小数，比较比例用未舍入值计算。
- 第 13 页原生表格：TP 26、FP 42、FN 40、TN 154，与精确率、召回率一致。
- 第 16 页原生表格：申请书六类预算 1800、1200、2000、1000、800、700 元，总计 7500 元。
- 第 4–6 页为代码对应的结构示意图，不是实测流程耗时或因果图。

## 图像来源与使用范围

| 图像 | 来源与处理 | 用途 |
|---|---|---|
| 学校标识、校园建筑、红蓝装饰、电脑边框 | 用户提供知旅模板的原有素材；保留母版/版式，封面文字已替换 | 保持模板视觉一致性 |
| `evidence/local_archive.png` | 2026-10-29 本地前端运行实拍；嵌入模板电脑屏幕，保留完整截图范围 | 第 8 页 |
| `evidence/local_detail.png` | 同一本地前端的详情页面实拍；使用内置档案数据 | 第 15 页 |

未使用 AI 生成图冒充产品或实验截图。官网当次连接失败的记录见 `evidence/web_capture.json`，本地访问记录见 `evidence/local_capture.json`；原采集 JSON 记录入口访问，详情图片单独留存，未为缺失的详情请求回执编造时间戳。
