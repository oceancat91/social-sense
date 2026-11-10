# -*- coding: utf-8 -*-
"""把创新点段落压缩到 600 字以内（保留学术/工程/社会三条主线）。"""
import pathlib
import re

SCRIPT = pathlib.Path(r"D:\HuaweiMoveData\Users\32002\Desktop\social-sense\scripts\fill_midterm_report.py")
text = SCRIPT.read_text(encoding="utf-8")

NEW = '''innovation = """一、学术创新：把结论可信度做成可判定的规则，而不是交给模型自评

单平台层 Skill5 产出 OT₀ 后，Skill6 用 G1–G7 七条纯规则门禁逐项核对：趋势断言须与声量实际走向一致、情绪断言须与 sent_mean 一致、立场断言不得与全局主导立场相反、风险等级不得夸大 Skill3 判据、证据链须完整。规则不调用大模型，因此不存在"模型自认正确"的循环论证；不通过即驳回或受限改写。跨平台层再用 CX1–CX5 拦住"平台不足却下跨平台结论""断言无证据"等越界情形。

模型同样"先分解、再建模"：趋势由 EMA、季节由 Fourier 基、冲击由 PELT 变点、残差由谱分解给出，分解不含可学习参数、四个分量可单独验证；各分量配专属编码器，主干 Mamba 只服务残差通路。

二、工程创新：层次化多 Agent + 唯一消息契约

平台 Agent（每平台一套 Skill1–6）、融合层（对齐 + 融合）、主控 Agent 三层，层间只通过 PlatformReport 契约通信，平台实现可独立替换。对齐坚持外连接加平台内 z-score，明令禁止跨平台插值冒充本平台观测；编排用 LangGraph，缺依赖时回退线性执行，保证任意环境可跑通。

三、社会价值：用可量化指标暴露平台分裂

茧房指数 = 0.4·立场分歧 + 0.3·情绪分歧 + 0.3·(1 − 声量共振)：立场分歧取各平台立场分布的 JS 散度、情绪分歧取情绪均值极差、声量共振取声量序列 Pearson 相关。当同一话题在不同平台"立场对立、情绪反向、声量不共振"时该指数趋近 1，即定量证明各平台私域各自形成回音室，把"信息茧房"从主观描述变成可比、可复现的硬指标。"""'''

pattern = re.compile(r'^innovation = """.*?"""', re.S | re.M)
if not pattern.search(text):
    raise SystemExit("未找到 innovation 段落")
text = pattern.sub(lambda _: NEW, text, count=1)
SCRIPT.write_text(text, encoding="utf-8")

for name in ("progress", "innovation", "reflection", "budget_plan"):
    m = re.search(rf'^{name} = """(.*?)"""', text, re.S | re.M)
    if not m:
        continue
    body = re.sub(r"\s+", "", m.group(1))
    limit = {"progress": 2000, "innovation": 600, "reflection": 2000, "budget_plan": 2000}[name]
    print(f"  {name:12}: {len(body):5} 字 / 限 {limit} -> {'OK' if len(body) <= limit else '超限'}")
