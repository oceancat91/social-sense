"""Native-source-preserving ppt-master authoring. Only slide-local content changes."""
from pathlib import Path
import xml.etree.ElementTree as E
import copy,json,shutil,re

ROOT=Path(__file__).resolve().parents[1];P=ROOT/'presentation';A=P/'authoring-svg-flat'
NS='http://www.w3.org/2000/svg';E.register_namespace('',NS)
BLUE='#4472C4';DARK='#44546A';TEAL='#0D3745';RED='#BE2623';INK='#243446';MUTED='#64748B';PALE='#EDF2F8';WHITE='#FFFFFF'
def el(parent,tag,**attrs):return E.SubElement(parent,'{'+NS+'}'+tag,{k.replace('_','-'):str(v) for k,v in attrs.items()})
def group(root,key,x,y,w,h,role=None):
    g=el(root,'g',id=key,**{'data-pptx-bounds':f'{x} {y} {w} {h}'})
    if role:g.set('data-pptx-role',role)
    el(g,'rect',x=x,y=y,width=w,height=h,fill='none')
    return g
def rect(g,x,y,w,h,fill=WHITE,stroke=None,rx=0):
    a=dict(x=x,y=y,width=w,height=h,fill=fill)
    if stroke:a.update(stroke=stroke,stroke_width=1.2)
    if rx:a.update(rx=rx,ry=rx)
    return el(g,'rect',**a)
def txt(g,x,y,s,size=24,color=INK,bold=False,anchor='start',leading=1.45):
    t=el(g,'text',x=x,y=y,font_size=size,fill=color,font_family='Microsoft YaHei',text_anchor=anchor,font_weight='bold' if bold else 'normal')
    lines=s.split('\n');t.text=lines[0]
    for line in lines[1:]:el(t,'tspan',x=x,dy=round(size*leading,2)).text=line
    return t
def line(g,x1,y1,x2,y2,color=BLUE,width=2):return el(g,'line',x1=x1,y1=y1,x2=x2,y2=y2,stroke=color,stroke_width=width)
def arrow(g,x1,y1,x2,y2,color=BLUE):
    line(g,x1,y1,x2-9,y2,color,2.5);el(g,'polygon',points=f'{x2},{y2} {x2-10},{y2-5} {x2-10},{y2+5}',fill=color)
def card(root,key,x,y,w,h,title,body,accent=BLUE,size=22):
    g=group(root,key,x,y,w,h);rect(g,x,y,w,h,WHITE,accent,8);line(g,x+3,y+3,x+3,y+h-3,accent,5)
    txt(g,x+24,y+40,title,27,accent,True);txt(g,x+24,y+85,body,size,INK,leading=1.55);return g
def base(n,title,index,subtitle='',keep=()):
    t=E.parse(A/f'slide_{n:02d}.svg');r=t.getroot()
    for ch in list(r):
        ref=ch.get('data-pptx-source-ref','')
        if ch.tag=='{'+NS+'}g' and not ref:
            r.remove(ch);continue
        if ref.startswith('slide:') and ch.get('id') not in keep:
            imgs=list(ch.iter('{'+NS+'}image'))
            is_logo=any(i.get('href','').endswith('/image5.png') for i in imgs)
            if not is_logo:r.remove(ch)
    h=group(r,'midterm-header',95,16,815,83,'header');txt(h,112,63,title,34,DARK,True)
    if subtitle:
        g=group(r,'page-subtitle',75,108,1130,50);txt(g,80,140,subtitle,22,MUTED)
    f=group(r,'midterm-footer',70,680,1100,25,'footer')
    txt(f,76,700,'SocialSense  ·  创新训练类中期答辩',13,MUTED)
    txt(f,1155,700,f'{index:02d} / 18'+('  备份' if index>12 else ''),13,MUTED,anchor='end')
    return t,r
def write(t,name):t.write(A/name,encoding='utf-8',xml_declaration=True)
def source_text(r,shape,lines,size,x,y,leading=1.35,anchor='start'):
    g=next(e for e in r.iter() if e.get('id')==shape)
    for e in list(g):
        if e.tag=='{'+NS+'}text':g.remove(e)
    txt(g,x,y,lines,size,DARK,True,anchor,leading)
def table(root,key,x,y,w,h,columns,rows,widths,size=22):
    g=group(root,key,x,y,w,h)
    g.set('data-pptx-replace-with','table')
    allrows=[columns]+rows;rh=h/len(allrows);cw=[w*v/sum(widths) for v in widths]
    vals=[]
    for i,row in enumerate(allrows):
        xx=x;rv=[]
        for j,v in enumerate(row):
            fill=BLUE if i==0 else (WHITE if i%2 else '#F3F6FA');col=WHITE if i==0 else INK
            right=bool(re.match(r'^[\d,.]+$',str(v))) and i>0
            rect(g,xx,y+i*rh,cw[j],rh,fill,'#D8E0EB')
            txt(g,xx+cw[j]-14 if right else xx+14,y+i*rh+rh/2+size*.35,str(v),size,col,i==0,'end' if right else 'start')
            rv.append({'text':str(v),'fill':fill,'color':col,'align':'r' if right else 'l','valign':'middle','bold':i==0,'font_size':size,'padding':{'left':14,'right':14,'top':5,'bottom':5},'borders':{k:{'style':'solid','color':'#D8E0EB','width':1.2}for k in ['top','bottom','left','right']}})
            xx+=cw[j]
        vals.append(rv)
    data={'schema':'ppt-master.semantic-table.v2','name':key,'x':x,'y':y,'width':w,'height':h,'columns':vals[0],'rows':vals[1:],'column_widths':widths,'row_heights':[1]*len(allrows),'style':{'font_family':'Microsoft YaHei','font_size':size,'band_row':False}}
    m=E.Element('{'+NS+'}metadata',{'type':'application/json'});m.text=json.dumps(data,ensure_ascii=False);g.insert(0,m);return g

# 1 Cover: original campus photograph, diagonal cut, school mark and text slots.
t=E.parse(A/'slide_01.svg');r=t.getroot()
source_text(r,'shape-2','SocialSense\n基于多源社交媒体协同的\n舆情溯源与辅助预测系统',42,632,296,1.43,'middle')
source_text(r,'shape-3','创新训练类中期答辩',22,632,213,1.2,'middle')
# The source author/date fields are children of a group, not the group itself.
cover_group=next(e for e in r if e.get('id')=='shape-4')
for e in list(cover_group):
    if e.tag=='{'+NS+'}text':cover_group.remove(e)
source_text(r,'shape-5','汇报人：张艺嘉',22,365,521)
source_text(r,'shape-6','2026 年 11 月',22,480,649)
source_text(r,'shape-14','成员：詹江叶煜  郑锦凡  王悦  吴珂欣',20,407,575)
source_text(r,'shape-16','指导教师：树杨',22,623,521)
write(t,'slide_01.svg')

# 2 Five numbered problems: retains source's 3+2 two-column rhetoric.
t,r=base(6,'从多平台信息到可核查的辅助判断',2,'面向公共议题观察与传播研究，先解决证据和评价口径')
items=[('01','平台数据难直接比较','统一字段、时间和缺失标记\n保留各平台的观测范围',80,180),('02','生成结论缺少核验','让趋势、情绪和风险判断\n回到可引用的观测证据',80,340),('03','预测价值需要实测','同时报告数值误差、方向\n尖峰检出与误报',80,500),('04','平台分歧难以解释','对齐时间，再比较立场与声量\n统计差异仍需事件证据',690,180),('05','传播关系尚待补齐','现有相关性不等于因果传播\n以可追溯关系样本推进溯源',690,340)]
for num,title,body,x,y in items:
    g=group(r,'problem-'+num,x,y,510,135);el(g,'circle',cx=x+32,cy=y+30,r=30,fill=BLUE);txt(g,x+32,y+38,num,23,WHITE,True,'middle');txt(g,x+82,y+33,title,28,TEAL,True);txt(g,x+82,y+78,body,23,INK)
g=group(r,'problem-value',690,525,510,112);rect(g,690,525,510,112,PALE);txt(g,714,565,'本阶段定位',22,BLUE,True);txt(g,714,605,'可运行原型 + 可复核研究记录',25,INK,True)
write(t,'slide_06.svg')

# 3 Original left 2x2 blocks + right feature: four progress panels and one pending goal.
t,r=base(5,'对照立项目标，四条主线已形成原型',3,'中期状态按代码与记录判断；原型完成不等于研究验证完成')
for k,x,y,title,body in [
('data',70,180,'01 数据接入与标准化','已有适配接口、清洗与数据契约\n仍需逐平台稳定性验证'),
('analysis',70,410,'02 跨平台分析','已实现时间对齐与差异汇总\n语义级同事件对齐待完成'),
('forecast',410,180,'03 辅助预测','已训练四分量模型并验证数值包\n误差、泛化与误报仍需改进'),
('ui',410,410,'04 可视化与报告','已有档案浏览、详情及规则校准\n线上联调与用户试用待补齐')]:
    card(r,k,x,y,322,200,title,body,size=19)
g=group(r,'pending-tracing',775,180,435,430);rect(g,775,180,435,430,PALE)
txt(g,805,229,'05 传播路径溯源',29,TEAL,True);txt(g,805,293,'当前：方法调研与接口梳理',24,INK,True)
txt(g,805,348,'下一步先建立关系样本，\n比较简单节点排序与图模型，\n再验证关键节点和路径线索。',24,INK,leading=1.65)
txt(g,805,553,'尚未形成已验证的 GNN 溯源成果',20,RED,True)
write(t,'slide_05.svg')

# 4 Architecture keeps a dominant central flow flanked by explanatory modules.
t,r=base(9,'系统架构以报告契约连接分析与应用',4,'实际模块：agent / multiagent / social_forecast / backend / frontend')
card(r,'input-layer',70,190,280,360,'数据与单平台分析','关键词与观测数据\n采集清洗 → 立场画像\n文本与时序分析\n检索补充 → 结论校准',size=21)
g=group(r,'central-pipeline',375,180,530,455)
for y,title,sub in [(190,'PlatformReport','文本 · 时序 · 元数据 · 引用'),(320,'时间对齐 → 差异融合','平台内标准化 · 保留缺失'),(450,'跨平台主控与 CX 校准','受证据约束的汇总结论')]:
    rect(g,395,y,485,102,PALE,BLUE,7);txt(g,637,y+40,title,26,BLUE,True,'middle');txt(g,637,y+77,sub,21,INK,False,'middle')
    if y<450:line(g,637,y+102,637,y+130,BLUE,3)
txt(g,637,605,'旁路：时序预测 → 数值结果',24,TEAL,True,'middle')
card(r,'application-layer',935,190,280,360,'服务与交互','Flask API\n三维档案浏览\n证据详情与研究记录\n预测展示与人工复核',size=22)
g=group(r,'arrow-left',351,355,23,35);arrow(g,351,373,374,373)
g=group(r,'arrow-right',906,355,28,35);arrow(g,906,373,934,373)
write(t,'slide_09.svg')

# 5 Source left flow + two right explanatory bands.
t,r=base(12,'让结论回到证据：两层规则校准',5,'规则负责发现不一致；关键结论仍需人工复核')
g=group(r,'verification-flow',70,185,335,435)
for y,title,color in [(190,'原始观测与来源',TEAL),(300,'生成候选结论',BLUE),(410,'规则核验与受限改写',BLUE),(520,'保留证据后输出',TEAL)]:
    rect(g,85,y,305,72,PALE,color,7);txt(g,237,y+46,title,25,color,True,'middle')
    if y<520:line(g,237,y+72,237,y+110,color,2)
card(r,'single-gates',445,185,765,208,'G1—G7  单平台核验','趋势 · 情绪 · 立场 · 引用标识\n数值边界 · 空窗表述 · 风险与证据一致性',size=25)
card(r,'cross-gates',445,420,765,200,'CX1—CX5  跨平台核验','平台覆盖 · 分歧诚实 · 引用平台有效\n每条断言绑定平台 · 全空数据不作强结论',accent=TEAL,size=25)
write(t,'slide_12.svg')

# 6 Source left model visualization + four right module rows.
t,r=base(10,'四分量建模，分别学习热度的不同结构',6,'输入过去 28 天，直接预测未来 6 天；图示对应当前 forward 路径')
g=group(r,'decomposition',65,185,500,435);rect(g,65,185,500,435,PALE)
txt(g,315,241,'输入热度 x',29,TEAL,True,'middle');txt(g,315,298,'x = T + S + C + R',32,BLUE,True,'middle')
for i,(name,sub) in enumerate([('T 趋势','EMA'),('S 季节','Fourier'),('C 冲击','事件信号'),('R 剩余','代数剩余项')]):
    x=88+i*116;rect(g,x,340,104,92,WHITE,BLUE,5);txt(g,x+52,375,name,22,BLUE,True,'middle');txt(g,x+52,409,sub,17,INK,False,'middle')
txt(g,315,492,'四路编码 → 稀疏专家融合',27,TEAL,True,'middle');txt(g,315,543,'预测增量 → 累加回水平域',25,INK,False,'middle');txt(g,315,591,'EMA 含可学习平滑参数',20,MUTED,False,'middle')
for i,(h,b) in enumerate([('分量专属编码','线性 / PatchCNN / 稀疏事件 / 轻量 SSM'),('四路数值路由','路由输入包含 T、S、C、R；默认 top-k = 2'),('文本是可选路径','完整模型含门控文本增量；数值验证关闭文本'),('部署验证有明确边界','只验证 CPU 数值路径，不等于完整文本路径等价')]):
    y=180+i*116;g=group(r,'model-detail-'+str(i),600,y,610,101);txt(g,610,y+30,h,28,BLUE,True);txt(g,610,y+73,b,21,INK);line(g,610,y+99,1200,y+99,'#D9E1ED',1)
write(t,'slide_10.svg')

# 7 Editable native chart from the actual verification JSON.
ver=json.loads((ROOT.parents[1]/'social_forecast/results/retrain_20261019/deployment_verification.json').read_text())
m=ver['numeric_holdout_metrics'];v=[m['persist_standardized_mse'],m['standardized_mse']]
t,r=base(18,'实测结果：数值拟合与预警仍有提升空间',7,'2026-10-19 CPU 数值路径验证；测试窗口 262 个')
g=group(r,'mse-panel',65,180,560,458);rect(g,65,180,560,458,PALE);txt(g,92,225,'标准化 log1p 空间 MSE',27,TEAL,True)
chart=group(g,'mse-comparison',95,253,500,337);chart.set('data-pptx-replace-with','chart')
px,py,pw,ph=145,280,405,230
for k in range(5):
    val=k*.5;y=py+ph*(1-val/2);ln=line(chart,px,y,px+pw,y,'#D8E0EB',1);ln.set('id','mse-grid-'+str(k));txt(chart,px-12,y+6,f'{val:.1f}',17,INK,anchor='end')
for i,(value,color,label) in enumerate(zip(v,['#AAB7C9',BLUE],['持续值','数值路径'])):
    cx=px+pw*(i+.5)/2;bh=ph*value/2;rect(chart,cx-43,py+ph-bh,86,bh,color);txt(chart,cx,py+ph-bh-12,f'{value:.3f}',23,INK,True,'middle');txt(chart,cx,py+ph+35,label,21,INK,False,'middle')
metadata={'name':'mse-comparison','x':95,'y':253,'width':500,'height':337,'type':'column','categories':['持续值','数值路径'],'series':[{'name':'MSE','values':v,'point_colors':['#AAB7C9',BLUE]}],'show_legend':False,'gap_width':135.465116,'plot_area':{'x':px,'y':py,'width':pw,'height':ph},'axes':{'category':{'position':'bottom','font_size':21,'color':INK},'value':{'position':'left','minimum':0,'maximum':2,'major_unit':.5,'number_format':'0.0','major_gridlines':True,'font_size':17,'color':INK}},'data_labels':{'show_value':True,'position':'outside_end','number_format':'0.000','font_size':23,'bold':True,'color':INK},'style':{'font_family':'Microsoft YaHei','colors':[BLUE],'text_color':INK,'axis_color':'#D8E0EB','grid_color':'#D8E0EB','chart_area_fill':'none','plot_area_fill':'none'}}
me=E.Element('{'+NS+'}metadata',{'type':'application/json'});me.text=json.dumps(metadata,ensure_ascii=False);chart.insert(0,me)
takeaway=group(g,'mse-takeaway',85,595,520,34);txt(takeaway,95,620,'较持续值基线高 23.87% · 误差尚未占优',22,RED,True)
g=group(r,'metric-panel',660,180,550,458);rect(g,660,180,550,458,PALE)
txt(g,690,240,'65.53%',49,BLUE,True);txt(g,930,231,'方向准确率',24,INK,True);txt(g,930,267,'235 个非平坦窗口',20,MUTED)
line(g,690,297,1170,297,'#CED9E6',1);txt(g,690,345,'0.610',43,BLUE,True);txt(g,930,338,'尖峰 AUC',25,INK,True)
txt(g,690,403,'召回率 39.39%  /  精确率 38.24%',23,INK)
txt(g,690,448,'预警阈值来自验证集，测试集仅用于评估',20,MUTED)
line(g,690,474,1170,474,'#CED9E6',1);txt(g,690,522,'242.17 KiB',34,TEAL,True);txt(g,690,562,'数值包 · 49,373 参数 · 262 窗口一致',21,INK)
txt(g,690,605,'文件体积不等于运行内存；重叠窗口不独立',18,RED)
write(t,'slide_18.svg')

# 8 Actual screenshot in source laptop frame.
t,r=base(20,'交互原型：从档案入口进入研究记录',8,'本地仓库运行实拍 · 2026-10-29 · 内置档案数据',keep=('shape-15','shape-16','shape-279','shape-19','shape-20'))
for g in r:
    if g.get('id')=='shape-16':
        for child in list(g):g.remove(child)
        el(g,'image',href='../images/local_archive.png',x=559.4,y=176.27,width=628.33,height=389,preserveAspectRatio='none')
g=group(r,'demo-explanation',35,215,385,355)
txt(g,60,263,'三维档案终端',31,TEAL,True);txt(g,60,322,'浏览与检索议题档案\n查看平台和观测范围\n进入详情与研究记录',25,INK,leading=1.7)
txt(g,60,507,'该截图证明前端交互已运行。\n线上服务及数据链路仍需联调。',19,MUTED,leading=1.55)
write(t,'slide_20.svg')

# 9 Source left feature image replaced by research proposition; right item progression.
t,r=base(16,'项目特色在于证据约束与可验证的系统组合',9,'借鉴基础方法，明确工程贡献；算法优势由实验检验')
g=group(r,'innovation-statement',65,185,365,450);rect(g,65,185,365,450,PALE)
txt(g,96,246,'面向舆情任务',31,TEAL,True);txt(g,96,302,'证据可追查\n模块可替换\n结果可复核',33,BLUE,True,leading=1.8);txt(g,96,565,'定位：方法探索与工程实现\n不主张基础算法首创',21,MUTED)
for i,(h,b) in enumerate([('证据校准贯穿分析链','受 ReAct / RAG 启发，以数据契约和规则核验落地 [7,10]'),('分量编码面向突发热度','借鉴 DLinear / xPatch / Mamba，扩展四分量路径 [3–6]'),('轻量交付接受行为验证','数值包等价性与文本收益分开评价，保留负结果 [9]'),('交互界面支持人工复核','将来源、范围和研究记录组织到档案视图')]):
    y=185+i*113;g=group(r,'innovation-'+str(i),470,y,740,98);el(g,'circle',cx=489,cy=y+20,r=8,fill=BLUE);txt(g,514,y+30,h,27,BLUE,True);txt(g,514,y+74,b,20,INK)
write(t,'slide_16.svg')

# 10 Retains source three-column information architecture.
t,r=base(17,'五位成员围绕可检查交付物协作',10,'以接口、实验记录与验收条件连接开发和科研训练')
card(r,'team-architecture',70,190,350,370,'架构与交付','张艺嘉\n总体架构、模型实现与导出\n前后端联调、研究记录\n\n交付：可运行原型与验证包',size=22)
card(r,'team-data',465,190,350,370,'数据与评估','王悦：数据清洗与质量检查\n郑锦凡：基线、消融与误差分析\n\n交付：数据说明与统一评估表',size=21)
card(r,'team-graph-ui',860,190,350,370,'传播研究与交互','詹江叶煜：传播图与事件对齐\n吴珂欣：三维档案与交互测试\n\n交付：关系样本与试用记录',size=21)
g=group(r,'training-value',70,590,1140,60);txt(g,640,625,'科研训练收获：统一口径 · 面对负结果 · 明确证据边界 · 协同复盘',26,TEAL,True,'middle')
write(t,'slide_17.svg')

# 11 Timeline replaces source timeline image with editable milestones.
t,r=base(26,'下一阶段以验证和补齐关键证据为重点',11,'项目周期延续至 2027 年 6 月；以下为计划与验收条件')
g=group(r,'roadmap',75,195,1135,365);line(g,148,250,1135,250,BLUE,4)
for i,(date,head,body) in enumerate([('2026.11—12','补齐基础证据','固化数据与评估协议\n建立简单基线及事件样本\n验收：评估表、标注说明'),('2027.01—03','验证核心研究','消融、跨话题、传播图比较\n线上联调与小规模试用\n验收：误差分析、试用记录'),('2027.04—06','成果整理与结题','收敛已验证模块与文档\n完善软著及论文材料\n验收：结题材料与实际回执')]):
    x=95+i*383;el(g,'circle',cx=x+36,cy=250,r=14,fill=BLUE);txt(g,x,217,date,26,BLUE,True);txt(g,x,312,head,29,TEAL,True);txt(g,x,363,body,23,INK,leading=1.65)
g=group(r,'budget-boundary',80,566,1115,88);rect(g,80,566,1115,88,PALE);txt(g,104,600,'申请书预算 7,500 元；实际获批额度、支出和调剂审批待财务记录核对。',24,INK,True);txt(g,104,634,'优先投入：数据验证、必要算力、研究与成果整理。',21,MUTED)
write(t,'slide_26.svg')

# 12 Closing: preserve cover/end graphics, replace only semantic text slots.
t=E.parse(A/'slide_27.svg');r=t.getroot()
source_text(r,'shape-17','请各位老师指正',53,611,352)
source_text(r,'shape-20','已形成研究原型，下一步补齐验证与溯源',23,612,399)
source_text(r,'shape-18','汇报人：张艺嘉  ·  指导教师：树杨\n成员：詹江叶煜  郑锦凡  王悦  吴珂欣',22,568,497,1.7)
source_text(r,'shape-19','2026 年 11 月  ·  进入问答',22,729,651)
write(t,'slide_27.svg')

# 13 Copy source 18: restore fresh skeleton from the original before body composition.
# It is copied from the edited source page, then all intended slide-local authored content is removed.
t,r=base(18,'备份｜评价协议与误报漏报明细',13,'数值路径：CPU / with_text=False / L=28 / P=6')
for ch in list(r):
    if ch.get('id') in ['mse-panel','mse-comparison','mse-takeaway','metric-panel']:r.remove(ch)
# remove prior generated frame duplicated by base()
seen=set()
for ch in list(r)[::-1]:
    k=ch.get('id')
    if k in seen and k in ['midterm-header','midterm-footer','page-subtitle']:r.remove(ch)
    seen.add(k)
card(r,'evaluation-protocol',65,180,550,450,'数据与时间切分','1339 天：2023.01.01—2026.08.31\n训练 / 验证 / 测试：937 / 135 / 267 天\n测试窗口：262；方向有效窗口：235\n\n仅训练段拟合 log1p 后的标准化器\n方向排除真实变化幅度最低 10% 窗口\n尖峰标签按测试集真实增量 q75 定义',size=20)
g=group(r,'thresholds',660,180,550,163);txt(g,682,217,'标签阈值与报警阈值分别定义',26,TEAL,True);txt(g,682,260,'报警：预测增量 > 验证集阈值 0.4694\n标签：真实增量 > 测试集分位数 1.6922',21,INK,leading=1.6)
table(r,'confusion-counts',675,365,515,186,['','真实尖峰','真实非尖峰'],[['报警','26','42'],['不报警','40','154']],[1.1,1,1],22)
g=group(r,'eval-limit',670,573,530,65);txt(g,681,598,'标签用于回溯评价，不是预先已知的尖峰标准。\n窗口重叠，后续需滚动评估及分块置信区间。',19,RED)
write(t,'evaluation_protocol.svg')

# 14 Evidence map uses source large-left visual + right two feature boxes.
t,r=base(15,'备份｜文献启发与当前实现的边界',14,'文献支持研究设计，不自动构成本项目的性能证据')
for i,(title,body) in enumerate([('DLinear / xPatch [3,4]','分解、线性基线与 PatchCNN；项目扩展四分量路径。'),('Mamba / PELT [5,6]','选择性状态与变点建模；项目采用轻量实现与事件信号。'),('RAG / ReAct [7,10]','外部证据与行动反馈；项目以契约和规则约束生成。'),('Time-LLM 与消融研究 [8,9]','文本或大模型的价值必须独立消融，不能先验假定。')]):
    y=180+i*112;g=group(r,'paper-map-'+str(i),70,y,715,98);rect(g,70,y,715,98,PALE);txt(g,90,y+34,title,25,BLUE,True);txt(g,90,y+76,body,20,INK)
card(r,'scope-distinction',825,180,385,206,'已实现 ≠ 已证明','框架与代码可检查\n相对性能仍需统一基线\n回音室需互动网络证据 [1]',size=22)
card(r,'missing-evaluation',825,415,385,206,'待完成的验证','分量 / 文本 / 路由消融\n跨话题与滚动时间评估\n传播关系与标注样本 [2]',accent=TEAL,size=22)
write(t,'slide_15.svg')

# 15 Actual local detail screenshot replaces original demo frame.
t,r=base(21,'备份｜详情界面保留来源与观测范围',15,'本地运行实拍 · 仓库内置档案数据 · 非线上实时抓取证明')
g=group(r,'detail-screenshot',55,182,795,475);el(g,'image',href='../images/local_detail.png',x=55,y=182,width=795,height=475,preserveAspectRatio='xMidYMid meet')
card(r,'detail-fields',885,205,325,395,'可检查的入口','平台 / 来源\n观测时间范围\n摘要与主导立场\n研究记录与访问日志\n\n截图内条数属于该档案，\n不等于预测实验样本量。',size=21)
write(t,'slide_21.svg')

# 16 Native editable budget table; no fabricated actual spending.
t,r=base(13,'备份｜经费按申请预算列示，实支待核账',16,'材料依据：立项申请书预算；原草稿调整建议尚缺审批与票据')
table(r,'application-budget',70,180,640,432,['原预算科目','金额 / 元'],[['云服务器','1,800'],['数据采集与接口','1,200'],['软件开发与模型训练','2,000'],['大模型调用','1,000'],['调研差旅','800'],['知识产权及论文','700'],['合计','7,500']],[3.1,1],23)
card(r,'budget-verification',755,180,455,432,'下一步核对','获批额度与实际到账\n逐笔支出、账单和凭证编号\n预算科目与调剂审批\n\n原草稿提出调用费增至 2200 元，\n目前仅按调整建议记录。\n不据此计算执行率与结余。',size=22)
write(t,'slide_13.svg')

# 17 Keeps source six-box layout.
t,r=base(25,'备份｜风险与验收计划',17,'用可检查的样本、记录和指标判断阶段任务是否完成')
for i,(title,body) in enumerate([('01 事件对齐','先建立人工标注样本\n报告同事件识别准确率与召回'),('02 传播关系','核查来源、时间戳和引用边\n区分首发线索与因果传播'),('03 预测泛化','统一基线与消融协议\n滚动切分、跨话题再评估'),('04 规则覆盖','整理误判与漏检案例\n人工抽查通过和驳回结论'),('05 部署可靠性','测量目标环境内存与延迟\n记录弱网、缺依赖和降级'),('06 成果与经费','整理申请材料和财务台账\n状态以正式回执或凭证为准')]):
    x=70+(i%3)*390;y=180+(i//3)*240;card(r,'risk-'+str(i),x,y,350,210,title,body,size=21)
write(t,'slide_25.svg')

# 18 references, concise bibliographic text; full searchable provenance in repo.
t,r=base(23,'备份｜参考文献与证据入口',18,'已保存 10 篇原文、重点段落阅读记录及代码映射；检索限制见研究日志')
refs=[
('[1] Cinelli et al. (2020, preprint)','Echo Chambers on Social Media:\nA comparative analysis · arXiv:2004.09603'),
('[2] Zannettou et al. (2017)','The Web Centipede · arXiv:1705.06947'),
('[3] Zeng et al. (AAAI 2023)','Are Transformers Effective for Time Series\nForecasting? · arXiv:2205.13504'),
('[4] Stitsyuk & Choi (2024, preprint)','xPatch · arXiv:2412.17323'),
('[5] Gu & Dao (2023, preprint)','Mamba · arXiv:2312.00752'),
('[6] Killick et al. (2011, preprint)','Optimal detection of changepoints with\na linear computational cost · arXiv:1101.1438'),
('[7] Lewis et al. (NeurIPS 2020)','Retrieval-Augmented Generation for\nKnowledge-Intensive NLP Tasks · 2005.11401'),
('[8] Jin et al. (ICLR 2024)','Time-LLM · arXiv:2310.01728'),
('[9] Tan et al. (NeurIPS 2024)','Are Language Models Actually Useful for\nTime Series Forecasting? · 2406.16964'),
('[10] Yao et al. (ICLR 2023)','ReAct · arXiv:2210.03629')]
for i,(title,body) in enumerate(refs):
    x=75+(i//5)*600;y=175+(i%5)*90;g=group(r,'ref-'+str(i),x,y,555,82);txt(g,x+5,y+23,title,21,BLUE,True);txt(g,x+5,y+51,body,17,INK,leading=1.35)
g=group(r,'evidence-index',75,637,1130,33);txt(g,80,658,'仓库索引：docs/midterm_20261029/   ·   实验依据：retrain_20261019/deployment_verification.json',16,MUTED)
write(t,'slide_23.svg')

pages=[(1,'slide_01.svg'),(6,'slide_06.svg'),(5,'slide_05.svg'),(9,'slide_09.svg'),(12,'slide_12.svg'),(10,'slide_10.svg'),(18,'slide_18.svg'),(20,'slide_20.svg'),(16,'slide_16.svg'),(17,'slide_17.svg'),(26,'slide_26.svg'),(27,'slide_27.svg'),(18,'evaluation_protocol.svg'),(15,'slide_15.svg'),(21,'slide_21.svg'),(13,'slide_13.svg'),(25,'slide_25.svg'),(23,'slide_23.svg')]
(P/'page_plan.json').write_text(json.dumps({'schema':'ppt-master.roundtrip-page-plan.v1','pages':[{'source_slide':n,'svg':s}for n,s in pages]},ensure_ascii=False,indent=2),encoding='utf-8')
for name in ['local_archive.png','local_detail.png']:shutil.copy2(ROOT/'evidence'/name,P/'images'/name)
print('Authored',len(pages),'planned pages. Inherited Master/Layout objects retained.')
