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

Layer B（Phase 3.9.6 T14，人工提交的证据接收链，与 Layer A 正交、互不顶替）：

- GET  /governance/activation/intake-summary     （真实 USER + RELEASE_READ）
- GET  /governance/activation/evidence-list       （真实 USER + RELEASE_READ，裁决候选）
- GET  /governance/activation/decision-ledger    （真实 USER + RELEASE_READ）
- POST /governance/activation/evidence           （真实 USER + RELEASE_READ + T13 存储安全）
- POST /governance/activation/evidence-decision  （真实 USER + RELEASE_SIGNOFF + 人工裁决）
- POST /governance/activation/review-package     （真实 USER + RELEASE_READ，材料≠裁决）
- POST /governance/activation/final-decision     （真实 USER + RELEASE_SIGNOFF，登记人裁决，永不激活）

Layer B 所有写操作均复用 T12 ``require_activation_operation`` 做 fail-closed 白名单门禁
（AI / SYSTEM 主体一律 403；未登记操作默认拒绝），并复用 T13 ``EvidenceStoragePolicy``
做"只存引用、不存原文、拒绝裸密钥"的存储安全守门。Layer B 只登记事实与人裁决，
绝不翻转 ``engineering_enabled``、不产出 ``engineering_approved``、不宣布 Production GO、
不绕过 ``ControlledActivationGate``（红线①②④⑤⑨⑩）。

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
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

# 让 backend/app 命名空间可解析 agents 企业包（与 governance_release.py 一致）。
_BOIP_ROOT = Path(__file__).resolve().parents[3]
if str(_BOIP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOIP_ROOT))

from agents.config_loader import load_engineering_enabled  # noqa: E402
from agents.enterprise.audit import AuditActorKind, AuditService  # noqa: E402
from agents.enterprise.production_release import (  # noqa: E402
    ActivationEvidenceIntakeError,
    ActivationEvidenceIntakeService,
    ActivationIntakeServiceError,
    EvidenceIntegrityStatus,
    EngineeringActivationContract,
    FinalActivationReviewPackage,
    FinalDecisionOutcome,
    FinalHumanDecisionError,
    FinalHumanDecisionLedger,
    HumanSignoffRegistry,
    ProductionActivationReadinessGate,
    ProductionHumanReviewPacket,
    SignoffDecision,
    SignoffRole,
    assemble_activation_readiness_dossier,
    build_chain_of_custody,
    build_default_signoff_requirements,
    build_evidence_provenance,
    build_final_human_activation_decision,
    build_human_signoff_record,
)
from agents.enterprise.production_release.evidence_storage_safety import (  # noqa: E402
    EvidenceStoragePolicy,
    EvidenceStorageSafetyError,
)
from agents.enterprise.production_release.permission_boundary import (  # noqa: E402
    ActivationOperation,
    require_activation_operation,
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

# Layer B 进程内缓存（按 "org_id:rc_id" 索引）。系统真相源始终是：
# - AuditService（append-only 审计留痕）；
# - 各领域服务自身的 in-memory 状态（证据提交 / 裁决 / 评审包）。
# 本路由只是无状态网关：进程重启即丢失，真实生产激活仍须主理人在人类终端、
# 四角色签署后显式执行（红线①）。Phase 3.9.6 收口态为"证据就绪层"，不承载放行。
_INTAKE_SERVICES: dict[str, ActivationEvidenceIntakeService] = {}
_DECISION_LEDGERS: dict[str, FinalHumanDecisionLedger] = {}
_REVIEW_PACKAGES: dict[str, FinalActivationReviewPackage] = {}


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


# --------------------------------------------------------------------------- #
# Layer B 缓存与权限抽取                                                          #
# --------------------------------------------------------------------------- #
def _actor_kind_str(principal: GovernancePrincipal) -> str:
    """把治理主体类别归一为小写字符串（'user' / 'agent' / 'service' / 'unknown'）。

    注意：``principal.actor_kind`` 是 ``ActorKind`` 枚举，``str()`` 会得到
    ``'ActorKind.USER'`` 而非其值；必须用 ``.value``（这与
    ``_require_user_principal`` 用 ``!= 'user'`` 比较枚举值的语义一致，因为
    ``ActorKind`` 是 ``str`` 枚举，枚举值 ``== 'user'``）。
    """

    ak = getattr(principal, "actor_kind", None)
    if ak is None:
        return "unknown"
    return str(getattr(ak, "value", ak)).strip().lower() or "unknown"


def _granted_permissions(principal: GovernancePrincipal) -> List[str]:
    """把主体持有的治理权限展开为字符串列表（供 T12 白名单校验）。

    与 actor_kind 同理：``GovernancePermission`` 是 ``str`` 枚举，``str(p)`` 会
    得到 ``'GovernancePermission.RELEASE_READ'`` 而非其取值，必须用 ``.value``。
    """

    return [
        str(getattr(p, "value", p))
        for p in getattr(principal, "permissions", ())
    ]


def _enforce_activation_operation(
    *, operation: "ActivationOperation", principal: GovernancePrincipal
) -> None:
    """T12 fail-closed 权限边界（SSOT）：任何未登记 / 非 user / 缺权限的操作 403。

    这是 Layer B 写操作的唯一权限事实源；FastAPI 的 ``require_governance_permission``
    依赖只负责把 Bearer 令牌解析为真实 USER 主体，真正的"谁能做哪个治理动作"
    仍由本函数裁决（deny-by-default 白名单）。
    """

    try:
        require_activation_operation(
            operation=operation,
            actor_kind=_actor_kind_str(principal),
            granted_permissions=_granted_permissions(principal),
        )
    except EnterpriseRedLineViolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


def _get_intake_service(rc_id: str, org_id: str) -> ActivationEvidenceIntakeService:
    """按 "org_id:rc_id" 取或建 Layer B 证据接收服务（进程内缓存）。"""

    key = f"{org_id}:{rc_id}"
    svc = _INTAKE_SERVICES.get(key)
    if svc is None:
        svc = ActivationEvidenceIntakeService(
            rc_id=rc_id,
            audit=AuditService(org_id=org_id),
            root_dir=str(_BOIP_ROOT),
        )
        _INTAKE_SERVICES[key] = svc
    return svc


def _get_decision_ledger(rc_id: str, org_id: str) -> FinalHumanDecisionLedger:
    """按 "org_id:rc_id" 取或建 Layer B 最终裁决登记簿（进程内缓存）。"""

    key = f"{org_id}:{rc_id}"
    led = _DECISION_LEDGERS.get(key)
    if led is None:
        led = FinalHumanDecisionLedger(rc_id=rc_id, audit=AuditService(org_id=org_id))
        _DECISION_LEDGERS[key] = led
    return led


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


# --------------------------------------------------------------------------- #
# Layer B 请求体                                                                #
# --------------------------------------------------------------------------- #
class ActivationEvidenceSubmitRequest(BaseModel):
    """真实人工提交一条激活证据的请求（只收引用，不收正文，红线⑦）。"""

    evidence_type: str
    title: str
    content_reference: str  # 本地路径 / 工单号 / 外部 URL / 线下件编号（非正文）
    origin_system: str
    origin_reference: str
    declared_sha256: Optional[str] = None
    captured_at: Optional[str] = None
    chain_of_custody: List[Dict[str, object]] = []
    submission_id: Optional[str] = None
    integrity_status: Optional[str] = None  # EvidenceIntegrityStatus 取值
    recompute_hash: bool = True


class ActivationEvidenceDecisionRequest(BaseModel):
    """真实人工对单条证据作裁决（唯一能产出 APPROVED_BY_HUMAN 的路径）。"""

    submission_id: str
    approved: bool
    reason: str  # 非空；无理由的批准不可采信


class ActivationReviewPackageRequest(BaseModel):
    """请求生成供真实人工裁决的只读评审材料包（材料 ≠ 裁决）。"""

    package_id: Optional[str] = None
    gate_snapshot: Optional[Dict[str, Any]] = None


class ActivationFinalDecisionRequest(BaseModel):
    """登记一条**已经发生**的真实人工最终裁决（记录，不是 AI 的结论）。"""

    outcome: str  # go | no_go | defer
    signature_reference: str  # 线下签署件 / 工单 / 邮件存档坐标（必填）
    reason: str  # 非空
    package_id: Optional[str] = None  # 绑定已生成评审包；缺省则基于当前事实现建
    conditions: List[str] = []
    decided_at: Optional[str] = None


# --------------------------------------------------------------------------- #
# Layer B 只读端点                                                              #
# --------------------------------------------------------------------------- #
@router.get("/intake-summary")
def intake_summary(
    rc_id: str = DEFAULT_RC_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """Layer B 证据接收现状只读汇总（fail-closed：只陈述事实，不声明放行）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    svc = _get_intake_service(rc_id, org_id)
    return svc.summarize().to_dict()


@router.get("/decision-ledger")
def decision_ledger(
    rc_id: str = DEFAULT_RC_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """Layer B 最终裁决登记簿快照（human_go_recorded 仅表示"人已登记"，非放行）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    ledger = _get_decision_ledger(rc_id, org_id)
    return ledger.snapshot().to_dict()


# 供前端「证据裁决控件」拉取 submission_id 候选的只读列表端点（T15）。
# 不暴露证据原文（T13 存储安全：只返回引用/哈希/派生事实）。
@router.get("/evidence-list")
def evidence_list(
    rc_id: str = DEFAULT_RC_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """Layer B 已提交证据列表（只读；只含引用/哈希/派生事实，不含原文）。

    前端「证据裁决控件（POST /evidence-decision）」需要 ``submission_id`` 下拉候选，
    本端点即为其数据源。返回每个 submission 的 ``to_dict()``（含 status /
    structurally_valid / is_human_approved / is_human_rejected / awaiting_human_review
    / human_decision_by 等事实字段），供真实责任人人工裁决时选择。
    """

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    svc = _get_intake_service(rc_id, org_id)
    return [s.to_dict() for s in svc.submissions]


# --------------------------------------------------------------------------- #
# Layer B 写入端点（T12 门禁 + T13 存储安全 + 真实 USER 强制）                     #
# --------------------------------------------------------------------------- #
@router.post("/evidence")
def submit_evidence(
    body: ActivationEvidenceSubmitRequest,
    rc_id: str = DEFAULT_RC_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """真实人工提交一条激活证据（T5）。

    - T12 门禁：``SUBMIT_EVIDENCE`` 操作须为真实 USER 且持 ``RELEASE_READ``；
    - T13 存储安全：拒绝把裸密钥当引用、拒绝 inline 正文；
    - 提交者必须是真实自然人（``build_evidence_provenance`` 强制 submitted_by_kind=user）；
    - 提交只推进到结构校验，绝不视为采信（红线④⑨）。
    """

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _enforce_activation_operation(
        operation=ActivationOperation.SUBMIT_EVIDENCE, principal=principal
    )

    # T13 存储安全守门（fail-closed）。
    storage = EvidenceStoragePolicy(root_dir=str(_BOIP_ROOT))
    try:
        storage.ensure_no_inline_content(declared_content=None)
        storage.ensure_reference_not_secret(body.content_reference)
    except EvidenceStorageSafetyError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        provenance = build_evidence_provenance(
            origin_system=body.origin_system,
            origin_reference=body.origin_reference,
            submitted_by=principal.actor_id,
            submitted_by_kind="user",
            declared_sha256=body.declared_sha256,
            captured_at=body.captured_at,
            chain_of_custody=build_chain_of_custody(body.chain_of_custody),
        )
    except ActivationEvidenceIntakeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    integrity = EvidenceIntegrityStatus.PENDING
    if body.integrity_status:
        try:
            integrity = EvidenceIntegrityStatus(body.integrity_status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"非法 integrity_status：{body.integrity_status!r}",
            )

    svc = _get_intake_service(rc_id, org_id)
    try:
        sub = svc.submit_evidence(
            actor_kind=AuditActorKind.USER,
            actor_id=principal.actor_id,
            evidence_type=body.evidence_type,
            title=body.title,
            content_reference=body.content_reference,
            provenance=provenance,
            submission_id=body.submission_id,
            integrity_status=integrity,
            recompute_hash=body.recompute_hash,
        )
    except ActivationIntakeServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except EnterpriseRedLineViolationError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return sub.to_dict()


@router.post("/evidence-decision")
def record_evidence_decision(
    body: ActivationEvidenceDecisionRequest,
    rc_id: str = DEFAULT_RC_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_SIGNOFF)
    ),
):
    """真实人工对单条证据裁决（approve / reject，红线④⑨）。

    唯一能产出 ``APPROVED_BY_HUMAN`` 的路径；要求 ``reason`` 非空；结构校验失败的
    证据不得被批准。本端点不改变任何闸门状态（红线⑩）。
    """

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _enforce_activation_operation(
        operation=ActivationOperation.RECORD_EVIDENCE_DECISION, principal=principal
    )

    svc = _get_intake_service(rc_id, org_id)
    try:
        updated = svc.record_human_evidence_decision(
            actor_kind=AuditActorKind.USER,
            actor_id=principal.actor_id,
            submission_id=body.submission_id,
            approved=body.approved,
            reason=body.reason,
        )
    except ActivationIntakeServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return updated.to_dict()


@router.post("/review-package")
def build_review_package_endpoint(
    body: ActivationReviewPackageRequest,
    rc_id: str = DEFAULT_RC_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """生成供真实人工裁决的只读评审材料包（T8，材料 ≠ 裁决，红线⑤⑩）。

    必须由真实自然人发起；构建期对产物做放行词元扫描，就绪度上限
    ``READY_FOR_HUMAN_FINAL_REVIEW``，永不含 engineering_approved / Production GO。
    生成的包按 package_id 缓存，供 ``/final-decision`` 绑定。
    """

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _enforce_activation_operation(
        operation=ActivationOperation.BUILD_REVIEW_PACKAGE, principal=principal
    )

    svc = _get_intake_service(rc_id, org_id)
    try:
        package = svc.build_review_package(
            actor_kind=AuditActorKind.USER,
            actor_id=principal.actor_id,
            gate_snapshot=body.gate_snapshot,
            package_id=body.package_id,
        )
    except ActivationIntakeServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _REVIEW_PACKAGES[package.package_id] = package
    return package.to_dict()


@router.post("/final-decision")
def record_final_decision(
    body: ActivationFinalDecisionRequest,
    rc_id: str = DEFAULT_RC_ID,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_SIGNOFF)
    ),
):
    """登记一条**已经发生**的真实人工最终裁决（T9，记录 ≠ 激活，红线①②⑤⑨⑩）。

    - 裁决只能来自真实自然人（``decided_by`` 强制取自主体的 actor_id）；
    - 必须绑定真实评审包：优先复用调用方指定的已生成包，否则基于当前事实现建；
    - ``GO`` 裁决要求评审包就绪度为 ``READY_FOR_HUMAN_FINAL_REVIEW``，否则被拒；
    - 即便登记 GO，``engineering_enabled`` 仍为 False、激活执行态仍为
      ``PENDING_HUMAN_TERMINAL_ACTION`` —— 激活由主理人在人类终端执行。
    """

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _enforce_activation_operation(
        operation=ActivationOperation.RECORD_FINAL_DECISION, principal=principal
    )

    try:
        outcome = FinalDecisionOutcome(body.outcome)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"非法裁决结果：{body.outcome!r}（须为 {[x.value for x in FinalDecisionOutcome]}）",
        )

    svc = _get_intake_service(rc_id, org_id)
    ledger = _get_decision_ledger(rc_id, org_id)

    # 绑定真实评审包：优先复用调用方指定的已生成包，否则基于当前事实现建。
    package: Optional[FinalActivationReviewPackage] = None
    if body.package_id:
        package = _REVIEW_PACKAGES.get(body.package_id)
    if package is None:
        package = svc.build_review_package(
            actor_kind=AuditActorKind.USER,
            actor_id=principal.actor_id,
            package_id=body.package_id,
        )
        _REVIEW_PACKAGES[package.package_id] = package

    try:
        decision = build_final_human_activation_decision(
            decision_id="fhd-" + uuid.uuid4().hex[:12],
            outcome=outcome,
            decided_by=principal.actor_id,
            decided_by_kind="user",
            signature_reference=body.signature_reference,
            reason=body.reason,
            package=package,
            conditions=list(body.conditions),
            decided_at=body.decided_at,
        )
    except FinalHumanDecisionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        ledger.record(actor_kind=AuditActorKind.USER, decision=decision)
    except FinalHumanDecisionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return decision.to_dict()
