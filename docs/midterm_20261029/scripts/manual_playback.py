"""Use ppt-master's transition core to retain visual effects and disable timers."""
from pathlib import Path
from zipfile import ZipFile
import argparse
import json
import sys
from lxml import etree

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("input", type=Path)
parser.add_argument("output", type=Path)
parser.add_argument("--skill-dir", type=Path, default=Path("C:/Users/32002/.agents/skills/ppt-master"))
args = parser.parse_args()
assert args.input.resolve() != args.output.resolve(), "Keep the original native export intact"
sys.path.insert(0, str(args.skill_dir / "scripts"))
from pptx_transitions import (
    EnterUpdate, AdvanceUpdate, apply_slide_motion_xml,
    read_slide_transition_xml, set_package_use_timings,
)

with ZipFile(args.input) as z:
    entries = z.infolist()
    parts = {entry.filename: z.read(entry) for entry in entries}

ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
rows = []
for name in list(parts):
    if not (name.startswith("ppt/slides/slide") and name.endswith(".xml")):
        continue
    before_xml = parts[name].decode("utf-8")
    before = read_slide_transition_xml(before_xml)
    after_xml, uses = apply_slide_motion_xml(
        before_xml, enter=EnterUpdate(policy="preserve"), advance=AdvanceUpdate(mode="click")
    )
    after = read_slide_transition_xml(after_xml)
    assert not uses and after.advance_after_ms is None and after.advance_on_click is True
    assert before.canonical_effect == after.canonical_effect
    assert before.duration_ms == after.duration_ms and before.speed == after.speed
    # Verify shapes and all pre-existing object-animation markup are preserved.
    for tag in ("cSld", "timing"):
        b = etree.fromstring(before_xml.encode()).find("p:" + tag, ns)
        a = etree.fromstring(after_xml.encode()).find("p:" + tag, ns)
        assert (b is None) == (a is None)
        if b is not None:
            assert etree.tostring(b, method="c14n") == etree.tostring(a, method="c14n")
    parts[name] = after_xml.encode("utf-8")
    rows.append({"part": name, "effect": after.canonical_effect,
                 "before_advance_ms": before.advance_after_ms, "after_advance_ms": None,
                 "advance_on_click": True})

set_package_use_timings(parts, enabled=False)
args.output.parent.mkdir(exist_ok=True, parents=True)
with ZipFile(args.output, "w") as out:
    written = set()
    for entry in entries:
        out.writestr(entry, parts[entry.filename]);written.add(entry.filename)
    for name, data in parts.items():
        if name not in written:out.writestr(name, data)

task = Path(__file__).resolve().parents[1]
receipt = {"tool": "ppt-master.pptx_transitions", "policy": "enter=preserve; advance=click; useTimings=false",
           "input": str(args.input), "output": str(args.output), "slides": rows,
           "shape_and_object_timing_unchanged": True}
(task/"presentation/validation/manual_playback.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding="utf-8")
print("Retained all visual transitions and object animation; disabled automatic advance on",len(rows),"slides.")
print(args.output)
