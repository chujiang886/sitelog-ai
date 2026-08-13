"""Backend FastAPI 路由：企业生产变更管控平面 API（Phase 3.9.7-change）。

暴露生产变更管控平面的**只读查看**与**真实人工登记**两类端点：

- GET  /governance/change/readiness
- GET  /governance/change/plan
- GET  /governance/change/window
- GET  /governance/change/preflight
- GET  /governance/change/checkpoint
- GET  /governance/change/abort-policy
- GET  /governance/change/rollback-reference
- GET  /governance/change/post-verification
- GET  /governance/change/evidence
- GET  /governance/change/simulation
- GET  /governance/change/failure-scenarios
- GET  /governance/change/package
- GET  /governance/change/decision-ledger
- POST /governance/change/plan                       （真实 USER + RELEASE_READ）
- POST /governance/change/window                      （真实 USER + RELEASE_READ）
- POST /governance/change/preflight                   （真实 USER + RELEASE_READ）
- POST /governance/change/checkpoint                  （真实 USER + RELEASE_READ）
- POST /governance/change/abort-policy                （真实 USER + RELEASE_READ）
- POST /governance/change/rollback-reference           （真实 USER + RELEASE_READ）
- POST /governance/change/post-verification           （真实 USER + RELEASE_READ）
- POST /governance/change/evidence                    （真实 USER + RELEASE_READ，只收引用）
- POST /governance/change/simulation                  （真实 USER + RELEASE_READ，synthetic）
- POST /governance/change/failure-scenarios           （真实 USER + RELEASE_READ，只读评估）
- POST /governance/change/package                     （真实 USER + RELEASE_READ，材料≠执行）
- POST /governance/change/signoff                     （真实 USER + RELEASE_SIGNOFF）
- POST /governance/change/decision                    （真实 USER + RELEASE_SIGNOFF，记录≠执行）

所有写操作均复用 ``require_change_operation`` 做 fail-closed 白名单门禁（AI / SYSTEM 主体
一律 403；未登记操作默认拒绝）。本路由**不持有**生产状态，不写密钥，不执行部署 / 变更 /
回滚 / 应用 / 迁移 / 激活。

**明确不提供** ``POST /governance/change/execute`` / ``/deploy`` / ``/rollback`` /
``/apply`` / ``/migrate`` / ``/activate``：真实生产变更只能由主理人在人类终端、四角色签署后
显式发起（红线①/③/⑩）。
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

# 让 backend/app 命名空间可解析 agents 企业包（与 governance_activation.py 一致）。
_BOIP_ROOT = Path(__file__).resolve().parents[3]
if str(_BOIP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOIP_ROOT))

from agents.config_loader import load_engineering_enabled  # noqa: E402
from agents.enterprise.audit import AuditActorKind, AuditService  # noqa: E402
from agents.enterprise.production_change import (  # noqa: E402
    ChangeOperation,
    ProductionChangeControlService,
    require_change_operation,
)
from agents.enterprise.production_change.models import (  # noqa: E402
    ChangeDecisionDraftStatus,
    ChangeExecutionMode,
    ChangePreflightStatus,
    ChangeRequest,
    ChangeSimulationOutcome,
    ChangeState,
    ChangeVerificationStatus,
)
from agents.enterprise.production_change.api_contract import build_api_contract  # noqa: E402
from agents.enterprise.production_change.validator import (  # noqa: E402
    check_change_control_invariants,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError  # noqa: E402

from app.core.csrf import csrf_protect  # noqa: E402
from app.identity import (  # noqa: E402
    GovernancePermission,
    GovernancePrincipal,
    require_governance_permission,
    require_same_org,
)

router = APIRouter(
    prefix="/governance/change",
    tags=["governance-change"],
    dependencies=[Depends(csrf_protect)],
)

OrgHeader = Annotated[Optional[str], Header(alias="org-id")]

DEFAULT_CHANGE_ID = "CHG-3.9.7"


def _ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _require_user_principal(principal: GovernancePrincipal) -> None:
    """AI / SYSTEM 主体一律拒绝（红线⑥/⑧）。"""

    if getattr(principal, "actor_kind", None) != "user":
        raise HTTPException(status_code=403, detail="仅真实 USER 责任人可操作生产变更管控")


def _org(principal: GovernancePrincipal, requested: Optional[str]) -> str:
    """组织标识以主体为准；客户端只能复述，不能指定（跨组织访问 403）。"""

    return require_same_org(principal, requested or "")


def _git_head() -> str:
    return (
        subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_BOIP_ROOT,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        or "unknown"
    )


def _actor_kind_str(principal: GovernancePrincipal) -> str:
    ak = getattr(principal, "actor_kind", None)
    if ak is None:
        return "unknown"
    return str(getattr(ak, "value", ak)).strip().lower() or "unknown"


def _granted_permissions(principal: GovernancePrincipal) -> List[str]:
    return [str(getattr(p, "value", p)) for p in getattr(principal, "permissions", ())]


def _enforce_change_operation(
    *, operation: "ChangeOperation", principal: GovernancePrincipal
) -> None:
    """fail-closed 权限边界（SSOT）：任何未登记 / 非 user / 缺权限的操作 403。"""

    try:
        require_change_operation(
            operation=operation,
            actor_kind=_actor_kind_str(principal),
            granted_permissions=_granted_permissions(principal),
        )
    except EnterpriseRedLineViolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


def _service(org_id: str) -> ProductionChangeControlService:
    return ProductionChangeControlService(
        org_id=org_id, audit=AuditService(org_id=org_id)
    )


# 进程内裁决登记簿（系统真相源始终是 AuditService append-only）。
_CHANGE_DECISIONS: dict[str, Dict[str, object]] = {}


# --------------------------------------------------------------------------- #
# 请求体                                                                       #
# --------------------------------------------------------------------------- #
class ChangePlanRequest(BaseModel):
    change_id: str
    plan_reference: str
    rollback_plan_reference: str
    steps: List[str] = []


class ChangeWindowRequest(BaseModel):
    change_id: str
    window_start: str
    window_end: str


class ChangePreflightRequest(BaseModel):
    change_id: str
    checks: Dict[str, bool] = {}
    missing: List[str] = []


class ChangeCheckpointRequest(BaseModel):
    change_id: str
    checkpoint_id: str
    note: str = ""


class ChangeAbortPolicyRequest(BaseModel):
    change_id: str
    auto_abort_conditions: List[str] = []


class ChangeRollbackReferenceRequest(BaseModel):
    change_id: str
    last_known_good_version: str
    last_known_good_commit: str
    database_revision: Optional[str] = None
    config_baseline: Optional[str] = None
    rollback_steps_reference: Optional[str] = None
    recovery_validation_reference: Optional[str] = None


class ChangePostVerificationRequest(BaseModel):
    change_id: str
    verification_id: str
    verification_type: str
    status: str = "pending_verification"
    verified_by: Optional[str] = None
    detail: str = ""


class ChangeEvidenceRequest(BaseModel):
    change_id: str
    evidence_id: str
    evidence_type: str
    source: str
    source_reference: str
    integrity_status: str = "pending"
    verification_status: str = "pending_verification"
    sha256: Optional[str] = None


class ChangeSimulationRequest(BaseModel):
    change_id: str
    simulation_id: str
    title: str = "synthetic-change"
    preflight_checks: Dict[str, bool] = {}
    abort_conditions_present: bool = False
    last_known_good_version: Optional[str] = None
    last_known_good_commit: Optional[str] = None


class ChangeFailureScenariosRequest(BaseModel):
    change_id: str
    scenarios: List[Dict[str, object]] = []


class ChangePackageRequest(BaseModel):
    change_id: str
    package_id: Optional[str] = None
    title: str = "synthetic-change"


class ChangeSignoffRequest(BaseModel):
    role: str  # production-owner | release-manager | security-owner | auditor
    decision: str  # go | no_go | need_more_evidence
    reason: str = ""
    signature_reference: str  # 线下签署文档 / 工单 / 归档审批坐标（必填）
    change_id: str = DEFAULT_CHANGE_ID


class ChangeDecisionRequest(BaseModel):
    outcome: str  # go | no_go | defer
    signature_reference: str  # 线下签署件 / 工单 / 邮件存档坐标（必填）
    reason: str  # 非空
    change_id: str = DEFAULT_CHANGE_ID
    conditions: List[str] = []
    decided_at: Optional[str] = None


# --------------------------------------------------------------------------- #
# 只读端点                                                                     #
# --------------------------------------------------------------------------- #
@router.get("/readiness")
def readiness(
    change_id: str = DEFAULT_CHANGE_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """生产变更管控就绪档案（只读合成；status_terminal 恒为 BUILT_NO_GO）。"""

    _require_user_principal(principal)
    _org(principal, org_id)
    inv = check_change_control_invariants()
    return {
        "change_id": change_id,
        "status_terminal": "PHASE_3_9_7_PRODUCTION_CHANGE_CONTROL_BUILT_NO_GO",
        "engineering_enabled": load_engineering_enabled(),
        "real_execution_endpoints_present": False,
        "gate_invariants_ok": inv["ok"],
        "forbidden_count": inv["forbidden_count"],
        "category_count": inv["category_count"],
        "note": "变更管控层已构建但全企业层 BUILT_NO_GO；真实变更须主理人在人类终端发起",
    }


@router.get("/contract")
def contract(
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """变更管控 API 契约 SSOT（只读；列出 present / absent 路由）。"""

    _require_user_principal(principal)
    _org(principal, org_id)
    return build_api_contract()


@router.get("/plan")
def get_plan(
    change_id: str = DEFAULT_CHANGE_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    _require_user_principal(principal)
    _org(principal, org_id)
    return {"change_id": change_id, "plan": None, "note": "尚无登记计划（只读）"}


@router.get("/window")
def get_window(
    change_id: str = DEFAULT_CHANGE_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    _require_user_principal(principal)
    _org(principal, org_id)
    return {"change_id": change_id, "window": None, "note": "尚无预约窗口（只读）"}


@router.get("/preflight")
def get_preflight(
    change_id: str = DEFAULT_CHANGE_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    _require_user_principal(principal)
    _org(principal, org_id)
    return {"change_id": change_id, "preflight": None, "note": "尚无预检记录（只读）"}


@router.get("/checkpoint")
def get_checkpoint(
    change_id: str = DEFAULT_CHANGE_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    _require_user_principal(principal)
    _org(principal, org_id)
    return {"change_id": change_id, "checkpoints": [], "note": "尚无检查点（只读）"}


@router.get("/abort-policy")
def get_abort_policy(
    change_id: str = DEFAULT_CHANGE_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    _require_user_principal(principal)
    _org(principal, org_id)
    return {
        "change_id": change_id,
        "abort_policy": {"human_abort_required": True},
        "note": "中止策略必须人工触发（AI 不得自动中止，红线③/⑩）",
    }


@router.get("/rollback-reference")
def get_rollback_reference(
    change_id: str = DEFAULT_CHANGE_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    _require_user_principal(principal)
    _org(principal, org_id)
    return {
        "change_id": change_id,
        "rollback_reference": None,
        "note": "回滚引用仅记录，不执行真实回滚（只读）",
    }


@router.get("/post-verification")
def get_post_verification(
    change_id: str = DEFAULT_CHANGE_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    _require_user_principal(principal)
    _org(principal, org_id)
    return {"change_id": change_id, "post_verifications": [], "note": "尚无变更后验证（只读）"}


@router.get("/evidence")
def get_evidence(
    change_id: str = DEFAULT_CHANGE_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    _require_user_principal(principal)
    _org(principal, org_id)
    return {"change_id": change_id, "evidence": [], "note": "尚无变更证据（只读）"}


@router.get("/simulation")
def get_simulation(
    change_id: str = DEFAULT_CHANGE_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    _require_user_principal(principal)
    _org(principal, org_id)
    return {
        "change_id": change_id,
        "simulation": None,
        "note": "受控仿真结果永远是仿真（is_simulation 恒 True，红线⑨）",
    }


@router.get("/failure-scenarios")
def get_failure_scenarios(
    change_id: str = DEFAULT_CHANGE_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    _require_user_principal(principal)
    _org(principal, org_id)
    return {"change_id": change_id, "scenarios": [], "note": "尚无失败场景评估（只读）"}


@router.get("/package")
def get_package(
    change_id: str = DEFAULT_CHANGE_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    _require_user_principal(principal)
    _org(principal, org_id)
    return {
        "change_id": change_id,
        "package": None,
        "note": "受控变更包 simulated_only 恒 True（材料≠执行，红线⑤/⑩）",
    }


@router.get("/decision-ledger")
def decision_ledger(
    change_id: str = DEFAULT_CHANGE_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """变更裁决登记簿快照（human_decision_recorded 仅表示"人已登记"，非执行）。"""

    _require_user_principal(principal)
    _org(principal, org_id)
    return {
        "change_id": change_id,
        "decisions": list(_CHANGE_DECISIONS.values()),
        "note": "登记≠执行；真实变更由主理人在人类终端发起",
    }


# --------------------------------------------------------------------------- #
# 写入端点：真实人工登记（fail-closed 门禁 + 真实 USER 强制）                       #
# --------------------------------------------------------------------------- #
@router.post("/plan")
def post_plan(
    body: ChangePlanRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _enforce_change_operation(operation=ChangeOperation.RECORD_CHANGE_PLAN, principal=principal)
    svc = _service(org_id)
    plan = svc.build_plan(
        change_id=body.change_id,
        plan_reference=body.plan_reference,
        rollback_plan_reference=body.rollback_plan_reference,
        steps=body.steps,
    )
    svc.record_change_plan_registered(
        actor_id=principal.actor_id, change_id=plan.change_id,
        detail=f"plan={body.plan_reference}",
    )
    return plan.to_dict()


@router.post("/window")
def post_window(
    body: ChangeWindowRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _enforce_change_operation(operation=ChangeOperation.RESERVE_CHANGE_WINDOW, principal=principal)
    svc = _service(org_id)
    win = svc.reserve_window(
        change_id=body.change_id,
        window_start=body.window_start,
        window_end=body.window_end,
        reserved_by=principal.actor_id,
    )
    svc.record_change_window_reserved(
        actor_id=principal.actor_id, change_id=win.change_id,
        detail=f"window={body.window_start}..{body.window_end}",
    )
    return win.to_dict()


@router.post("/preflight")
def post_preflight(
    body: ChangePreflightRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _enforce_change_operation(operation=ChangeOperation.RECORD_CHANGE_PREFLIGHT, principal=principal)
    svc = _service(org_id)
    result = svc.evaluate_preflight(checks=body.checks, missing=body.missing)
    svc.record_change_preflight_recorded(
        actor_id=principal.actor_id, change_id=body.change_id,
        status=result.status.value, detail=f"missing={len(result.missing)}",
    )
    return result.to_dict()


@router.post("/checkpoint")
def post_checkpoint(
    body: ChangeCheckpointRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _enforce_change_operation(operation=ChangeOperation.RECORD_CHANGE_CHECKPOINT, principal=principal)
    svc = _service(org_id)
    cp = svc.record_checkpoint(
        checkpoint_id=body.checkpoint_id,
        change_id=body.change_id,
        recorded_by=principal.actor_id,
        note=body.note,
    )
    svc.record_change_checkpoint_recorded(
        actor_id=principal.actor_id, change_id=body.change_id,
        detail=f"cp={body.checkpoint_id}",
    )
    return cp.to_dict()


@router.post("/abort-policy")
def post_abort_policy(
    body: ChangeAbortPolicyRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _enforce_change_operation(operation=ChangeOperation.REGISTER_CHANGE_ABORT_POLICY, principal=principal)
    svc = _service(org_id)
    ap = svc.build_abort_policy(
        change_id=body.change_id, auto_abort_conditions=body.auto_abort_conditions
    )
    svc.record_change_abort_policy_registered(
        actor_id=principal.actor_id, change_id=body.change_id,
        detail=f"conditions={len(body.auto_abort_conditions)}",
    )
    return ap.to_dict()


@router.post("/rollback-reference")
def post_rollback_reference(
    body: ChangeRollbackReferenceRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _enforce_change_operation(operation=ChangeOperation.REGISTER_CHANGE_ROLLBACK_REF, principal=principal)
    svc = _service(org_id)
    ref = svc.build_rollback_reference(
        change_id=body.change_id,
        last_known_good_version=body.last_known_good_version,
        last_known_good_commit=body.last_known_good_commit,
        database_revision=body.database_revision,
        config_baseline=body.config_baseline,
        rollback_steps_reference=body.rollback_steps_reference,
        recovery_validation_reference=body.recovery_validation_reference,
    )
    svc.record_change_rollback_reference_registered(
        actor_id=principal.actor_id, change_id=body.change_id,
        detail=f"lkg={body.last_known_good_version}",
    )
    return ref.to_dict()


@router.post("/post-verification")
def post_post_verification(
    body: ChangePostVerificationRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _enforce_change_operation(operation=ChangeOperation.RECORD_POST_CHANGE_VERIFICATION, principal=principal)
    try:
        status = ChangeVerificationStatus(body.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"非法 verification status：{body.status!r}")
    svc = _service(org_id)
    pv = svc.register_post_verification(
        verification_id=body.verification_id,
        change_id=body.change_id,
        verification_type=body.verification_type,
        status=status,
        verified_by=body.verified_by,
        detail=body.detail,
    )
    svc.record_post_change_verification_registered(
        actor_id=principal.actor_id, change_id=body.change_id,
        detail=f"type={body.verification_type};status={body.status}",
    )
    return pv.to_dict()


@router.post("/evidence")
def post_evidence(
    body: ChangeEvidenceRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _enforce_change_operation(operation=ChangeOperation.SUBMIT_CHANGE_EVIDENCE, principal=principal)
    svc = _service(org_id)
    ev = svc.build_evidence(
        evidence_id=body.evidence_id,
        evidence_type=body.evidence_type,
        source=body.source,
        source_reference=body.source_reference,
        change_id=body.change_id,
        integrity_status=body.integrity_status,
        verification_status=body.verification_status,
        sha256=body.sha256,
    )
    svc.record_change_evidence_submitted(
        actor_id=principal.actor_id, change_id=body.change_id,
        detail=f"type={body.evidence_type}",
    )
    return ev.to_dict()


@router.post("/simulation")
def post_simulation(
    body: ChangeSimulationRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """真实人工触发受控（合成）仿真（红线⑨：结果永远是仿真，不执行真实变更）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _enforce_change_operation(operation=ChangeOperation.PERFORM_CHANGE_SIMULATION, principal=principal)
    svc = _service(org_id)
    change = svc.create_change_request(
        change_id=body.change_id,
        title=body.title,
        description="synthetic change simulation",
        requested_by=principal.actor_id,
    )
    rollback = None
    if body.last_known_good_version and body.last_known_good_commit:
        rollback = svc.build_rollback_reference(
            change_id=body.change_id,
            last_known_good_version=body.last_known_good_version,
            last_known_good_commit=body.last_known_good_commit,
        )
    result = svc.run_simulation(
        simulation_id=body.simulation_id,
        change=change,
        rollback_reference=rollback,
        preflight_checks=body.preflight_checks,
        abort_conditions_present=body.abort_conditions_present,
    )
    svc.record_change_simulation_performed(
        actor_id=principal.actor_id, change_id=body.change_id,
        outcome=result.outcome.value, detail="is_simulation=true",
    )
    return result.to_dict()


@router.post("/failure-scenarios")
def post_failure_scenarios(
    body: ChangeFailureScenariosRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _enforce_change_operation(operation=ChangeOperation.EVALUATE_FAILURE_SCENARIO, principal=principal)
    svc = _service(org_id)
    evals = svc.evaluate_failure_scenarios(change_id=body.change_id, scenarios=body.scenarios)
    svc.record_failure_scenario_evaluated(
        actor_id=principal.actor_id, change_id=body.change_id,
        detail=f"scenarios={len(evals)}",
    )
    return [e.to_dict() for e in evals]


@router.post("/package")
def post_package(
    body: ChangePackageRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """生成受控变更包（材料 ≠ 执行，simulated_only 恒 True，红线⑤/⑩）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _enforce_change_operation(operation=ChangeOperation.BUILD_CHANGE_PACKAGE, principal=principal)
    svc = _service(org_id)
    change = svc.create_change_request(
        change_id=body.change_id,
        title=body.title,
        description="controlled change package",
        requested_by=principal.actor_id,
    )
    pkg = svc.build_package(
        package_id=body.package_id or f"pkg-{uuid.uuid4().hex[:12]}",
        change=change,
    )
    svc.record_change_package_generated(
        actor_id=principal.actor_id, change_id=body.change_id,
        detail="simulated_only=true",
    )
    return pkg.to_dict()


@router.post("/signoff")
def post_signoff(
    body: ChangeSignoffRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_SIGNOFF)
    ),
):
    """真实人工签署生产变更管控结论（红线⑥/⑧）。

    - 仅 governance-admin（持有 RELEASE_SIGNOFF）可调用；
    - actor_kind 必须 'user'（AI 主体 403）；
    - 签署落 AuditService（append-only）为系统真相源；
    - 本端点**不**翻转 engineering_enabled、不执行、不激活、不宣布 GO。
    """

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _enforce_change_operation(operation=ChangeOperation.REGISTER_CHANGE_SIGNOFF, principal=principal)
    if not body.signature_reference.strip():
        raise HTTPException(
            status_code=400,
            detail="签署须携带真实 signature_reference（线下签署文档 / 工单 / 归档审批坐标）",
        )
    audit = AuditService(org_id=org_id)
    signoff_id = "chg-aso-" + uuid.uuid4().hex[:12]
    try:
        audit.record_change_human_decision_recorded(
            record_id=signoff_id,
            actor_id=principal.actor_id,
            action="register_change_signoff",
            target=f"{body.change_id}:{body.role}",
            detail=f"decision={body.decision}; reason={body.reason!r}",
            ts=_ts(),
        )
    except EnterpriseRedLineViolationError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {
        "signoff_id": signoff_id,
        "change_id": body.change_id,
        "role": body.role,
        "decision": body.decision,
        "actor_id": principal.actor_id,
        "actor_kind": "user",
        "signature_reference": body.signature_reference,
        "note": "SIGN-OFF ONLY: 签署留痕，不翻转 engineering_enabled / 不执行变更",
    }


@router.post("/decision")
def post_decision(
    body: ChangeDecisionRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_SIGNOFF)
    ),
):
    """登记一条**已经发生**的真实人工变更裁决（记录 ≠ 执行，红线①②⑤⑨⑩）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _enforce_change_operation(operation=ChangeOperation.RECORD_CHANGE_DECISION, principal=principal)
    if not body.signature_reference.strip():
        raise HTTPException(
            status_code=400,
            detail="裁决须携带真实 signature_reference（线下签署件 / 工单 / 邮件存档坐标）",
        )
    if not body.reason.strip():
        raise HTTPException(status_code=400, detail="裁决 reason 不可为空")
    audit = AuditService(org_id=org_id)
    decision_id = "chg-dec-" + uuid.uuid4().hex[:12]
    try:
        audit.record_change_human_decision_recorded(
            record_id=decision_id,
            actor_id=principal.actor_id,
            action="record_change_decision",
            target=body.change_id,
            detail=f"outcome={body.outcome}; conditions={len(body.conditions)}",
            ts=_ts(),
        )
    except EnterpriseRedLineViolationError as e:
        raise HTTPException(status_code=403, detail=str(e))
    entry = {
        "decision_id": decision_id,
        "change_id": body.change_id,
        "outcome": body.outcome,
        "decided_by": principal.actor_id,
        "decided_by_kind": "user",
        "signature_reference": body.signature_reference,
        "reason": body.reason,
        "conditions": list(body.conditions),
        "decided_at": body.decided_at or _ts(),
        "engineering_enabled": load_engineering_enabled(),
        "execution_state": "PENDING_HUMAN_TERMINAL_ACTION",
    }
    _CHANGE_DECISIONS[decision_id] = entry
    return entry


__all__ = ["router"]
