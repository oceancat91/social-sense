from pathlib import Path
import csv, json, hashlib, re

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
(ROOT / 'evidence').mkdir(exist_ok=True)
rows = []
examples = {}
patterns = {
    'wuhan_library': lambda s: bool(re.search(r'武汉大学|武大', s) and '图书馆' in s),
    'houhui_you_friend': lambda s: '后会友期' in s,
    'houhui_you_have': lambda s: '后会有期' in s,
}
for p in sorted((REPO / 'agent/dataset/real_multiplatform/raw').rglob('*.csv')):
    counts = {k: 0 for k in patterns}
    dates = {k: [] for k in patterns}
    total = 0
    try:
        with p.open(encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                total += 1
                body = row.get('text_structured_clean') or ''
                for key, test in patterns.items():
                    if test(body):
                        counts[key] += 1
                        dates[key].append(row.get('publish_time', '')[:10])
                        if key != 'wuhan_library' and len(examples.get(key, [])) < 7:
                            match = re.search(r'后会[友有]期', body)
                            excerpt = body[max(0,match.start()-25):match.end()+90]
                            examples.setdefault(key, []).append({'path':str(p.relative_to(REPO)), 'text_context':excerpt})
        rows.append({'path':str(p.relative_to(REPO)), 'platform':p.parent.name,
                     'rows':total, 'counts':counts,
                     'matched_date_range':{k:[min(v),max(v)] for k,v in dates.items() if v}})
    except UnicodeError:
        rows.append({'path':str(p.relative_to(REPO)), 'status':'encoding_error'})

code_paths = [
    'backend/app/routes/analysis.py', 'backend/app/routes/forecast.py',
    'backend/app/services/forecast_service.py', 'frontend/src/forecast-chart.ts',
    'frontend/src/forecast-api.ts', 'frontend/src/scene.ts', 'frontend/src/main.ts',
    'multiagent/contract.py', 'multiagent/align.py', 'multiagent/fuse.py', 'multiagent/master.py',
    'agent/Conclusion/calib/gates.py', 'social_forecast/models/rep_moe.py',
    'social_forecast/layers/rep_fusion.py',
    'social_forecast/results/retrain_20261019/deployment_verification.json',
]
record = {'scanned_csv_files':len(rows), 'total_rows':sum(r.get('rows',0)for r in rows),
          'selection_definition':'Substring keyword candidates, not a labeled event dataset; no deduplication.',
          'files':rows, 'title_disambiguation_examples':examples,
          'code_hashes':{p:hashlib.sha256((REPO/p).read_bytes()).hexdigest()for p in code_paths}}
(ROOT/'evidence/repository_audit.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'scanned_csv_files':len(rows),'matched_files':[r for r in rows if any(r.get('counts',{}).values())],
                  'title_context':examples},ensure_ascii=False))
