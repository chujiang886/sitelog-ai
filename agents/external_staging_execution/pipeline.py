"""Phase 3.9.11 —— 执行编排器（Tasks 15-24）。

``ExecutionPipeline`` 编排执行计划（plan-only / contract-test / 待真实资源）。

fail-closed：
- **不**真实部署 / 回滚 / 连接真实资源；
- 仅生成计划、运行契约模拟、登记 pending；
- 证据链只含 plan/contract/pending，无真实执行证据。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any

from agents.external_staging_execution.adapters import probe_all
from agents.external_staging_execution.evidence import (
    ExecutionEvidenceChain,
    ExecutionEvidenceItem,
)
from agents.external_staging_execution.models import (
    build_default_execution_plan,
    ExecutionPlan,
)


class ExecutionPipeline:
    """执行编排器（无真实执行）。"""

    def __init__(
        self,
        *,
        environment_identity: dict[str, Any] | None = None,
        actor: str = "AI_CHIEF_ARCHITECT",
    ) -> None:
        self.environment_identity = environment_identity or {
            "environment": "external_staging",
            "production": False,
        }
        self.actor = actor

    def execute_plan(self) -> ExecutionPlan:
        """编排执行计划（无真实执行）。"""

        return build_default_execution_plan()

    def run_evidence_chain(self) -> ExecutionEvidenceChain:
        """采集证据链（plan/contract/pending，无真实执行证据）。"""

        chain = ExecutionEvidenceChain()
        _ = _dt.datetime.now(_dt.timezone.utc).isoformat()

        chain.add(
            ExecutionEvidenceItem(
                evidence_id="ev-exec-preflight",
                step_kind="preflight",
                evidence_type="contract_test",
                environment="external_staging",
                actor=self.actor,
                verification_status="pending_external_staging_resource",
                detail="Preflight contract-test passed (plan-only safety); no real execution.",
            )
        )
        chain.add(
            ExecutionEvidenceItem(
                evidence_id="ev-exec-deploy-plan",
                step_kind="deploy",
                evidence_type="plan_only",
                environment="external_staging",
                actor=self.actor,
                verification_status="pending_external_staging_resource",
                detail="Deployment plan generated (plan-only); not deployed.",
            )
        )

        # 8 资源 pending 证据（诚实）
        for r in probe_all():
            chain.add(
                ExecutionEvidenceItem(
                    evidence_id=f"ev-exec-{r.resource_type}",
                    step_kind="e2e",
                    evidence_type="pending",
                    environment="external_staging",
                    actor=self.actor,
                    verification_status="pending_external_staging_resource",
                    detail=r.detail,
                )
            )

        chain.add(
            ExecutionEvidenceItem(
                evidence_id="ev-exec-failure",
                step_kind="failure",
                evidence_type="contract_test",
                environment="external_staging",
                actor=self.actor,
                verification_status="pending_external_staging_resource",
                detail="Failure injection contract-test (fake adapter); no real fault.",
            )
        )
        chain.add(
            ExecutionEvidenceItem(
                evidence_id="ev-exec-recovery",
                step_kind="recovery",
                evidence_type="contract_test",
                environment="external_staging",
                actor=self.actor,
                verification_status="pending_external_staging_resource",
                detail="Recovery drill contract-test (fake adapter); no real recovery.",
            )
        )
        chain.add(
            ExecutionEvidenceItem(
                evidence_id="ev-exec-rollback-plan",
                step_kind="rollback",
                evidence_type="plan_only",
                environment="external_staging",
                actor=self.actor,
                verification_status="pending_external_staging_resource",
                detail="Rollback plan generated (plan-only); not executed.",
            )
        )
        return chain


__all__ = ["ExecutionPipeline"]
