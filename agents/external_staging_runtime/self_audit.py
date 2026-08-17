"""Phase 3.9.14 —— fail-closed 不变量自审（self_audit，T39）。

程序化校验全部 fail-closed 不变量：
- ``engineering_enabled=False`` / ``real_apply_allowed=False`` / ``is_production=False``；
- 7 层结论无 production 泄漏、变更管控永不 GO/APPROVED；
- API 契约仅读、禁变更；
- 确定性执行包可重建并校验（篡改即变）；
- 凭据深扫无明文密钥。

返回结构化 ``SelfAuditReport``；任一违例即 ``passed=False``（fail-closed，不静默降级）。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from agents.external_staging_runtime.api_contract import EXTERNAL_RUNTIME_API_CONTRACT
from agents.external_staging_runtime.change_control import TERMINAL_STATE
from agents.external_staging_runtime.machine_package import (
    build_machine_package,
    validate_package,
)


@dataclass
class SelfAuditCheck:
    """单条自审检查。"""

    name: str
    passed: bool
    detail: str


@dataclass
class SelfAuditReport:
    """自审结论（结构化，机器可读）。"""

    passed: bool
    terminal_state: str
    package_hash: str
    checks: tuple[SelfAuditCheck, ...]
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _chk(name: str, fn) -> SelfAuditCheck:
    """运行单条检查；捕获一切异常为失败（fail-closed，不掩盖）。"""

    try:
        ok, detail = fn()
        return SelfAuditCheck(name=name, passed=bool(ok), detail=str(detail))
    except Exception as e:  # noqa: BLE001
        return SelfAuditCheck(name=name, passed=False, detail=f"{type(e).__name__}: {e}")


def run_self_audit() -> SelfAuditReport:
    """运行全部 fail-closed 不变量自审。"""

    checks: list[SelfAuditCheck] = []

    # 1. 确定性执行包构建 + validate（含逐层红线 + 凭据深扫）
    def _machine_package() -> tuple[bool, str]:
        pkg = build_machine_package()
        validate_package(pkg)  # 失败即抛 AssertionError
        return True, f"hash={pkg['package_hash'][:16]}…, deterministic={pkg['deterministic']}"

    checks.append(_chk("machine_package_fail_closed", _machine_package))

    # 2. API 契约仅读、禁变更
    def _contract() -> tuple[bool, str]:
        c = EXTERNAL_RUNTIME_API_CONTRACT
        ok = (
            c["real_execution_allowed"] is False
            and c["real_apply_allowed"] is False
            and c["is_production"] is False
            and c["engineering_enabled"] is False
            and all(not e.get("mutates") for e in c["endpoints"])
            and len(c["forbidden"]) > 0
        )
        return ok, f"endpoints={len(c['endpoints'])}, forbidden={len(c['forbidden'])}"

    checks.append(_chk("api_contract_readonly", _contract))

    # 3. 变更管控：永不 GO/APPROVED/PRODUCTION_READY（is_go_or_approved 恒 False）
    def _change_control() -> tuple[bool, str]:
        from agents.external_staging_runtime.change_control import evaluate_change_control

        v = evaluate_change_control()
        ok = (
            v.is_production is False
            and v.real_apply_allowed is False
            and v.is_go_or_approved is False
            and v.terminal_state == TERMINAL_STATE
        )
        return ok, f"apply_gate_state={v.apply_gate_state.value}"

    checks.append(_chk("change_control_never_go", _change_control))

    # 4. 隔离：无 production 泄漏
    def _isolation() -> tuple[bool, str]:
        from agents.external_staging_runtime.isolation import ExternalStagingIsolationAuditor

        r = ExternalStagingIsolationAuditor().audit_all()
        return (r.passed and not r.production_leakage and r.real_resources_present == 0), (
            f"domains={len(r.domains)}, leakage={r.production_leakage}"
        )

    checks.append(_chk("isolation_no_production_leakage", _isolation))

    # 5. 资格：13 项 code-verified、0 运行时执行
    def _qualification() -> tuple[bool, str]:
        from agents.external_staging_runtime.qualification import RuntimeQualificationHarness

        r = RuntimeQualificationHarness().qualify_all()
        ok = (
            r.is_production is False
            and r.real_apply_allowed is False
            and r.code_verified_count == r.total
            and r.runtime_executed_count == 0
        )
        return ok, f"code_verified={r.code_verified_count}/{r.total}"

    checks.append(_chk("qualification_structural_only", _qualification))

    # 6. 故障恢复：production 回滚永远禁止
    def _recovery() -> tuple[bool, str]:
        from agents.external_staging_runtime.failure_recovery import FailureRecoveryRollbackPlan

        r = FailureRecoveryRollbackPlan().build()
        return (r.production_rollback_forbidden and not r.is_production and not r.real_apply_allowed), (
            f"allowed_local={r.allowed_local_steps}"
        )

    checks.append(_chk("production_rollback_forbidden", _recovery))

    # 7. 证据：无 production 泄漏、零违例
    def _evidence() -> tuple[bool, str]:
        from agents.external_staging_runtime.evidence import build_phase3914_evidence

        m = build_phase3914_evidence()
        return (not m.has_production_leakage() and len(m.violations()) == 0), (
            f"items={len(m.items)}, violations={len(m.violations())}"
        )

    checks.append(_chk("evidence_no_leakage", _evidence))

    passed = all(c.passed for c in checks)
    # 取包哈希（machine_package 检查若失败则回退空串）
    pkg_hash = ""
    try:
        pkg_hash = build_machine_package()["package_hash"]
    except Exception:  # noqa: BLE001
        pass

    return SelfAuditReport(
        passed=passed,
        terminal_state=TERMINAL_STATE,
        package_hash=pkg_hash,
        checks=tuple(checks),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


__all__ = ["SelfAuditCheck", "SelfAuditReport", "run_self_audit"]
