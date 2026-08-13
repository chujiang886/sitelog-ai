#!/usr/bin/env python3
"""AuditActionCategory provenance validator (Phase 3.9.4-R2).

Reads the machine-readable SSOT ledger (.ai/baselines/audit_action_category_ledger.json)
produced by scripts/build_audit_category_ledger.py and verifies, fail-closed:

  1. Ledger.total == len(AuditActionCategory)
  2. union(Ledger phases' members) == set(AuditActionCategory)
  3. no orphan   (enum member not in ledger)
  4. no ghost    (ledger member not in enum)
  5. no duplicate ownership (a member must belong to exactly ONE introduction phase)
  6. every phase's `commit` exists in Git history
  7. the members introduced at each phase commit (re-extracted from Git) equal the
     ledger's recorded members for that phase (real provenance, not prose)

Additionally (R2-5) it verifies the human-readable Markdown mirror's phase/commit/total
table is consistent with the JSON SSOT.

No member set is hard-coded here (that was the R1 design flaw). The ONLY facts this
script knows are: the ledger file path, the audit.py path, and the Markdown path.
All member facts come from Git (via the build script) and the live enum.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / ".ai/baselines/audit_action_category_ledger.json"
MD_PATH = ROOT / ".ai/AUDIT_ACTION_CATEGORY_LEDGER.md"
AUDIT_PATH = "agents/enterprise/audit.py"

_FAIL = 1


def git_extract(commit: str) -> set[str] | None:
    """Extract AuditActionCategory member names from audit.py at <commit>. None if missing."""
    try:
        out = subprocess.check_output(
            ["git", "show", f"{commit}:{AUDIT_PATH}"], text=True
        )
    except subprocess.CalledProcessError:
        return None
    lines = out.splitlines()
    in_class = False
    members: set[str] = set()
    for ln in lines:
        if re.match(r"^class AuditActionCategory\b", ln):
            in_class = True
            continue
        if in_class and re.match(r"^class [A-Z]", ln):
            break
        if in_class:
            m = re.match(r"^    ([A-Z][A-Z0-9_]+) = ", ln)
            if m:
                members.add(m.group(1))
    return members


def fail(msg: str) -> int:
    print(f"[FAIL] {msg}", file=sys.stderr)
    return _FAIL


def load_ledger() -> dict:
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def check_markdown_consistency(ledger: dict) -> int:
    """R2-5: Markdown phase/commit/total table must match JSON SSOT."""
    if not MD_PATH.exists():
        return fail(f"Markdown mirror missing: {MD_PATH}")
    text = MD_PATH.read_text(encoding="utf-8")
    # total
    if f"总数 = **{ledger['total']}**" not in text:
        return fail(
            f"Markdown total does not match ledger total ({ledger['total']})"
        )
    # phase/commit rows in the §2 table
    rows = re.findall(
        r"^\|\s*([0-9.]+)\s*\|\s*`([0-9a-f]+)`\s*\|", text, flags=re.M
    )
    md_phases = {phase: commit for phase, commit in rows}
    for phase, info in ledger["phases"].items():
        if md_phases.get(phase) != info["commit"]:
            return fail(
                f"Markdown phase {phase} commit {md_phases.get(phase)} "
                f"!= ledger commit {info['commit']}"
            )
    # every ledger phase must appear in Markdown
    missing = [p for p in ledger["phases"] if p not in md_phases]
    if missing:
        return fail(f"Markdown missing phases: {missing}")
    print(f"[ok]   Markdown mirror consistent with JSON ({len(md_phases)} phases)")
    return 0


def main() -> int:
    ledger = load_ledger()
    total = ledger["total"]

    # import live enum (current code / CI working tree)
    try:
        sys.path.insert(0, str(ROOT))
        from agents.enterprise.audit import AuditActionCategory
    except Exception as exc:  # noqa: BLE001
        return fail(f"cannot import AuditActionCategory: {exc}")
    actual = {m.name for m in AuditActionCategory}

    # 1) total
    if len(actual) != total:
        return fail(f"enum total {len(actual)} != ledger total {total}")
    print(f"[info] enum total = {len(actual)}")

    # build ledger union + ownership map
    union: set[str] = set()
    ownership: Counter[str] = Counter()
    for phase, info in ledger["phases"].items():
        for m in info["members"]:
            union.add(m)
            ownership[m] += 1

    # 2) union == enum
    if union != actual:
        orphan = sorted(actual - union)
        ghost = sorted(union - actual)
        return fail(
            f"ledger union != enum; orphan={orphan}; ghost={ghost}"
        )

    # 3/4 detailed
    orphan = actual - union
    ghost = union - actual
    if orphan:
        return fail(f"orphan members (in enum, not in ledger): {sorted(orphan)}")
    if ghost:
        return fail(f"ghost members (in ledger, not in enum): {sorted(ghost)}")

    # 5) duplicate ownership
    dups = [m for m, n in ownership.items() if n > 1]
    if dups:
        return fail(f"duplicate-owned members (belong to >1 phase): {sorted(dups)}")

    # 6) each phase commit exists
    for phase, info in ledger["phases"].items():
        try:
            subprocess.check_call(
                ["git", "cat-file", "-e", f"{info['commit']}^{{commit}}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            return fail(f"phase {phase} commit {info['commit']} not found in Git")

    # 7) re-extract introduced members from each phase commit == ledger
    cumulative: set[str] = set()
    for phase, info in ledger["phases"].items():
        commit = info["commit"]
        at_commit = git_extract(commit)
        if at_commit is None:
            return fail(f"phase {phase}: cannot read audit.py at {commit}")
        expected = set(at_commit) if info["is_baseline"] else (set(at_commit) - cumulative)
        recorded = set(info["members"])
        if recorded != expected:
            miss = sorted(expected - recorded)
            extra = sorted(recorded - expected)
            return fail(
                f"phase {phase}: extracted-introduced != ledger; "
                f"missing_in_ledger={miss}; extra_in_ledger={extra}"
            )
        cumulative |= recorded
        print(
            f"[ok]   {phase:7s} (+{info['introduced_count']:<2d}) "
            f"total_at_commit={info['total_at_commit']}"
        )

    # R2-5 Markdown consistency
    rc = check_markdown_consistency(ledger)
    if rc:
        return rc

    print(
        f"[PASS] AuditActionCategory total={total}; 0 orphan / 0 ghost / "
        f"0 duplicate-ownership; Git provenance verified for all {len(ledger['phases'])} phases."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
