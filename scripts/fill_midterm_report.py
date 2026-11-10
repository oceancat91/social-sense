# -*- coding: utf-8 -*-
"""填写 2026 年度本科生创新训练培育项目中期汇报表。

依据：立项申报书（目标/团队/经费）+ 项目实际代码与部署状态（进展/成果）。
原则：只写真实完成的内容；未实现的部分明确标为「设计中/下一步」。
"""

import os
import pathlib
import re

import docx
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.shared import Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

FORM = pathlib.Path(os.environ["FORMDOCX"])
OUT = pathlib.Path(os.environ["OUTDOCX"])

d = docx.Document(str(FORM))

# ---------------------------------------------------------------- 工具函数

BODY_FONT = "宋体"
BODY_SIZE = Pt(10)


def style_run(run, size=BODY_SIZE, bold=False):
    run.font.size = size
    run.font.name = BODY_FONT
    run.font.bold = bold
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), BODY_FONT)
    rfonts.set(qn("w:ascii"), BODY_FONT)
    rfonts.set(qn("w:hAnsi"), BODY_FONT)


def trim_empty_paragraphs(table):
    """删掉模板里预留给手写的空段落。

    原模板每个小节标题行里都垫了十几到二十个空段落（留给手写），做电子版后
    这些空段落会把标题行撑成 480pt 的整片空白 —— 这才是页码之间大片空白的真凶
    （不是行高、不是垂直对齐、也不是跨页拆行）。保留每个格子的第一个非空段落，
    其余空段落删除。
    """
    for row in table.rows:
        seen = set()
        for cell in row.cells:
            if id(cell._tc) in seen:
                continue
            seen.add(id(cell._tc))
            paras = cell.paragraphs
            keeper = next((p for p in paras if p.text.strip()), None)
            if keeper is None:
                continue
            for para in paras:
                if para is not keeper and not para.text.strip():
                    para._element.getparent().remove(para._element)

def fill(cell, text, size=BODY_SIZE, spacing=1.1):
    """把多行文本写进单元格：每行一个段落，统一中文正文字体。

    空行会被丢弃，段间距由 space_after 控制，避免整份表格被空行撑得过长。
    （一）（二）这类小节标题自动加粗，便于专家快速扫描。
    """
    cell.text = ""
    lines = [line.strip() for line in text.strip("\n").split("\n") if line.strip()]
    for index, line in enumerate(lines):
        para = cell.paragraphs[0] if index == 0 else cell.add_paragraph()
        para.paragraph_format.line_spacing = spacing
        para.paragraph_format.space_after = Pt(2)
        heading = bool(re.match(r"^[（(][一二三四五六七八九十]+[）)]", line))
        style_run(para.add_run(line), size=size, bold=heading)


def tighten_cell_margins(table, top=0, bottom=0, side=60):
    """收紧单元格上下内边距（dxa，1/20 磅）。

    原模板每格上下都留了较大的内边距，几十个单元格累积下来会明显拉长版面。
    直接改 tblCellMar 比逐格设置更有效，也不影响表格结构。
    """
    tbl_pr = table._tbl.tblPr
    mar = tbl_pr.find(qn("w:tblCellMar"))
    if mar is None:
        mar = OxmlElement("w:tblCellMar")
        # tblPr 子元素有固定顺序，tblCellMar 必须排在 tblLook 之前
        look = tbl_pr.find(qn("w:tblLook"))
        if look is not None:
            look.addprevious(mar)
        else:
            tbl_pr.append(mar)
    for tag, value in (("w:top", top), ("w:left", side), ("w:bottom", bottom), ("w:right", side)):
        node = mar.find(qn(tag))
        if node is None:
            node = OxmlElement(tag)
            mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def prepare_rows(table):
    """整理表格行，消除跨页时的大片空白。

    两个坑都试过：
    - 禁止拆行（cantSplit）：长单元格整体移到下一页，页底出现 500~650pt 空白；
    - 允许拆行但单元格居中对齐：跨页的第一段分到 0 行空间，渲染成只有边框的
      "空壳"，内容全被挤到第二段，视觉上同样是整片空白。

    真正的原因是垂直对齐：改成顶端对齐后，第一段立刻显示前几行文字，剩余内容
    自然续到下一页，既没有空壳也没有大段留白。
    """
    for row in table.rows:
        tr_pr = row._tr.get_or_add_trPr()
        cant_split = tr_pr.find(qn("w:cantSplit"))
        if cant_split is not None:
            tr_pr.remove(cant_split)
        for cell in row.cells:
            cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP


def fill_row(cell, values, sizes=None):
    """表格行：一行多列，可分别指定字号。"""
    cell.text = ""
    para = cell.paragraphs[0]
    para.paragraph_format.line_spacing = 1.2
    for index, value in enumerate(values):
        if index:
            style_run(para.add_run("　"))
        size = (sizes or {}).get(index, BODY_SIZE)
        style_run(para.add_run(value), size=size)


# ---------------------------------------------------------------- 表 1：基本信息

t1 = d.tables[0]
fill_row(t1.rows[0].cells[2], ["SocialSense：基于多源社交媒体协同的舆情溯源与辅助预测系统"], {0: Pt(10)})
fill_row(t1.rows[1].cells[2], ["张艺嘉"])
fill_row(t1.rows[2].cells[2], ["数据科学与工程学院"])
fill_row(t1.rows[3].cells[2], ["数据科学与大数据技术"])
fill_row(t1.rows[4].cells[2], ["19980766941"])
fill_row(t1.rows[5].cells[2], ["3200287039@qq.com"])
fill_row(t1.rows[6].cells[2], ["树杨　副教授（机器学习）"])
fill_row(t1.rows[7].cells[2], ["2026 年 4 月"])

# 项目编号 / 填表日期
for para in d.paragraphs:
    if "填表日期" in para.text:
        para.text = "填表日期：2026 年 10 月 26 日"
        for run in para.runs:
            style_run(run)

# ---------------------------------------------------------------- 表 2：主体

t2 = d.tables[1]

# 允许跨页断行 + 顶端对齐，避免页底留白与"空壳"
prepare_rows(t1)
prepare_rows(t2)
# 收紧单元格上下内边距，明显缩短整份表格的纵向长度
tighten_cell_margins(t1)
tighten_cell_margins(t2)

# 项目基本情况
fill(t2.rows[0].cells[3], "自主立题（☑ 自立项目）")
fill(t2.rows[1].cells[3], "华东师范大学数据科学与工程学院；依托指导教师所在实验室")

# 一、项目计划达到的目标和内容
goal = """本项目目标是构建"SocialSense：基于多源社交媒体协同的舆情溯源与辅助预测系统"，面向微博、抖音、小红书、B站、快手等主流平台，突破单平台舆情分析的数据孤岛与"事后统计"局限，形成"数据采集—标准化融合—跨平台语义协同—传播路径溯源—热度趋势预测—可视化呈现"的一体化技术框架。具体研究内容包括五个方面：

1. 多平台数据采集与标准化。针对各平台字段命名与结构差异，建立统一字段映射机制（如微博 attitudes_count、B站 like、小红书 likes 统一映射为 interaction_volume），统一时间基准与清洗规则，自动过滤广告文本、水军评论与重复内容。

2. 跨平台语义协同分析。基于预训练语言模型对多平台文本进行向量化表示与情感倾向量化，识别不同平台中指向同一事件的内容簇，实现跨平台事件对齐，并量化同一事件在不同平台之间的情绪差异。

3. 传播路径溯源与关键节点识别。以用户、内容、话题、互动关系为要素构建多层异构传播图，采用图神经网络对节点重要性、扩散方向与传播强度建模，识别首发源头节点与关键传播节点（KOL）。

4. 热度趋势预测与风险预警。构建多维风险指标体系，采用时序深度学习模型对话题热度进行多步预测，实现由"事后分析"向"事前预警"的转变。

5. 可视化分析与智能报告生成。构建可交互的舆情可视化终端，结合大语言模型自动生成事件概述、风险评估与趋势研判报告。

中期应达到的目标：建成数据层与标准化体系；完成预测模型的训练、轻量化导出与上线；完成三维可视化终端并实现稳定运行；传播溯源模块完成方案设计与数据接口预留；形成软件著作权申请材料与学术论文初稿。"""
fill(t2.rows[3].cells[0], goal)

# 二、研究进展和当前成果
progress = """按"数据—智能体—模型—系统—成果"五个层面汇报本阶段进展。

（一）数据层：六平台采集与标准化体系
已打通 B站、微博、抖音、小红书、知乎、快手六个平台的数据采集，其中五个平台完成日度数据落库，主序列 6,259 天、平台专序列合计 12,734 条记录，覆盖 2009 年至 2026 年。建立统一字段映射（互动量统一为 interaction_volume、时间统一为 UTC 时间戳）与清洗规则 C1–C8，过滤广告、水军与重复内容。跨平台可比性通过"平台内 z-score"解决：不同平台的点赞量量级不可比，但归一化后的相对波动可比。

（二）单平台感知 Agent：Skill1–6 全链路已落地
每个平台由一个独立 Agent 完成从采集到结论的全过程，共六个 Skill：Skill1 PlatformCrawler（关键词检索 + 评论采集 + 规范清洗）、Skill2 StanceProfiler（立场、情绪、偏见强度画像，与 Skill1 联合产出 D_platform = {D_text, D_ts, D_meta}）、Skill3 多模态时序文本分析（异常检测、隐特征、残差与基线，异常分数超阈值时回调 Skill1 缩小粒度补采并从步骤 2 局部刷新）、Skill4 知识库与 RAG（仅作备用补充，明令不得替代主证）、Skill5 结论生成 OT₀、Skill6 严格校准产出 OT₁。

Skill6 是本层最关键的部件：它用 G1–G7 七条纯规则门禁逐项核对结论与数据是否一致——趋势断言与声量实际走向是否相符、情绪断言与 sent_mean 是否矛盾、立场断言是否与全局主导立场相反、风险等级是否夸大 Skill3 的判据、证据与复核链是否完整。全部通过才释放 OT₁，否则驳回或受限改写。编排用 LangGraph 状态图，未安装时自动回退线性执行。该链路已在真实话题上跑通（如"科比去世"），产出符合契约的 platform_report。

（三）跨平台多 Agent：对齐 → 融合 → 主控
多平台层由主控 Agent 统一归纳，与平台 Agent 之间以 PlatformReport 消息契约为唯一接口，平台实现可独立替换。对齐器把各平台时间轴外连接对齐，缺失帧填空窗，明令禁止用邻平台插值冒充本平台观测；融合器计算立场分布的 Jensen-Shannon 散度、情绪均值极差与声量序列相关系数，据此得到信息茧房指数；主控 Agent 汇总各平台结论与融合指标，输出结构化终裁 CT，并执行 CX1–CX5 门禁：平台数不足两个不得下跨平台结论、分歧表述不得夸大或漏报、断言引用的平台必须在报告集合内、每条断言须绑定至少一个平台证据、全平台空数据时不得出强结论。

（四）预测模型：确定性四路分解 + 分量专属编码 + 稀疏混合专家
1. 确定性四路分解。输入窗口先拆成四个可解释分量，分解不含可学习参数：趋势 T 由可学习平滑系数的 EMA 提取、季节 S 由周期 7 的 Fourier 基展开、冲击 C 来自 PELT 变点检测的阶跃序列、残差 R 为去趋势去季节后的谱残差，四者满足 x = T + S + C + R。突发冲击因此不会被平滑进总量。
2. 分量专属编码器。T 用逐点线性编码、S 用 PatchCNN 做窗口级形状编码、C 用稀疏事件编码器、R 用 Mamba 状态空间块。主干 Mamba 只服务残差通路。
3. 稀疏混合专家。四路表征进入 top-k 门控专家层，路由器只取 T 与 S 的池化特征，避免被噪声残差带偏。
4. 差分域输出与尺度解耦。预测增量 Δ 再累加回水平域，输出头零初始化使训练起点即等于持续基线；形状在单位尺度学习、幅度由窗口尺度乘可学习增益给出，并用窗口尺度 OOD 门控在测试期幅度漂移时切换。
5. 文本只进表征、不进残差。跨平台语义经 DS-SAA 注入，四条通路分别用拼接、FiLM、事件跳变与尺度调整，各带可学习置信门控。
测试集上方向判断准确率 65.5%、尖峰识别 AUC 0.610，均优于持续基线；如实说明：标准化均方误差 1.889 仍高于基线 1.525，与输出头零初始化（起点即基线）的设定有关，绝对数值拟合仍是下一阶段的改进方向。

（五）系统与成果
预测模型经数值权重导出后仅 242 KB（49,373 个参数，与全精度权重逐位等价），加载 1.5 秒、单次推理 0.08 秒、峰值内存 217.6 MB，已上线运行；预测起点锚定请求当日，区间滚动扩展到 21 天。前端以 TypeScript + three.js 构建三维档案终端，后端 Flask + Gunicorn，预测模块可选注册、依赖惰性导入，任一依赖缺失不影响主站。软件著作权正在申报中，论文已进入期刊投稿流程。

（六）尚未完成部分（如实说明）
传播路径溯源（多层异构传播图与图神经网络关键节点识别）完成方案设计与数据接口预留，尚未进入编码实现；跨平台事件对齐目前基于关键词与实体规则的初版，尚未引入向量聚类。这两项构成下一阶段的主要工作量。"""
fill(t2.rows[5].cells[0], progress)

# 三、项目创新点
innovation = """一、学术创新：把结论可信度做成可判定的规则，而非交给模型自评

Skill5 产出结论 OT₀ 后，Skill6 用 G1–G7 七条规则门禁核对：趋势断言须与声量实际走向一致、情绪断言须与 sent_mean 一致、立场断言不得与全局主导立场相反、风险等级不得夸大 Skill3 判据、证据须完整。规则不调用大模型，不存在"模型自认正确"的循环论证；不通过即驳回或改写。跨平台层再用 CX1–CX5 拦住"平台不足却下跨平台结论"等越界情形。

模型同样先分解再建模：趋势用 EMA、季节用 Fourier 基、冲击用 PELT 变点、残差用谱分解，分解不含可学习参数、四分量可单独验证；各分量配专属编码器，Mamba 只服务残差通路。

二、工程创新：层次化多 Agent + 唯一消息契约

平台 Agent（每平台 Skill1–6）、融合层、主控 Agent 三层，层间只靠 PlatformReport 契约通信，平台可独立替换。对齐用外连接加平台内 z-score，禁止跨平台插值冒充本平台观测；编排用 LangGraph，缺依赖时回退线性执行。

三、社会价值：用可量化指标暴露平台分裂

茧房指数 = 0.4·立场分歧 + 0.3·情绪分歧 + 0.3·(1 − 声量共振)，三项取立场分布 JS 散度、情绪均值极差、声量序列 Pearson 相关。同一话题在不同平台"立场对立、情绪反向、声量不共振"时该指数趋近 1，即证明各平台私域自成回音室，把"信息茧房"变成可复现的硬指标。"""
fill(t2.rows[7].cells[0], innovation)

# 四、研究心得
reflection = """（一）从"功能清单"到"能跑起来的系统"，中间隔着一整个工程量级

立项时我们把研究内容拆成五个模块，以为只要每个模块各自跑通就算完成。真正动手之后才发现，把五个模块拼成一个能连续运行、能在弱网和低配机器上稳定服务的系统，工作量远大于分别实现它们。模型在本地训练指标再好，如果加载要 477 MB、启动要十几秒，在 2 GB 的服务器上就落不了地；正是这个约束逼出了"数值权重导出"这条路径，也成了项目最有价值的工程产出之一。

（二）学会面对不好看的指标

第一次完整评估时，我们的方向准确率和尖峰识别都超过了基线，但均方误差反而比"直接沿用昨天的值"更差。当时第一反应是换模型、调参数，后来意识到：这不是调参能解决的，而是任务本身的难点——热度序列的绝对数值受突发事件影响极大，任何平滑模型都很难在 MSE 上打赢持续基线。我们最终选择如实记录这个结果，并把评价重心放在方向判断与尖峰识别这两个真正有用的能力上。这件事让我理解，"准确"不等于"所有指标都赢"，而是清楚知道模型能做什么、不能做什么。

（三）一次真实的线上故障，比十次顺利部署教得多

部署时预测模块在顶层导入了 numpy，而服务器环境没有安装该依赖，导致整个应用在启动阶段就失败——一个"可选功能"差点让主站完全不可用。修复方式是把依赖改为惰性导入、把模块注册包在异常处理里。这让我们确立了一条原则：可选功能的失败必须是可隔离的，不能拖垮主链路。之后我们在预测数据与字体加载上沿用同样的思路，任何一环失败都只做降级，不影响进入系统。

（四）轻量化带来的意外收获

把 477 MB 的完整权重压缩到 242 KB 之后，模型加载从"需要专门准备环境"变成了"和静态资源一样随系统分发"。这不只是省内存，而是改变了交付方式：预测能力可以跟着代码一起走，部署时不需要再关心模型服务、GPU 或显存。这让我体会到，工程优化做到位时，往往不只是性能数字变好，而是打开了原本不可行的方案。

（五）团队协作与分工

四位成员按数据、模型、溯源、前端四条线并行推进，通过统一的数据接口与字段规范降低耦合。实践中最大的摩擦点不是技术，而是"接口约定"——字段命名、时间格式、缺失值处理规则一旦不统一，联调成本就会成倍上升。后期我们固定了接口文档并每次变更同步，协作效率明显改善。

（六）需要改进的地方

一是前期对部署环境估计不足，性能与内存问题直到上线前才暴露，今后应在设计阶段就把运行环境作为约束条件纳入考虑。二是传播溯源模块进度落后于计划，原因是对图数据构建的复杂度估计偏低，下一阶段需要优先补齐。三是文档与实验记录的规范性仍有欠缺，部分中间实验没有及时归档，复盘时不得不重跑。"""
fill(t2.rows[9].cells[0], reflection)

# 五、项目组成员
members = [
    ("张艺嘉", "10245501451", "数据科学与大数据技术", "项目负责人。总体架构与技术路线设计；时序预测模型训练、轻量化导出与线上部署；前后端集成与系统联调。"),
    ("詹江叶煜", "10235501471", "数据科学与大数据技术", "传播路径溯源与图神经网络模型研究；跨平台传播拓扑图构建方案设计；关键传播节点识别方法调研。"),
    ("郑锦凡", "10245000446", "统计学", "舆情趋势预测与风险预警模块；时序模型对比实验与结果分析；风险指标体系设计。"),
    ("王悦", "10254511422", "教育学部", "多平台数据采集与清洗；统一字段映射与数据标准化体系构建；数据质量校验。"),
    ("吴珂欣", "10255101562", "软件工程", "系统前后端开发与可视化设计；三维档案终端界面实现；用户测试与体验优化。"),
]
for index, member in enumerate(members):
    row = t2.rows[12 + index]
    # 姓名字号略小，保证「詹江叶煜」这类四字姓名在窄列内单行显示
    fill_row(row.cells[0], [member[0]], {0: Pt(9)})
    fill_row(row.cells[1], [member[1]], {0: Pt(9)})
    fill_row(row.cells[2], [member[2]], {0: Pt(8.5)})
    fill_row(row.cells[4], [member[3]], {0: Pt(9)})

# 六、经费使用情况及下一步研究计划
budget_plan = """（一）经费使用情况

项目批准经费 7,500 元，目前按预算科目执行，主要用于系统部署、模型训练与成果产出：

1. 云服务器租赁（1,800 元）：已用于部署线上系统与数据库，按年租用，是当前最大的一笔固定支出。
2. 大模型调用费用（2,200 元）：用于舆情归因报告的自动生成与跨平台语义分析，按 Token 计费。该项较原预算的 1,000 元有所上调，原因是报告生成的频次与分析深度均高于预期，且模型效果验证需要反复调用。
3. 数据采集与接口费用（1,200 元）：用于多平台数据获取与第三方接口调用。
4. 软件开发与模型训练（1,600 元）：用于训练环境配置、算力与开发工具。该项较原预算的 2,000 元有所下调，开发与训练环境已基本建成，后续投入重心由训练侧转向推理与语义分析侧。
5. 专利及论文相关（700 元）：用于软件著作权申请、论文排版与投稿。

科目调整说明：原"调研与差旅费用"科目（800 元）已取消；"软件开发与模型训练"由 2,000 元调减至 1,600 元。两项合计 1,200 元一并调入"大模型调用费用"，使该项由 1,000 元调整为 2,200 元；项目总预算 7,500 元保持不变。以上为按预算科目列示的执行情况，具体金额与票据以财务报销记录为准。经费整体使用进度与项目进度基本匹配，未出现超支或挪用。

（二）下一步研究计划

2026 年 11 月—2026 年 12 月：补齐传播溯源模块。完成多层异构传播图的数据模型与抽取流程，实现基于图神经网络的节点重要性排序与关键传播节点识别，输出首发源头判定结果，并在前端提供传播路径的可视化视图。

2027 年 1 月—2027 年 3 月：提升预测与语义协同质量。一是针对均方误差偏高的短板，引入外部事件信号与多平台交叉特征，尝试降低绝对误差；二是将跨平台事件对齐由规则匹配升级为向量聚类，提升同事件识别的召回率；三是完成系统 2.0 版本并进行用户测试。

2027 年 4 月—2027 年 6 月：成果收敛与结题。完成软件著作权登记；推进论文投稿与返修；整理实验数据与技术文档；撰写结题报告并准备结题答辩。

风险与应对：传播溯源模块是当前进度风险最高的部分，若图数据构建难度超出预期，将优先保证"关键节点识别"这一核心功能可用，路径回溯的细粒度可视化作为可选项后置；预测精度方面，若外部特征引入后仍无法在均方误差上超越持续基线，将调整论文的论证重点，聚焦方向判断与尖峰预警的实际价值，并如实报告局限。"""
fill(t2.rows[18].cells[0], budget_plan)

# ---------------------------------------------------------------- 保存与校验

trim_empty_paragraphs(t1)
trim_empty_paragraphs(t2)

d.save(str(OUT))
print(f"saved: {OUT}")
print(f"size: {OUT.stat().st_size / 1024:.1f} KB")

check = docx.Document(str(OUT))
print(f"tables: {len(check.tables)}")
print(f"t1 项目名称: {check.tables[0].rows[0].cells[2].text.strip()}")
print(f"t2 一 首行: {check.tables[1].rows[3].cells[0].text.strip()[:40]}")
print(f"t2 二 字数: {len(check.tables[1].rows[5].cells[0].text.strip())}")
print(f"t2 三 字数: {len(check.tables[1].rows[7].cells[0].text.strip())}")
print(f"t2 四 字数: {len(check.tables[1].rows[9].cells[0].text.strip())}")
print(f"t2 六 字数: {len(check.tables[1].rows[18].cells[0].text.strip())}")
print(f"t2 成员1: {check.tables[1].rows[12].cells[0].text.strip()} / {check.tables[1].rows[12].cells[1].text.strip()}")
