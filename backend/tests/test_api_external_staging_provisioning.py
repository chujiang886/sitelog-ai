"""Phase 3.9.12 —— 供给算子 API 测试（Tasks 28/29/30/31，fail-closed）。

覆盖：7 只读/登记路由 + 安全/成本/审计模块。
规则：所有响应 production=false / engineering_enabled=false / 无真实执行；
human-input-record 仅 USER 可登记、禁 AI、禁明文、禁非法 category。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

PREFIX = "/api/external-staging-provisioning"
ALLOWED_GATE = {"blocked", "pending_human_input", "ready_for_human_provisioning_review"}


def test_status():
    r = client.get(f"{PREFIX}/status")
    assert r.status_code == 200
    d = r.json()
    assert d["production"] is False
    assert d["engineering_enabled"] is False
    assert d["production_activation_prohibited"] is True
    assert d["pending_resources"] == 8
    assert d["operator_gate_status"] in ALLOWED_GATE


def test_bom():
    r = client.get(f"{PREFIX}/bom")
    assert r.status_code == 200
    d = r.json()
    assert d["production"] is False
    assert d["total"] == 8
    assert d["pending"] == 8
    assert all(res["status"] == "pending_external_staging_resource" for res in d["resources"])


def test_gate():
    r = client.get(f"{PREFIX}/gate")
    assert r.status_code == 200
    assert r.json()["operator_gate_status"] in ALLOWED_GATE


def test_iac_dry_run():
    r = client.get(f"{PREFIX}/iac-dry-run")
    assert r.status_code == 200
    d = r.json()
    assert d["all_ok"] is True
    assert d["credential_leak_hits"] == []
    assert len(d["count_zero_modules"]) == 4
    assert d["default_provider"] == "tencentcloud"


def test_package():
    r = client.get(f"{PREFIX}/package")
    assert r.status_code == 200
    d = r.json()
    assert d["phase"] == "3.9.12"
    assert d["terminal_state"] == "EXTERNAL_STAGING_PROVISIONING_OPERATOR_READY_BUILT_NO_GO"
    assert d["contains_real_secret"] is False
    assert d["engineering_enabled"] is False
    assert len(d["pending_resources"]) == 8


def test_runbook():
    r = client.get(f"{PREFIX}/runbook")
    assert r.status_code == 200
    d = r.json()
    assert d["production"] is False
    assert "provisioning_runbook" in d
    assert "cleanup_rollback_runbook" in d
    assert "human_input_table" in d


def test_human_record_ok():
    r = client.post(
        f"{PREFIX}/human-input-record",
        json={
            "record_id": "rec-1",
            "actor_kind": "USER",
            "actor_id": "u_123",
            "category": "external_staging_provisioning_runbook_viewed",
            "action": "view",
            "target": "docs/EXTERNAL_STAGING_PROVISIONING_RUNBOOK.md",
        },
    )
    assert r.status_code in (200, 202)
    d = r.json()
    assert d["accepted"] is True
    assert d["engineering_enabled_unchanged"] is False
    assert d["event"]["actor_kind"] == "USER"
    assert d["event"]["contains_real_secret"] is False


def test_human_record_rejects_ai():
    r = client.post(
        f"{PREFIX}/human-input-record",
        json={
            "record_id": "rec-2",
            "actor_kind": "AI",
            "actor_id": "ai_1",
            "category": "external_staging_provisioning_runbook_viewed",
        },
    )
    assert r.status_code == 403


def test_human_record_rejects_bad_category():
    r = client.post(
        f"{PREFIX}/human-input-record",
        json={
            "record_id": "rec-3",
            "actor_kind": "USER",
            "actor_id": "u_1",
            "category": "not_a_real_category",
        },
    )
    assert r.status_code == 400


def test_human_record_rejects_secret_in_detail():
    r = client.post(
        f"{PREFIX}/human-input-record",
        json={
            "record_id": "rec-4",
            "actor_kind": "USER",
            "actor_id": "u_1",
            "category": "external_staging_provisioning_runbook_viewed",
            "detail": "password=supersecret123",
        },
    )
    assert r.status_code == 400
