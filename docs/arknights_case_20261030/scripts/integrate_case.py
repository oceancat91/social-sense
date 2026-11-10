"""Integrate three bounded teaching examples into a native round-trip deck."""
from pathlib import Path
import hashlib
import json
import shutil
import xml.etree.ElementTree as E

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
PREVIOUS = REPO / 'docs/midterm_20261029'
A = ROOT / 'authoring-svg-flat'
S = 'http://www.w3.org/2000/svg'
E.register_namespace('', S)

# (shape id, replacement, width, optional explicit height, optional font size)
# Keep every source identity; resize only the transparent text frame being edited.
EDITS = {
    2: [
        ('shape-4', '用一个热梗，理解多平台分析的难点', 785, None, None),
        ('shape-7', '情境示例：“笑飞了”——理解语境、比较平台、观察热度（非实测数据）', 1120, None, None),
        ('shape-17', '同一个梗，平台口径不同\n先统一时间、字段与缺失标记', 415, 80, None),
        ('shape-22', '词面情绪不等于真实态度', 415, None, None),
        ('shape-24', '“笑飞了”可能是开心或反讽\n结合对象、上下文与引用复核', 415, 80, None),
        ('shape-30', '热度上升之后是否持续？\n用误差、方向和尖峰指标检验', 415, 80, None),
        ('shape-36', '同一话题可能出现立场分歧\n先比较差异，再核查具体证据', 415, 80, None),
        ('shape-42', '最早采到，不等于真正首发\n溯源仍需引用与传播关系样本', 415, 80, None),
        ('shape-46', '技术价值', 350, None, None),
        ('shape-47', '把热度与判断连接到证据', 465, None, None),
    ],
    5: [
        ('shape-4', '“笑飞了”是好评吗？让判断回到证据', 785, None, None),
        ('shape-7', '示例强调上下文复核；G/CX 规则核查一致性，不能代替反讽识别', 1120, None, None),
        ('shape-15', '原句、上下文与来源', 285, None, None),
        ('shape-18', '形成候选态度判断', 285, None, None),
        ('shape-25', '保留依据与不确定性', 285, None, None),
        ('shape-31', '趋势、情绪、立场与观测是否一致\n引用标识 · 数值边界 · 空窗 · 风险依据', 715, 100, None),
        ('shape-37', '平台覆盖 · 分歧诚实 · 引用平台有效\n断言绑定平台；引用内容仍须人工核对', 715, 100, None),
    ],
    6: [
        ('shape-7', '梗热度类比：长期讨论 / 周期活跃 / 突然走红 / 其余波动（示意）', 1120, None, None),
        ('shape-15', '讨论热度 x', 390, None, None),
        ('shape-32', '过去 28 天 → 未来 6 天（当前设定）', 460, None, None),
        ('shape-35', '长期积累与周期活跃', 575, None, None),
        ('shape-36', 'T：EMA 趋势；S：Fourier 周期', 575, None, None),
        ('shape-40', '突然走红与其余波动', 575, None, None),
        ('shape-41', 'C：事件信号；R：代数剩余项', 575, None, None),
        ('shape-45', '分开编码，再融合预测', 575, None, None),
        ('shape-46', '四路数值表征路由；top-k = 2；文本可选', 575, None, None),
        ('shape-50', '用真实实验检验收益', 575, None, None),
        ('shape-51', '下页为既有数据结果，不是方舟案例实验', 575, None, None),
    ],
}

NOTES = {
    2: '用材料中的“笑飞了”举例：它可能是开心，也可能是反讽，只看词面很容易误读。同一个梗跨平台传播时，声量口径、讨论对象和立场还可能不同。SocialSense因此把平台信息整理为统一报告，对齐时间、比较差异，并让判断回到引用证据；热度变化则交给独立实验检验。这个例子只帮助理解问题，没有作为方舟社区实测。',
    5: '还是“笑飞了”：判断它是好评还是反讽，需要看讨论对象和上下文。项目的两层规则检查的是结论与观测是否一致：单平台核对趋势、情绪、立场、引用和空窗，跨平台核对覆盖、分歧及断言绑定。技术价值在于暴露不一致、保留复核依据；规则本身不能证明模型读懂了梗，关键含义仍需人工核对。',
    6: '把梗的热度想成长期讨论、周期活跃、突然走红和其余波动，就能直观理解趋势、季节、冲击和剩余四个分量；这只是类比，不代表已经识别出这些原因。代码分别编码四路分量，再用数值表征进行稀疏专家融合，输入过去二十八天，预测未来六天。完整模型还有可选文本路径；下页指标来自既有数据的数值路径验证，不是方舟案例实验。',
}

def set_text(root, shape_id, value, width, height=None, size=None):
    g = next(e for e in root.iter() if e.get('id') == shape_id)
    assert g.get('data-pptx-source-ref', '').startswith('slide:')
    t = g.find(f'{{{S}}}text')
    assert t is not None
    old = ''.join(t.itertext())
    x, y, oldw, oldh = map(float, g.get('data-pptx-frame').split())
    tx, ty = float(t.get('x')), float(t.get('y'))
    anchor = t.get('text-anchor', 'start')
    if anchor == 'middle':
        x = tx - width / 2
    elif anchor == 'end':
        x = tx - width
    h = height or oldh
    g.set('data-pptx-frame', f'{x:g} {y:g} {width:g} {h:g}')
    path = g.find(f'{{{S}}}path')
    assert path is not None and path.get('fill') == 'none'
    path.set('d', f'M {x:g} {y:g} L {x+width:g} {y:g} L {x+width:g} {y+h:g} L {x:g} {y+h:g} Z')
    line_height = float(t.get('data-paragraph-line-height', float(t.get('font-size')) * 1.5))
    for c in list(t):
        t.remove(c)
    for k in ('data-pptx-text-model', 'data-paragraph-line-height'):
        t.attrib.pop(k, None)
    if size:
        t.set('font-size', str(size))
    lines = value.split('\n')
    t.text = lines[0]
    for v in lines[1:]:
        E.SubElement(t, f'{{{S}}}tspan', {'x': str(tx), 'dy': f'{line_height:g}'}).text = v
    return {'shape': shape_id, 'before': old, 'after': value}

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    for folder in ('deliverables', 'evidence', 'notes', 'sources'):
        (ROOT / folder).mkdir(exist_ok=True)
    changed = {}
    for page, edits in EDITS.items():
        path = A / f'slide_{page:02d}.svg'
        tree = E.parse(path)
        changed[page] = [set_text(tree.getroot(), *e) for e in edits]
        tree.write(path, encoding='utf-8', xml_declaration=True)
    for page, note in NOTES.items():
        (ROOT / 'notes' / f'slide_{page:02d}.md').write_text(note + '\n', encoding='utf-8')

    script = (PREVIOUS / 'deliverables/六分钟讲稿与四分钟问答.md').read_text(encoding='utf-8')
    for page, note in NOTES.items():
        start = script.index(f'## 第{page}页')
        body = script.index('\n\n', start) + 2
        end = script.index('\n## 第', body)
        script = script[:body] + note + '\n' + script[end:]
    script = script.replace('# SocialSense 六分钟讲稿与四分钟问答', '# SocialSense 六分钟讲稿与四分钟问答（案例融入版）', 1)
    script += '''\n## 案例相关追问\n\n- **这个案例已经实际跑过吗？** 没有。本轮只把用户提供的社区观察文案用作讲解例子，未采集或标注方舟数据。第7页的指标来自原有实验，不能视为游戏社区泛化成绩。\n- **系统能识别反讽和所有梗吗？** 尚未证明。当前文本塔主要使用 TF-IDF 等特征，规则检查结论与观测、来源结构的一致性。梗义、反讽、图像和音频语义仍需专门标注、方法与评价，不能由现有门禁通过率代替。\n\n本轮仅更新第2、5、6页。实际讲述时每页案例引入控制在一句，不展开游戏背景。360秒为排练预算，不是实测录音时长。\n'''
    (ROOT / 'deliverables/六分钟讲稿与四分钟问答_案例融入版.md').write_text(script, encoding='utf-8')
    (ROOT / 'page_plan.json').write_text(json.dumps({'schema': 'ppt-master.roundtrip-page-plan.v1', 'pages': [{'source_slide': i} for i in range(1, 19)]}, indent=2), encoding='utf-8')
    original = REPO.parent / '方舟七年梗文化观察-文字整理.md'
    copied = ROOT / 'sources' / original.name
    shutil.copy2(original, copied)
    evidence = {
        'source': str(original), 'sha256': digest(original),
        'edited_pages': [2, 5, 6], 'unchanged_visible_pages': [i for i in range(1, 19) if i not in EDITS],
        'case_status': 'illustrative_only_not_empirical',
        'source_sections_used': ['开场', '二、梗的分类与传播判断', '四、官方该怎么做：记录（仅观察维度）'],
        'interpretation': '开心或反讽及四类热度结构为教学类比，不是从原文得到的已标注数据或因果解释。',
        'excluded': ['游戏发展史', '玩法清单', '厂商与人物评价', '官方接梗渠道', '资源助推推测', '品牌策略'],
        'code': {},
        'page_edits': changed,
    }
    for rel in ['multiagent/contract.py','multiagent/align.py','multiagent/fuse.py','multiagent/master.py','agent/Conclusion/calib/gates.py','agent/MultimodalAnalyzer/text_tower.py','social_forecast/models/rep_moe.py','social_forecast/layers/rep_fusion.py']:
        p = REPO / rel
        evidence['code'][rel] = digest(p)
    (ROOT / 'evidence/case_provenance.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Edited only slides 2, 5, 6; synchronized their notes and standalone script.')

if __name__ == '__main__':
    main()
