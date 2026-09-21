"""Canonical 12-domain code ↔ Chinese name mapping for dataset tools."""
from __future__ import annotations

import json
from pathlib import Path

_DOMAIN_JSON = Path(__file__).resolve().parents[1] / "dataset" / "domains.json"
DOMAIN_NAMES: dict[str, str] = json.loads(_DOMAIN_JSON.read_text(encoding="utf-8"))
DOMAIN_ZH_TO_CODE: dict[str, str] = {zh: code for code, zh in DOMAIN_NAMES.items()}
