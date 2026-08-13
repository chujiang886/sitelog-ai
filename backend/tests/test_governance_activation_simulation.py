"""Phase 3.9.8 T13/T16：生产激活干跑模拟 API 测试（simulation-only，红线守约）。

重点断言：
- 所有响应携带 simulation_only=true；
- run 报告 production_activated/real_signoff_count/engineering_enabled 恒为红线值；
- 绝不提供 /activate /deploy-production /go（路由不应存在）。
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def sim_env(governance_env):
    """复用治理测试环境，暴露 client + 治理管理员 token。"""

    return governance_env


def _g(path: str) -> str:
    return f"/governance/activation/simulation{path}"


def test_capability_marks_simulation_only(sim_env):
    client = sim_env["client"]
    headers = sim_env["bearer"](sim_env["admin_token"])
    resp = client.get(_g("/"), headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["simulation_only"] is True
    assert body["not_production"] is True
    assert "POST /governance/activation/activate" in body["forbidden_endpoints"]
    assert body["red_lines"]["production_activated"] is False
    assert body["red_lines"]["engineering_enabled"] is False


def test_scenarios_list_14(sim_env):
    client = sim_env["client"]
    headers = sim_env["bearer"](sim_env["admin_token"])
    resp = client.get(_g("/scenarios"), headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["simulation_only"] is True
    assert body["count"] == 14
    assert len(body["scenarios"]) == 14


def test_negative_paths_list_12(sim_env):
    client = sim_env["client"]
    headers = sim_env["bearer"](sim_env["admin_token"])
    resp = client.get(_g("/negative-paths"), headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["simulation_only"] is True
    assert body["count"] == 12
    # 每条负路径都应被 reject（fail-closed）。
    for p in body["negative_paths"]:
        assert p["rejected"] is True, p


def test_run_dry_run_and_report(sim_env):
    client = sim_env["client"]
    headers = sim_env["bearer"](sim_env["admin_token"])
    resp = client.post(_g("/run"), json={"scenario": "production_activation_full_dry_run"}, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["simulation_only"] is True
    sim_id = body["simulation_id"]
    report = body["report"]
    # 红线守约：报告永不含放行效力。
    assert report["production_activated"] is False
    assert report["real_signoff_count"] == 0
    assert report["engineering_enabled"] is False
    assert report["simulation_only"] is True
    assert report["status"] in ("simulation_pass", "simulation_blocked")

    # 读取 latest 与按 id 读取，结果一致。
    latest = client.get(_g("/report/latest"), headers=headers)
    assert latest.status_code == 200
    assert latest.json()["report"]["simulation_id"] == sim_id

    by_id = client.get(_g(f"/report/{sim_id}"), headers=headers)
    assert by_id.status_code == 200
    assert by_id.json()["report"]["simulation_id"] == sim_id


def test_forbidden_activation_endpoints_absent(sim_env):
    client = sim_env["client"]
    headers = sim_env["bearer"](sim_env["admin_token"])
    # 真实 /activate /deploy-production /go 端点不应存在于本模拟路由（也不应存在于激活路由）。
    for ep in ("/governance/activation/activate", "/governance/activation/deploy-production",
               "/governance/activation/go"):
        r = client.post(ep, json={}, headers=headers)
        # 不存在 → 404（路由未注册），而非 200/执行。
        assert r.status_code == 404, (ep, r.status_code, r.text)


def test_unauthenticated_rejected(sim_env):
    client = sim_env["client"]
    resp = client.get(_g("/scenarios"))
    # 无 Bearer → 401/403（fail-closed）。
    assert resp.status_code in (401, 403), resp.status_code
