"""Phase 3.9.12 —— Operator Gate（独立 3 态闸门，Task 18）。

汇总检查（fail-closed），状态**仅** 3 态（与 3.9.10/3.9.11 的 4 态 GateStatus 正交，
禁 GO / APPROVED / PRODUCTION_READY）：

- ``BLOCKED``
- ``PENDING_HUMAN_INPUT``
- ``READY_FOR_HUMAN_PROVISIONING_REVIEW``

裁决：任一 block 级失败 → BLOCKED；等待真人输入/授权 → PENDING_HUMAN_INPUT；
**绝不**越级至 READY/GO。READY_FOR_HUMAN_PROVISIONING_REVIEW 仅为「就绪待真人评审」，
不含任何「已通过/可上线」语义。

复用（治理 复用纪律）：
- ``agents.external_staging_qualification.gate``：GateCheck / CredentialLeakError /
  assert_no_credential_leak。
- ``agents.external_staging_qualification.credential_scanner``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.external_staging_qualification.credential_scanner import (
    assert_no_credential_leak,
    CredentialLeakError,
)
from agents.external_staging_qualification.gate import GateCheck
from agents.external_staging_qualification.models import (
    ExternalStagingEnvironmentIdentity,
)

from agents.external_staging_provisioning.bom import ProvisioningBom
from agents.external_staging_provisioning.models import (
    ExternalStagingProvisioningError,
    OperatorGateStatus,
)


@dataclass
class OperatorGateResult:
    """Operator 闸门评估结果（独立 3 态）。"""

    status: OperatorGateStatus
    checks: tuple[GateCheck, ...] = field(default_factory=tuple)
    evidence_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            # 3 态中无「GO/APPROVED」语义；passed 仅表示「非 BLOCKED」。
            "passed": self.status is not OperatorGateStatus.BLOCKED,
            "is_ready_for_human_review": self.status
            is OperatorGateStatus.READY_FOR_HUMAN_PROVISIONING_REVIEW,
            "checks": [c.to_dict() for c in self.checks],
            "evidence_hash": self.evidence_hash,
        }


class ExternalStagingProvisioningOperatorGate:
    """外部预生产供给算子闸门（fail-closed 评估器，独立 3 态）。"""

    def evaluate(
        self,
        *,
        bom: ProvisioningBom | None = None,
        environment_identity: dict[str, Any] | None = None,
        iac_dry_run_ok: bool = True,
        adapter_contract_ok: bool = True,
        engineering_enabled: bool = False,
        security_ok: bool = True,
        regression_ok: bool = True,
        repo_clean: bool = True,
        additional_pending_inputs: tuple[str, ...] = (),
        human_input_required: bool = True,
    ) -> OperatorGateResult:
        checks: list[GateCheck] = []

        # 1) BOM 完整性（8 资源）
        bom_ok = bom is not None and len(bom.entries) == 8
        checks.append(
            GateCheck(
                "provisioning_bom_complete",
                bom_ok,
                "block",
                f"供给 BOM 资源数={len(bom.entries) if bom else 0}（应为 8）。",
            )
        )

        # 2) BOM 全部诚实 PENDING
        if bom is not None:
            all_pending = bom.all_pending()
            checks.append(
                GateCheck(
                    "bom_all_pending",
                    all_pending,
                    "block",
                    "8 资源全部诚实 PENDING（Track B 待真人）。"
                    if all_pending
                    else "存在非 PENDING 资源（Track B 必须全 PENDING）。",
                )
            )

        # 3) 凭据引用安全（扫描 BOM 引用 + 环境身份，不忽略泄漏）
        if bom is not None:
            try:
                ref_map = {
                    e.resource_id: {
                        "iac_module": e.iac_module or "",
                        "default_provider_service": e.default_provider_service or "",
                    }
                    for e in bom.entries
                }
                if environment_identity:
                    ref_map["__identity__"] = {
                        k: (v or "")
                        for k, v in environment_identity.items()
                        if k not in ("production",)
                    }
                assert_no_credential_leak(mapping=ref_map)
                cred_ok = True
                cred_detail = "供给 BOM / 环境身份无明文凭据泄漏。"
            except CredentialLeakError as exc:
                cred_ok = False
                cred_detail = str(exc)
            checks.append(
                GateCheck("credential_reference_safety", cred_ok, "block", cred_detail)
            )

        # 4) IaC 干跑校验通过
        checks.append(
            GateCheck(
                "iac_dry_run",
                iac_dry_run_ok,
                "block",
                "IaC 干跑校验通过（无明文/占位齐备/默认 provider 合规）。"
                if iac_dry_run_ok
                else "IaC 干跑校验失败（见 Dry-run Guard）。",
            )
        )

        # 5) 适配器契约测试通过
        checks.append(
            GateCheck(
                "adapter_contract_tests",
                adapter_contract_ok,
                "block",
                "8 资源 Adapter 契约测试全通过（诚实 PENDING）。"
                if adapter_contract_ok
                else "Adapter 契约测试未全通过。",
            )
        )

        # 6) 环境身份 production=false
        prod_false = (
            environment_identity.get("production") is False
            if environment_identity
            else False
        )
        checks.append(
            GateCheck(
                "environment_not_production",
                prod_false,
                "block",
                "环境身份 production=false。" if prod_false else "环境身份 production=true（红线）。",
            )
        )

        # 7) engineering_enabled=false（最高红线）
        checks.append(
            GateCheck(
                "engineering_enabled_false",
                engineering_enabled is False,
                "block",
                "engineering_enabled=false（最高红线守约）。"
                if engineering_enabled is False
                else "engineering_enabled=true（红线违例）。",
            )
        )

        # 8) 安全 / 回归 / 仓库清洁
        checks.append(
            GateCheck("security", security_ok, "block", "安全扫描通过。" if security_ok else "安全扫描失败。")
        )
        checks.append(
            GateCheck("full_regression", regression_ok, "block", "全量回归 0 failed。" if regression_ok else "全量回归存在失败。")
        )
        checks.append(
            GateCheck("repository_clean", repo_clean, "block", "工作树清洁。" if repo_clean else "工作树不清洁。")
        )

        status = self._decide(
            checks, additional_pending_inputs, human_input_required
        )
        return OperatorGateResult(status=status, checks=tuple(checks))

    @staticmethod
    def _decide(
        checks: list[GateCheck],
        additional_pending_inputs: tuple[str, ...],
        human_input_required: bool,
    ) -> OperatorGateStatus:
        if any(not c.passed and c.severity == "block" for c in checks):
            return OperatorGateStatus.BLOCKED
        pending_due_to_inputs = bool(additional_pending_inputs) or human_input_required
        if pending_due_to_inputs:
            return OperatorGateStatus.PENDING_HUMAN_INPUT
        return OperatorGateStatus.READY_FOR_HUMAN_PROVISIONING_REVIEW


__all__ = [
    "OperatorGateResult",
    "ExternalStagingProvisioningOperatorGate",
]
