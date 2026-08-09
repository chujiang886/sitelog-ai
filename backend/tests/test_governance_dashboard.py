"""Phase 3.8.26 治理驾驶舱 FastAPI 路由测试（TestClient）。

验证 Task2 的 HTTP 端点：GET /governance/workflows|reviews|audit|summary、
POST /governance/review/confirm，以及「强制 USER」红线（缺头 / 非 user 头 → 403/422）。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.governance_dashboard import (
    _build_demo_service,
    set_dashboard_service,
)

USER_HEADERS = {"x-actor-id": "governor-1", "x-actor-kind": "user"}


@pytest.fixture
def client():
    app = FastAPI()
    # 局部引入以避免触发完整 app.main（含 DB 路由）的副作用。
    from app.api.governance_dashboard import router

    app.include_router(router)
    svc = _build_demo_service()
    svc._orchestrator.register_candidate(
        workflow_id="gw-1", source_type="assistant_draft", source_id="ans-1",
        title="密封胶核查", source_facts=["f1"], references=["r1"],
    )
    svc._orchestrator.submit_for_review(workflow_id="gw-1", actor_id="ai")
    set_dashboard_service(svc)
    with TestClient(app) as c:
        yield c


def test_workflows_requires_user_header(client):
    # 缺 x-actor-id（必填头）→ 422
    r = client.get("/governance/workflows")
    assert r.status_code in (401, 403, 422)


def test_confirm_review_rejects_non_user(client):
    r = client.post(
        "/governance/review/confirm",
        headers={"x-actor-id": "ai-1", "x-actor-kind": "ai"},
        json={"workflow_id": "gw-1", "decision": "confirmed", "reason": "x"},
    )
    assert r.status_code == 403


def test_list_pending_reviews(client):
    r = client.get("/governance/reviews", headers=USER_HEADERS)
    assert r.status_code == 200
    assert any(w["workflow_id"] == "gw-1" for w in r.json())


def test_summary(client):
    r = client.get("/governance/summary", headers=USER_HEADERS)
    assert r.status_code == 200
    assert r.json()["pending_review"] == 1


def test_confirm_review_via_http(client):
    r = client.post(
        "/governance/review/confirm", headers=USER_HEADERS,
        json={"workflow_id": "gw-1", "decision": "confirmed", "reason": "经核查属实"},
    )
    assert r.status_code == 200
    assert r.json()["decision"] == "confirmed"
    # 再次查询执行状态，确认已推进
    r2 = client.get("/governance/workflows/gw-1", headers=USER_HEADERS)
    assert r2.status_code == 200
    assert r2.json()["status"] == "human_confirmed"


def test_audit_records_via_http(client):
    client.post(
        "/governance/review/confirm", headers=USER_HEADERS,
        json={"workflow_id": "gw-1", "decision": "confirmed", "reason": "ok"},
    )
    r = client.get("/governance/audit?limit=50", headers=USER_HEADERS)
    assert r.status_code == 200
    assert len(r.json()) >= 2
