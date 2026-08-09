"""Phase 3.8.26 治理持久化与人工操作界面层 —— 八类 fail-closed 测试（Task 8）。

八类断言（任意一类失败即说明红线被穿透）：
① DB 级：status 六态白名单 CHECK —— 任何 auto_* 写入被拒；
② DB 级：requires_human_confirmation 恒真 CHECK —— 置 False 被拒；
③ DB 级：execution.actor_kind='user' CHECK —— AI 登记执行被拒；
④ 结构级：两表不得出现 forbidden 列名（engineering_approved/approved/quote/sign…）；
⑤ Repository：组织隔离 —— 越权组织取不到、空 org 抛错；
⑥ 人类门控：AI 身份在 repo 与 API 两层均被拒（红线③/④/⑥）；
⑦ Repository：禁用态（forbidden status）在 repo 层被拒；
⑧ Audit：record_human_approval 结构性禁制 + WORKFLOW_VIEW/REVIEW/EXECUTION 复用。

DB 通过真实 Alembic 迁移（升级到 head）建表，确保测试的是生产形态 schema。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

BACKEND = Path(__file__).resolve().parents[1]
PY = sys.executable

# 把 backend/app 与 BOIP 根目录都纳入导入路径（agents 企业包）。
for p in (str(BACKEND), str(BACKEND.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

from agents.enterprise.audit import (  # noqa: E402
    AuditActionCategory,
    AuditService,
    EnterpriseRedLineViolationError,
)
from agents.enterprise.audit import AuditActorKind  # noqa: E402

from app.db.models.governance_workflow import (  # noqa: E402
    GOVERNANCE_WORKFLOW_FORBIDDEN_STATUS_VALUES,
    GovernanceExecutionRecordDB,
    GovernanceWorkflowRecord,
    _FORBIDDEN_COLUMN_NAMES,
)
from app.db.repositories.governance_workflow_repository import (  # noqa: E402
    GovernanceRepositoryError,
    GovernanceWorkflowRepository,
    OrgScopeError,
)
from app.api.governance_operations import router  # noqa: E402
from app.db.session import get_db  # noqa: E402


@pytest.fixture
def db_maker(tmp_path):
    """真实迁移建库，返回 sessionmaker（绑定到该临时库）。"""

    db_file = tmp_path / "gov_test.db"
    url = f"sqlite:///{db_file}"
    env = dict(os.environ, DATABASE_URL=url)
    # 跑真实 Alembic 迁移到 head（验证生产形态 schema + 约束）。
    subprocess.run(
        [PY, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND), env=env, check=True,
    )
    engine = create_engine(url, connect_args={"check_same_thread": False})
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    yield maker
    engine.dispose()


@pytest.fixture
def dbsession(db_maker):
    s = db_maker()
    yield s
    s.close()


@pytest.fixture
def api_client(db_maker):
    app = FastAPI()
    app.include_router(router)

    def _override():
        s = db_maker()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c


USER = {"x-actor-id": "user-chen", "x-actor-kind": "user"}
AI = {"x-actor-id": "ai-bot", "x-actor-kind": "ai"}


# --------------------------------------------------------------------------- #
# ① DB 级：status 六态白名单 CHECK                                             #
# --------------------------------------------------------------------------- #
def test_status_whitelist_enforced_db(dbsession):
    """任何 auto_* 状态写入被 CHECK 约束拒绝（红线③）。"""

    with pytest.raises(Exception):
        dbsession.execute(text(
            "INSERT INTO governance_workflow_records "
            "(workflow_id, status, source_id, org_id, created_at, updated_at, "
            ' "references", source_facts, human_notes) '
            "VALUES ('x1','auto_approved','s1','o1',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,"
            "'[]','[]','[]')"
        ))
        dbsession.commit()
    dbsession.rollback()
    # 确认行确实没写进去
    n = dbsession.execute(text(
        "SELECT COUNT(*) FROM governance_workflow_records WHERE workflow_id='x1'"
    )).scalar()
    assert n == 0


# --------------------------------------------------------------------------- #
# ② DB 级：requires_human_confirmation 恒真 CHECK                              #
# --------------------------------------------------------------------------- #
def test_requires_human_cannot_be_false_db(dbsession):
    dbsession.execute(text(
        "INSERT INTO governance_workflow_records "
        "(workflow_id, status, source_id, org_id, created_at, updated_at, "
        ' "references", source_facts, human_notes) '
        "VALUES ('x2','created','s2','o2',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,"
        "'[]','[]','[]')"
    ))
    dbsession.commit()
    # 试图把人工确认要求置 False —— 必须被 CHECK 拒绝（红线④）
    with pytest.raises(Exception):
        dbsession.execute(text(
            "UPDATE governance_workflow_records SET requires_human_confirmation=0 "
            "WHERE workflow_id='x2'"
        ))
        dbsession.commit()
    dbsession.rollback()


# --------------------------------------------------------------------------- #
# ③ DB 级：execution.actor_kind='user' CHECK                                   #
# --------------------------------------------------------------------------- #
def test_execution_actor_must_be_user_db(dbsession):
    dbsession.execute(text(
        "INSERT INTO governance_workflow_records "
        "(workflow_id, status, source_id, org_id, created_at, updated_at, "
        ' "references", source_facts, human_notes) '
        "VALUES ('x3','created','s3','o3',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,"
        "'[]','[]','[]')"
    ))
    dbsession.commit()
    with pytest.raises(Exception):
        dbsession.execute(text(
            "INSERT INTO governance_execution_records "
            "(record_id, workflow_id, org_id, action, actor, actor_kind, source, source_chain) "
            "VALUES ('e1','x3','o3','act','ai-bot','ai','src','[]')"
        ))
        dbsession.commit()
    dbsession.rollback()
    n = dbsession.execute(text(
        "SELECT COUNT(*) FROM governance_execution_records WHERE record_id='e1'"
    )).scalar()
    assert n == 0


# --------------------------------------------------------------------------- #
# ④ 结构级：两表不得含 forbidden 列名                                          #
# --------------------------------------------------------------------------- #
def test_no_forbidden_columns():
    wf_cols = {c.name for c in GovernanceWorkflowRecord.__table__.columns}
    ex_cols = {c.name for c in GovernanceExecutionRecordDB.__table__.columns}
    overlap = set(_FORBIDDEN_COLUMN_NAMES) & (wf_cols | ex_cols)
    assert not overlap, f"两表出现了红线禁列：{overlap}"


# --------------------------------------------------------------------------- #
# ⑤ Repository：组织隔离                                                       #
# --------------------------------------------------------------------------- #
def test_repository_org_isolation(dbsession):
    repo = GovernanceWorkflowRepository(dbsession)
    repo.save_workflow(GovernanceWorkflowRecord(
        workflow_id="w-iso", status="created", source_id="s", org_id="ORG-A",
        source_facts=[], references=[], human_notes=[],
    ))
    # 同组织可见
    assert repo.get_workflow("w-iso", "ORG-A") is not None
    # 越权组织不可见
    assert repo.get_workflow("w-iso", "ORG-B") is None
    # 空 org 直接报错
    with pytest.raises(OrgScopeError):
        repo.get_workflow("w-iso", "")
    # list 也隔离
    assert repo.list_workflows("ORG-B") == []


# --------------------------------------------------------------------------- #
# ⑥ 人类门控：AI 身份在 repo 与 API 两层均被拒                                 #
# --------------------------------------------------------------------------- #
def test_repo_rejects_ai_actor(dbsession):
    repo = GovernanceWorkflowRepository(dbsession)
    repo.save_workflow(GovernanceWorkflowRecord(
        workflow_id="w-ai", status="created", source_id="s", org_id="O",
        source_facts=[], references=[], human_notes=[],
    ))
    with pytest.raises(Exception):
        repo.update_status("w-ai", "O", status="in_progress",
                           actor_id="ai-bot", actor_kind=AuditActorKind.AI)


def test_api_rejects_ai_actor(api_client):
    r = api_client.get("/governance/ops/workflows", headers=AI)
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# ⑦ Repository：禁用态在 repo 层被拒                                           #
# --------------------------------------------------------------------------- #
def test_repo_rejects_forbidden_status(dbsession):
    repo = GovernanceWorkflowRepository(dbsession)
    repo.save_workflow(GovernanceWorkflowRecord(
        workflow_id="w-fb", status="created", source_id="s", org_id="O",
        source_facts=[], references=[], human_notes=[],
    ))
    with pytest.raises(GovernanceRepositoryError):
        repo.update_status("w-fb", "O", status="auto_approved", actor_id="user-x")
    # 备用：forbidden 列表中的其它项同样拒
    for fb in GOVERNANCE_WORKFLOW_FORBIDDEN_STATUS_VALUES[:3]:
        with pytest.raises(GovernanceRepositoryError):
            repo.update_status("w-fb", "O", status=fb, actor_id="user-x")


# --------------------------------------------------------------------------- #
# ⑧ Audit：record_human_approval 禁制 + VIEW/REVIEW/EXECUTION 复用             #
# --------------------------------------------------------------------------- #
def test_audit_forbids_record_human_approval():
    svc = AuditService(org_id="o-aud")
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.record_human_approval  # 结构性拦截（红线⑥）


def test_audit_workflow_categories_reuse():
    # ① VIEW 已新增，审计动作大类总数 68 → 69
    assert hasattr(AuditActionCategory, "AGENT_GOVERNANCE_WORKFLOW_VIEW")
    assert len(list(AuditActionCategory)) == 69
    svc = AuditService(org_id="o-aud")
    # ② 复用 REVIEW / EXECUTION / CREATE（三个已有大类）写入正确分类、actor=user
    r_rev = svc.record_agent_governance_workflow_review(record_id="r1", actor_id="u1")
    r_exe = svc.record_agent_governance_workflow_execution(record_id="r2", actor_id="u1")
    r_cre = svc.record_agent_governance_workflow_create(record_id="r3", actor_id="u1")
    r_viw = svc.record_agent_governance_workflow_view(record_id="r4", actor_id="u1")
    assert r_rev.category == AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_REVIEW
    assert r_exe.category == AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_EXECUTION
    assert r_cre.category == AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_CREATE
    assert r_viw.category == AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_VIEW
    for r in (r_rev, r_exe, r_cre, r_viw):
        assert r.actor_kind.value == "user"
