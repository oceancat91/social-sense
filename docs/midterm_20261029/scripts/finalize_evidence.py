"""Recheck stored evidence and package the completed midterm artifacts.

This does not train a model, invoke external services, or edit application code.
"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from zipfile import ZipFile
import hashlib
import json
import subprocess
import sys
import shutil
import importlib.util
import types
import argparse
from lxml import etree
from pypdf import PdfReader

TASK = Path(__file__).resolve().parents[1]
REPO = TASK.parents[1]
TZ = timezone(timedelta(hours=8))
NOW = datetime.now(TZ).isoformat()
sys.path.insert(0, str(REPO))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--pptx", type=Path, default=TASK/"presentation/exports/presentation_20261030_015340_native_charts_tables_manual.pptx")
parser.add_argument("--deck-pdf", type=Path, default=TASK/"build/deck_release/render.pdf")
parser.add_argument("--report-pdf", type=Path, default=TASK/"build/report_final/render.pdf")
args = parser.parse_args()

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

papers = TASK / "research/acquisition.json"
records = json.loads(papers.read_text(encoding="utf-8"))
pdf = TASK / "research/papers/P01_echo_chambers_preprint.pdf"
if not any(r["id"] == "P01_echo_chambers_preprint" for r in records):
    records.append({
        "id": "P01_echo_chambers_preprint",
        "title": "Echo Chambers on Social Media: A comparative analysis",
        "source_url": "https://arxiv.org/pdf/2004.09603v1",
        "retrieved_at": datetime.fromtimestamp(pdf.stat().st_mtime, TZ).isoformat(),
        "timestamp_basis": "local file modification time; the original live request receipt was not saved",
        "status": "downloaded",
        "version_note": "2020 preprint; not the inaccessible 2021 PNAS final version",
        "pages": len(PdfReader(pdf).pages),
        "sha256": sha(pdf),
        "path": "papers/" + pdf.name,
    })
write(papers, records)
for row in records:
    if row["status"] == "downloaded":
        assert sha(TASK / "research" / row["path"]) == row["sha256"]

paths = [
    "agent/agent/orchestrator.py", "agent/MultimodalAnalyzer/text_tower.py",
    "agent/Conclusion/calib/gates.py", "agent/KnowledgeAugmentor/store.py",
    "multiagent/contract.py", "multiagent/align.py", "multiagent/fuse.py", "multiagent/master.py",
    "social_forecast/models/rep_moe.py", "social_forecast/layers/rep_fusion.py",
    "social_forecast/layers/Mamba_block.py", "social_forecast/layers/jump_pelt.py",
    "social_forecast/scripts/verify_forecast_checkpoint.py",
    "social_forecast/scripts/export_numeric_checkpoint.py",
    "social_forecast/results/retrain_20261019/deployment_verification.json",
    "frontend/src/archives-api.ts", "frontend/src/archive-loop.ts",
    "backend/app/routes/archives.py", "backend/data/archives.snapshot.json",
]
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
diff = subprocess.check_output(["git", "diff", "--", *paths], cwd=REPO)
write(TASK / "evidence/code_snapshot.json", {
    "captured_at": NOW, "git_head": head,
    "tracked_diff_sha256": hashlib.sha256(diff).hexdigest(),
    "tracked_diff_bytes": len(diff),
    "files": [{"path": p, "bytes": (REPO/p).stat().st_size, "sha256": sha(REPO/p)} for p in paths],
    "note": "Snapshot of reviewed files; this artifact task did not edit these application files.",
})

v = json.loads((REPO / paths[14]).read_text(encoding="utf-8"))
m = v["numeric_holdout_metrics"]
c = m["confusion"]
assert sum(c.values()) == 262
assert abs(c["tp"]/(c["tp"]+c["fn"]) - m["saved_validation_threshold_recall"]) < 1e-12
assert abs(c["tp"]/(c["tp"]+c["fp"]) - m["saved_validation_threshold_precision"]) < 1e-12
assert v["protocol"]["rows"]["all"] == sum(v["protocol"]["rows"][k] for k in ["train", "validation", "test"])

# Use the real fusion implementation for a transparent, tiny diagnostic input.
# Load just the two pure computation modules, not multiagent's LLM entry points.
package_name = "_midterm_fusion_check"
package = types.ModuleType(package_name)
package.__path__ = [str(REPO / "multiagent")]
sys.modules[package_name] = package
for leaf in ("contract", "fuse"):
    spec = importlib.util.spec_from_file_location(package_name + "." + leaf, REPO / "multiagent" / (leaf + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
fuse = module.fuse
aligned = {
    "platforms": ["diagnostic_a", "diagnostic_b"], "time_axis": ["t1", "t2"],
    "aligned_ts": {},
    "z_series": {"diagnostic_a": {"volume": [-1.0, 1.0]},
                 "diagnostic_b": {"volume": [1.0, -1.0]}},
}
reports = [
    {"platform": "diagnostic_a", "stance_dist": {"support": 1.0}, "meta": {"sentiment_global_mean": 1.0}},
    {"platform": "diagnostic_b", "stance_dist": {"oppose": 1.0}, "meta": {"sentiment_global_mean": -1.0}},
]
fused = fuse(aligned, reports)
assert fused["echo_chamber_score"] == 1.3
write(TASK / "evidence/metric_consistency.json", {
    "checked_at": NOW, "kind": "stored-result arithmetic and synthetic diagnostic, not model retraining",
    "confusion_total": sum(c.values()), "metric_arithmetic": "passed",
    "mse_relative_increase_percent": (m["standardized_mse"]/m["persist_standardized_mse"]-1)*100,
    "numeric_kib": v["artifacts"]["numeric_checkpoint"]["bytes"]/1024,
    "full_mib": v["artifacts"]["full_checkpoint"]["bytes"]/1024**2,
    "fusion_synthetic_input": {"aligned": aligned, "reports": reports},
    "fusion_synthetic_output": fused,
    "interpretation": "A reproducible negative-correlation counterexample to the [0,1] comment, not a real social-media measurement.",
})

source_checks = []
for row in json.loads((TASK / "sources/manifest.json").read_text(encoding="utf-8")):
    original, local = Path(row["original"]), TASK/"sources"/row["file"]
    match = sha(original) == sha(local) == row["sha256"]
    assert match
    source_checks.append({"file": row["file"], "original_and_copy_unchanged": match})

export = args.pptx.resolve()
out = TASK / "deliverables"
targets = [
    (export, out / "SocialSense_中期答辩_6分钟主讲_含问答备份.pptx"),
    (args.deck_pdf, out / "SocialSense_中期答辩_6分钟主讲_含问答备份.pdf"),
    (args.report_pdf, out / "2026年度中期汇报表_SocialSense_修订稿.pdf"),
]
for src, dst in targets:
    shutil.copy2(src, dst)

ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main", "p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
visible = []
with ZipFile(export) as z, ZipFile(TASK/"presentation/sources/source.pptx") as src:
    slide_parts = [n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
    note_parts = [n for n in z.namelist() if n.startswith("ppt/notesSlides/notesSlide") and n.endswith(".xml")]
    chart_parts = [n for n in z.namelist() if n.startswith("ppt/charts/chart") and n.endswith(".xml")]
    table_count = 0
    for i in range(1, 19):
        e = etree.fromstring(z.read(f"ppt/slides/slide{i}.xml"))
        visible.append("\n".join(e.xpath("//a:t/text()", namespaces=ns)))
        table_count += len(e.findall(".//a:tbl", ns))
        assert not e.xpath('//p:transition/@advTm', namespaces=ns)
    preserved = [n for n in src.namelist() if n.startswith(("ppt/slideMasters/", "ppt/slideLayouts/")) and n.endswith(".xml")]
    all_preserved = all(z.read(n) == src.read(n) for n in preserved)
    assert all_preserved
    assert len(slide_parts) == len(note_parts) == 18
    assert len(chart_parts) == 1 and table_count == 2
    text = "\n".join(visible)
    for obsolete in ["知旅", "2025-11-19", "LLM2Trip", "2000并发"]:
        assert obsolete not in text
    assert "SocialSense" in text and "65.53%" in text and "树杨" in text
    props = etree.fromstring(z.read("ppt/presProps.xml"))
    assert props.find("p:showPr",ns).get("useTimings") == "0"

assert len(PdfReader(targets[1][1]).pages) == 18
assert len(PdfReader(targets[2][1]).pages) == 7
assert json.loads((TASK/"evidence/notes_timing.json").read_text())["sum_seconds"] == 360
write(TASK / "evidence/final_verification.json", {
    "checked_at": NOW, "source_checks": source_checks,
    "slide_count": 18, "speaker_note_count": 18, "native_charts": 1, "native_tables": 2,
    "master_layout_xml_byte_identical": all_preserved,
    "obsolete_template_text_check": "passed", "main_timing_seconds": 360,
    "deck_pdf_pages": 18, "report_pdf_pages": 7,
    "automatic_advance_slides": 0, "use_timings": False,
    "status": "passed", "qa_document": "QA_REPORT.md",
})
write(TASK / "evidence/deliverable_manifest.json", {
    "created_at": NOW,
    "files": [{"path": f.relative_to(TASK).as_posix(), "bytes": f.stat().st_size, "sha256": sha(f)}
              for f in sorted(out.iterdir()) if f.is_file()],
})
print("Checked original sources, stored metrics, 18 slides/notes, 1 chart, 2 tables, and PDF pagination.")
print("All master/layout XML is byte-identical to the source template.")
for src, dst in targets:
    print(dst.name, dst.stat().st_size)
