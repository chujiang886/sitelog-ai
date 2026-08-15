#!/usr/bin/env python3
"""Phase 3.9.11 —— 生成确定性执行包（Tasks 27-28）。

输出 ``.ai/staging/external_staging_execution_qualification_package.json``：
- 复用 3.9.10 资格层身份（production=false）/ 8 资源登记簿（全 PENDING）；
- 执行计划（plan-only / contract-test / pending）；
- 证据链（plan/contract/pending，无真实执行证据）；
- 闸门（PENDING_EXTERNAL_STAGING_RESOURCE，无 GO）；
- 确定性 SHA-256（相同事实 → 相同哈希）。

commit 语义：``baseline_commit``=Phase 3.9.10-R1 冻结 base；``source_commit``/
``evidence_source_commit``/``package_generated_from_commit``=当前 3.9.11 HEAD。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agents.external_staging_execution.config import load_external_staging_identity
from agents.external_staging_execution.gate import ExternalStagingExecutionGate
from agents.external_staging_execution.models import build_default_execution_plan
from agents.external_staging_execution.package import build_execution_package
from agents.external_staging_execution.pipeline import ExecutionPipeline
from agents.external_staging_qualification.models import (
    ExternalStagingResourceRegistry,
)

PHASE_BASE = "2f4a9838bcfc7105bc561f74fb2658906801e011"
OUT = REPO_ROOT / ".ai" / "staging" / "external_staging_execution_qualification_package.json"


def _git_head() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-commit", default=None)
    args = ap.parse_args()

    src = args.source_commit or _git_head()
    ident = load_external_staging_identity()
    registry = ExternalStagingResourceRegistry.build_default()
    plan = build_default_execution_plan()
    pipe = ExecutionPipeline()
    chain = pipe.run_evidence_chain()
    pending_resources = tuple(r.resource_id for r in registry.resources)

    gate = ExternalStagingExecutionGate().evaluate(
        plan=plan,
        evidence_chain=chain,
        environment_identity=ident.to_dict(),
        registry=registry,
        additional_pending_resources=pending_resources,
        human_verification_required=True,
    )

    pkg = build_execution_package(
        source_commit=src,
        environment_identity=ident,
        plan=plan,
        evidence_chain=chain,
        gate=gate,
        pending_resources=pending_resources,
        human_pending=("external_resource_provisioning", "four_role_signoff"),
        baseline_commit=PHASE_BASE,
        evidence_source_commit=src,
        package_generated_from_commit=src,
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(pkg, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[OK] wrote {OUT}")
    print(f"[OK] phase={pkg['phase']} terminal_state={pkg['terminal_state']}")
    print(f"[OK] gate.status={pkg['gate']['status']} package_hash={pkg['package_hash']}")
    print(
        f"[OK] contains_real_secret={pkg['contains_real_secret']} "
        f"production_activation_prohibited={pkg['production_activation_prohibited']} "
        f"engineering_enabled={pkg['engineering_enabled']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
