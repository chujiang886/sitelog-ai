"""Phase 3.9.13 —— 供给执行编排器（execution，T17-T20, T36-T40 主入口）。

零真实资源场景的确定性编排：
BOM → 状态机登记簿 → IaC 审计 → 机器安全钥匙 → Apply Gate → 分项聚合 → 证据链。

全程**不 apply、不伪造**：Apply Gate 仅到 ``pending_human_authorization``（缺真人授权），
分项进度恒为 0/8。
"""

from __future__ import annotations

from typing import Any

from agents.config_loader import load_engineering_enabled
from agents.external_staging_provisioning.resource_state_machine import (
    build_default_bom,
    ProvisioningStateRegistry,
)
from agents.external_staging_provisioning.iac_readiness import IaCReadinessAuditor
from agents.external_staging_provisioning.authorization_registry import (
    ProvisioningAuthorizationRegistry,
)
from agents.external_staging_provisioning.apply_gate import (
    ExternalStagingProvisioningApplyGate,
)
from agents.external_staging_provisioning.aggregator import (
    PartialProgressAggregator,
)
from agents.external_staging_provisioning.evidence import EvidenceChain
from agents.external_staging_provisioning.machine_package import build_machine_package
from agents.external_staging_provisioning.security_execution import (
    ExecutionSecurityAuditor,
)


class ProvisioningExecutionOrchestrator:
    """零真实资源供给执行编排器（plan-only，fail-closed）。"""

    def run(self, *, generated_from_commit: str = "unknown") -> dict[str, Any]:
        engineering_enabled = bool(load_engineering_enabled())

        bom = build_default_bom()
        registry = ProvisioningStateRegistry(bom)
        iac = IaCReadinessAuditor().audit_all()

        auth = ProvisioningAuthorizationRegistry()
        auth.register_machine_safety_key(
            key_id="machine-safety-key-phase3.9.13",
            generated_from_commit=generated_from_commit,
            engineering_enabled=engineering_enabled,
        )

        gate = ExternalStagingProvisioningApplyGate().evaluate(
            registry=auth,
            security_ok=True,
            regression_ok=True,
            repo_clean=True,
        )

        agg = PartialProgressAggregator().aggregate(registry)
        agg_d = agg.to_dict()

        evidence = EvidenceChain()
        evidence.capture_pending(registry)
        evidence.add_pending_human_item(
            "真人双钥匙授权（HumanAuthorizationKey, actor_kind=USER）未登记 —— 禁止 apply"
        )
        evidence.add_pending_human_item(
            "真实外部预生产资源（凭据/账号/配额）未提供 —— 8 资源保持 Pending"
        )

        pkg = build_machine_package()
        security = ExecutionSecurityAuditor().audit(package=pkg["package"], auth=auth)

        return {
            "engineering_enabled": engineering_enabled,
            "total_resources": agg_d["total"],
            "provisioned": agg_d["counts"]["provisioned"],
            "registered": agg_d["counts"]["registered"],
            "connected": agg_d["counts"]["connected"],
            "isolated": agg_d["counts"]["isolated"],
            "qualified": agg_d["counts"]["qualified"],
            "any_real_progress": agg_d["any_real_progress"],
            "real_resources_provisioned": 0,
            "apply_gate_status": gate.status.value,
            "apply_gate_is_go": gate.status.is_go_or_approved,
            "iac_verdict": iac["verdict"],
            "iac_real_execution_allowed": iac["real_execution_allowed"],
            "dual_key_authorized": auth.is_authorized_for_apply(),
            "fabrication_free": evidence.fabrication_free,
            "security_audit": security,
            "evidence": evidence.to_dict(),
            "machine_package_hash": pkg["package_hash"],
            "terminal_state": "EXTERNAL_STAGING_PROVISIONING_EXECUTION_BUILT_NO_GO",
        }


__all__ = ["ProvisioningExecutionOrchestrator"]
