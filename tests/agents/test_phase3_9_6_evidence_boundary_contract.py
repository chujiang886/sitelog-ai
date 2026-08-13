"""Phase 3.9.6-R1 边界对账契约测试：机器闸门 ↔ 复核包 ↔ API 契约 ↔ 人工清单 1:1 一致。

这些测试是 R1 对账的机器护栏：任何"事实漂移"（路由数、阻断器/待核验数、Layer B 归属、
放行词元、人工清单映射）都会让本套件失败，从而阻止带漂移的提交进入收口。

全部 fail-closed：绝不 skip / xfail 到绿（红线⑧）。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agents.enterprise.production_release import activation_readiness as ar  # noqa: E402
from agents.enterprise.production_release.permission_boundary import (  # noqa: E402
    ActivationPermissionBoundary,
)

PACKET_PATH = ROOT / ".ai" / "release-gate" / "production_activation_review_packet.json"
CONTRACT_PATH = ROOT / ".ai" / "baselines" / "production_activation_api_contract.json"
CHECKLIST_PATH = (
    ROOT / ".ai" / "runbooks" / "production_activation" / "HUMAN_ACTIVATION_CHECKLIST.md"
)

EXPECTED_BLOCKERS = {
    "B1-real-idp",
    "B2-real-secrets",
    "B3-real-telemetry",
    "B4-real-alert-routing",
    "B5-four-role-signoff",
    "B6-real-topology",
}
EXPECTED_PENDING = {
    "PV1-real-idp",
    "PV2-real-secrets",
    "PV3-real-telemetry",
    "PV4-real-alert",
    "PV5-real-topology",
    "PV6-engineering-enabled",
}


def _machine_gate_blockers() -> set[str]:
    return {b.blocker_id for b in ar.build_default_activation_blockers()}


def _machine_gate_pending() -> set[str]:
    return {p.id for p in ar.build_default_pending_verification_registry()}


# --------------------------------------------------------------------------- #
# 1) 机器闸门自身：B1-B6 / PV1-PV6 一个不多一个不少（SSOT）
# --------------------------------------------------------------------------- #
def test_machine_gate_blockers_b1_b6() -> None:
    ids = _machine_gate_blockers()
    assert len(ids) == 6
    assert ids == EXPECTED_BLOCKERS


def test_machine_gate_pending_pv1_pv6() -> None:
    ids = _machine_gate_pending()
    assert len(ids) == 6
    assert ids == EXPECTED_PENDING


# --------------------------------------------------------------------------- #
# 2) 复核包必须 1:1 镜像机器闸门（B1-B6 / PV1-PV6）
# --------------------------------------------------------------------------- #
def test_packet_mirrors_machine_gate_1to1() -> None:
    assert PACKET_PATH.exists(), f"packet missing: {PACKET_PATH}"
    pkt = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
    pkt_blockers = {b["blocker_id"] for b in pkt["blockers"]}
    pkt_pending = {p["id"] for p in pkt["pending_verification"]}
    assert pkt_blockers == _machine_gate_blockers(), "packet blockers != machine gate B1-B6"
    assert pkt_pending == _machine_gate_pending(), "packet pending != machine gate PV1-PV6"
    assert len(pkt_blockers) == 6
    assert len(pkt_pending) == 6


# --------------------------------------------------------------------------- #
# 3) 复核包 schema 2.0.0 + 红线 + 篡改哈希
# --------------------------------------------------------------------------- #
def test_packet_schema_and_red_lines() -> None:
    pkt = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
    assert str(pkt["schema_version"]).startswith("2."), "packet schema must be 2.x"
    assert (
        pkt["terminal_status"] == "PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO"
    )
    assert pkt["engineering_enabled"] is False
    assert pkt["contains_real_secret"] is False
    assert "layer_b" in pkt, "packet must document Layer B (closure-report drift fix)"
    assert len(pkt["layer_b"]["boundary"]["operations"]) >= 7


def test_packet_tamper_evident_sha256() -> None:
    pkt = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
    canonical = {k: v for k, v in pkt.items() if k != "packet_sha256"}
    expect = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()
    assert pkt["packet_sha256"] == expect, "packet_sha256 mismatch — regen needed"


# --------------------------------------------------------------------------- #
# 4) API 契约：15 路由，Layer A+B，无放行端点，权限白名单
# --------------------------------------------------------------------------- #
def test_api_contract_route_count_and_layers() -> None:
    assert CONTRACT_PATH.exists(), f"contract missing: {CONTRACT_PATH}"
    c = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert c["route_count"] == 24, f"expected 24 routes, got {c['route_count']}"
    routes = c["routes"]
    assert len(routes) == 24
    layer_b = {r["path"] for r in routes if r["layer"] == "B"}
    assert len(layer_b) == 7, f"expected 7 distinct Layer B paths, got {len(layer_b)}"
    layer_c = {r["path"] for r in routes if r["layer"] == "C"}
    assert len(layer_c) == 9, f"expected 9 distinct Layer C final-review paths, got {len(layer_c)}"
    for r in routes:
        assert not r["path"].endswith("/activate")
        assert not r["path"].endswith("/deploy-production")
        assert r["permission"] in ("RELEASE_READ", "RELEASE_SIGNOFF")
        assert r["actor_kind"] == "user"
        assert r["csrf_protected"] is True


# --------------------------------------------------------------------------- #
# 5) 权限边界（T12）：7 操作白名单，deny-by-default
# --------------------------------------------------------------------------- #
def test_permission_boundary_whitelist() -> None:
    boundary = ActivationPermissionBoundary(rc_id="RC-3.9.6").describe()
    ops = boundary["operations"]
    assert len(ops) == 16
    for op in ops:
        assert op["required_actor_kind"] == "user"
        assert op["required_permission"] in (
            "governance:release:read",
            "governance:release:signoff",
        )


# --------------------------------------------------------------------------- #
# 6) 人工清单必须 1:1 映射机器闸门 + 硬规则门禁 engineering_enabled
# --------------------------------------------------------------------------- #
def test_checklist_maps_machine_gate_and_hard_rule() -> None:
    assert CHECKLIST_PATH.exists(), f"checklist missing: {CHECKLIST_PATH}"
    text = CHECKLIST_PATH.read_text(encoding="utf-8")
    for bid in EXPECTED_BLOCKERS:
        assert bid in text, f"checklist missing blocker mapping: {bid}"
    for pid in EXPECTED_PENDING:
        assert pid in text, f"checklist missing pending mapping: {pid}"
    # 硬规则：engineering_enabled 置位前置条件为闸门 READY_FOR_HUMAN_SIGNOFF
    assert "READY_FOR_HUMAN_SIGNOFF" in text
    assert "engineering_enabled" in text
    # 禁止项：不提供 /activate 或 /deploy-production
    assert "/activate" in text
    assert "/deploy-production" in text
