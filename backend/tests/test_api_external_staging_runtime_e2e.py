"""Phase 3.9.14 —— 运行时部署与端到端资格认定 API 测试（fail-closed）。

覆盖 7 个只读 GET 端点：/status /isolation /qualification /health /e2e
/change-control /evidence。
规则：所有响应 engineering_enabled=False / real_execution_allowed=False /
real_apply_allowed=False / is_production=False / contains_real_secret=False /
fabrication_free=True；8 资源全 pending；变更闸门永不 GO。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

PREFIX = "/api/v1/external-staging-runtime-e2e"
TERMINAL_STATE = "PHASE_3_9_14_EXTERNAL_STAGING_RUNTIME_E2E_QUALIFICATION_BUILT_NO_GO"
ALLOWED_APPLY_GATE = {
    "pending_human_authorization",
    "authorized_awaiting_apply",
    "blocked",
    "denied",
}


def _assert_common(d: dict):
    assert d["phase"] == "3.9.14"
    assert d["terminal_state"] == TERMINAL_STATE
    assert d["engineering_enabled"] is False
    assert d["real_execution_allowed"] is False
    assert d["real_apply_allowed"] is False
    assert d["is_production"] is False
    assert d["contains_real_secret"] is False
    assert d["fabrication_free"] is True
    assert isinstance(d.get("source_commit"), str) and d["source_commit"]


def test_status():
    r = client.get(f"{PREFIX}/status")
    assert r.status_code == 200
    d = r.json()
    _assert_common(d)
    assert len(d["package_hash"]) == 64
    assert d["deterministic"] is True
    assert d["total_resources"] == 8
    assert d["resources_pending"] == 8
    assert d["layer_count"] == 7


def test_isolation_no_production_leakage():
    r = client.get(f"{PREFIX}/isolation")
    assert r.status_code == 200
    d = r.json()
    _assert_common(d)
    assert d["passed"] is True
    assert d["domain_count"] == 9
    assert d["production_leakage"] is False
    assert d["real_resources_present"] == 0


def test_qualification_structural_only():
    r = client.get(f"{PREFIX}/qualification")
    assert r.status_code == 200
    d = r.json()
    _assert_common(d)
    assert d["total"] == 13
    assert d["code_verified_count"] == 13
    assert d["runtime_executed_count"] == 0
    assert d["is_production"] is False
    assert d["real_apply_allowed"] is False


def test_health_plan_only():
    r = client.get(f"{PREFIX}/health")
    assert r.status_code == 200
    d = r.json()
    _assert_common(d)
    assert d["overall_status"] == "PLAN_ONLY"


def test_e2e_structural_ok():
    r = client.get(f"{PREFIX}/e2e")
    assert r.status_code == 200
    d = r.json()
    _assert_common(d)
    assert d["terminal_state"] == TERMINAL_STATE
    assert len(d["steps"]) == 6
    assert d["passed"] is True


def test_change_control_never_go():
    r = client.get(f"{PREFIX}/change-control")
    assert r.status_code == 200
    d = r.json()
    _assert_common(d)
    assert d["is_go_or_approved"] is False
    assert d["apply_gate_state"] in ALLOWED_APPLY_GATE
    assert d["dual_key_authorized"] is False
    assert d["human_actor_required"] is True
    assert d["four_role_signoff_required"] is True


def test_evidence_no_leakage():
    r = client.get(f"{PREFIX}/evidence")
    assert r.status_code == 200
    d = r.json()
    _assert_common(d)
    assert d["production_leakage"] is False
    assert len(d["items"]) == 7
    assert d["violations"] == []
    assert len(d["integrity_hash"]) == 64


def test_forbidden_methods_rejected():
    # 禁 POST/PUT/DELETE：路由仅注册 GET，其它方法应 405。
    for method in ("post", "put", "delete"):
        fn = getattr(client, method)
        r = fn(f"{PREFIX}/status")
        assert r.status_code in (404, 405), f"unexpected {method} status {r.status_code}"
