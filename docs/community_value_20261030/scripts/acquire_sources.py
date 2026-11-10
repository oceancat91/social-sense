"""Download public, cited research illustrations without altering their bytes."""
from pathlib import Path
from urllib.request import urlopen, Request
from concurrent.futures import ThreadPoolExecutor
import hashlib, json
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = [
    ('official_summer_1.jpg','https://img2-tc.tapimg.com/moment/etag/FoWkEMraPRQSh9dH0v5LBSnQ_SKX_20260805175534.png/_tap_ugc.jpg','https://www.taptap.cn/moment/834126362733185189','明日方舟素材分享帖：图片1','游戏美术权利归鹰角网络；教学案例引用'),
    ('official_summer_2.jpg','https://img2-tc.tapimg.com/moment/etag/Fstb99T-eJkgMMvFAs3bd98wVAXX_20260805175536.png/_tap_ugc.jpg','https://www.taptap.cn/moment/834126362733185189','明日方舟素材分享帖：图片2','游戏美术权利归鹰角网络；教学案例引用'),
    ('official_summer_3.jpg','https://img2-tc.tapimg.com/moment/etag/Fk8qmLylTBijnnHQBH0_bNRSOBdS_20260805175540.png/_tap_ugc.jpg','https://www.taptap.cn/moment/834126362733185189','明日方舟素材分享帖：图片3','游戏美术权利归鹰角网络；教学案例引用'),
    ('official_summer_4.jpg','https://img2-tc.tapimg.com/moment/etag/FgNw6QClOTrvTBMXgaHWn8ScZQtC_20260805175542.png/_tap_ugc.jpg','https://www.taptap.cn/moment/834126362733185189','明日方舟素材分享帖：图片4','游戏美术权利归鹰角网络；教学案例引用'),
    ('yuqing_trace.png','https://files.yqt365.com/fileOnline/20210704/c85f2ab77c5a40eaab5c169d2cf70ddc.png','https://files.yqt365.com/fileOnline/instruction.html','舆情通官方使用说明：微博溯源截图','产品图片权利归原发布方；用于功能比较，不代表本项目界面'),
]

PAGES = [
    ('sina_product.html','https://yuqing.sina.com/undefined/about'),
    ('yuqing_manual.html','https://files.yqt365.com/fileOnline/instruction.html'),
    ('official_material_post.html','https://www.taptap.cn/moment/834126362733185189'),
    ('fan_generator.html','https://github.com/Minecrash98/zhe-pian-da-di-font-pack'),
    ('meme_diffusion_2018.pdf','https://seclab.bu.edu/papers/memes-IMC2018.pdf'),
]

def get(url, limit):
    with urlopen(Request(url, headers={'User-Agent':'Mozilla/5.0 (compatible; academic-source-review)'}),timeout=30) as response:
        data=response.read(limit+1)
        if len(data)>limit: raise ValueError('Download exceeds review size limit')
        return data,response.geturl(),response.headers.get('Content-Type')

def asset(row):
    name,url,page,title,rights=row
    try:
        data,final,ctype=get(url,15_000_000)
        p=ROOT/'images'/name;p.write_bytes(data)
        im=Image.open(p);im.verify()
        im=Image.open(p)
        return {'file':str(p.relative_to(ROOT)),'source_page':page,'asset_url':url,'resolved_url':final,'title':title,'rights':rights,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'dimensions':list(im.size),'format':im.format,'download_date':'2026-10-30','status':'downloaded'}
    except Exception as exc:return {'file':name,'asset_url':url,'status':'failed','error':str(exc)}

def page(row):
    name,url=row
    try:
        data,final,ctype=get(url,30_000_000)
        p=ROOT/'research'/name;p.write_bytes(data)
        return {'file':str(p.relative_to(ROOT)),'url':url,'resolved_url':final,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'status':'downloaded'}
    except Exception as exc:return {'file':name,'url':url,'status':'failed','error':str(exc)}

if __name__=='__main__':
    (ROOT/'research').mkdir(exist_ok=True);(ROOT/'evidence').mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        images=list(pool.map(asset,ASSETS))
        pages=list(pool.map(page,PAGES))
    (ROOT/'evidence/network_assets.json').write_text(json.dumps(images,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'research/acquisition.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2),encoding='utf-8')
    for r in images+pages:print(r['file'],r['status'],r.get('dimensions',''),r.get('error',''))
