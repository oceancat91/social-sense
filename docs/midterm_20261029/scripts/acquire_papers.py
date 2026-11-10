from pathlib import Path
import concurrent.futures, urllib.request, hashlib, json, datetime
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1]
PAPERS=[
('P01_echo_chambers','The echo chamber effect on social media','https://www.research.unipd.it/retrieve/d7dfc79c-468f-4a65-b9b1-f07f123602a9/cinelli-et-al-2021-the-echo-chamber-effect-on-social-media.pdf'),
('P02_web_centipede','The Web Centipede','https://arxiv.org/pdf/1705.06947'),
('P03_dlinear','Are Transformers Effective for Time Series Forecasting?','https://arxiv.org/pdf/2205.13504'),
('P04_xpatch','xPatch: Dual-Stream Time Series Forecasting with Exponential Seasonal-Trend Decomposition','https://arxiv.org/pdf/2412.17323'),
('P05_mamba','Mamba: Linear-Time Sequence Modeling with Selective State Spaces','https://arxiv.org/pdf/2312.00752'),
('P06_pelt','Optimal detection of changepoints with a linear computational cost','https://arxiv.org/pdf/1101.1438'),
('P07_rag','Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks','https://arxiv.org/pdf/2005.11401'),
('P08_time_llm','Time-LLM: Time Series Forecasting by Reprogramming Large Language Models','https://arxiv.org/pdf/2310.01728'),
('P09_llm_ablation','Are Language Models Actually Useful for Time Series Forecasting?','https://arxiv.org/pdf/2406.16964'),
('P10_react','ReAct: Synergizing Reasoning and Acting in Language Models','https://arxiv.org/pdf/2210.03629'),
]
def fetch(item):
    key,title,url=item; dst=ROOT/'research/papers'/f'{key}.pdf'
    meta={'id':key,'title':title,'source_url':url,'retrieved_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()}
    try:
        if not dst.exists():
            req=urllib.request.Request(url,headers={'User-Agent':'SocialSense academic reference archive/1.0'})
            data=urllib.request.urlopen(req,timeout=45).read()
            if not data.startswith(b'%PDF'):raise ValueError('Response is not a PDF')
            dst.write_bytes(data)
        reader=PdfReader(dst)
        text='\n\n'.join(f'## PDF page {i+1}\n\n{p.extract_text()}' for i,p in enumerate(reader.pages))
        dst.with_suffix('.txt').write_text(text,encoding='utf-8')
        meta.update(status='downloaded',pages=len(reader.pages),sha256=hashlib.sha256(dst.read_bytes()).hexdigest(),path=f'papers/{dst.name}')
    except Exception as e:meta.update(status='failed',error=str(e))
    print(key,meta['status'],flush=True);return meta
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(fetch,PAPERS))
(ROOT/'research/acquisition.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
