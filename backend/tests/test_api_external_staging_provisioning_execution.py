"""Phase 3.9.13 —— 供给执行 API 测试（fail-closed）。

覆盖 5 个只读 GET 端点：/status /resources /iac-readiness /apply-gate /evidence。
规则：所有响应 engineering_enabled=false / real_execution_allowed=false /
contains_real_secret=false / fabrication_free=true；8 资源全 pending；apply gate 永不 GO。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

PREFIX = "/api/v1/external-staging-provisioning-execution"
ALLOWED_APPLY_GATE = {
    "blocked",
    "plan_only",
    "pending_human_authorization",
    "authorized_for_external_staging_apply",
}


def test_status():
    r = client.get(f"{PREFIX}/status")
    assert r.status_code == 200
    d = r.json()
    assert d["phase"] == "3.9.13"
    assert d["terminal_state"] == "EXTERNAL_STAGING_PROVISIONING_EXECUTION_BUILT_NO_GO"
    assert d["engineering_enabled"] is False
    assert d["real_execution_allowed"] is False
    assert d["total_resources"] == 8
    for k in ("provisioned", "registered", "connected", "isolated", "qualified"):
        assert d[k] == 0
    assert d["any_real_progress"] is False
    assert d["apply_gate_status"] == "pending_human_authorization"
    assert d["dual_key_authorized"] is False
    assert d["fabrication_free"] is True
    assert d["contains_real_secret"] is False


def test_resources_all_pending():
    r = client.get(f"{PREFIX}/resources")
    assert r.status_code == 200
    d = r.json()
    assert d["engineering_enabled"] is False
    assert d["real_execution_allowed"] is False
    assert d["total"] == 8
    assert d["all_pending"] is True
    assert len(d["resources"]) == 8
    assert d["contains_real_secret"] is False


def test_iac_readiness_no_real_execution():
    r = client.get(f"{PREFIX}/iac-readiness")
    assert r.status_code == 200
    d = r.json()
    assert d["real_execution_allowed"] is False
    assert d["contains_real_secret"] is False
    assert len(d["modules"]) == 8


def test_apply_gate_never_go():
    r = client.get(f"{PREFIX}/apply-gate")
    assert r.status_code == 200
    d = r.json()
    assert d["engineering_enabled"] is False
    assert d["apply_gate_status"] in ALLOWED_APPLY_GATE
    assert d["apply_gate_is_go"] is False
    assert d["dual_key_authorized"] is False
    assert d["real_execution_allowed"] is False
    assert d["contains_real_secret"] is False


def test_evidence_fabrication_free():
    r = client.get(f"{PREFIX}/evidence")
    assert r.status_code == 200
    d = r.json()
    assert d["engineering_enabled"] is False
    assert d["fabrication_free"] is True
    assert len(d["machine_package_hash"]) == 64
    assert d["evidence"]["fabrication_free"] is True
    assert len(d["evidence"]["records"]) == 8
    assert d["contract"]["real_execution_allowed"] is False
    assert d["real_execution_allowed"] is False
    assert d["contains_real_secret"] is False
