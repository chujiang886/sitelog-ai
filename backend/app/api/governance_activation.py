"""Backend FastAPI 路由：生产激活证据就绪 API（Phase 3.9.6 Task 16-17）。

暴露生产激活控制平面的**只读查看**与**真实人工签署**两类端点：

- GET  /governance/activation/readiness
- GET  /governance/activation/evidence
- GET  /governance/activation/blockers
- GET  /governance/activation/pending-verifications
- GET  /governance/activation/signoff-requirements
- GET  /governance/activation/review-packet
- GET  /governance/activation/contract
- POST /governance/activation/signoff            （真实 USER + RELEASE_SIGNOFF + 审计）

红线（fail-closed，全程）：
- 所有端点强制真实 USER，凭据只能来自 ``Authorization: Bearer <token>``（Phase 3.8.28）。
- 读端点要求 ``RELEASE_READ``；签署端点要求 ``RELEASE_SIGNOFF``（默认只授予 governance-admin，
  职责分离：auditor/viewer 只读）。
- 签名落 AuditService（append-only，actor_kind 恒 'user'）为系统真相源；本路由不新建
  任何"放行状态"，最终 GO 仍只由真实四角色签署决定（红线②/⑧/⑩）。
- AI 主体无法到达本路由（Bearer 即真实 USER）；任何 ``actor_kind != user`` 的直接调用
  一律 403。
- 本路由**不持有**生产状态，不写密钥，不执行部署 / 激活 / 回滚。
- **不提供** ``POST /governance/activation/activate`` 与 ``POST /governance/activation/deploy-production``：
  真实生产激活只能由主理人在人类终端、四角色签署后显式执行（红线①）。

权限复用说明：``GovernancePermission`` 当前仅有 ``RELEASE_READ`` / ``RELEASE_SIGNOFF``，
激活签署与发布签署共用同一组"真实责任人 + 治理管理员"权限模型（四角色一致、管理员独享签署），
故本路由复用之，不另起一套权限枚举（reuse-not-duplicate）。
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

# 让 backend/app 命名空间可解析 agents 企业包（与 governance_release.py 一致）。
_BOIP_ROOT = Path(__file__).resolve().parents[3]
if str(_BOIP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOIP_ROOT))

from agents.config_loader import load_engineering_enabled  # noqa: E402
from agents.enterprise.audit import AuditService  # noqa: E402
from agents.enterprise.production_release import (  # noqa: E402
    EngineeringActivationContract,
    HumanSignoffRegistry,
    ProductionActivationReadinessGate,
    ProductionHumanReviewPacket,
    SignoffDecision,
    SignoffRole,
    assemble_activation_readiness_dossier,
    build_default_signoff_requirements,
    build_human_signoff_record,
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
    prefix="/governance/activation",
    tags=["governance-activation"],
    dependencies=[Depends(csrf_protect)],
)

OrgHeader = Annotated[Optional[str], Header(alias="org-id")]

DEFAULT_RC_ID = "RC-3.9.6"

# 进程内签署登记簿（按 rc_id 缓存）；系统真相源始终是 AuditService（append-only）。
_REGISTRIES: dict[str, HumanSignoffRegistry] = {}


def _ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _require_user_principal(principal: GovernancePrincipal) -> None:
    """AI / SYSTEM 主体一律拒绝（红线⑥/⑧）。"""

    if getattr(principal, "actor_kind", None) != "user":
        raise HTTPException(status_code=403, detail="仅真实 USER 责任人可操作生产激活签署")


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


def _get_registry(rc_id: str) -> HumanSignoffRegistry:
    reg = _REGISTRIES.get(rc_id)
    if reg is None:
        reg = HumanSignoffRegistry(rc_id=rc_id)
        _REGISTRIES[rc_id] = reg
    return reg


def _dossier(rc_id: str) -> dict:
    """基于当前仓库事实合成只读激活就绪 dossier（不含真实签署时为 fail-closed）。"""

    registry = _get_registry(rc_id)
    return assemble_activation_readiness_dossier(
        rc_id=rc_id, root_dir=str(_BOIP_ROOT), signoff_registry=registry
    )


# --------------------------------------------------------------------------- #
# 请求体                                                                       #
# --------------------------------------------------------------------------- #
class ActivationSignoffRequest(BaseModel):
    role: str  # production-owner | release-manager | security-owner | auditor
    decision: str  # go | no_go | need_more_evidence
    reason: str = ""
    signature_reference: str  # 线下签署文档 / 工单 / 归档审批坐标（必填）
    evidence_scope_reviewed: List[str] = []


# --------------------------------------------------------------------------- #
# 只读端点                                                                     #
# --------------------------------------------------------------------------- #
@router.get("/readiness")
def readiness(
    rc_id: str = DEFAULT_RC_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """生产激活就绪 dossier（只读合成；status_terminal 恒为 BUILT_NO_GO）。"""

    _require_user_principal(principal)
    _org(principal, org_id)
    return _dossier(rc_id)


@router.get("/evidence")
def evidence(
    rc_id: str = DEFAULT_RC_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """激活证据包 v2（3.9.0-3.9.5 证据聚合，只读）。"""

    _require_user_principal(principal)
    _org(principal, org_id)
    return _dossier(rc_id)["evidence_bundle"]


@router.get("/blockers")
def blockers(
    rc_id: str = DEFAULT_RC_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """生产激活阻断器清单（B1-B6，真实前置条件）。"""

    _require_user_principal(principal)
    _org(principal, org_id)
    return _dossier(rc_id)["blockers"]


@router.get("/pending-verifications")
def pending_verifications(
    rc_id: str = DEFAULT_RC_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """待核验事项（PV1-PV6，须真实人工/真实生产数据提供与验证）。"""

    _require_user_principal(principal)
    _org(principal, org_id)
    return _dossier(rc_id)["pending_verification"]


@router.get("/signoff-requirements")
def signoff_requirements(
    rc_id: str = DEFAULT_RC_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """四角色真实人工签署要求（未签署即 PENDING，fail-closed）。"""

    _require_user_principal(principal)
    _org(principal, org_id)
    return _dossier(rc_id)["signoff_requirements"]


@router.get("/contract")
def contract(
    rc_id: str = DEFAULT_RC_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """工程激活契约：AI 只判定 activation_allowed_for_human，绝不自行开启。"""

    _require_user_principal(principal)
    _org(principal, org_id)
    return _dossier(rc_id)["contract"]


@router.get("/review-packet")
def review_packet(
    rc_id: str = DEFAULT_RC_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """供真实责任人审核的复核包（Task 11/12，机器可读，无真实 secret）。"""

    _require_user_principal(principal)
    _org(principal, org_id)
    d = _dossier(rc_id)
    packet = ProductionHumanReviewPacket(
        release_candidate=rc_id,
        commit_sha=_git_head(),
        artifact_manifest={
            "evidence_bundle": d["evidence_bundle"],
            "status_terminal": d["status_terminal"],
        },
        test_summary={
            "full_test_suite": "pending_verification",
            "note": "真实 CI 全绿由人工/CI 提供，本包不声明通过",
        },
        security_summary={
            "production_security_scan": "scripts/lint/check_production_security.py",
            "status": "pending_verification",
        },
        identity_summary={
            "idp_real_config": "pending_verification",
            "note": "真实 IdP 凭证由人类提供，AI 不持有",
        },
        dr_summary={
            "rollback_reference": "present",
            "recovery_validation": "present",
            "drill": "synthetic",
        },
        observability_summary={
            "telemetry_provider": "synthetic",
            "note": "真实遥测由人类接入",
        },
        telemetry_summary={"real_topology": "pending_verification"},
        incident_readiness={"alert_routing": "pending_verification"},
        rollback={
            "last_known_good_commit": _git_head(),
            "rollback_steps_reference": ".ai/runbooks/PRODUCTION_ROLLBACK_RUNBOOK.md",
        },
        pending_verification=tuple(d["pending_verification"]),
        blockers=tuple(d["blockers"]),
        required_signatures=tuple(d["signoff_requirements"]),
    )
    return packet.to_dict()


# --------------------------------------------------------------------------- #
# 写入端点：真实人工签署                                                       #
# --------------------------------------------------------------------------- #
@router.post("/signoff")
def signoff(
    body: ActivationSignoffRequest,
    rc_id: str = DEFAULT_RC_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_SIGNOFF)
    ),
):
    """真实人工签署生产激活就绪结论（红线⑥/⑧）。

    - 仅 governance-admin（持有 RELEASE_SIGNOFF）可调用；
    - actor_kind 必须 'user'（AI 主体 403）；
    - 签署落 AuditService（append-only）为系统真相源；
    - 本端点**不**翻转 engineering_enabled、不部署、不激活、不宣布 GO。
    """

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    try:
        role = SignoffRole(body.role)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"非法签署角色：{body.role!r}（须为 {[r.value for r in SignoffRole]}）",
        )
    try:
        decision = SignoffDecision(body.decision)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"非法签署决策：{body.decision!r}（须为 {[x.value for x in SignoffDecision]}）",
        )
    if not body.signature_reference.strip():
        raise HTTPException(
            status_code=400,
            detail="签署须携带真实 signature_reference（线下签署文档 / 工单 / 归档审批坐标）",
        )

    audit = AuditService(org_id=org_id)
    signoff_id = "aso-" + uuid.uuid4().hex[:12]
    try:
        audit.record_human_signoff_registered(
            record_id=signoff_id,
            actor_id=principal.actor_id,
            target=f"{rc_id}:{role.value}",
            detail=f"decision={decision.value}; reason={body.reason!r}",
        )
    except EnterpriseRedLineViolationError as e:
        raise HTTPException(status_code=403, detail=str(e))

    # 进程内登记（系统真相源仍是 AuditService）。
    reg = _get_registry(rc_id)
    rec = build_human_signoff_record(
        signoff_id=signoff_id,
        rc_id=rc_id,
        role=role,
        decision=decision,
        actor_id=principal.actor_id,
        actor_kind="user",
        signature_reference=body.signature_reference,
        reason=body.reason,
        evidence_scope_reviewed=list(body.evidence_scope_reviewed),
    )
    reg.register(rec)
    return rec.to_dict()
