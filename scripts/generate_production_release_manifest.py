#!/usr/bin/env python3
"""Phase 3.9.2 生产发布产物 SHA-256 manifest 生成器。

只读扫描 Commit A 的交付产物，计算 SHA-256，并记录生成时刻的 git HEAD（= Commit A）。
输出 JSON manifest（Commit B 内容）。本脚本不写入任何生产事实、不部署、不改 engineering_enabled。

用法：
    backend/.venv/bin/python scripts/generate_production_release_manifest.py --root .
    # 输出：.ai/reviews/phase3.9.2_production_release_manifest.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Commit A 交付产物清单（相对仓库根）。缺项标记 "<missing>"，不抛错。
DELIVERABLES: list[str] = [
    # 包源码
    "agents/enterprise/production_release/__init__.py",
    "agents/enterprise/production_release/forbidden.py",
    "agents/enterprise/production_release/models.py",
    "agents/enterprise/production_release/evidence.py",
    "agents/enterprise/production_release/gate.py",
    "agents/enterprise/production_release/package.py",
    "agents/enterprise/production_release/service.py",
    # 后端接线
    "backend/app/api/governance_release.py",
    # 测试
    "tests/agents/test_production_release_gate_evidence.py",
    # Runbooks
    ".ai/runbooks/production_release/controlled_activation.md",
    ".ai/runbooks/production_release/rollback.md",
    ".ai/runbooks/production_release/disaster_recovery_drill.md",
    # 收口报告
    ".ai/reviews/phase3.9.2_production_release_gate_evidence_package_report.md",
    # SSOT / 基线
    ".ai/project_status.json",
    ".ai/baselines/phase3.8_governance_release_baseline.json",
    # 本生成器自身
    "scripts/generate_production_release_manifest.py",
]

MANIFEST_PATH = ".ai/reviews/phase3.9.2_production_release_manifest.json"
MISSING = "<missing>"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _git_head(root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:  # pragma: no cover - 环境异常
        return MISSING


def build_manifest(root: Path) -> dict:
    entries: dict[str, str] = {}
    missing = 0
    for rel in DELIVERABLES:
        p = root / rel
        if p.is_file():
            entries[rel] = _sha256(p)
        else:
            entries[rel] = MISSING
            missing += 1
    return {
        "phase": "3.9.2",
        "layer": "Enterprise Production Release Gate & Evidence Package Layer",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commit_a_head": _git_head(root),
        "tool": "scripts/generate_production_release_manifest.py",
        "total_count": len(DELIVERABLES),
        "missing_count": missing,
        "entries": entries,
        "note": (
            "manifest 仅描述 Commit A 交付产物的哈希与 HEAD；不包含真实密钥、真实权限、"
            "真实激活。真实生产部署与 engineering_enabled 开启只能源于人类终端。"
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate Phase 3.9.2 production release manifest")
    ap.add_argument("--root", default=".", help="BOIP repository root")
    ap.add_argument("--out", default=MANIFEST_PATH, help="output manifest path (relative to root)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    manifest = build_manifest(root)
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[manifest] wrote {out}")
    print(f"[manifest] commit_a_head={manifest['commit_a_head']}")
    print(f"[manifest] total={manifest['total_count']} missing={manifest['missing_count']}")
    if manifest["missing_count"]:
        print("[manifest] WARNING: some deliverables are missing (<missing>):")
        for rel, v in manifest["entries"].items():
            if v == MISSING:
                print(f"  - {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
