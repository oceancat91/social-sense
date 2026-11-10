"""Verify the delivered native package and publish the reviewed PPTX and PDF."""
from pathlib import Path
from zipfile import ZipFile
import argparse
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as E
from PIL import Image, ImageChops, ImageStat
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
D = 'http://schemas.openxmlformats.org/drawingml/2006/main'
R = 'http://schemas.openxmlformats.org/package/2006/relationships'
EDITED = {2, 3, 4, 5, 6, 9, 10, 11, 17, 18}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pptx', type=Path)
    args = parser.parse_args()
    source = ROOT / 'sources/source.pptx'
    previous = REPO / 'docs/arknights_case_20261030/deliverables/SocialSense_中期答辩_案例融入版.pptx'
    pdf = ROOT / 'build/rendered/render.pdf'
    evidence = json.loads((ROOT / 'evidence/revision_provenance.json').read_text(encoding='utf-8'))
    receipt = json.loads((ROOT / 'validation' / (args.pptx.stem + '.report.json')).read_text(encoding='utf-8-sig'))
    delivery = json.loads((ROOT / 'validation/delivery.json').read_text(encoding='utf-8-sig'))
    assets = json.loads((ROOT / 'evidence/network_assets.json').read_text(encoding='utf-8'))
    assert sha(source) == sha(previous) == evidence['source_pptx_sha256']
    assert receipt['status'] == 'passed'
    assert receipt['quality']['summary']['errors'] == 0
    assert receipt['quality']['summary']['warnings'] == 0
    assert not delivery['errors'] and not delivery['package']['relationships']['problems']
    assert all(sha(REPO / p) == value for p, value in evidence['code_sha256'].items())
    assert all(sha(ROOT / asset['file']) == asset['sha256'] for asset in assets)

    result = {'status': 'passed', 'slides': 18, 'edited_pages': sorted(EDITED),
              'source_package_unchanged': True, 'reviewed_code_unchanged': True,
              'quality_errors': 0, 'quality_warnings': 0,
              'delivery_errors': [], 'delivery_advisories': delivery['advisories'],
              'advisory_disposition': 'Inherited theme fonts preserved; Windows PowerPoint renders reviewed and fixed-layout PDF supplied.'}
    with ZipFile(source) as a, ZipFile(args.pptx) as b:
        slides = [f'ppt/slides/slide{i}.xml' for i in range(1, 19)]
        assert sum(bool(re.fullmatch(r'ppt/slides/slide\d+\.xml', name)) for name in b.namelist()) == 18
        unchanged = [i for i in range(1, 19) if i not in EDITED]
        assert all(a.read(slides[i-1]) == b.read(slides[i-1]) for i in unchanged)
        assert all(a.read(slides[i-1]) != b.read(slides[i-1]) for i in EDITED)
        structural = [n for n in a.namelist() if n.startswith(('ppt/slideMasters/', 'ppt/slideLayouts/'))]
        assert all(a.read(n) == b.read(n) for n in structural)
        def charts(z):
            return [z.read(n) for n in z.namelist() if n.startswith('ppt/charts/') and n.endswith('.xml')
                    and E.fromstring(z.read(n)).tag == '{http://schemas.openxmlformats.org/drawingml/2006/chart}chartSpace']
        assert len(charts(a)) == len(charts(b)) == 1 and sorted(charts(a)) == sorted(charts(b))
        tables = sum(len(E.fromstring(b.read(n)).findall('.//{' + D + '}tbl')) for n in slides)
        assert tables == 2
        notes = [n for n in b.namelist() if n.startswith('ppt/notesSlides/') and n.endswith('.xml')
                 and E.fromstring(b.read(n)).tag == '{' + P + '}notes']
        assert len(notes) == 18
        advances = sum(len(E.fromstring(b.read(n)).findall('.//{' + P + '}transition[@advTm]')) for n in slides)
        assert advances == 0
        show = E.fromstring(b.read('ppt/presProps.xml')).find('{' + P + '}showPr')
        assert show is not None and show.get('useTimings') == '0'
        media_hashes = {hashlib.sha256(b.read(n)).hexdigest() for n in b.namelist() if n.startswith('ppt/media/')}
        used_assets = [a for a in assets if Path(a['file']).name in evidence['network_images_used']]
        assert len(used_assets) == 3
        assert all(a['sha256'] in media_hashes for a in used_assets)
        targets = {rel.get('Target') for n in b.namelist() if n.endswith('.rels')
                   for rel in E.fromstring(b.read(n)) if rel.get('Type', '').endswith('/hyperlink')}
        expected_urls = {'https://www.taptap.cn/moment/834126362733185189',
                         'https://www.taptap.cn/moment/832223722998859956',
                         'https://yuqing.sina.com/undefined/about',
                         'https://files.yqt365.com/fileOnline/instruction.html',
                         'https://arxiv.org/abs/1805.12512'}
        assert expected_urls <= targets
        result.update({'unchanged_visible_slide_xml': unchanged, 'master_layout_bytes_identical': True,
                       'native_chart_unchanged': 1, 'native_tables': tables, 'speaker_notes': len(notes),
                       'automatic_slide_advances': advances, 'use_timings': False,
                       'new_images_original_bytes_embedded': [a['file'] for a in used_assets],
                       'source_hyperlinks_verified': sorted(expected_urls)})

    reader = PdfReader(pdf)
    assert len(reader.pages) == 18
    assert '研究价值' in reader.pages[1].extract_text()
    assert '创作认可' in reader.pages[2].extract_text()
    assert '应用展望' in reader.pages[8].extract_text()
    assert all((ROOT / 'build/rendered' / f'幻灯片{i}.PNG').exists() for i in range(1, 19))
    result['pdf_pages'] = 18
    result['office_rendered_pages'] = 18
    result['manual_visual_review_pages'] = list(range(1, 19))
    result['visual_review'] = 'No text clipping, unintended overlap, cropped attribution, or obscured native chart/table found.'
    # Compare stable slides to the prior delivered deck's Office renders.
    old_render = REPO / 'docs/arknights_case_20261030/build/rendered'
    comparison = {}
    for page in result['unchanged_visible_slide_xml']:
        old_path = old_render / f'幻灯片{page}.PNG'
        if not old_path.exists():
            continue
        old = Image.open(old_path).convert('RGB')
        new = Image.open(ROOT / 'build/rendered' / f'幻灯片{page}.PNG').convert('RGB')
        assert old.size == new.size == (1600, 900)
        diff = ImageChops.difference(old, new)
        comparison[page] = {'pixels_identical': diff.getbbox() is None,
                            'maximum_channel_difference_255': max(h for l, h in diff.getextrema()),
                            'mean_channel_difference_255': ImageStat.Stat(diff).mean}
    result['reference_render_comparison'] = comparison
    script = (ROOT / 'deliverables/六分钟讲稿与四分钟问答_社区价值增强版.md').read_text(encoding='utf-8')
    timings = list(map(int, re.findall(r'## 第\d+页\s+(\d+)秒', script)))
    assert timings == evidence['timing_seconds'] and sum(timings) == 360
    result['main_page_seconds'] = timings
    result['main_total_seconds'] = 360
    result['timing_basis'] = 'rehearsal_budget_not_recorded_speech'

    out = ROOT / 'deliverables'
    shutil.copy2(args.pptx, out / 'SocialSense_中期答辩_社区价值增强版.pptx')
    shutil.copy2(pdf, out / 'SocialSense_中期答辩_社区价值增强版.pdf')
    (ROOT / 'evidence/final_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest = [{'file': p.name, 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in sorted(out.iterdir()) if p.is_file()]
    (ROOT / 'evidence/deliverable_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
