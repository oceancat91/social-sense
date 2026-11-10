from pathlib import Path
import sys,json
from pypdf import PdfReader
root=Path(__file__).resolve().parents[1]
groups={
'a': [('P01_echo_chambers_preprint',[1,2,3]),('P02_web_centipede',[5,6,7]),('P03_dlinear',[2,3,5])],
'b': [('P04_xpatch',[2,3,5]),('P05_mamba',[2,3,4]),('P06_pelt',[3,4,5])],
'c': [('P07_rag',[2,3,5]),('P08_time_llm',[2,3,5]),('P09_llm_ablation',[2,3,4]),('P10_react',[2,3,5])]
}
for key,pages in groups[sys.argv[1]]:
    reader=PdfReader(root/'research/papers'/f'{key}.pdf')
    out='\n\n'.join(f'## PDF page {i}\n'+reader.pages[i-1].extract_text() for i in pages)
    (root/'research'/f'{key}_reading_excerpt.txt').write_text(out,encoding='utf-8')
    print('\nPAPER',key,'READ PAGES',pages,'\n'+out)
