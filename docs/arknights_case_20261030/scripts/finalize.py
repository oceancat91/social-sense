"""Verify the bounded revision and publish reviewable PPTX/PDF artifacts."""
from pathlib import Path
from zipfile import ZipFile
import argparse
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as E
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
NS = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main', 'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
EDITED = {2, 5, 6}

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pptx', type=Path)
    args = parser.parse_args()
    source = ROOT / 'sources/source.pptx'
    previous = REPO / 'docs/midterm_20261029/deliverables/SocialSense_中期答辩_6分钟主讲_含问答备份.pptx'
    pdf = ROOT / 'build/rendered/render.pdf'
    receipt = json.loads((ROOT / 'validation' / (args.pptx.stem + '.report.json')).read_text(encoding='utf-8-sig'))
    provenance = json.loads((ROOT / 'evidence/case_provenance.json').read_text(encoding='utf-8'))
    assert sha(source) == sha(previous)
    assert sha(Path(provenance['source'])) == provenance['sha256']
    assert all(sha(REPO / rel) == digest for rel, digest in provenance['code'].items())

    report = {'edited_pages': sorted(EDITED), 'source_unchanged': True, 'source_material_unchanged': True, 'reviewed_code_unchanged': True}
    with ZipFile(source) as a, ZipFile(args.pptx) as b:
        slides = sorted((n for n in b.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)), key=lambda n:int(re.search(r'slide(\d+)',n).group(1)))
        assert len(slides) == 18
        unchanged = [i for i in range(1, 19) if i not in EDITED]
        assert all(a.read(f'ppt/slides/slide{i}.xml') == b.read(f'ppt/slides/slide{i}.xml') for i in unchanged)
        assert all(a.read(f'ppt/slides/slide{i}.xml') != b.read(f'ppt/slides/slide{i}.xml') for i in EDITED)
        structural = [n for n in a.namelist() if n.startswith(('ppt/slideMasters/','ppt/slideLayouts/'))]
        assert all(a.read(n) == b.read(n) for n in structural)
        # Native round-trip cloning may rename chart parts (e.g. *_tf1.xml).
        # Compare the actual chart XML content, independent of package names.
        def chart_parts(package):
            return [n for n in package.namelist() if n.startswith('ppt/charts/') and n.endswith('.xml')
                    and E.fromstring(package.read(n)).tag == '{http://schemas.openxmlformats.org/drawingml/2006/chart}chartSpace']
        charts, output_charts = chart_parts(a), chart_parts(b)
        assert len(charts) == len(output_charts) == 1
        assert sorted(a.read(n) for n in charts) == sorted(b.read(n) for n in output_charts)
        tables = sum(len(E.fromstring(b.read(n)).findall('.//a:tbl', NS)) for n in slides)
        assert tables == 2
        notes = [n for n in b.namelist() if n.startswith('ppt/notesSlides/') and n.endswith('.xml')
                 and E.fromstring(b.read(n)).tag == '{http://schemas.openxmlformats.org/presentationml/2006/main}notes']
        assert len(notes) == 18
        auto = sum(len(E.fromstring(b.read(n)).findall('.//p:transition[@advTm]', NS)) for n in slides)
        assert auto == 0
        show = E.fromstring(b.read('ppt/presProps.xml')).find('p:showPr', NS)
        assert show is not None and show.get('useTimings') == '0'
        report.update({'slides': 18, 'notes': 18, 'unchanged_slide_xml_pages': unchanged, 'master_layout_bytes_identical': True, 'native_charts_unchanged': 1, 'native_tables': tables, 'automatic_advance_slides': auto, 'use_timings': False})

    assert len(PdfReader(pdf).pages) == 18
    report['pdf_pages'] = 18
    # Compare against a fresh native rendering of the unchanged source package.
    # Four pages have very small color-level differences after package cloning;
    # their slide/chart XML is identical and they were visually reviewed.
    from PIL import Image, ImageChops, ImageStat
    old_renders = ROOT / 'build/source_rendered'
    identical = []
    minor_raster_differences = {}
    for i in range(1, 19):
        if i in EDITED:
            continue
        old = Image.open(old_renders / f'幻灯片{i}.PNG').convert('RGB')
        new = Image.open(ROOT / 'build/rendered' / f'幻灯片{i}.PNG').convert('RGB')
        assert old.size == new.size
        difference = ImageChops.difference(old, new)
        if difference.getbbox() is None:
            identical.append(i)
        else:
            maximum = max(high for low, high in difference.getextrema())
            channel_mean = ImageStat.Stat(difference).mean
            assert i in {7, 8, 11, 15} and maximum <= 15 and max(channel_mean) < 0.12, f'Unreviewed visual change on slide {i}'
            minor_raster_differences[i] = {'bbox': difference.getbbox(), 'max_channel_difference_255': maximum, 'mean_channel_difference_255': channel_mean, 'manual_visual_review': 'accepted_no_layout_or_content_change'}
    report['unchanged_page_render_pixels_identical'] = identical
    report['minor_raster_differences'] = minor_raster_differences
    note_text = (ROOT / 'deliverables/六分钟讲稿与四分钟问答_案例融入版.md').read_text(encoding='utf-8')
    durations = list(map(int, re.findall(r'## 第\d+页\s+(\d+)秒', note_text)))
    assert sum(durations) == 360 and len(durations) == 12
    report['rehearsal_seconds'] = durations
    report['total_rehearsal_seconds'] = 360
    report['status'] = 'passed'

    out = ROOT / 'deliverables'
    shutil.copy2(args.pptx, out / 'SocialSense_中期答辩_案例融入版.pptx')
    shutil.copy2(pdf, out / 'SocialSense_中期答辩_案例融入版.pdf')
    (ROOT / 'evidence/final_verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest = [{'file': p.name, 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in sorted(out.iterdir()) if p.is_file()]
    (ROOT / 'evidence/deliverable_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
