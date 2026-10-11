"""主张 ledger 的共享常量与底层读写（`_load_jsonl` / `_sha12`）。"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


CALIBRATION_PATH = ROOT / "evals" / "datasets" / "demo" / "calibration_30.jsonl"


SIGNATURES_PATH = ROOT / "evals" / "claims" / "r1b_signatures.json"


EFFECT_PLAN_PATH = ROOT / "docs" / "EFFECT_PLAN.md"


_ORPHAN_SCAN_DOCS = ("docs/EXPERIMENTS.md", "docs/README.md", "README.md", "CLAUDE.md")


_ORPHAN_RE = re.compile(r"(应为空|逐位相同|全绿|一致|通过率|达线|不达线|\d+\.\d{3})")


_SOURCED_RE = re.compile(r"(证据：|复现：|`[a-z_]+ [\w\-./]+`|ledger\.md#)")


_PROV_KEYS = (
    "code_version",
    "golden_sha256",
    "script",
    "argv",
    "model_refs",
    "sampling",
    "experiment_config_hash",
    "dependency_lock_hash",
)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _sha12(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
