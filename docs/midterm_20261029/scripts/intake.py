from pathlib import Path
import json, shutil, hashlib
from pypdf import PdfReader
from docx import Document
from pptx import Presentation
ROOT = Path(__file__).resolve().parents[1]
DESK = ROOT.parents[1].parent
files=['知旅-基于多源数据融合的动态旅游规划平台(1).pptx','2026年度中期汇报表.docx','大创中期介绍20261026(1).pdf','附件3 项目中期检查评分表【答辩专家】.docx','附件2 本科生创新训练培育项目（创新训练类）立项申报书.pdf']
for name in ['sources','research/papers','evidence','deliverables','build/previews']:
    (ROOT/name).mkdir(parents=True,exist_ok=True)
manifest=[]
for name in files:
    src=DESK/name; dst=ROOT/'sources'/name
    if not dst.exists(): shutil.copy2(src,dst)
    manifest.append({'file':name,'original':str(src),'sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'bytes':src.stat().st_size})
    if src.suffix=='.pdf':
        d=PdfReader(src); body='\n\n'.join(f'## 第 {i+1} 页\n\n{p.extract_text()}' for i,p in enumerate(d.pages))
    elif src.suffix=='.docx':
        d=Document(src); chunks=[p.text for p in d.paragraphs]
        for ti,t in enumerate(d.tables):
            chunks.append(f'\n## Table {ti}')
            for ri,row in enumerate(t.rows):
                seen=set(); cells=[]
                for ci,c in enumerate(row.cells):
                    if c._tc in seen:continue
                    seen.add(c._tc);cells.append(f'[{ci}] {c.text}')
                chunks.append(f'Row {ri}: '+' | '.join(cells))
        body='\n\n'.join(chunks)
    else:
        d=Presentation(src); chunks=[]
        for i,s in enumerate(d.slides):
            def texts(shapes):
                out=[]
                for sh in shapes:
                    if sh.shape_type==6:out.extend(texts(sh.shapes))
                    if sh.has_text_frame:out.append(sh.text)
                    if sh.has_table:out.extend(' | '.join(c.text for c in row.cells) for row in sh.table.rows)
                return out
            chunks.append(f'## Slide {i+1}\n'+'\n'.join(texts(s.shapes)))
        body='\n\n'.join(chunks)
        print('template',len(d.slides),'slides',int(d.slide_width),int(d.slide_height))
    dst.with_suffix('.md').write_text(body,encoding='utf-8')
(ROOT/'sources/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
