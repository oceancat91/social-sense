from pathlib import Path
import json,re
from docx import Document
from docx.shared import Pt,Cm,RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH,WD_BREAK
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
import report_content as c

root=Path(__file__).resolve().parents[1]
doc=Document(root/'sources/2026年度中期汇报表.docx')
out=root/'deliverables/2026年度中期汇报表_SocialSense_修订稿.docx'
def font(run,size=11,bold=False):
    run.font.name='宋体';run.font.size=Pt(size);run.font.bold=bold;run.font.color.rgb=RGBColor(0,0,0)
    run._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'宋体')
def para(p,text,size=11,bold=False):
    p.clear();font(p.add_run(text),size,bold)
    f=p.paragraph_format;f.space_before=Pt(0);f.space_after=Pt(4);f.line_spacing=Pt(16)
    f.keep_together=True;f.keep_with_next=bold;f.widow_control=True;f.page_break_before=False
def replace(cell,text):
    cell.text=''
    for i,line in enumerate(text.splitlines()):
        p=cell.paragraphs[0] if i==0 else cell.add_paragraph()
        heading=bool(re.match(r'^（[一二三四五六七八九]）',line))
        para(p,line,11,heading)
        if heading:p.paragraph_format.space_before=Pt(5)
    cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.TOP
for style in ['Normal','Title','Heading 1','Heading 2']:
    if style not in doc.styles:doc.styles.add_style(style,WD_STYLE_TYPE.PARAGRAPH)
    s=doc.styles[style];s.font.name='宋体';s.font.color.rgb=RGBColor(0,0,0)
    s._element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),'宋体')
for p in list(doc.paragraphs):
    if not p.text.strip():p._element.getparent().remove(p._element)
for p in doc.paragraphs:
    if '项目编号' in p.text:para(p,'项目编号：2026PY—                    ',11);p.paragraph_format.space_after=Pt(35)
    elif '2026年度本科生' in p.text:
        para(p,p.text,17,True);p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.style='Title';p.paragraph_format.space_after=Pt(20)
    elif p.text=='中期汇报表':
        para(p,p.text,24,True);p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.space_after=Pt(36)
    elif '填表日期' in p.text:
        para(p,'填表日期：2026 年 10 月 30 日',12);p.alignment=WD_ALIGN_PARAGRAPH.CENTER;p.paragraph_format.space_before=Pt(30)
for ti,t in enumerate(doc.tables):
    for row in t.rows:
        trpr=row._tr.get_or_add_trPr()
        for e in list(trpr):
            if e.tag in (qn('w:trHeight'),qn('w:cantSplit')):trpr.remove(e)
        seen=set()
        for cell in row.cells:
            if id(cell._tc) in seen:continue
            seen.add(id(cell._tc));pr=cell._tc.get_or_add_tcPr()
            margins=OxmlElement('w:tcMar')
            for k,v in [('top',85),('bottom',85),('left',100),('right',100)]:
                x=OxmlElement('w:'+k);x.set(qn('w:w'),str(v));x.set(qn('w:type'),'dxa');margins.append(x)
            pr.append(margins)
            borders=OxmlElement('w:tcBorders')
            for k in ['top','left','bottom','right']:
                x=OxmlElement('w:'+k);x.set(qn('w:val'),'single');x.set(qn('w:sz'),'6');x.set(qn('w:color'),'B7B7B7');borders.append(x)
            pr.append(borders);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            for p in cell.paragraphs:
                for run in p.runs:font(run,11)
                p.paragraph_format.line_spacing=Pt(16);p.paragraph_format.space_after=Pt(2)
                p.paragraph_format.keep_together=True;p.paragraph_format.keep_with_next=False;p.paragraph_format.page_break_before=False
t=doc.tables[1]
for row,text in [(3,c.GOALS),(5,c.PROGRESS),(7,c.INNOVATION),(9,c.REFLECTION),(18,c.BUDGET)]:replace(t.rows[row].cells[0],text)
for p in t.rows[5].cells[0].paragraphs:
    p.paragraph_format.line_spacing=Pt(15)
    p.paragraph_format.space_after=Pt(3)
    if p.runs and p.runs[0].bold:p.paragraph_format.space_before=Pt(3)
for i,task in enumerate(c.TASKS):replace(t.rows[12+i].cells[4],task)
for idx in [2,4,6,8,10,17]:
    row=t.rows[idx];cell=row.cells[0]
    for p in cell.paragraphs:
        txt=p.text.strip();para(p,txt,11,True)
    shd=OxmlElement('w:shd');shd.set(qn('w:fill'),'F2F2F2');cell._tc.get_or_add_tcPr().append(shd)
for cell in t.rows[11].cells:
    for p in cell.paragraphs:p.paragraph_format.keep_with_next=True
t.rows[10].cells[0].paragraphs[0].paragraph_format.page_break_before=True
t.rows[6].cells[0].paragraphs[0].paragraph_format.page_break_before=True
for i in range(12,17):
    t.rows[i]._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
    for j in [0,1,2]:
        for p in t.rows[i].cells[j].paragraphs:p.alignment=WD_ALIGN_PARAGRAPH.CENTER
# Cover remains the original form; start the substantive report on a fresh page.
p=OxmlElement('w:p');r=OxmlElement('w:r');br=OxmlElement('w:br');br.set(qn('w:type'),'page');r.append(br);p.append(r);t._element.addprevious(p)
for sec in doc.sections:
    f=sec.footer.paragraphs[0];f.alignment=WD_ALIGN_PARAGRAPH.CENTER
    font(f.add_run('— '),9);fld=OxmlElement('w:fldSimple');fld.set(qn('w:instr'),'PAGE');f._p.append(fld);font(f.add_run(' —'),9)
doc.core_properties.title='2026年度中期汇报表 SocialSense'
doc.core_properties.subject='创新训练类中期检查'
doc.core_properties.comments='依据项目代码和2026-10-19独立验证记录修订；未核实经费和成果回执不列为已完成。'
out.parent.mkdir(exist_ok=True,parents=True);doc.save(out)
counts={k:len(getattr(c,k)) for k in ['GOALS','PROGRESS','INNOVATION','REFLECTION','BUDGET']}
assert counts['PROGRESS']<=2000 and counts['INNOVATION']<=600 and counts['REFLECTION']<=2000 and counts['BUDGET']<=2000
(root/'evidence/report_word_counts.json').write_text(json.dumps(counts,ensure_ascii=False,indent=2),encoding='utf-8')
(root/'deliverables/中期汇报表正文.md').write_text('\n\n'.join('# '+h+'\n\n'+v for h,v in [('目标与内容',c.GOALS),('研究进展和当前成果',c.PROGRESS),('创新特色',c.INNOVATION),('研究心得',c.REFLECTION),('经费与下一步计划',c.BUDGET)]),encoding='utf-8')
print(out);print(counts)
