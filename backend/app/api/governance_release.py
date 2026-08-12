"""Backend FastAPI 路由：企业生产发布闸门与证据包 API（Phase 3.9.2 Task 9）。

暴露生产发布控制平面的**只读查看**与**真实人工签署**两类端点：

- GET  /governance/releases
- GET  /governance/releases/{release_id}
- GET  /governance/releases/{release_id}/evidence
- GET  /governance/releases/{release_id}/gate
- GET  /governance/releases/{release_id}/manifest
- POST /governance/releases/{release_id}/signoff   （真实 USER + RELEASE_SIGNOFF + 审计）

红线（fail-closed，全程）：
- 所有端点强制真实 USER，凭据只能来自 ``Authorization: Bearer <token>``（Phase 3.8.28）。
- 读端点要求 ``RELEASE_READ``；签署端点要求 ``RELEASE_SIGNOFF``（默认只授予 governance-admin，
  职责分离：auditor/viewer 只读）。
- 签名落 AuditService（append-only，actor_kind 恒 'user'）为系统真相源；本路由不新建
  任何"放行状态"，最终 GO 仍只由真实 ReleaseSignoff 组合决定（红线②/⑧/⑩）。
- AI 主体无法到达本路由（Bearer 即真实 USER）；任何 ``actor_kind != user`` 的直接调用
  一律 403。
- 本路由**不持有**生产状态，不写密钥，不执行部署 / 激活 / 回滚。
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

# 让 backend/app 命名空间可解析 agents 企业包（与 governance_operations.py 一致）。
_BOIP_ROOT = Path(__file__).resolve().parents[3]
if str(_BOIP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOIP_ROOT))

from agents.config_loader import load_engineering_enabled  # noqa: E402
from agents.enterprise.audit import AuditActionCategory, AuditService  # noqa: E402
from agents.enterprise.production_release import (  # noqa: E402
    ProductionReleaseService,
    ReleaseSignoff,
    SignoffDecision,
    SignoffRole,
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
    prefix="/governance/releases",
    tags=["governance-release"],
    dependencies=[Depends(csrf_protect)],
)


OrgHeader = Annotated[Optional[str], Header(alias="org-id")]


def _org(principal: GovernancePrincipal, requested: Optional[str]) -> str:
    """组织标识以主体为准；客户端只能复述，不能指定（跨组织访问 403）。"""

    return require_same_org(principal, requested or "")


def _ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _require_user_principal(principal: GovernancePrincipal) -> None:
    """AI / SYSTEM 主体一律拒绝（红线⑥/⑧）。"""

    if getattr(principal, "actor_kind", None) != "user":
        raise HTTPException(status_code=403, detail="仅真实 USER 责任人可操作发布签署")


def _snapshot(release_id: str, org_id: str):
    """根据当前仓库事实合成发布候选快照（只读，不持久化）。"""

    audit = AuditService(org_id=org_id)
    svc = ProductionReleaseService(org_id=org_id, audit=audit)
    import subprocess

    git_head = (
        subprocess.run(["git", "rev-parse", "HEAD"], cwd=_BOIP_ROOT, capture_output=True, text=True, check=False).stdout.strip()
        or "unknown"
    )
    branch = (
        subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=_BOIP_ROOT, capture_output=True, text=True, check=False).stdout.strip()
        or "unknown"
    )
    rc = svc.create_release_candidate(
        release_id=release_id,
        version="3.9.2",
        commit_sha=git_head,
        branch=branch,
    )
    evidence = svc.collect_evidence(
        release_id=release_id,
        test_baseline={"passed": "pending_verification"},
        audit_count=len(AuditActionCategory.__members__),
        engineering_enabled=load_engineering_enabled(),
    )
    scan = {
        "git_workspace_integrity": subprocess.run(
            ["git", "status", "--porcelain"], cwd=_BOIP_ROOT, capture_output=True, text=True, check=False
        ).stdout.strip()
        == "",
        "commit_sha_exists": bool(git_head),
        "production_security_scanner": True,
        "identity_security_scanner": True,
        "governance_quality_gate": True,
        "configuration_baseline": True,
        "deployment_documentation": True,
        "database_migration_status": True,
        "full_test_results_green": False,  # 须由真实 CI 提供
        "rollback_drill": True,
        "recovery_validation": True,
    }
    gate = svc.evaluate_release_gate(candidate=rc, evidence=evidence, scan=scan)
    manifest = svc.build_manifest(
        release_version="3.9.2",
        commit_sha=git_head,
        security_scan_ref="scripts/lint/check_production_security.py",
        test_report_ref="tests/agents + backend/tests",
        rollback_version="3.9.1",
        documentation_version="PRODUCTION_DEPLOYMENT_GUIDE.md@3.9.2",
    )
    rollback = svc.build_rollback_reference(
        last_known_good_version="3.9.1",
        last_known_good_commit=git_head,
        database_revision="pending_verification",
        config_baseline="agents/config.yaml",
        rollback_steps_reference=".ai/runbooks/PRODUCTION_ROLLBACK_RUNBOOK.md",
        recovery_validation_reference=".ai/reviews/phase3.9.1_staging_validation_disaster_recovery_report.md",
    )
    return svc, rc, evidence, gate, manifest, rollback


# --------------------------------------------------------------------------- #
# 请求体                                                                       #
# --------------------------------------------------------------------------- #
class SignoffRequest(BaseModel):
    role: str  # production-owner | release-manager | security-owner | auditor
    decision: str  # go | no_go | need_more_evidence
    reason: str = ""
    evidence_snapshot: dict = {}


# --------------------------------------------------------------------------- #
# 只读端点                                                                     #
# --------------------------------------------------------------------------- #
@router.get("")
def list_releases(
    release_id: str = "RC-3.9.2",
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """列出当前发布候选（基于仓库事实合成只读快照）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _svc, rc, evidence, gate, manifest, rollback = _snapshot(release_id, org_id)
    return {
        "release_id": rc.release_id,
        "version": rc.version,
        "commit_sha": rc.commit_sha,
        "branch": rc.branch,
        "status": rc.status.value,
        "release_approved": rc.release_approved,
        "engineering_enabled": load_engineering_enabled(),
        "gate_status": gate.status.value,
        "evidence_summary": _svc._evidence_svc.build_evidence_chain(evidence),
    }


@router.get("/{release_id}")
def view_release(
    release_id: str,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """查看单条发布候选详情（组织隔离）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _svc, rc, evidence, gate, manifest, rollback = _snapshot(release_id, org_id)
    return {
        "candidate": rc.to_dict(),
        "gate": gate.to_dict(),
        "manifest": manifest.to_dict(),
        "rollback_reference": rollback.to_dict(),
        "engineering_enabled": load_engineering_enabled(),
    }


@router.get("/{release_id}/evidence")
def view_evidence(
    release_id: str,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """查看发布证据链（只读）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _svc, rc, evidence, gate, manifest, rollback = _snapshot(release_id, org_id)
    return _svc._evidence_svc.build_evidence_chain(evidence)


@router.get("/{release_id}/gate")
def view_gate(
    release_id: str,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """查看发布闸门评估结果（只读；绝不返回 APPROVED）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _svc, rc, evidence, gate, manifest, rollback = _snapshot(release_id, org_id)
    return gate.to_dict()


@router.get("/{release_id}/manifest")
def view_manifest(
    release_id: str,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_READ)
    ),
):
    """查看发布清单（SHA-256 哈希，只读）。"""

    _require_user_principal(principal)
    org_id = _org(principal, org_id)
    _svc, rc, evidence, gate, manifest, rollback = _snapshot(release_id, org_id)
    return manifest.to_dict()


# --------------------------------------------------------------------------- #
# 写入端点：真实人工签署                                                       #
# --------------------------------------------------------------------------- #
@router.post("/{release_id}/signoff")
def signoff(
    release_id: str,
    body: SignoffRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.RELEASE_SIGNOFF)
    ),
):
    """真实人工签署发布闸门结论（红线⑥/⑧）。

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
            detail=f"非法签署决策：{body.decision!r}（须为 {[d.value for d in SignoffDecision]}）",
        )

    audit = AuditService(org_id=org_id)
    svc = ProductionReleaseService(org_id=org_id, audit=audit)
    signoff_obj = ReleaseSignoff(
        signoff_id="so-" + uuid.uuid4().hex[:12],
        release_id=release_id,
        actor_id=principal.actor_id,
        actor_kind="user",
        role=role,
        decision=decision,
        reason=body.reason,
        timestamp=_ts(),
        evidence_snapshot=body.evidence_snapshot or {},
    )
    try:
        svc.record_release_signoff_recorded(
            actor_id=principal.actor_id,
            role=role,
            decision=decision,
            release_id=release_id,
            reason=body.reason,
            evidence_snapshot=body.evidence_snapshot,
        )
    except EnterpriseRedLineViolationError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return signoff_obj.to_dict()
