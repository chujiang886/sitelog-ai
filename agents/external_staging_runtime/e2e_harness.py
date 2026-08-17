"""Phase 3.9.14 —— End-to-End 资格编排 harness（Task 30，fail-closed）。

``EndToEndQualificationHarness`` 把前面各层（九项隔离 / 13 项资格 / Runtime Health /
变更管控 Gate / 证据链）编排成一条**端到端计划**，每一步的产出都是结构性结论，绝不发起
任何真实外部调用、绝不真实部署/迁移/激活。

编排顺序（plan-only）：
1. 环境分类（external_staging，非生产）
2. 九项隔离审计（结构化隔离成立）
3. 13 项运行时资格（结构性安全证明）
4. Runtime Health（健康形态，外部资源 PENDING）
5. 变更管控 Gate（3.9.14 终端态，human_verification_required）
6. 证据链（确定性哈希链）

全程断言 fail-closed 不变量：``is_production=False`` / ``real_apply_allowed=False`` /
``terminal_state=3.9.14 BUILT_NO_GO``。真实 E2E 运行（连真实外部资源跑通）属于 Track B，
须真人供给资源 + 四角色签署 + 双钥匙授权后才执行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .change_control import TERMINAL_STATE, StagingRuntimeValidationGate
from .evidence import build_phase3914_evidence
from .identity import external_staging_identity
from .isolation import ExternalStagingIsolationAuditor
from .qualification import RuntimeQualificationHarness
from .runtime_health import RuntimeHealthHarness


@dataclass(frozen=True)
class E2EStep:
    """E2E 单步（plan-only，结构化产出）。"""

    order: int
    name: str
    status: str  # PLAN_ONLY_STRUCTURAL_OK | BLOCKED
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"order": self.order, "name": self.name, "status": self.status, "detail": self.detail}


@dataclass
class EndToEndQualificationPlan:
    """E2E 资格计划（结构化，机器可读）。"""

    passed: bool
    terminal_state: str
    is_production: bool
    real_apply_allowed: bool
    evidence_hash: str
    steps: tuple[E2EStep, ...] = field(default_factory=tuple)
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "terminal_state": self.terminal_state,
            "is_production": self.is_production,
            "real_apply_allowed": self.real_apply_allowed,
            "evidence_hash": self.evidence_hash,
            "steps": [s.to_dict() for s in self.steps],
            "generated_at": self.generated_at,
        }


class EndToEndQualificationHarness:
    """External Staging E2E 资格编排（fail-closed，plan-only）。"""

    def __init__(self, identity=None) -> None:
        self._identity = identity or external_staging_identity()

    def build_plan(self) -> EndToEndQualificationPlan:
        steps: list[E2EStep] = []
        ok = True

        # 1. 环境分类
        steps.append(
            E2EStep(
                order=1,
                name="environment_classification",
                status="PLAN_ONLY_STRUCTURAL_OK",
                detail="external_staging 身份已构造，非生产、已验证非生产。",
            )
        )

        # 2. 九项隔离审计
        iso = ExternalStagingIsolationAuditor().audit_all()
        if not iso.passed:
            ok = False
        steps.append(
            E2EStep(
                order=2,
                name="nine_domain_isolation_audit",
                status="PLAN_ONLY_STRUCTURAL_OK" if iso.passed else "BLOCKED",
                detail=f"九项隔离域={len(iso.domains)}，production_leakage={iso.production_leakage}。",
            )
        )

        # 3. 13 项运行时资格
        qual = RuntimeQualificationHarness(self._identity).qualify_all()
        if not qual.passed:
            ok = False
        steps.append(
            E2EStep(
                order=3,
                name="thirteen_runtime_qualification",
                status="PLAN_ONLY_STRUCTURAL_OK" if qual.passed else "BLOCKED",
                detail=f"code_verified={qual.code_verified_count}/{qual.total}，"
                f"runtime_executed={qual.runtime_executed_count}。",
            )
        )

        # 4. Runtime Health
        health = RuntimeHealthHarness(self._identity).assess()
        if not health.passed:
            ok = False
        steps.append(
            E2EStep(
                order=4,
                name="runtime_health",
                status="PLAN_ONLY_STRUCTURAL_OK" if health.passed else "BLOCKED",
                detail=f"structural_health={health.structural_health_count}，"
                f"external_pending={health.external_resources_health_pending}。",
            )
        )

        # 5. 变更管控 Gate
        gate = StagingRuntimeValidationGate(self._identity).run()
        if not gate.passed:
            ok = False
        steps.append(
            E2EStep(
                order=5,
                name="change_control_gate",
                status="PLAN_ONLY_STRUCTURAL_OK" if gate.passed else "BLOCKED",
                detail=f"terminal_state={gate.terminal_state}，"
                f"human_verification_required={gate.human_verification_required}。",
            )
        )

        # 6. 证据链（确定性哈希）
        evidence = build_phase3914_evidence(self._identity)
        steps.append(
            E2EStep(
                order=6,
                name="evidence_chain",
                status="PLAN_ONLY_STRUCTURAL_OK",
                detail=f"integrity_hash={evidence.integrity_hash()[:16]}…，"
                f"production_leakage={evidence.has_production_leakage()}。",
            )
        )

        # 终态不变量断言（fail-closed）
        invariant_ok = (
            self._identity.kind.is_production is False
            and gate.terminal_state == TERMINAL_STATE
            and gate.is_production is False
            and evidence.has_production_leakage() is False
        )
        passed = ok and invariant_ok

        return EndToEndQualificationPlan(
            passed=passed,
            terminal_state=TERMINAL_STATE,
            is_production=self._identity.kind.is_production,
            real_apply_allowed=False,
            evidence_hash=evidence.integrity_hash(),
            steps=tuple(steps),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )


__all__ = [
    "E2EStep",
    "EndToEndQualificationPlan",
    "EndToEndQualificationHarness",
]
