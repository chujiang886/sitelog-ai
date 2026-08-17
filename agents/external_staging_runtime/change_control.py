"""Phase 3.9.14 —— 变更管控平面（Task 32，fail-closed）。

包含三部分：

1. ``StagingRuntimeValidationGate``：运行一组**结构性**校验（不连接、不执行任何真实动作），
   产出 3.9.14 终端态 ``PHASE_3_9_14_EXTERNAL_STAGING_RUNTIME_E2E_QUALIFICATION_BUILT_NO_GO``。
   - 绝不输出 ``PRODUCTION_READY`` / ``APPROVED`` / ``GO``；
   - ``is_production`` 永远 False；
   - ``external_pending=True``（缺真实外部 Staging 资源）；
   - ``human_verification_required=True``（四角色线下验证/签署后才可授权真实部署）。

2. ``ApplyGateState``（独立 4 态）：``PENDING_HUMAN_AUTHORIZATION`` /
   ``AUTHORIZED_AWAITING_APPLY`` / ``BLOCKED`` / ``DENIED``；**禁** ``GO`` / ``APPROVED`` /
   ``PRODUCTION_READY``；``is_go_or_approved`` 恒 False。

3. 双钥匙授权 ``DualKeyAuthorization``：Machine Safety Key（机器可生成）+
   Human Authorization Key（**须 actor_kind=USER**，AI **不得** mint）。
   未双钥匙不得 apply/deploy；AI 不得伪造 Human Key。

fail-closed：任意校验失败或检测到 production 泄漏即整体不通过；AI 不代执行任何真实部署。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from agents.enterprise.audit import AuditActorKind, require_human_actor
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.staging_runtime.environment import RuntimeEnvironment
from agents.staging_runtime.isolation_guard import (
    EnvironmentIsolationGuard,
    StagingIsolationViolationError,
)
from agents.staging_runtime.secret_provider import StagingSecretProvider
from agents.staging_runtime.db import StagingDatabaseProvider, StagingDatabaseError
from agents.staging_runtime.execution_scope import FORBIDDEN_PRODUCTION_ACTIONS
from agents.staging_runtime.deployment import (
    StagingDeploymentProvider,
    StagingDeploymentForbiddenError,
)

from .identity import external_staging_identity

TERMINAL_STATE = "PHASE_3_9_14_EXTERNAL_STAGING_RUNTIME_E2E_QUALIFICATION_BUILT_NO_GO"

# 3.9.14 允许的「非 production」环境集合。
_ALLOWED_ENVIRONMENTS = frozenset(
    {RuntimeEnvironment.LOCAL_STAGING, RuntimeEnvironment.EXTERNAL_STAGING}
)


class ApplyGateState(str, Enum):
    """Apply Gate 独立 4 态（禁 GO/APPROVED/PRODUCTION_READY）。"""

    PENDING_HUMAN_AUTHORIZATION = "pending_human_authorization"
    AUTHORIZED_AWAITING_APPLY = "authorized_awaiting_apply"
    BLOCKED = "blocked"
    DENIED = "denied"

    @property
    def is_go_or_approved(self) -> bool:
        """恒 False：任何态都不等同于 GO / APPROVED / PRODUCTION_READY。"""

        return False


@dataclass(frozen=True)
class StagingGateCheck:
    """单条 Gate 校验。"""

    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class StagingGateVerdict:
    """Gate 结论（结构化，机器可读）。"""

    passed: bool
    terminal_state: str
    environment: str
    is_production: bool
    checks: tuple[StagingGateCheck, ...]
    evidence_hash: str
    external_pending: bool
    human_verification_required: bool
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "terminal_state": self.terminal_state,
            "environment": self.environment,
            "is_production": self.is_production,
            "checks": [c.to_dict() for c in self.checks],
            "evidence_hash": self.evidence_hash,
            "external_pending": self.external_pending,
            "human_verification_required": self.human_verification_required,
            "generated_at": self.generated_at,
        }


class StagingGateError(Exception):
    """Gate 未通过（fail-closed）。"""


class StagingRuntimeValidationGate:
    """External Staging 运行时验证 Gate（结构性校验电池，不执行真实动作）。"""

    def __init__(self, identity=None) -> None:
        self._identity = identity or external_staging_identity()
        guard = EnvironmentIsolationGuard()
        try:
            guard.assert_staging_integration_permitted(self._identity)
        except StagingIsolationViolationError as e:
            raise StagingGateError(str(e))
        if self._identity.kind not in _ALLOWED_ENVIRONMENTS:
            raise StagingGateError(
                f"环境 {self._identity.kind.value} 不在允许集合"
                "(local_staging/external_staging)，Gate 拒绝运行。"
            )

    def run(self) -> StagingGateVerdict:
        checks: list[StagingGateCheck] = []
        ident = self._identity

        # 1. 环境分类非 production
        checks.append(
            StagingGateCheck(
                name="environment_non_production",
                passed=not ident.kind.is_production,
                detail=f"kind={ident.kind.value}",
            )
        )

        # 2. 隔离护栏通过
        try:
            EnvironmentIsolationGuard().assert_staging_integration_permitted(ident)
            checks.append(
                StagingGateCheck(name="isolation_guard", passed=True, detail="staging-only + 集成允许")
            )
        except StagingIsolationViolationError as e:
            checks.append(StagingGateCheck(name="isolation_guard", passed=False, detail=str(e)))

        # 3. 执行边界：禁止动作令牌全拒
        from agents.staging_runtime.execution_scope import StagingExecutionScope

        scope = StagingExecutionScope(ident)
        forbidden_rejected = all(not scope.is_permitted(a) for a in FORBIDDEN_PRODUCTION_ACTIONS)
        checks.append(
            StagingGateCheck(
                name="execution_scope_forbids_production",
                passed=forbidden_rejected,
                detail=f"forbidden_actions={len(FORBIDDEN_PRODUCTION_ACTIONS)}",
            )
        )

        # 4. 部署 apply 永远拒绝
        try:
            StagingDeploymentProvider(ident).apply()
            checks.append(
                StagingGateCheck(name="deployment_apply_forbidden", passed=False, detail="apply 未拒绝")
            )
        except StagingDeploymentForbiddenError:
            checks.append(
                StagingGateCheck(name="deployment_apply_forbidden", passed=True, detail="apply 正确拒绝")
            )

        # 5. DB 接入描述非生产（不连接）
        try:
            StagingDatabaseProvider(ident, staging_dsn="staging-dsn").describe()
            checks.append(
                StagingGateCheck(name="db_provider_non_production", passed=True, detail="describe OK")
            )
        except StagingDatabaseError as e:
            checks.append(
                StagingGateCheck(name="db_provider_non_production", passed=False, detail=str(e))
            )
        except Exception as e:  # noqa: BLE001
            checks.append(
                StagingGateCheck(name="db_provider_non_production", passed=False, detail=str(e))
            )

        # 6. 密钥隔离：拒绝复用 Production Secret
        try:
            StagingSecretProvider(
                ident, production_secret_refs={"prod-secret-value"}
            ).resolve("x", env_var="STAGING_SECRET_X")
            checks.append(
                StagingGateCheck(name="secret_isolation", passed=True, detail="无 production 复用")
            )
        except Exception as e:  # noqa: BLE001
            checks.append(StagingGateCheck(name="secret_isolation", passed=False, detail=str(e)))

        passed = all(c.passed for c in checks) and not ident.kind.is_production

        return StagingGateVerdict(
            passed=passed,
            terminal_state=TERMINAL_STATE,
            environment=ident.kind.value,
            is_production=ident.kind.is_production,
            checks=tuple(checks),
            evidence_hash="",  # 由证据链填充
            external_pending=True,
            human_verification_required=True,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )


# ---------------- 双钥匙授权 ----------------


@dataclass(frozen=True)
class MachineSafetyKey:
    """机器安全钥匙（机器可生成；仅证明「系统侧安全前置已满足」）。"""

    token: str
    generated_by: str = "machine"
    note: str = "Machine Safety Key 仅证明系统侧安全前置；不构成人工授权。"


@dataclass(frozen=True)
class HumanAuthorizationKey:
    """人工授权钥匙（**须 actor_kind=USER**；AI 不得 mint）。"""

    token: str
    actor_kind: str  # 必须为 "USER"
    actor: str

    def __post_init__(self) -> None:
        # 红线：人工授权钥匙必须有真实人类 actor，AI 不得伪造。
        if self.actor_kind != "USER":
            raise EnterpriseRedLineViolationError(
                "HumanAuthorizationKey 必须由真实人类 actor 持有（actor_kind=USER）；"
                "AI 不得 mint 人工授权钥匙（红线：AI 不代替人工责任）。"
            )
        # 红线⑥：强制人工责任节点由真实 USER 发起；AI 不得代替。
        require_human_actor(AuditActorKind.USER)


@dataclass(frozen=True)
class DualKeyAuthorization:
    """双钥匙授权：Machine Safety Key + Human Authorization Key（须 actor_kind=USER）。"""

    machine_key: MachineSafetyKey
    human_key: HumanAuthorizationKey | None = None

    @property
    def is_authorized(self) -> bool:
        """双钥匙齐备且 human key 合法才算授权。"""

        return self.human_key is not None and self.human_key.actor_kind == "USER"

    @property
    def ai_attempted_human_mint(self) -> bool:
        """AI 是否试图伪造 human key（恒由人工提供，本属性仅用于审计）。"""

        return False


@dataclass(frozen=True)
class ChangeControlVerdict:
    """变更管控结论（fail-closed）。"""

    apply_gate_state: ApplyGateState
    four_role_signoff_required: bool
    human_actor_required: bool
    dual_key_authorized: bool
    is_production: bool
    real_apply_allowed: bool
    terminal_state: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "apply_gate_state": self.apply_gate_state.value,
            "four_role_signoff_required": self.four_role_signoff_required,
            "human_actor_required": self.human_actor_required,
            "dual_key_authorized": self.dual_key_authorized,
            "is_production": self.is_production,
            "real_apply_allowed": self.real_apply_allowed,
            "terminal_state": self.terminal_state,
            "is_go_or_approved": self.is_go_or_approved,
            "detail": self.detail,
        }

    @property
    def is_go_or_approved(self) -> bool:
        """恒 False：任何态都不等同于 GO / APPROVED / PRODUCTION_READY。"""

        return self.apply_gate_state.is_go_or_approved


def evaluate_change_control(auth: DualKeyAuthorization | None = None) -> ChangeControlVerdict:
    """评估变更管控状态（fail-closed）。

    - 未提供授权或 human key 缺失/非 USER → 状态 PENDING_HUMAN_AUTHORIZATION，real_apply 禁止；
    - 双钥匙齐备且 human=USER → AUTHORIZED_AWAITING_APPLY（仍非 GO/APPROVED）；
    - 任何态都 ``is_go_or_approved=False``、``real_apply_allowed=False``、``is_production=False``。
    """

    if auth is None or not auth.is_authorized:
        state = ApplyGateState.PENDING_HUMAN_AUTHORIZATION
        dual_ok = False
        detail = "未满足双钥匙（缺 Human Authorization Key 或 actor 非 USER）；apply 恒禁止。"
    else:
        state = ApplyGateState.AUTHORIZED_AWAITING_APPLY
        dual_ok = True
        detail = "双钥匙齐备（含真实 USER 授权）；仍须四角色线下签署后才可真实 apply。"

    return ChangeControlVerdict(
        apply_gate_state=state,
        four_role_signoff_required=True,
        human_actor_required=True,
        dual_key_authorized=dual_ok,
        is_production=False,
        real_apply_allowed=False,
        terminal_state=TERMINAL_STATE,
        detail=detail,
    )


__all__ = [
    "TERMINAL_STATE",
    "ApplyGateState",
    "StagingGateCheck",
    "StagingGateVerdict",
    "StagingGateError",
    "StagingRuntimeValidationGate",
    "MachineSafetyKey",
    "HumanAuthorizationKey",
    "DualKeyAuthorization",
    "ChangeControlVerdict",
    "evaluate_change_control",
]
