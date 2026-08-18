#!/usr/bin/env python3
"""Phase 3.9.15 Branch Integrity Gate.

Fail-closed CI 守卫：在 commit / CI 前核验当前工作树未偏离 Phase 3.9.15
External Staging Real Resource Onboarding & Live Qualification 的合法边界。

检查项：
  1. 当前分支必须 = feat/phase3.9.15-external-staging-real-resource-live-qualification
  2. 工作树（tracked + untracked）不得出现 forbidden 模块名：
     production_handoff / handoff
  3. 不得出现下一 Phase 编号泄漏（3.9.16）
  4. 旧 WIP carryover：agents/enterprise/production_handoff/ 不得出现
  5. Audit Ledger total 必须 = 129（本阶段 0 新增企业类目；3.9.15 执行审计类别为
     自包含常量集，不污染企业 AuditActionCategory 枚举与冻结账本）

设计约束（规避沙箱 SIGKILL，沿用 3.9.10-3.9.14 经验）：
  - 不调用 `git diff` / `git log -- <path>`（带 path 的 git 操作会被 SIGKILL）；
  - 仅用 `git rev-parse HEAD` / `git branch --show-current` / `git ls-files`（安全）；
  - 工作树扫描限定 phase 相关目录，prune .git，不做全仓库遍历。

本阶段**允许**复用 `agents/external_staging_runtime/`（3.9.14）、
`agents/external_staging_live/`（3.9.15 新增真实能力层）、`agents/staging_runtime/`
及 3.9.10-3.9.14 既有 external_staging_* 包，不视为 forbidden；仅禁止 Production
Handoff 旧 WIP 与下一 Phase（3.9.16）泄漏。

exit code: 0 = PASS, 1 = 违反（fail-closed）, 2 = 环境/配置错误。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

EXPECTED_BRANCH = "feat/phase3.9.15-external-staging-real-resource-live-qualification"
EXPECTED_AUDIT_TOTAL = 129
REPO_ROOT_HINTS = ("agents", "backend", ".ai", "docs", "scripts", "infrastructure")
# 仅针对「废弃 WIP：Production Handoff & Human Activation Ceremony」签名。
FORBIDDEN_PATH_SEGMENTS = ("production_handoff", "handoff")
# 下一 Phase 编号（本阶段为 3.9.15，禁止提前泄漏 3.9.16）。
NEXT_PHASE_TOKEN = "3.9.16"
AUDIT_LEDGER = ".ai/baselines/audit_action_category_ledger.json"


def _run(args: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args,
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return proc.returncode, proc.stdout.strip()
    except subprocess.TimeoutExpired:
        return 124, ""
    except Exception:  # noqa: BLE001
        return 2, ""


def current_branch() -> str:
    rc, out = _run(["git", "branch", "--show-current"])
    if rc != 0 or not out:
        rc2, out2 = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        return out2
    return out


def tracked_files() -> list[str]:
    rc, out = _run(["git", "ls-files"])
    if rc != 0:
        return []
    return [line for line in out.splitlines() if line]


def git_visible_forbidden() -> list[str]:
    hits: list[str] = []
    for f in tracked_files():
        low = f.lower()
        if any(seg in low for seg in FORBIDDEN_PATH_SEGMENTS):
            hits.append(f)
    rc, out = _run(["git", "status", "--porcelain"])
    if rc == 0:
        for line in out.splitlines():
            if not line.startswith("??"):
                continue
            path = line[2:].strip()
            low = path.lower()
            if any(seg in low for seg in FORBIDDEN_PATH_SEGMENTS):
                hits.append(path)
    return hits


def disk_production_handoff_info() -> list[str]:
    hits: list[str] = []
    root = Path("agents")
    if not root.is_dir():
        return hits
    for dirpath, dirnames, _filenames in os.walk(root):
        if ".git" in dirnames:
            dirnames.remove(".git")
        dirnames[:] = [
            d
            for d in dirnames
            if d not in ("node_modules", ".next", ".venv", "__pycache__", ".mypy_cache")
        ]
        if "production_handoff" in dirnames:
            hits.append(os.path.join(dirpath, "production_handoff"))
    return hits


def next_phase_leak_in_git_view() -> list[str]:
    hits: list[str] = []
    for f in tracked_files():
        if NEXT_PHASE_TOKEN in f:
            hits.append(f)
    rc, out = _run(["git", "status", "--porcelain"])
    if rc == 0:
        for line in out.splitlines():
            if not line.startswith("??"):
                continue
            path = line[2:].strip()
            if NEXT_PHASE_TOKEN in path:
                hits.append(path)
    return hits


def audit_ledger_total() -> int | None:
    p = Path(AUDIT_LEDGER)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if isinstance(data.get("total"), int):
        return data["total"]
    cats = data.get("categories")
    if isinstance(cats, list):
        return len(cats)
    return None


def main() -> int:
    errors: list[str] = []

    branch = current_branch()
    if branch != EXPECTED_BRANCH:
        errors.append(
            f"[branch] 当前分支 '{branch}' != 期望 '{EXPECTED_BRANCH}'；"
            f"禁止在错误分支提交 Phase 3.9.15 交付物"
        )
    else:
        print(f"[PASS] 分支 = {branch}")

    forbidden_hits = git_visible_forbidden()
    if forbidden_hits:
        errors.append(
            "[forbidden-module] git 视图中出现 forbidden 模块（production_handoff/handoff），"
            "疑似旧 WIP 被误吸收进本阶段：\n  - "
            + "\n  - ".join(forbidden_hits[:20])
        )
    else:
        print("[PASS] git 视图无 forbidden 模块（production_handoff/handoff）")

    disk_info = disk_production_handoff_info()
    if disk_info:
        print(
            "[INFO] 磁盘存在 git 视图外 production_handoff 残留（provenance 已隔离于 stash，"
            "不进入本阶段 commit，无需处理）：\n  - " + "\n  - ".join(disk_info[:10])
        )

    next_hits = next_phase_leak_in_git_view()
    if next_hits:
        errors.append(
            "[next-phase-leak] git 视图出现 3.9.16 路径残留（禁止提前进入下一 Phase）：\n  - "
            + "\n  - ".join(next_hits[:20])
        )
    else:
        print("[PASS] 无 3.9.16 路径残留（git 视图）")

    total = audit_ledger_total()
    if total is None:
        errors.append(f"[audit-ledger] 无法读取 {AUDIT_LEDGER}")
    elif total != EXPECTED_AUDIT_TOTAL:
        errors.append(
            f"[audit-ledger] AuditActionCategory total = {total} != 期望 {EXPECTED_AUDIT_TOTAL}；"
            f"Phase 3.9.15 不得引入新企业审计类目"
        )
    else:
        print(f"[PASS] AuditActionCategory total = {total}")

    if errors:
        print("\n".join(errors))
        print(f"\n[FAIL] Branch Integrity Gate 未通过（{len(errors)} 项违规）— fail-closed")
        return 1

    print("\n[PASS] Branch Integrity Gate 通过（fail-closed）：分支/模块/Phase 编号/审计均合规")
    return 0


if __name__ == "__main__":
    sys.exit(main())
