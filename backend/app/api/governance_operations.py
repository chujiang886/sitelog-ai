"""Backend FastAPI 路由：企业智能体治理·人工操作界面 API（Phase 3.8.26 Task 5）。

暴露真实责任人（USER）对持久化治理工作流的「登记 / 查看 / 研判确认 / 结果提交 / 闭环」五类操作。

红线（fail-closed，全程）：
- 所有端点强制真实 USER，且身份**只能**来自 ``Authorization: Bearer <token>``：
  后端验签 → 回库确认账号仍 active → 重读治理角色 → 判权限（Phase 3.8.28 T3）。
  3.8.28 之前这里读的是**旧式身份请求头**，任何人都能
  凭两个自填的头成为"真实责任人"；现在请求里不存在任何可声明身份的字段，
  携带旧头一律 400（红线③/④/⑥）。
- 每个端点声明所需治理权限，默认拒绝：无治理角色的合法登录用户同样进不来。
- 写操作全部经 ``GovernanceWorkflowRepository`` 落库，并由 ``AuditService`` 如实留痕
  （复用 AGENT_GOVERNANCE_WORKFLOW_CREATE/REVIEW/EXECUTION 三类审计；不提供
  record_human_approval，红线②/⑥）。
- 本路由**不持有**治理状态机：它只把真实人工的操作事实**快照**写入关系库，供跨重启追溯。
  3.8.25 的 live orchestrator 仍是内存态真相源；本路由是「Workflow → Database →
  Human UI → Audit」链路中的持久化与人工入口环节（复用而非重建）。
- DB 层 CHECK 约束（status 六态白名单 / requires_human_confirmation 恒真 /
  actor_kind='user'）构成第二、第三道防线，即便绕过本 API 直连 DB 也过不了。
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

# 让 backend/app 命名空间可解析 agents 企业包（与 governance_dashboard.py 一致）。
_BOIP_ROOT = Path(__file__).resolve().parents[3]
if str(_BOIP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOIP_ROOT))

from agents.enterprise.audit import AuditService  # noqa: E402

from app.db.session import get_db  # noqa: E402
from app.db.models.governance_workflow import (  # noqa: E402
    GOVERNANCE_REVIEW_DECISION_VALUES,
    GovernanceExecutionRecordDB,
    GovernanceWorkflowRecord,
)
from app.db.repositories.governance_workflow_repository import (  # noqa: E402
    GovernanceRepositoryError,
    GovernanceWorkflowRepository,
)
from app.core.csrf import csrf_protect  # noqa: E402
from app.identity import (  # noqa: E402
    GovernancePermission,
    GovernancePrincipal,
    accountability_context,
    format_accountability,
    record_accountability,
    require_governance_permission,
    require_same_org,
)

# CSRF 双提交防护（T1）：对所有 /governance/ops 请求生效；
# 只读方法（GET）由 csrf_protect 内部豁免，状态变更方法强制校验。
# 生产环境默认开启，开发/测试环境由 CSRF_PROTECTION_ENABLED 控制（默认关闭），
# 因此既有测试在开发配置下不受影响。
router = APIRouter(
    prefix="/governance/ops",
    tags=["governance-human-ops"],
    dependencies=[Depends(csrf_protect)],
)


# 人工操作界面静态页（仅含人工入口，无任何自动按钮，红线③/④/⑥）。
_UI_PATH = Path(__file__).resolve().parents[1] / "static" / "governance_human_ui.html"


# --------------------------------------------------------------------------- #
# 真实人工门控（红线⑥）                                                        #
# --------------------------------------------------------------------------- #
OrgHeader = Annotated[Optional[str], Header(alias="org-id")]


def _org(principal: GovernancePrincipal, requested: Optional[str]) -> str:
    """组织标识以主体为准；客户端只能复述，不能指定（跨组织访问 403）。"""

    return require_same_org(principal, requested or "")


def _ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _view_detail(
    principal: GovernancePrincipal, *, action: str, resource: str
) -> str:
    """只读动作的审计 detail：直接携带责任五元组。

    读动作不另起一条问责记录（读没有"责任后果"，只有"知情范围"），但它同样
    需要能回答"谁以什么身份看过哪些治理事实" —— 组织内部审查最常问的正是
    这个。因此把五元组塞进本就要写的 VIEW 审计 detail 里，零额外记录。
    """

    return format_accountability(
        accountability_context(principal, action=action, resource=resource)
    )


def _wf_to_dict(rec: GovernanceWorkflowRecord) -> dict:
    return {
        "workflow_id": rec.workflow_id,
        "status": rec.status,
        "source_id": rec.source_id,
        "org_id": rec.org_id,
        "source_type": rec.source_type,
        "title": rec.title,
        "description": rec.description,
        "source_facts": rec.source_facts,
        "references": rec.references,
        "human_notes": rec.human_notes,
        "created_by": rec.created_by,
        "confirmed_by": rec.confirmed_by,
        "confirmed_at": rec.confirmed_at,
        "completed_by": rec.completed_by,
        "completed_at": rec.completed_at,
        "archived": rec.archived,
        "archived_by": rec.archived_by,
        "draft_id": rec.draft_id,
        "task_id": rec.task_id,
        "requires_human_confirmation": rec.requires_human_confirmation,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "updated_at": rec.updated_at.isoformat() if rec.updated_at else None,
    }


def _ex_to_dict(rec: GovernanceExecutionRecordDB) -> dict:
    return {
        "record_id": rec.record_id,
        "workflow_id": rec.workflow_id,
        "org_id": rec.org_id,
        "action": rec.action,
        "actor": rec.actor,
        "actor_kind": rec.actor_kind,
        "timestamp": rec.timestamp,
        "result": rec.result,
        "note": rec.note,
        "decision": rec.decision,
        "source": rec.source,
        "source_chain": rec.source_chain,
        "audit_record_id": rec.audit_record_id,
        "audit_category": rec.audit_category,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }


# --------------------------------------------------------------------------- #
# 请求体                                                                       #
# --------------------------------------------------------------------------- #
class ReportWorkflowRequest(BaseModel):
    source_id: str
    title: str
    description: str = ""
    source_type: str = "human_reported"
    source_facts: list = []
    references: list = []


class ConfirmReviewRequest(BaseModel):
    decision: str  # confirmed | rejected | need_more_info
    reason: str = ""


class SubmitResultRequest(BaseModel):
    result: str
    note: str = ""
    decision: str = ""


class CloseWorkflowRequest(BaseModel):
    note: str = ""


# --------------------------------------------------------------------------- #
# 端点                                                                         #
# --------------------------------------------------------------------------- #
@router.get("/ui")
def human_operation_ui():
    """返回人工操作界面静态页（仅含人工入口，无自动按钮）。

    页面本身公开可访问（如同登录页），但所有读写操作仍须持 Bearer 凭据并通过治理权限校验。
    """

    if not _UI_PATH.exists():
        raise HTTPException(status_code=404, detail="UI 文件缺失")
    return FileResponse(str(_UI_PATH), media_type="text/html")


@router.post("/workflows", status_code=201)
def report_workflow(
    body: ReportWorkflowRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.WORKFLOW_REPORT)
    ),
    db=Depends(get_db),
):
    """真实人工上报/登记一条治理工作流（status=created）。"""

    actor_id = principal.actor_id
    org_id = _org(principal, org_id)
    repo = GovernanceWorkflowRepository(db)
    wid = "wf-" + uuid.uuid4().hex[:12]
    rec = GovernanceWorkflowRecord(
        workflow_id=wid,
        status="created",
        source_id=body.source_id,
        org_id=org_id,
        source_type=body.source_type,
        title=body.title,
        description=body.description,
        source_facts=body.source_facts,
        references=body.references,
        human_notes=[],
        created_by=actor_id,
    )
    try:
        repo.save_workflow(rec)
    except GovernanceRepositoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit = AuditService(org_id=org_id)
    audit.record_agent_governance_workflow_create(
        record_id="aud-" + uuid.uuid4().hex[:12],
        actor_id=actor_id,
        action="create_workflow",
        target=wid,
        detail=f"title={body.title}",
        ts=_ts(),
    )
    # T4：责任五元组独立成条，动作名固定，便于一次捞全某人全部治理动作。
    record_accountability(
        audit,
        principal,
        action="report_workflow",
        resource=wid,
        kind="create",
        detail=f"title={body.title}",
        record_id="acct-" + uuid.uuid4().hex[:12],
        ts=_ts(),
    )
    return {"workflow_id": wid, "status": "created"}


@router.get("/workflows")
def list_workflows(
    org_id: OrgHeader = None,
    status: Optional[str] = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.WORKFLOW_READ)
    ),
    db=Depends(get_db),
):
    """列出本组织治理工作流（默认排除已归档）。"""

    actor_id = principal.actor_id
    org_id = _org(principal, org_id)
    repo = GovernanceWorkflowRepository(db)
    rows = repo.list_workflows(org_id, status=status)
    audit = AuditService(org_id=org_id)
    audit.record_agent_governance_workflow_view(
        record_id="aud-" + uuid.uuid4().hex[:12],
        actor_id=actor_id,
        action="list_workflows",
        target=org_id,
        detail=_view_detail(principal, action="list_workflows", resource=org_id),
        ts=_ts(),
    )
    return [_wf_to_dict(r) for r in rows]


@router.get("/workflows/{workflow_id}")
def view_workflow(
    workflow_id: str,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.EXECUTION_READ)
    ),
    db=Depends(get_db),
):
    """查看单条工作流及其执行记录（组织隔离）。"""

    actor_id = principal.actor_id
    org_id = _org(principal, org_id)
    repo = GovernanceWorkflowRepository(db)
    wf = repo.get_workflow(workflow_id, org_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="工作流不存在或越权访问（红线⑤）")
    execs = repo.list_executions(workflow_id, org_id)
    audit = AuditService(org_id=org_id)
    audit.record_agent_governance_workflow_view(
        record_id="aud-" + uuid.uuid4().hex[:12],
        actor_id=actor_id,
        action="view_workflow",
        target=workflow_id,
        detail=_view_detail(
            principal, action="view_workflow", resource=workflow_id
        ),
        ts=_ts(),
    )
    return {"workflow": _wf_to_dict(wf), "executions": [_ex_to_dict(e) for e in execs]}


@router.post("/workflows/{workflow_id}/confirm-review")
def confirm_review(
    workflow_id: str,
    body: ConfirmReviewRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.REVIEW_CONFIRM)
    ),
    db=Depends(get_db),
):
    """真实人工研判确认（红线③/④/⑥）。

    - decision=confirmed → 状态推进到 human_confirmed；
    - rejected / need_more_info → 状态保持 under_review，仅记录研判结论。
    所有情形都落一条执行记录（actor_kind='user'）。
    """

    actor_id = principal.actor_id
    org_id = _org(principal, org_id)
    if body.decision not in GOVERNANCE_REVIEW_DECISION_VALUES:
        raise HTTPException(
            status_code=400,
            detail=f"非法 decision：{body.decision!r}（须为 {GOVERNANCE_REVIEW_DECISION_VALUES}）",
        )
    repo = GovernanceWorkflowRepository(db)
    new_status = "human_confirmed" if body.decision == "confirmed" else None
    try:
        if new_status:
            repo.update_status(
                workflow_id, org_id, status=new_status, actor_id=actor_id
            )
        ex = GovernanceExecutionRecordDB(
            record_id="ex-" + uuid.uuid4().hex[:12],
            workflow_id=workflow_id,
            org_id=org_id,
            action="confirm_review",
            actor=actor_id,
            actor_kind="user",
            timestamp=_ts(),
            result=body.reason,
            note="",
            decision=body.decision,
            source="human_ui",
            source_chain=["human_ui"],
            audit_record_id="",
            audit_category="agent_governance_workflow_review",
        )
        repo.add_execution(ex)
    except GovernanceRepositoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit = AuditService(org_id=org_id)
    audit.record_agent_governance_workflow_review(
        record_id="aud-" + uuid.uuid4().hex[:12],
        actor_id=actor_id,
        action="confirm_review",
        target=workflow_id,
        detail=f"decision={body.decision};reason={body.reason}",
        ts=_ts(),
    )
    record_accountability(
        audit,
        principal,
        action="confirm_review",
        resource=workflow_id,
        kind="review",
        detail=f"decision={body.decision};reason={body.reason}",
        record_id="acct-" + uuid.uuid4().hex[:12],
        ts=_ts(),
    )
    wf = repo.get_workflow(workflow_id, org_id)
    return {"workflow_id": workflow_id, "status": wf.status if wf else None}


@router.post("/workflows/{workflow_id}/submit-result")
def submit_result(
    workflow_id: str,
    body: SubmitResultRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.EXECUTION_SUBMIT)
    ),
    db=Depends(get_db),
):
    """真实人工提交执行结果（红线⑥）。

    状态推进到 in_progress（真实人工正在处置）；结果文本落执行记录。
    """

    actor_id = principal.actor_id
    org_id = _org(principal, org_id)
    repo = GovernanceWorkflowRepository(db)
    try:
        repo.update_status(
            workflow_id, org_id, status="in_progress", actor_id=actor_id
        )
        ex = GovernanceExecutionRecordDB(
            record_id="ex-" + uuid.uuid4().hex[:12],
            workflow_id=workflow_id,
            org_id=org_id,
            action="submit_result",
            actor=actor_id,
            actor_kind="user",
            timestamp=_ts(),
            result=body.result,
            note=body.note,
            decision=body.decision,
            source="human_ui",
            source_chain=["human_ui"],
            audit_record_id="",
            audit_category="agent_governance_workflow_execution",
        )
        repo.add_execution(ex)
    except GovernanceRepositoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit = AuditService(org_id=org_id)
    audit.record_agent_governance_workflow_execution(
        record_id="aud-" + uuid.uuid4().hex[:12],
        actor_id=actor_id,
        action="submit_result",
        target=workflow_id,
        detail=f"result={body.result[:120]}",
        ts=_ts(),
    )
    record_accountability(
        audit,
        principal,
        action="submit_result",
        resource=workflow_id,
        kind="execution",
        detail=f"result={body.result[:120]}",
        record_id="acct-" + uuid.uuid4().hex[:12],
        ts=_ts(),
    )
    wf = repo.get_workflow(workflow_id, org_id)
    return {"workflow_id": workflow_id, "status": wf.status if wf else None}


@router.post("/workflows/{workflow_id}/close")
def close_workflow(
    workflow_id: str,
    body: CloseWorkflowRequest,
    org_id: OrgHeader = None,
    principal: GovernancePrincipal = Depends(
        require_governance_permission(GovernancePermission.WORKFLOW_CLOSE)
    ),
    db=Depends(get_db),
):
    """真实人工闭环工作流（→ completed，红线④/⑥）。

    这是人工责任闭环，不是 AI 自动关闭；必须由真实 USER 发起。
    """

    actor_id = principal.actor_id
    org_id = _org(principal, org_id)
    repo = GovernanceWorkflowRepository(db)
    try:
        repo.close_workflow(workflow_id, org_id, actor_id=actor_id, note=body.note)
    except GovernanceRepositoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit = AuditService(org_id=org_id)
    audit.record_agent_governance_workflow_execution(
        record_id="aud-" + uuid.uuid4().hex[:12],
        actor_id=actor_id,
        action="close_workflow",
        target=workflow_id,
        detail=f"note={body.note[:120]}",
        ts=_ts(),
    )
    record_accountability(
        audit,
        principal,
        action="close_workflow",
        resource=workflow_id,
        kind="execution",
        detail=f"note={body.note[:120]}",
        record_id="acct-" + uuid.uuid4().hex[:12],
        ts=_ts(),
    )
    wf = repo.get_workflow(workflow_id, org_id)
    return {"workflow_id": workflow_id, "status": wf.status if wf else None}
