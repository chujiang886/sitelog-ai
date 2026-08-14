"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— T3 测试（Task 7-9）。

覆盖：
- Task 7 Staging Manifest：build 出非生产 manifest、require_non_production 拒绝 production。
- Task 8 Deployment Provider：plan() 返回人工步骤、apply() 永远拒绝真实部署。
- Task 9 Execution Scope：允许动作白名单、禁止动作黑名单、未知动作默认拒绝。

红线约定：不修改 engineering_enabled；需要模拟启用态时 monkeypatch red_line 函数。
"""

from __future__ import annotations

import pytest

from agents.staging_runtime.config import load_staging_identity, StagingResourceReadiness
from agents.staging_runtime.manifest import (
    build_staging_runtime_manifest,
    StagingRuntimeManifest,
    StagingManifestProductionError,
)
from agents.staging_runtime.deployment import (
    StagingDeploymentProvider,
    StagingDeploymentForbiddenError,
)
from agents.staging_runtime.execution_scope import (
    StagingExecutionScope,
    StagingExecutionScopeViolation,
    FORBIDDEN_PRODUCTION_ACTIONS,
    ALLOWED_STAGING_ACTIONS,
)
from agents.staging_runtime.environment import RuntimeEnvironment


@pytest.fixture
def identity():
    return load_staging_identity()


# ─────────────────────────── Task 7: Staging Manifest ─────────────────────────


def test_build_manifest_is_non_production(identity):
    manifest = build_staging_runtime_manifest(identity, secret_names=["llm_api_key"])
    assert isinstance(manifest, StagingRuntimeManifest)
    assert manifest.is_production is False
    assert manifest.non_production_bound is True
    assert manifest.environment == "local_staging"
    assert manifest.identity_fingerprint
    # secret_presence 仅记录是否配置（布尔），不泄露明文。
    assert manifest.secret_presence == {"llm_api_key": False}


def test_manifest_require_non_production_rejects_production():
    bad = StagingRuntimeManifest(
        environment="production",
        is_production=True,
        non_production_bound=False,
        identity_fingerprint="x",
        purpose="p",
    )
    with pytest.raises(StagingManifestProductionError):
        bad.require_non_production()


def test_manifest_resource_readiness_pending_by_default(identity):
    manifest = build_staging_runtime_manifest(identity)
    assert manifest.resource_readiness == StagingResourceReadiness.PENDING_EXTERNAL_STAGING_RESOURCE.value


# ───────────────────────── Task 8: Deployment Provider ────────────────────────


def test_deployment_plan_is_local_and_human_authorized(identity):
    provider = StagingDeploymentProvider(identity)
    plan = provider.plan()
    assert plan.is_production is False
    assert plan.requires_human_authorization is True
    assert any("人工" in s or "授权" in s for s in plan.steps)


def test_deployment_apply_always_forbidden(identity):
    provider = StagingDeploymentProvider(identity)
    with pytest.raises(StagingDeploymentForbiddenError):
        provider.apply()


# ───────────────────────── Task 9: Execution Scope ───────────────────────────


def test_scope_allows_whitelisted_staging_action(identity):
    scope = StagingExecutionScope(identity)
    scope.assert_permitted("validate_local_staging")
    assert scope.is_permitted("build_evidence_package") is True


def test_scope_forbids_production_action(identity):
    scope = StagingExecutionScope(identity)
    verdict = scope.check("deploy_production")
    assert verdict.permitted is False
    with pytest.raises(StagingExecutionScopeViolation):
        scope.assert_permitted("deploy_production")


def test_scope_denies_unknown_action_fail_closed(identity):
    scope = StagingExecutionScope(identity)
    assert scope.is_permitted("some_unknown_action") is False


def test_forbidden_and_allowed_disjoint():
    assert FORBIDDEN_PRODUCTION_ACTIONS.isdisjoint(ALLOWED_STAGING_ACTIONS)


def test_scope_requires_staging_identity():
    from agents.staging_runtime.environment import EnvironmentIdentity, EnvironmentResources
    from agents.staging_runtime.isolation_guard import StagingIsolationViolationError

    dev = EnvironmentIdentity(
        kind=RuntimeEnvironment.DEVELOPMENT, name="d", purpose="p",
        resources=EnvironmentResources(),
    )
    with pytest.raises(StagingIsolationViolationError):
        StagingExecutionScope(dev)
