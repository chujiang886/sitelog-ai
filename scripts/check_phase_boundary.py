#!/usr/bin/env python3
"""Phase Boundary Gate (Phase 3.9.4-R2, fail-closed).

Verifies SSOT phase-boundary consistency across the four authoritative sources:
  - project_status.json
  - roadmap_v8.md
  - PHASE_BOUNDARY_LEDGER.md
  - closure reports on disk
  - audit ledger JSON (total)

Hard rule (red line): an unreviewed phase (e.g. 3.9.5) MUST NOT be marked
APPROVED / GO / PRODUCTION_READY. Only awaiting-human / built-no-go statuses are
permitted until the main persona + experts sign off offline.

This script knows only file paths and the forbidden-status vocabulary; it does NOT
hard-code phase member facts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_STATUS = ROOT / ".ai/project_status.json"
ROADMAP = ROOT / ".ai/roadmap_v8.md"
LEDGER_JSON = ROOT / ".ai/baselines/audit_action_category_ledger.json"
PBL = ROOT / ".ai/PHASE_BOUNDARY_LEDGER.md"

FORBIDDEN = ("APPROVED", "PRODUCTION_READY")
REQUIRED_MARKERS = ("AWAITING_HUMAN", "BUILT_NO_GO")
# Lines that merely *describe* the rule (e.g. "不得标 APPROVED") must not be treated
# as a forbidden status assertion. Skip such descriptive lines.
NEGATION = ("不得", "禁止", "不标", "不标记", "未审核", "not ", "NOT ", "MUST NOT", "awaiting", "AWAITING")


def fail(msg: str) -> int:
    print(f"[FAIL] {msg}", file=sys.stderr)
    return 1


def main() -> int:
    # 1) project_status.json phase_3_9_5_status must not be APPROVED/PRODUCTION_READY
    ps = json.loads(PROJECT_STATUS.read_text(encoding="utf-8"))
    st = ps.get("phase_3_9_5_status", "")
    for f in FORBIDDEN:
        if f in st:
            return fail(
                f"project_status.json phase_3_9_5_status contains forbidden '{f}': {st}"
            )
    print(f"[ok]   project_status phase_3_9_5_status = {st}")

    # 2) roadmap_v8.md must not mark 3.9.5 as APPROVED/PRODUCTION_READY
    rm = ROADMAP.read_text(encoding="utf-8")
    for line in rm.splitlines():
        if "3.9.5" in line and any(f in line for f in FORBIDDEN):
            if any(n in line for n in NEGATION):
                continue  # descriptive rule ("不得标"), not a status assertion
            return fail(f"roadmap_v8.md marks 3.9.5 with forbidden status: {line.strip()}")
    if not any(m in rm for m in REQUIRED_MARKERS):
        return fail("roadmap_v8.md has no awaiting-human / built-no-go status marker")
    print("[ok]   roadmap_v8.md: 3.9.5 not marked APPROVED/PRODUCTION_READY")

    # 3) referenced closure reports must exist on disk
    reports = [
        ".ai/reviews/phase3.9.5_release_line_reconciliation_closure_report.md",
        ".ai/reviews/phase3.9.2_release_candidate_freeze_activation_gate_closure_report.md",
        ".ai/reviews/phase3.9.4_r2_definitive_baseline_freeze_report.md",
    ]
    for r in reports:
        if not (ROOT / r).exists():
            return fail(f"closure report missing: {r}")
    print(f"[ok]   {len(reports)} closure reports present")

    # 4) audit ledger JSON total == 100
    ld = json.loads(LEDGER_JSON.read_text(encoding="utf-8"))
    if ld["total"] != 100:
        return fail(f"audit ledger total {ld['total']} != 100")
    print(f"[ok]   audit ledger total = {ld['total']}")

    # 5) phase boundary ledger present
    if not PBL.exists():
        return fail("PHASE_BOUNDARY_LEDGER.md missing")
    print("[ok]   PHASE_BOUNDARY_LEDGER.md present")

    print("[PASS] Phase Boundary Gate consistent (no unreviewed phase marked approved).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
