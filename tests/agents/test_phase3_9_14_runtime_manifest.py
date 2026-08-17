"""Phase 3.9.14 —— Runtime Manifest & Deployment Adapter fail-closed 测试（T44 覆盖）。

断言：
- 8 个 External Resource 全部 PENDING（未真实供给）；
- 13 项 Runtime Qualification 全部 NOT_EXECUTED（plan-only）；
- engineering_enabled=False / is_production=False / real_apply_allowed=False；
- 清单哈希确定性；
- 部署适配器仅产出 plan-only 计划，绝不 apply（本模块不定义 apply 方法）。
"""

from __future__ import annotations

from pathlib import Path

from agents.external_staging_runtime.deployment_adapter import StagingRuntimeDeploymentAdapter
from agents.external_staging_runtime.runtime_manifest import (
    build_staging_runtime_manifest,
    EXTERNAL_RESOURCE_KINDS,
    RUNTIME_QUALIFICATION_CHECKS,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STAGING_DIR = _REPO_ROOT / "infrastructure" / "staging"


def test_manifest_resource_count_and_pending():
    m = build_staging_runtime_manifest(_STAGING_DIR)
    assert len(m.external_resources) == 8 == len(EXTERNAL_RESOURCE_KINDS)
    for r in m.external_resources:
        assert r.status == "PENDING_EXTERNAL_STAGING_RESOURCE"
        assert r.registered is False
        assert r.provisioned is False
        assert r.verified is False


def test_manifest_qualification_count_and_not_executed():
    m = build_staging_runtime_manifest(_STAGING_DIR)
    assert len(m.runtime_qualifications) == 13 == len(RUNTIME_QUALIFICATION_CHECKS)
    for q in m.runtime_qualifications:
        assert q.status == "NOT_EXECUTED"
        assert q.executed is False
        assert q.result == "PLAN_ONLY"


def test_manifest_fail_closed_invariants():
    m = build_staging_runtime_manifest(_STAGING_DIR)
    assert m.engineering_enabled is False
    assert m.is_production is False
    assert m.real_apply_allowed is False
    assert m.real_execution_allowed is False
    assert m.deployment_mode == "PLAN_ONLY"
    assert m.iac_executable is True  # 第一优先级：IaC 已可执行


def test_manifest_hash_deterministic():
    h1 = build_staging_runtime_manifest(_STAGING_DIR).compute_hash()
    h2 = build_staging_runtime_manifest(_STAGING_DIR).compute_hash()
    assert h1 == h2
    assert len(h1) == 64  # SHA-256


def test_adapter_plan_only_never_applies():
    adapter = StagingRuntimeDeploymentAdapter(_STAGING_DIR)
    plan = adapter.plan()
    assert plan.plan_only is True
    assert plan.real_apply_allowed is False
    assert plan.iac_executable is True
    assert plan.external_resource_count == 8
    assert plan.runtime_qualification_count == 13
    assert plan.manifest_hash == build_staging_runtime_manifest(_STAGING_DIR).compute_hash()
    # 适配器刻意不提供 apply / deploy 方法（fail-closed by construction）
    assert not hasattr(adapter, "apply")
    assert not hasattr(adapter, "deploy")


def test_adapter_gate_fail_closed():
    adapter = StagingRuntimeDeploymentAdapter(_STAGING_DIR)
    gate = adapter.validate_gate()
    assert gate["real_apply_allowed"] is False
    assert gate["real_execution_allowed"] is False
    assert gate["engineering_enabled"] is False
    assert gate["is_production"] is False
    assert gate["gate"] == "PLAN_ONLY"
