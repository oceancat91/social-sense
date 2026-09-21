"""Domain taxonomy must stay a single invertible map across agent and dataset tools."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.dataset.common import DOMAIN_NAMES as SCRIPT_DOMAIN_NAMES
from scripts.dataset.common import DOMAIN_ZH_TO_CODE as SCRIPT_DOMAIN_ZH_TO_CODE
from tools.domains import DOMAIN_NAMES, DOMAIN_ZH_TO_CODE

ROOT = Path(__file__).resolve().parents[1]


def test_domain_maps_are_inverses_and_shared():
    source = json.loads((ROOT / "agent" / "dataset" / "domains.json").read_text(encoding="utf-8"))
    assert source == DOMAIN_NAMES == SCRIPT_DOMAIN_NAMES
    assert DOMAIN_ZH_TO_CODE == {zh: code for code, zh in DOMAIN_NAMES.items()}
    assert SCRIPT_DOMAIN_ZH_TO_CODE == DOMAIN_ZH_TO_CODE
    assert set(DOMAIN_NAMES) == set(DOMAIN_ZH_TO_CODE.values())
