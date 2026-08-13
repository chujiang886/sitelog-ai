#!/usr/bin/env python3
"""Repository Cleanliness / Ownership Gate (Phase 3.9.4-R2, fail-closed).

Verifies the working tree is clean: no uncommitted source, tests, SSOT, reports,
or source-unknown files. `git status --porcelain` already excludes git-ignored
files, so any untracked/modified line here is a real cleanliness violation.

Red lines honoured: no deploy, no data write, read-only git inspection.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    out = subprocess.check_output(
        ["git", "status", "--porcelain"], text=True, cwd=ROOT
    )
    lines = [ln for ln in out.splitlines() if ln.strip()]
    if lines:
        print("[FAIL] working tree not clean:", file=sys.stderr)
        for ln in lines:
            print(f"   {ln}", file=sys.stderr)
        return 1
    print("[ok] working tree clean (no uncommitted / untracked / source-unknown files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
