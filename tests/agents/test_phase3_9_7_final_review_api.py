"""Phase 3.9.7 T17 —— Layer C 最终人工评审只读层 fail-closed 测试套件。

守 fail-closed 纪律（与 3.9.6 同源）：AI 永不宣称 GO / APPROVED / PRODUCTION_READY /
自动激活；任何 fail-closed 行为变更均不得用 skip / xfail 绕过至绿（红线⑧）。

覆盖：
- 9 个 Layer C 路由全部存在、均为 GET、无 /activate / /deploy-production；
- 9 个 Layer C 操作在 T13 权限边界中统一映射 RELEASE_READ（fail-closed，
  AI / SYSTEM 主体一律 403，且全部为只读、不在 _WRITE_OPERATIONS）；
- ``_final_review_dossier`` 只读装配在 BUILT_NO_GO 态恒 ``engineering_enabled=False``，
  且 readiness / signoff / completeness / verification / handoff 全部处于"请人来判 /
  未就绪"态，绝不翻转开关、不宣布 GO、不激活（红线①②④⑤⑨⑩）。
"""

from __future__ import annotations

from app.api.governance_activation import _final_review_dossier, router
from agents.enterprise.production_release.permission_boundary import (
    OPERATION_PERMISSION,
    ActivationOperation,
    _WRITE_OPERATIONS,
)

#: Layer C 路径 → T13 白名单操作（全部映射 RELEASE_READ）。
LAYER_C: dict[str, ActivationOperation] = {
    "/governance/activation/final-review/evidence-snapshot": ActivationOperation.VIEW_FINAL_REVIEW_EVIDENCE,
    "/governance/activation/final-review/completeness-matrix": ActivationOperation.VIEW_FINAL_REVIEW_COMPLETENESS,
    "/governance/activation/final-review/signoff-matrix": ActivationOperation.VIEW_FINAL_REVIEW_SIGNOFF_MATRIX,
    "/governance/activation/final-review/signoff-conflicts": ActivationOperation.VIEW_FINAL_REVIEW_SIGNOFF_CONFLICTS,
    "/governance/activation/final-review/evidence-drift": ActivationOperation.VIEW_FINAL_REVIEW_EVIDENCE_DRIFT,
    "/governance/activation/final-review/review-packet": ActivationOperation.BUILD_FINAL_REVIEW_PACKET,
    "/governance/activation/final-review/readiness": ActivationOperation.EVALUATE_FINAL_REVIEW_READINESS,
    "/governance/activation/final-review/verify-decision": ActivationOperation.VERIFY_HUMAN_FINAL_DECISION,
    "/governance/activation/final-review/handoff-package": ActivationOperation.BUILD_FINAL_ACTIVATION_HANDOFF,
}


def _route_map() -> dict:
    return {getattr(r, "path", ""): r for r in router.routes}


def test_layer_c_routes_exist_and_get_only() -> None:
    routes = _route_map()
    for path in LAYER_C:
        assert path in routes, f"missing Layer C route: {path}"
        r = routes[path]
        methods = getattr(r, "methods", set())
        assert "GET" in methods, f"{path}: expected GET, got {methods}"
        assert not path.endswith("/activate")
        assert not path.endswith("/deploy-production")


def test_layer_c_operations_all_release_read() -> None:
    for op in LAYER_C.values():
        assert OPERATION_PERMISSION[op] == "governance:release:read", (
            f"{op.value} must map to RELEASE_READ (fail-closed read-only)"
        )


def test_layer_c_operations_not_write() -> None:
    for op in LAYER_C.values():
        assert op not in _WRITE_OPERATIONS, f"{op.value} must be read-only (not in _WRITE_OPERATIONS)"


def test_layer_c_dossier_fail_closed() -> None:
    d = _final_review_dossier("RC-3.9.6", "org-test")

    # 顶层恒 false（红线①）。
    assert d["engineering_enabled"] is False

    # 只读装配的必需键齐全（供前端 T15 消费）。
    for key in (
        "evidence_snapshot",
        "completeness_matrix",
        "signoff_matrix",
        "conflicts",
        "drift",
        "review_packet",
        "readiness",
        "abort_catalog",
        "verification",
        "handoff_package",
    ):
        assert key in d, f"dossier missing key: {key}"

    # readiness 处于"请人来判 / 未就绪"，绝非 GO / activated。
    assert d["readiness"]["state"] == "signoff_incomplete"
    assert d["readiness"]["engineering_enabled_false"] is True

    # 四角色签署结构未就位（红线⑩：AI 不构造 RECORDED）。
    assert d["signoff_matrix"]["signoff_complete"] is False
    assert set(d["signoff_matrix"]["missing_roles"]) == {
        "production-owner",
        "release-manager",
        "security-owner",
        "auditor",
    }

    # 证据完整性未就绪（不含 AI 审批）。
    assert d["completeness_matrix"]["is_evidence_complete"] is False

    # 人工最终裁决校验在 BUILT_NO_GO 态为 invalid（红线②：不输出 approved）。
    assert d["verification"]["status"] == "invalid"
    assert d["verification"]["engineering_enabled_remains_false"] is True

    # 交接包执行状态恒 pending_human_terminal_action（红线⑤：禁部署 / 激活）。
    assert d["handoff_package"]["execution_status"] == "pending_human_terminal_action"
    assert d["handoff_package"]["engineering_enabled_at_handoff"] is False

    # 中止条件目录就绪（10 项）。
    assert d["abort_catalog"]["condition_count"] == 10

    # 干净态下无冲突、无漂移（报告而非自动处置，红线⑨⑩）。
    assert d["conflicts"] == []
    assert d["drift"] == []
