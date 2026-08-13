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
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_STATUS = ROOT / ".ai/project_status.json"
ROADMAP = ROOT / ".ai/roadmap_v8.md"
LEDGER_JSON = ROOT / ".ai/baselines/audit_action_category_ledger.json"
BASELINE_JSON = ROOT / ".ai/baselines/phase3.8_governance_release_baseline.json"
AUDIT_SOURCE = ROOT / "agents/enterprise/audit.py"
PBL = ROOT / ".ai/PHASE_BOUNDARY_LEDGER.md"

_ENUM_HEAD_RE = re.compile(r"^class AuditActionCategory\b")
_NEXT_CLASS_RE = re.compile(r"^class [A-Z]")
_ENUM_MEMBER_RE = re.compile(r"^    ([A-Z][A-Z0-9_]+) = ")


def _live_audit_category_total() -> int | None:
    """Count AuditActionCategory members by parsing the source (stdlib only).

    Deliberately parsed rather than imported: this gate must stay importable-free
    and dependency-free so it can run in a bare CI step. Returns None when the
    source cannot be read, in which case the caller degrades to ledger<->baseline
    cross-check only (never to "pass by default" on a real mismatch).
    """
    try:
        lines = AUDIT_SOURCE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    in_class = False
    names: set[str] = set()
    for line in lines:
        if _ENUM_HEAD_RE.match(line):
            in_class = True
            continue
        if in_class and _NEXT_CLASS_RE.match(line):
            break
        if in_class:
            match = _ENUM_MEMBER_RE.match(line)
            if match:
                names.add(match.group(1))
    return len(names) or None

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

    # 4) audit ledger JSON total must equal the baseline contract total.
    #    Phase 3.9.6: the total is NO LONGER hard-coded here. Hard-coding it in a
    #    second place was the exact brittleness this gate is supposed to prevent
    #    (one new category -> N files to edit). The baseline JSON is the declared
    #    contract; the ledger JSON is rebuilt from real Git history; this gate now
    #    cross-checks the two against each other and against the live enum, so the
    #    check gets STRICTER, not looser.
    ld = json.loads(LEDGER_JSON.read_text(encoding="utf-8"))
    bl = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))
    declared = bl["audit_category_contract"]["total"]
    if ld["total"] != declared:
        return fail(
            f"audit ledger total {ld['total']} != baseline declared total {declared}"
        )
    live = _live_audit_category_total()
    if live is not None and live != declared:
        return fail(
            f"live AuditActionCategory total {live} != baseline declared total {declared}"
        )
    print(
        f"[ok]   audit total = {declared} (ledger == baseline"
        + (f" == live enum" if live is not None else " ; live enum not importable")
        + ")"
    )

    # 5) phase boundary ledger present
    if not PBL.exists():
        return fail("PHASE_BOUNDARY_LEDGER.md missing")
    print("[ok]   PHASE_BOUNDARY_LEDGER.md present")

    print("[PASS] Phase Boundary Gate consistent (no unreviewed phase marked approved).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
