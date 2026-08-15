"""Phase 3.9.12 —— Provisioning Validator（Task 19，fail-closed）。

组合校验外部预生产供给算子就绪层：

- 8 资源 BOM 全部诚实 PENDING（复用 qualification._FORBIDDEN_STATES / 无 GO/APPROVED）；
- IaC 干跑校验通过（复用 dry_run_guard）；
- 8 资源 Adapter 契约测试全通过（复用 execution.adapters）；
- Operator Gate 独立 3 态裁决（复用 gate.OperatorGateResult）。

提供 ``validate()`` 返回 ``OperatorGateResult``，以及 fail-closed 断言
``assert_operator_ready()``（供 CI / validate 脚本调用）。
"""

from __future__ import annotations

from typing import Any

from agents.external_staging_qualification.credential_scanner import (
    assert_no_credential_leak,
)
from agents.external_staging_qualification.models import _FORBIDDEN_STATES
from agents.external_staging_execution.adapters import (
    adapters_contract_test_all_pass,
    assert_no_real_execution_claimed,
    probe_all,
)

from agents.external_staging_provisioning.bom import (
    PENDING_STATUS,
    ProvisioningBom,
)
from agents.external_staging_provisioning.dry_run_guard import IacDryRunGuard
from agents.external_staging_provisioning.gate import (
    ExternalStagingProvisioningOperatorGate,
    OperatorGateResult,
)
from agents.external_staging_provisioning.models import (
    ExternalStagingProvisioningError,
    OperatorGateStatus,
)


class ExternalStagingProvisioningValidator:
    """外部预生产供给就绪验证器（fail-closed）。"""

    def __init__(self, iac_dir: str | None = None) -> None:
        self.iac_dir = iac_dir

    def validate(
        self,
        *,
        bom: ProvisioningBom | None = None,
        environment_identity: dict[str, Any] | None = None,
        engineering_enabled: bool = False,
        security_ok: bool = True,
        regression_ok: bool = True,
        repo_clean: bool = True,
        human_input_required: bool = True,
        run_iac_scan: bool = True,
    ) -> OperatorGateResult:
        """执行组合校验，返回 Operator Gate 3 态结果。"""

        if bom is None:
            bom = ProvisioningBom.build_default()

        # 1) BOM 完整性 + 全部 PENDING（fail-closed）
        bom.assert_all_pending()
        self._assert_no_forbidden_bom_status(bom)

        # 2) IaC 干跑校验（fail-closed，guard.evaluate 内部已含占位/凭据/provider 自检）
        iac_ok = True
        if run_iac_scan:
            guard = IacDryRunGuard(self.iac_dir)
            try:
                guard.evaluate()
            except ExternalStagingProvisioningError:
                iac_ok = False
                raise

        # 3) Adapter 契约测试（诚实 PENDING，无真实执行宣称）
        probe_results = probe_all()
        assert_no_real_execution_claimed(probe_results)
        adapter_ok = adapters_contract_test_all_pass()

        # 4) 凭据引用安全（BOM + 环境身份）
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
                if k != "production"
            }
        assert_no_credential_leak(mapping=ref_map)

        # 5) Operator Gate 裁决
        gate = ExternalStagingProvisioningOperatorGate()
        return gate.evaluate(
            bom=bom,
            environment_identity=environment_identity,
            iac_dry_run_ok=iac_ok,
            adapter_contract_ok=adapter_ok,
            engineering_enabled=engineering_enabled,
            security_ok=security_ok,
            regression_ok=regression_ok,
            repo_clean=repo_clean,
            human_input_required=human_input_required,
        )

    @staticmethod
    def _assert_no_forbidden_bom_status(bom: ProvisioningBom) -> None:
        for e in bom.entries:
            if e.status in _FORBIDDEN_STATES:
                raise ExternalStagingProvisioningError(
                    f"供给 BOM 资源 {e.resource_id} 状态 {e.status!r} 落入禁止态，拒绝。"
                )

    def assert_operator_ready(
        self,
        *,
        bom: ProvisioningBom | None = None,
        environment_identity: dict[str, Any] | None = None,
        engineering_enabled: bool = False,
    ) -> OperatorGateResult:
        """fail-closed 断言：算子就绪层处于合法就绪态。

        合法就绪态 = READY_FOR_HUMAN_PROVISIONING_REVIEW（**非** GO/APPROVED）。
        BLOCKED / PENDING_HUMAN_INPUT 均视为未就绪，抛错阻断。
        """

        result = self.validate(
            bom=bom,
            environment_identity=environment_identity,
            engineering_enabled=engineering_enabled,
        )
        if result.status is not OperatorGateStatus.READY_FOR_HUMAN_PROVISIONING_REVIEW:
            raise ExternalStagingProvisioningError(
                f"算子就绪层未达 READY_FOR_HUMAN_PROVISIONING_REVIEW，"
                f"当前={result.status.value}（BLOCKED/PENDING_HUMAN_INPUT 须先解决）。"
            )
        return result


__all__ = [
    "ExternalStagingProvisioningValidator",
]
