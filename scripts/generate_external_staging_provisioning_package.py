#!/usr/bin/env python3
"""Phase 3.9.12 —— 生成确定性供给算子包（Tasks 24-27）。

运行 validator + Operator Gate，产出
``.ai/staging/external_staging_provisioning_operator_package.json``。

确定性：相同事实 → 相同 SHA-256（via package.build_provisioning_package）。
fail-closed：任何校验失败即非零退出。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agents.external_staging_provisioning.dry_run_guard import IacDryRunGuard
from agents.external_staging_provisioning.gate import (
    ExternalStagingProvisioningOperatorGate,
)
from agents.external_staging_provisioning.bom import ProvisioningBom
from agents.external_staging_provisioning.package import build_provisioning_package
from agents.external_staging_qualification.models import (
    ExternalStagingEnvironmentIdentity,
)


def _git_head() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT)
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def main() -> int:
    commit = _git_head()
    identity = ExternalStagingEnvironmentIdentity(
        organization_id="ext-staging-org",
        domain_reference="staging.example.com",
        deployment_target_reference="ext-staging-deployment_target",
        database_reference="ext-staging-database",
        idp_reference="ext-staging-identity_provider",
        storage_reference="ext-staging-object_storage",
        telemetry_reference="ext-staging-telemetry",
        alert_reference="ext-staging-alert_sandbox",
    )
    bom = ProvisioningBom.build_default()

    # IaC 干跑
    iac = IacDryRunGuard().evaluate()
    iac_summary = iac.to_dict()

    # 适配器契约测试摘要
    from agents.external_staging_execution.adapters import (
        adapters_contract_test_all_pass,
        probe_all,
    )

    probe_results = probe_all()
    adapter_summary = {
        "total": len(probe_results),
        "all_honest_pending": all(r.is_honest() for r in probe_results),
        "contract_test_passed": adapters_contract_test_all_pass(),
    }

    # Operator Gate（human_input_required=True → PENDING_HUMAN_INPUT）
    gate = ExternalStagingProvisioningOperatorGate().evaluate(
        bom=bom,
        environment_identity=identity.to_dict(),
        iac_dry_run_ok=iac.all_ok,
        adapter_contract_ok=adapter_summary["contract_test_passed"],
        engineering_enabled=False,
        human_input_required=True,
    )

    pkg = build_provisioning_package(
        source_commit=commit,
        environment_identity=identity,
        bom=bom,
        gate=gate,
        iac_dry_run_summary=iac_summary,
        adapter_contract_summary=adapter_summary,
        baseline_commit=commit,
        package_generated_from_commit=commit,
    )

    out = REPO_ROOT / ".ai" / "staging" / "external_staging_provisioning_operator_package.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(pkg, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    print(f"[OK] wrote {out}")
    print(
        f"     phase={pkg['phase']} terminal_state={pkg['terminal_state']} "
        f"operator_gate={gate.status.value} hash={pkg['package_hash'][:16]}..."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
