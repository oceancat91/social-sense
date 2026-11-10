"""Author the requested value-rich revision in its native ppt-master workspace."""
from pathlib import Path
import hashlib
import json
import re
import xml.etree.ElementTree as E

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
A = ROOT / 'authoring-svg-flat'
NS = 'http://www.w3.org/2000/svg'
E.register_namespace('', NS)
BLUE, DARK, TEAL = '#4472C4', '#44546A', '#0D3745'
INK, MUTED, PALE, WHITE, RED = '#243446', '#64748B', '#EDF2F8', '#FFFFFF', '#BE2623'
EDITED = [2, 3, 4, 5, 6, 9, 10, 11, 17, 18]
SOURCES = {
    'W1': 'https://www.taptap.cn/moment/834126362733185189',
    'W2': 'https://www.taptap.cn/moment/832223722998859956',
    'W3': 'https://yuqing.sina.com/undefined/about',
    'W4': 'https://files.yqt365.com/fileOnline/instruction.html',
    'W5': 'https://arxiv.org/abs/1805.12512',
}

def el(parent, tag, **attrs):
    return E.SubElement(parent, '{' + NS + '}' + tag,
                        {k.replace('_', '-'): str(v) for k, v in attrs.items()})

def group(root, key, x, y, w, h, role=None):
    g = el(root, 'g', id=key, **{'data-pptx-bounds': f'{x} {y} {w} {h}'})
    if role:
        g.set('data-pptx-role', role)
    el(g, 'rect', x=x, y=y, width=w, height=h, fill='none')
    return g

def rect(g, x, y, w, h, fill=WHITE, stroke=None, rx=0):
    attrs = dict(x=x, y=y, width=w, height=h, fill=fill)
    if stroke:
        attrs.update(stroke=stroke, stroke_width=1.2)
    if rx:
        attrs.update(rx=rx, ry=rx)
    return el(g, 'rect', **attrs)

def txt(g, x, y, content, size=23, color=INK, bold=False, anchor='start', leading=1.45):
    t = el(g, 'text', x=x, y=y, font_size=size, fill=color,
           font_family='Microsoft YaHei', font_weight='bold' if bold else 'normal', text_anchor=anchor)
    lines = content.split('\n')
    t.text = lines[0]
    for line in lines[1:]:
        el(t, 'tspan', x=x, dy=round(size * leading, 2)).text = line
    return t

def cite(g, x, y, label, key, size=16):
    t = txt(g, x, y, '', size, BLUE)
    a = el(t, 'a', href=SOURCES[key])
    el(a, 'tspan', text_decoration='underline').text = label
    return t

def rule(g, x1, y1, x2, y2, color=BLUE, width=2):
    return el(g, 'line', x1=x1, y1=y1, x2=x2, y2=y2, stroke=color, stroke_width=width)

def base(page, title, subtitle):
    tree = E.parse(A / f'slide_{page:02d}.svg')
    r = tree.getroot()
    for child in list(r):
        ref = child.get('data-pptx-source-ref', '')
        if child.tag == '{' + NS + '}g' and not ref:
            r.remove(child)
        elif ref.startswith('slide:'):
            images = list(child.iter('{' + NS + '}image'))
            if not any(i.get('href', '').endswith('/image5.png') for i in images):
                r.remove(child)
    h = group(r, 'value-header', 95, 16, 815, 83, 'header')
    txt(h, 110, 63, title, 33, DARK, True)
    s = group(r, 'value-subtitle', 75, 108, 1130, 48)
    txt(s, 80, 139, subtitle, 21, MUTED)
    f = group(r, 'value-footer', 70, 680, 1100, 27, 'footer')
    txt(f, 76, 700, 'SocialSense  ·  创新训练类中期答辩', 13, MUTED)
    txt(f, 1155, 700, f'{page:02d} / 18' + ('  备份' if page > 12 else ''), 13, MUTED, anchor='end')
    return tree, r

def save(tree, page):
    tree.write(A / f'slide_{page:02d}.svg', encoding='utf-8', xml_declaration=True)

def numbered(r, key, x, y, w, h, number, heading, body, size=22):
    g = group(r, key, x, y, w, h)
    el(g, 'circle', cx=x+20, cy=y+22, r=19, fill=BLUE)
    txt(g, x+20, y+29, number, 18, WHITE, True, 'middle')
    txt(g, x+55, y+31, heading, 26, TEAL, True)
    txt(g, x+55, y+72, body, size, INK, leading=1.48)
    return g


# P02 modules: expanded argument, one original online image, source links.
t, r = base(2, '研究价值：从舆情监测走向社区互动',
            '以游戏梗文化为切入点：理解积极传播，连接创作来源、玩家表达与官方回应')
numbered(r, 'positive-spread', 65, 177, 735, 148, '01', '让积极内容被理解与看见',
         '角色、台词与共同经历被转化为可复用的表达，\n降低交流门槛，带动二次创作与圈层传播。\n分析对象因此应包含内容来源、变体和互动反馈。')
numbered(r, 'informed-response', 65, 333, 735, 148, '02', '让官方回应更有依据',
         '在转发、认可或使用玩家创作前，需要核对原始\n语境、作者与改编链，区分友好调侃和真实不满；\n这些信息可为素材支持、互动回应提供参考。')
numbered(r, 'community-trust', 65, 489, 735, 148, '03', '让社区维护兼顾参与和信任',
         '保留出处、解释立场差异，有助于呈现真实诉求、\n认可创作者贡献，并减少脱离语境的误判。\n正向互动的收益仍需试用与对照评估来验证。')
g = group(r, 'contest-evidence', 837, 171, 365, 498)
el(g, 'image', href='../images/summer_key_visual.jpg', x=855, y=175,
   width=330, height=440, preserveAspectRatio='xMidYMid meet')
cite(g, 851, 639, '[W2] TapTap 创作征集活动原图', 'W2', 16)
txt(g, 851, 664, '公开案例：征集二创、攻略与体验分享', 16, MUTED)
g = group(r, 'value-evidence', 70, 643, 740, 27)
cite(g, 80, 663, '[W1] 官方素材分享', 'W1', 16)
txt(g, 265, 663, '公开案例说明应用需求，不代表已验证的传播增益', 16, MUTED)
save(t, 2)

# P03 modules: ordered research workflow, official source material image.
t, r = base(3, '为什么需要溯源：从热梗流转到创作认可',
            '同一主题会被改写、拼接和跨平台转发；回应前需要可核查的出处与语境')
for i, (heading, body) in enumerate([
    ('追溯来源：找到可核查的原始表达', '区分活动素材、玩家原创与后续搬运；保存作者、\n发布时间和原链接，避免把最早采集误当真正首发。'),
    ('梳理传播：把内容变体放回关系链', '记录引用、改写与转发线索，比较平台扩散顺序；\n同源识别与传播图是后续重点，时间相关不等于因果。'),
    ('辅助回应：看见创作者与玩家诉求', '将出处、上下文与立场差异整理为可审阅档案，\n为素材支持、创作认可和社区答疑提供决策依据。'),
    ('评价反馈：观察互动与社区交流', '固定窗口比较二创参与、反馈质量和误读案例；\n控制版本活动等因素，避免把热度上涨归因于回应。'),
]):
    numbered(r, 'trace-stage-' + str(i), 65, 175+i*115, 755, 111,
             f'{i+1:02d}', heading, body, 21.5)
g = group(r, 'official-materials', 849, 174, 355, 496)
el(g, 'image', href='../images/official_summer_4.jpg', x=892, y=177,
   width=270, height=455.75, preserveAspectRatio='xMidYMid meet')
cite(g, 867, 655, '[W1] 官方公开素材图（完整比例）', 'W1', 16)
g = group(r, 'trace-evidence', 70, 643, 755, 29)
cite(g, 80, 665, '[W2] 征集要求原创首发', 'W2', 16)
cite(g, 297, 665, '[W5] 同源梗与跨社区传播研究', 'W5', 16)
save(t, 3)

# P04 modules: native editable architecture and a clearly marked research extension.
t, r = base(4, '技术如何承接：统一证据，再关联传播',
            '当前代码以 PlatformReport 连接单平台分析、跨平台比较与交互展示')
g = group(r, 'input-analysis', 65, 181, 285, 338)
rect(g, 65, 181, 285, 338, PALE)
txt(g, 85, 222, '① 单平台观测', 27, TEAL, True)
txt(g, 85, 272, '采集清洗与立场画像\n文本、时序及检索补充\n保留来源标识和元数据', 23, leading=1.6)
rule(g, 85, 382, 328, 382, '#CED9E6', 1)
txt(g, 85, 421, '已有价值', 22, BLUE, True)
txt(g, 85, 460, '将零散观测变为统一报告，\n为后续证据核查提供接口。', 20.5, leading=1.5)
g = group(r, 'report-fusion', 380, 181, 515, 338)
for y, heading, body in [
    (181, '② PlatformReport 数据契约', '结论 · 时序 · 元数据 · 引用'),
    (299, '③ 时间对齐与差异融合', '保留缺失；比较立场、情绪和声量'),
    (417, '④ 跨平台主控与 CX 校准', '把汇总结论绑定到具体平台证据'),
]:
    rect(g, 380, y, 515, 102, WHITE, BLUE, 6)
    txt(g, 637, y+38, heading, 25, BLUE, True, 'middle')
    txt(g, 637, y+76, body, 21, INK, False, 'middle')
    if y < 417:
        rule(g, 637, y+102, 637, y+118, BLUE, 2)
g = group(r, 'archive-application', 925, 181, 285, 338)
rect(g, 925, 181, 285, 338, PALE)
txt(g, 945, 222, '⑤ 服务与交互', 27, TEAL, True)
txt(g, 945, 272, 'Flask API 与三维档案\n组织范围、摘要和记录\n旁路接入数值预测结果', 22.5, leading=1.6)
rule(g, 945, 382, 1188, 382, '#CED9E6', 1)
txt(g, 945, 421, '面向人工复核', 22, BLUE, True)
txt(g, 945, 460, '帮助研究者回看观测依据，\n再判断是否适合官方回应。', 20.5, leading=1.5)
g = group(r, 'trace-extension', 70, 546, 1135, 113)
rect(g, 70, 546, 1135, 113, PALE)
txt(g, 92, 580, '面向梗溯源的后续衔接', 24, TEAL, True)
txt(g, 92, 616, '增加内容变体标注、原始链接与引用关系，再验证首发候选和传播链；现有时间对齐不等于语义同源识别。', 21)
txt(g, 92, 646, '代码定位：multiagent/contract.py · align.py · fuse.py；完整图传播溯源尚待验证。', 18, MUTED)
save(t, 4)

# P05 modules: semantic context, G/CX rules and the limits of factual support.
t, r = base(5, '支持正向互动，先让结论经得起复核',
            '“笑飞了”可能是赞赏，也可能是反讽；识别表达对象和语境，才能减少回应误判')
g = group(r, 'review-flow', 65, 180, 340, 472)
for y, heading in [(184, '原句、上下文与来源'), (294, '形成候选态度判断'),
                   (404, '规则核验与受限改写'), (514, '保留依据与不确定性')]:
    rect(g, 76, y, 318, 74, PALE, BLUE, 6)
    txt(g, 235, y+47, heading, 24, TEAL, True, 'middle')
    if y < 514:
        rule(g, 235, y+74, 235, y+110, BLUE, 2)
txt(g, 83, 631, '目的：减少脱离语境的强判断', 21, TEAL, True)
g = group(r, 'gates-single', 440, 180, 770, 211)
rect(g, 440, 180, 770, 211, WHITE, BLUE, 6)
txt(g, 464, 220, 'G1—G7：单平台结论与观测一致', 27, BLUE, True)
txt(g, 464, 267, '核对趋势、情绪、立场、引用标识、数值边界，\n检查空窗表述以及风险判断是否有观测依据。\n它能暴露结构性矛盾，不等于理解全部梗义与反讽。', 23, leading=1.48)
g = group(r, 'gates-cross', 440, 411, 770, 211)
rect(g, 440, 411, 770, 211, WHITE, TEAL, 6)
txt(g, 464, 451, 'CX1—CX5：跨平台汇总不掩盖分歧', 27, TEAL, True)
txt(g, 464, 498, '核对平台覆盖、分歧表述和引用平台的有效性，\n每条断言绑定平台；全空数据不生成强结论。\n引用存在不代表内容支持结论，仍须回看原文。', 23, leading=1.48)
g = group(r, 'response-use', 440, 636, 768, 29)
txt(g, 452, 657, '应用意义：让社区团队看见不同声音，保留可复核的回应依据。', 21, TEAL, True)
save(t, 5)

# P06 modules: model decomposition and a research-purpose explanation.
t, r = base(6, '热度预测：区分长期积累与突然走红',
            '四分量是建模假设；不把热度上涨直接解释为官方回应的因果效果')
g = group(r, 'decomposition-model', 65, 181, 495, 469)
rect(g, 65, 181, 495, 469, PALE)
txt(g, 312, 226, '输入热度 x', 29, TEAL, True, 'middle')
txt(g, 312, 276, 'x = T + S + C + R', 32, BLUE, True, 'middle')
for i, (name, desc) in enumerate([('T 趋势', 'EMA'), ('S 季节', 'Fourier'), ('C 冲击', '事件信号'), ('R 剩余', '代数剩余项')]):
    x = 84+i*117
    tile = el(g, 'g')
    rect(tile, x, 312, 106, 91, WHITE, BLUE, 5)
    txt(tile, x+53, 347, name, 22, BLUE, True, 'middle')
    txt(tile, x+53, 382, desc, 17, INK, False, 'middle')
txt(g, 312, 451, '四路编码 → 稀疏专家融合', 26, TEAL, True, 'middle')
txt(g, 312, 494, '预测增量 → 累加回水平域', 24, INK, False, 'middle')
txt(g, 312, 539, '过去 28 天 → 未来 6 天', 25, BLUE, True, 'middle')
rule(g, 87, 564, 538, 564, '#CED9E6', 1)
txt(g, 88, 597, '研究用途：辅助观察话题是否持续，\n为后续复核和社区互动研究安排时间窗。', 21, leading=1.5)
for i, (heading, body) in enumerate([
    ('按结构分别编码', '线性 / PatchCNN / 稀疏事件 / 轻量 SSM；\n分别处理趋势、周期、冲击和其余波动。'),
    ('四路数值表征参与路由', '默认 top-k = 2 进行专家选择；\n融合权重是否有效，需要消融实验验证。'),
    ('文本增量是可选路径', '完整模型有门控文本分支；现有部署验证\n关闭文本，不能推断已读懂游戏梗与图像。'),
    ('预测与传播解释分别评价', '下页为既有数据实测，不是方舟社区实验；\n跨话题泛化及回应效果仍需独立评估。'),
]):
    y = 181+i*119
    g = group(r, 'forecast-detail-' + str(i), 600, y, 610, 111)
    txt(g, 610, y+29, heading, 27, BLUE, True)
    txt(g, 610, y+67, body, 22, leading=1.45)
    if i < 3:
        rule(g, 610, y+110, 1200, y+110, '#D8E0EB', 1)
save(t, 6)

# P09 modules: factual comparison, prospective differentiation, limited application outlook.
t, r = base(9, '差异化定位：面向游戏社区的来源与互动研究',
            '比较的是研究切入点；优势需要同口径评价，不预设功能或性能全面领先')
g = group(r, 'market-capabilities', 65, 180, 550, 372)
rect(g, 65, 180, 550, 372, PALE)
txt(g, 90, 223, '成熟产品的公开能力', 28, TEAL, True)
txt(g, 90, 275, '新浪舆情通提供监测和预警，已覆盖\n微博 / 新闻溯源、传播效果与品牌洞察。\n其公开产品也已使用多智能体分析。', 24, leading=1.55)
txt(g, 90, 407, '差异化需要落实到具体任务的评价：\n围绕来源证据、同源变体与复核效率，\n检验游戏社区这一垂直场景的研究收益。', 23, leading=1.5)
cite(g, 90, 535, '[W3] 官方产品介绍', 'W3', 17)
cite(g, 295, 535, '[W4] 信息溯源说明', 'W4', 17)
g = group(r, 'research-difference', 650, 180, 560, 372)
txt(g, 670, 223, '本项目拟突出的研究切入点', 28, BLUE, True)
for y, head, body in [
    (266, '来源与创作认可', '追踪同源梗的改写和引用，保留创作者与语境。'),
    (360, '立场与互动时机', '结合平台分歧和热度，辅助发现参与与误读线索。'),
    (454, '回应与反馈评价', '关联官方回应和后续互动，检验是否改善交流。'),
]:
    txt(g, 672, y, head, 24, TEAL, True)
    txt(g, 672, y+36, body, 20.5)
g = group(r, 'light-application-outlook', 70, 576, 1135, 87)
rect(g, 70, 576, 1135, 87, PALE)
txt(g, 92, 610, '应用展望（后续）', 23, TEAL, True)
txt(g, 305, 610, '可面向游戏社区团队提供试点工具或专题报告。', 23)
txt(g, 92, 646, '先验证溯源质量、语境判断和人工复核效率，再评估服务方式；当前以创新训练和技术验证为主。', 21)
save(t, 9)

# P10 modules: truthful status of four workstreams and five-member responsibilities.
t, r = base(10, '中期进展：四条主线成型，关键验证待补齐',
            '按仓库实现与研究记录报告状态；由五名成员围绕可检查交付物协作')
for i, (head, body) in enumerate([
    ('01 数据接入与标准化', '已有适配接口、清洗与平台报告契约；\n逐平台稳定性和来源元数据仍需核查。'),
    ('02 跨平台分析与校准', '已实现时间对齐、差异汇总及 G/CX 规则；\n语义同事件对齐、梗义判断仍需标注样本。'),
    ('03 辅助预测与部署', '已训练四分量模型，完成 CPU 数值包验证；\n误差尚未优于持续值，文本收益和泛化待测。'),
    ('04 交互与研究记录', '已有三维档案入口、详情页和运行截图；\n线上全链路联调与用户试用待补齐。'),
]):
    x, y = 65+(i%2)*588, 178+(i//2)*169
    g = group(r, 'progress-' + str(i), x, y, 557, 151)
    rect(g, x, y, 557, 151, WHITE, BLUE, 6)
    txt(g, x+20, y+37, head, 26, BLUE, True)
    txt(g, x+20, y+82, body, 22, leading=1.55)
g = group(r, 'member-work', 70, 536, 1130, 136)
txt(g, 87, 564, '成员协作与交付', 24, TEAL, True)
txt(g, 87, 599, '张艺嘉：架构、模型与联调  ·  王悦：数据质量  ·  郑锦凡：基线与误差分析', 21.5)
txt(g, 87, 632, '詹江叶煜：事件对齐与传播关系  ·  吴珂欣：档案交互  ·  共同补齐：样本、评估表和试用记录', 21)
txt(g, 87, 659, '当前未形成已验证的完整图溯源成果；正式成果状态以申请回执和验收记录为准。', 18, MUTED)
save(t, 10)

# P11 modules: milestones and concrete validation outcomes, unchanged budget facts.
t, r = base(11, '下一阶段：把应用价值转化为验证任务',
            '项目周期至 2027 年 6 月；先建立可复核样本，再评价技术收益和使用价值')
g = group(r, 'validation-timeline', 70, 180, 1140, 362)
rule(g, 101, 242, 1150, 242, BLUE, 3)
for i, (date, heading, body) in enumerate([
    ('2026.11—12', '来源与关系样本', '标注素材、原创、改写与搬运\n记录原链接、时点和直接引用\n区分首发候选与已核实来源\n验收：标注说明、分歧样本集'),
    ('2027.01—03', '统一实验与试用', '同源识别、传播关系基线比较\n滚动切分、跨话题与分量消融\n小规模测量误链接和复核耗时\n验收：评估表、误差与试用记录'),
    ('2027.04—06', '互动研究与结题', '固定窗口观察二创与反馈质量\n记录版本、活动等混杂因素\n收敛已验证功能并整理成果\n验收：研究报告与正式回执'),
]):
    x = 83+i*385
    txt(g, x, 215, date, 26, BLUE, True)
    el(g, 'circle', cx=x+22, cy=242, r=10, fill=BLUE)
    txt(g, x, 293, heading, 28, TEAL, True)
    txt(g, x, 341, body, 22, leading=1.65)
txt(g, 85, 527, '关键问题：出处是否更准、误读是否减少、人工复核是否更高效；未有可信对照时只报告关联。', 21, TEAL, True)
g = group(r, 'budget-status', 80, 566, 1115, 89)
rect(g, 80, 566, 1115, 89, PALE)
txt(g, 102, 602, '申请书预算 7,500 元；实际获批额度、支出和调剂审批待财务记录核对。', 23, INK, True)
txt(g, 102, 635, '优先投入数据验证、必要算力与成果整理，形成科研训练过程和可检查的验收材料。', 21, MUTED)
save(t, 11)

# P17 modules: competitor's own historical example and research evaluation targets.
t, r = base(17, '备份｜竞品公开能力与差异化验证',
            '溯源已是成熟产品能力；本项目聚焦游戏社区语境，并用样本和实验检验特色')
g = group(r, 'competitor-source-image', 65, 178, 590, 494)
el(g, 'image', href='../images/yuqing_trace.png', x=65, y=186,
   width=590, height=425.39, preserveAspectRatio='xMidYMid meet')
cite(g, 77, 638, '[W4] 舆情通官方说明中的溯源截图', 'W4', 18)
txt(g, 77, 662, '历史功能示例（图内为2021年数据），非本项目界面', 17, MUTED)
g = group(r, 'competitive-boundary', 693, 180, 517, 155)
txt(g, 710, 216, '比较边界', 27, BLUE, True)
txt(g, 710, 259, '公开说明包含首发、参与者和传播路径。\n本项目以这些已有能力为参照，重点研究\n游戏梗的版本、语境与回应反馈的关联。', 22, leading=1.45)
g = group(r, 'differentiation-tests', 693, 348, 517, 157)
txt(g, 710, 385, '差异化如何验证', 27, TEAL, True)
txt(g, 710, 429, '同源版本：准确率、召回率与误链接率。\n来源复核：错误归因、可核查比例与耗时。\n回应研究：有效参与、反馈质量与误读例。', 22, leading=1.45)
g = group(r, 'paper-translation', 693, 523, 517, 148)
txt(g, 710, 555, '文献启发 [11 / W5]', 25, BLUE, True)
txt(g, 710, 592, '感知哈希、聚类与跨社区传播建模可作基线；\n中文游戏梗需单独标注，不能照搬原文效果。', 20.5, leading=1.5)
cite(g, 710, 661, 'IMC 2018 · On the Origins of Memes', 'W5', 16)
save(t, 17)

# P18 modules: complete existing bibliography plus the new primary paper and web index.
t, r = base(18, '备份｜参考文献与网络证据入口',
            '方法依据覆盖跨平台传播、分量预测和证据约束；论文、网页与图片留痕均保存于仓库')
refs = [
    ('[1] Cinelli et al. (2020, preprint)', 'Echo Chambers on Social Media: A comparative\nanalysis · arXiv:2004.09603'),
    ('[2] Zannettou et al. (2017)', 'The Web Centipede · arXiv:1705.06947'),
    ('[3] Zeng et al. (AAAI 2023)', 'Are Transformers Effective for Time Series\nForecasting? · arXiv:2205.13504'),
    ('[4] Stitsyuk & Choi (2024, preprint)', 'xPatch · arXiv:2412.17323'),
    ('[5] Gu & Dao (2023, preprint)', 'Mamba · arXiv:2312.00752'),
    ('[6] Killick et al. (2011, preprint)', 'Optimal detection of changepoints with a linear\ncomputational cost · arXiv:1101.1438'),
    ('[7] Lewis et al. (NeurIPS 2020)', 'Retrieval-Augmented Generation for\nKnowledge-Intensive NLP Tasks · 2005.11401'),
    ('[8] Jin et al. (ICLR 2024)', 'Time-LLM · arXiv:2310.01728'),
    ('[9] Tan et al. (NeurIPS 2024)', 'Are Language Models Actually Useful for\nTime Series Forecasting? · 2406.16964'),
    ('[10] Yao et al. (ICLR 2023)', 'ReAct · arXiv:2210.03629'),
    ('[11] Zannettou et al. (IMC 2018)', 'On the Origins of Memes by Means of Fringe\nWeb Communities · arXiv:1805.12512'),
]
for i, (heading, body) in enumerate(refs):
    col = 0 if i < 6 else 1
    row = i if i < 6 else i-6
    x, y = 75+col*600, 166+row*79
    g = group(r, 'bibliography-' + str(i), x, y, 555, 76)
    txt(g, x+5, y+22, heading, 20, BLUE, True)
    txt(g, x+5, y+46, body, 16.5, leading=1.28)
g = group(r, 'web-reference-index', 675, 568, 535, 75)
cite(g, 680, 589, 'W1 官方素材', 'W1', 16)
cite(g, 814, 589, 'W2 创作征集', 'W2', 16)
cite(g, 680, 618, 'W3 产品介绍', 'W3', 16)
cite(g, 814, 618, 'W4 溯源说明', 'W4', 16)
cite(g, 948, 618, 'W5 新增论文', 'W5', 16)
g = group(r, 'repository-evidence-index', 75, 650, 1125, 26)
txt(g, 80, 668, '仓库留痕：docs/community_value_20261030/research/SOURCES.md；预测实验与基础文献见 midterm_20261029。', 15.5, MUTED)
save(t, 18)


DURATIONS = [12, 38, 38, 36, 34, 40, 40, 28, 30, 24, 26, 14]
NOTES = {
    1: '各位老师好，我是张艺嘉。SocialSense围绕多源舆情开展证据分析、传播研究与辅助预测，下面汇报创新训练项目的中期进展。',
    2: '我们希望关注舆情的积极价值。游戏梗把角色、台词和共同经历变成交流语言，既带动二创，也连接玩家和官方。右侧创作征集，以及官方主动分享素材的公开记录，说明这种互动有具体场景。对项目而言，关键是帮助看清内容出处、玩家诉求与平台差异，为创作认可和社区沟通提供依据。参与增长等收益，则需要后续试用验证。',
    3: '以这个案例为例，技术任务可以展开成四步：先核对原始表达与创作者，再梳理改写、引用和转发关系，随后把语境与立场整理为可复核档案，最后观察回应后的交流。征集规则要求原创首发，也说明来源核验有现实需要。最早采集不等于真正首发，热度上涨也不等于回应有效。当前同源识别与完整传播关系仍是后续研究重点。',
    4: '这些需求如何落到代码？我们已经以统一的平台报告契约组织单平台结论、时序和来源信息，再做时间对齐与差异融合，经跨平台规则形成汇总。后端和档案界面承接查看，预测模块提供旁路结果。它为来源核查建立了数据与报告基础；面向梗的变体标注和引用边还需补充，当前时间对齐不能代替同源识别。',
    5: '正向互动同样需要谨慎理解语境。例如“笑飞了”可能是赞赏，也可能是反讽。单平台规则核对结论与观测是否一致，跨平台规则保留分歧并绑定引用平台。这样能暴露不一致，让社区团队回看依据；但引用标识存在不代表内容足以支持结论，规则也不能证明模型读懂了梗。关键含义与出处仍要人工复核。',
    6: '预测部分把热度分为趋势、季节、冲击和剩余四路，分别编码，再通过稀疏专家融合，输入过去二十八天，预测未来六天。用梗文化作类比，可以理解为长期积累、周期活跃、突然走红与其余波动；这只是建模假设，不是因果解释。它旨在辅助安排观察窗口。完整模型还有可选文本分支，现有验证关闭文本，下页也不是方舟社区的实验。',
    7: '已有实验中，方向准确率为百分之六十五点五三，尖峰AUC为零点六一，但MSE比持续值基线高约百分之二十三点八七，数值误差尚未占优。固定验证集阈值下，精确率和召回率均不足四成，预警价值还需改进。工程上，约二百四十二KiB的数值包，在二百六十二个测试窗口与原数值路径输出一致；这一结论不包含文本能力。',
    8: '这是仓库前端本地运行的真实截图，使用内置档案数据。它已经能组织议题、平台、观测范围和研究记录，便于查看与复核。未来梗案例也可以沿用这种档案组织方式，但图中没有接入方舟社区实测；线上采集、模型服务和报告接口仍需完整联调。',
    9: '竞品比较需要客观：新浪舆情通已有溯源、传播效果和品牌洞察。我们拟突出的方向，是围绕游戏社区把创作来源、平台语境和回应反馈关联起来，优势仍需评价。应用上可探索试点工具或专题报告，先证明来源更准、复核更高效，再讨论服务模式，当前重点仍是创新训练。',
    10: '中期已形成数据、跨平台分析、预测和交互四条原型主线。五名成员围绕架构、数据质量、实验、传播关系和交互协作，以接口、评估表、关系样本和试用记录作为交付物。后半程重点是补验证，尤其是同源识别、传播关系和线上联调。',
    11: '下一阶段先补齐来源和关系标注，再做统一基线、跨话题评估与小规模试用，最后研究互动反馈并整理结题成果。重点回答出处是否更准、误读是否减少、复核是否更高效。申请预算为七千五百元，实际支出与成果状态以财务凭证和正式回执为准。',
    12: '我们希望把多源舆情技术用于理解社区、支持创作认可和有依据的互动。当前已有研究原型，后续将补齐溯源与效果验证。请各位老师指正。',
    17: '左侧是舆情通官方说明中的历史功能截图，不是本项目界面。它说明成熟产品已有首发和传播路径分析。我们将通过同源识别、错误归因、复核耗时等指标验证游戏社区方向的价值；回应前后反馈只在控制活动等因素后解释，没有可信对照时只报告关联。新增梗传播论文提供了感知哈希、聚类和跨社区传播建模的参考，但其数据并非中文游戏社区。',
    18: '十一篇方法与应用研究文献均留有原文与重点阅读记录，网页配图也有来源和下载记录。文献解释研究设计，不能替代项目自身实验。指定学术检索入口此前访问受限，记录中已如实说明原始论文替代来源及实际阅读范围。',
}
for page, note in NOTES.items():
    (ROOT / 'notes' / f'slide_{page:02d}.md').write_text(note + '\n', encoding='utf-8')

out = ROOT / 'deliverables'
out.mkdir(exist_ok=True)
script = ['# SocialSense 六分钟讲稿与四分钟问答（社区价值增强版）',
          '主讲第1—12页，时间预算合计360秒；第13—18页为问答备份。页内文字供理解和追问，主讲按以下摘要讲述，不逐字朗读幻灯片。时间为排练预算，尚非实测录音时长。']
for page in range(1, 19):
    label = f'{DURATIONS[page-1]}秒' if page <= 12 else '问答备份'
    note = (ROOT / 'notes' / f'slide_{page:02d}.md').read_text(encoding='utf-8').strip()
    script.extend([f'## 第{page}页  {label}', note])
script.extend(['## 四分钟问答建议',
'''先给结论，再定位证据与后续验证。每题控制30—45秒；按数字页码跳转备份，不顺序播放全部备份页。

| 追问 | 建议回答 | 证据页 |
|---|---|---|
| 为什么选游戏梗文化？ | 同源改写、跨平台传播和语境差异集中出现，适合作为多源证据与溯源研究场景；积极价值包括创作参与、认可与沟通，效果需评估。 | 2、3 |
| 官方真的会做溯源吗？ | 已核实的是官方素材分享、平台征集的原创首发要求，以及成熟产品的溯源能力。这支持来源核验需求；未取得厂商内部流程或其采用本项目的证据。 | 3、17 |
| 比新浪舆情通强在哪里？ | 不能宣称全面领先。其已有溯源、传播与品牌洞察，我们聚焦游戏语境下的来源、变体和回应反馈关联，拟用错误归因与复核效率等指标验证。 | 9、17 |
| 游戏案例是否已经实测？ | 尚未完成游戏社区标注与实测。海报和素材是公开案例；第7页来自既有数值数据，不能视为游戏领域成绩。 | 6、7、13 |
| 能自动识别图片梗、反讽和真正首发吗？ | 目前不能作此保证。当前文本塔主要使用TF-IDF等特征，G/CX检查结构与观测一致性；跨模态同源和传播关系是后续研究。最早采到不自动等于源头。 | 4、5、17 |
| MSE不如基线，预测还有什么意义？ | 当前仅能报告已有方向、尖峰和部署结果，不能用其他指标抵消MSE不足。后续统一基线、分量消融、滚动与跨话题评价，决定保留哪些模块。 | 7、13、14 |
| 会把官方回应和热度上涨误当因果吗？ | 会预设时间窗，记录版本、活动、投放等因素；没有可信对照时只说明关联，不能宣称回应导致传播增长。 | 3、11、17 |
| 商业化如何考虑？ | 仅作应用展望：与社区团队试用工具或专题报告，先验证来源质量和复核效率。没有假设合同、营收、市场规模或付费转化。 | 9 |
| 能稳定上线吗？ | 已有本地交互与数值包验证；全链路服务、资源和异常场景仍需验收。本地界面截图不能证明线上数据链路稳定。 | 8、15 |
| 经费与成果完成了吗？ | 7500元来自申报预算，实际获批、实支与调剂按财务记录核对；软著及论文以正式回执为准。 | 11、16 |

排练节点：第3页结束1分28秒；第6页结束3分18秒；第7页结束3分58秒；第11页结束5分46秒。若超时，先压缩架构术语和成员分工，保留实测结果、价值主线和未完成事项。

网页与图片索引见 `../research/SOURCES.md`，验证工作流见 `../research/VALIDATION_WORKFLOW.md`。本轮商业应用仅保留第9页底部短段落。'''])
(out / '六分钟讲稿与四分钟问答_社区价值增强版.md').write_text('\n\n'.join(script) + '\n', encoding='utf-8')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

code_paths = ['multiagent/contract.py', 'multiagent/align.py', 'multiagent/fuse.py',
              'multiagent/master.py', 'agent/Conclusion/calib/gates.py',
              'agent/MultimodalAnalyzer/text_tower.py', 'social_forecast/models/rep_moe.py',
              'social_forecast/layers/rep_fusion.py',
              'social_forecast/results/retrain_20261019/deployment_verification.json']
provenance = {'source_pptx_sha256': sha(ROOT / 'sources/source.pptx'), 'edited_pages': EDITED,
              'referenced_pages': [i for i in range(1, 19) if i not in EDITED],
              'timing_seconds': DURATIONS, 'total_seconds': sum(DURATIONS),
              'code_sha256': {p: sha(REPO / p) for p in code_paths},
              'network_images_used': ['summer_key_visual.jpg', 'official_summer_4.jpg', 'yuqing_trace.png'],
              'game_case_status': 'public_illustration_and_future_research_not_measured_project_result'}
(ROOT / 'evidence/revision_provenance.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding='utf-8')
counts = {}
for page in range(1, 19):
    root = E.parse(A / f'slide_{page:02d}.svg').getroot()
    counts[page] = sum(len(''.join(e.itertext()).replace('\n', '')) for e in root.iter('{' + NS + '}text'))
print(json.dumps({'edited': EDITED, 'text_characters_by_page': counts,
                  'text_characters_total': sum(counts.values()), 'main_timing_seconds': sum(DURATIONS)}, ensure_ascii=False))
