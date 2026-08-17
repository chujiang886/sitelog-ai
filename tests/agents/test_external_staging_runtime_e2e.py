"""Phase 3.9.14 —— External Staging Runtime E2E 层测试（T34-T39 支撑，fail-closed）。

覆盖：
- machine_package：确定性哈希 + validate_package 红线不变量 + 篡改即拒；
- readonly_api：7 个只读端点均含 fail-closed 标记 + 未知端点抛错；
- dashboard：只读聚合视图有效；
- api_contract：仅读、禁变更；
- self_audit：全部 fail-closed 不变量自审通过。
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.external_staging_runtime.api_contract import EXTERNAL_RUNTIME_API_CONTRACT  # noqa: E402
from agents.external_staging_runtime.dashboard import build_readonly_dashboard  # noqa: E402
from agents.external_staging_runtime.machine_package import (  # noqa: E402
    build_machine_package,
    validate_package,
)
from agents.external_staging_runtime.readonly_api import dispatch  # noqa: E402
from agents.external_staging_runtime.self_audit import run_self_audit  # noqa: E402

ENDPOINTS = ["status", "isolation", "qualification", "health", "e2e", "change-control", "evidence"]
FB_KEYS = {
    "engineering_enabled",
    "real_apply_allowed",
    "real_execution_allowed",
    "is_production",
    "contains_real_secret",
    "fabrication_free",
}


def test_machine_package_deterministic():
    pkg1 = build_machine_package()
    pkg2 = build_machine_package()
    assert pkg1["package_hash"] == pkg2["package_hash"]
    assert pkg1["deterministic"] is True
    assert "built_at" in pkg1  # metadata, not hashed


def test_machine_package_validate_passes():
    pkg = build_machine_package()
    res = validate_package(pkg)
    assert res["valid"] is True
    assert res["terminal_state"].startswith("PHASE_3_9_14_")


def test_machine_package_validate_rejects_tamper():
    pkg = build_machine_package()
    # 篡改 engineering_enabled
    bad = copy.deepcopy(pkg)
    bad["package"]["engineering_enabled"] = True
    with pytest.raises(AssertionError):
        validate_package(bad)
    # 篡改哈希
    bad2 = copy.deepcopy(pkg)
    bad2["package_hash"] = "0" * 64
    with pytest.raises(AssertionError):
        validate_package(bad2)
    # 注入伪造 GO
    bad3 = copy.deepcopy(pkg)
    bad3["package"]["layers"]["change_control"]["is_go_or_approved"] = True
    with pytest.raises(AssertionError):
        validate_package(bad3)


def test_package_no_generated_at_in_hashed_content():
    import json

    pkg = build_machine_package()
    assert "generated_at" not in json.dumps(pkg["package"])


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_readonly_endpoint_present_and_fail_closed(endpoint):
    d = dispatch(endpoint)
    assert d["endpoint"] == endpoint
    missing = FB_KEYS - set(d.keys())
    assert not missing, f"{endpoint} missing fail-closed keys: {missing}"
    assert d["engineering_enabled"] is False
    assert d["is_production"] is False
    assert d["real_apply_allowed"] is False
    assert d["contains_real_secret"] is False
    assert d["fabrication_free"] is True


def test_readonly_unknown_endpoint_raises():
    with pytest.raises(KeyError):
        dispatch("does-not-exist")


def test_dashboard_valid():
    dash = build_readonly_dashboard()
    assert dash["package_valid"] is True
    assert len(dash["layers"]) == 7
    assert dash["engineering_enabled"] is False
    assert dash["real_apply_allowed"] is False


def test_api_contract_readonly():
    c = EXTERNAL_RUNTIME_API_CONTRACT
    assert c["real_execution_allowed"] is False
    assert c["real_apply_allowed"] is False
    assert c["engineering_enabled"] is False
    assert c["is_production"] is False
    assert len(c["endpoints"]) == 7
    assert all(not e.get("mutates") for e in c["endpoints"])
    assert len(c["forbidden"]) > 0


def test_self_audit_passes():
    rep = run_self_audit()
    assert rep.passed is True
    assert len(rep.checks) == 7
    assert all(c.passed for c in rep.checks)
    assert rep.terminal_state.startswith("PHASE_3_9_14_")
