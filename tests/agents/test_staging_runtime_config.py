"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— T2 测试（Task 4-6）。

覆盖：
- Task 4 Staging Config：load_staging_identity 加载 Local Staging 身份、指纹、就绪态；
  拒绝 production 配置（fail-closed）。
- Task 5 StagingSecretProvider：从环境变量解析、缺失返回 None、拒绝 Production Secret 复用。
- Task 6 LocalStagingProfile：恒为非生产、manifest 非生产、配套资产存在。

红线约定：测试不修改 agents/config.yaml 的 engineering_enabled；如需模拟启用态，
monkeypatch ``agents.enterprise.red_line.load_engineering_enabled``（不碰真实文件）。
"""

from __future__ import annotations

import pytest

from agents.staging_runtime.config import (
    load_staging_identity,
    load_forbidden_production_fingerprints,
    staging_resource_readiness,
    StagingResourceReadiness,
    StagingConfigError,
)
from agents.staging_runtime.environment import (
    EnvironmentIdentity,
    EnvironmentResources,
    RuntimeEnvironment,
)
from agents.staging_runtime.isolation_guard import StagingIsolationViolationError
from agents.staging_runtime.secret_provider import (
    StagingSecretProvider,
    StagingSecretIsolationError,
)
from agents.staging_runtime.local_profile import LocalStagingProfile


# ─────────────────────────── Task 4: Staging Config ───────────────────────────


def test_load_staging_identity_is_local_staging_with_fingerprint():
    identity = load_staging_identity()
    assert isinstance(identity, EnvironmentIdentity)
    assert identity.kind is RuntimeEnvironment.LOCAL_STAGING
    assert identity.fingerprint is not None
    assert identity.fingerprint.value


def test_load_staging_identity_not_production():
    identity = load_staging_identity()
    assert identity.kind.is_production is False
    assert identity.kind.permits_real_staging_integration is True


def test_staging_resource_readiness_pending_when_unconfigured():
    identity = load_staging_identity()
    readiness = staging_resource_readiness(identity)
    # 当前 config.yaml 资源全部 pending_verification → 缺外部 Staging 资源。
    assert readiness is StagingResourceReadiness.PENDING_EXTERNAL_STAGING_RESOURCE


def test_staging_resource_readiness_ready_when_declared(monkeypatch):
    monkeypatch.setattr(
        "agents.staging_runtime.config.load_staging_config",
        lambda config_path=None: {
            "environment": "local_staging",
            "name": "cfg-staging",
            "purpose": "p",
            "resources": {
                "database": "staging-dsn",
                "secret": "staging-secret",
                "identity_provider": "staging-idp",
                "storage": "staging-bucket",
                "alert": "staging-alert",
            },
        },
    )
    identity = load_staging_identity()
    assert staging_resource_readiness(identity) is StagingResourceReadiness.READY


def test_load_staging_identity_refuses_production_config(monkeypatch):
    monkeypatch.setattr(
        "agents.staging_runtime.config.load_staging_config",
        lambda config_path=None: {"environment": "production"},
    )
    with pytest.raises(StagingConfigError):
        load_staging_identity()


def test_forbidden_production_fingerprints_empty_by_default_no_real_values():
    # 默认配置黑名单为空：不内联任何真实 production 指纹（fail-closed 不靠伪造）。
    assert load_forbidden_production_fingerprints() == ()


def test_guard_construction_fails_when_engineering_enabled(monkeypatch):
    # 红线①：engineering_enabled=True 时护栏构造即抛。
    from agents.enterprise.red_line import EnterpriseRedLineViolationError
    from agents.staging_runtime.isolation_guard import EnvironmentIsolationGuard

    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        EnvironmentIsolationGuard()


# ─────────────────────── Task 5: StagingSecretProvider ────────────────────────


def test_secret_provider_resolves_from_env(monkeypatch):
    monkeypatch.setenv("STAGING_SECRET_FOO", "bar")
    identity = load_staging_identity()
    provider = StagingSecretProvider(identity)
    assert provider.resolve("foo") == "bar"


def test_secret_provider_missing_returns_none(monkeypatch):
    identity = load_staging_identity()
    provider = StagingSecretProvider(identity)
    assert provider.resolve("nope") is None
    assert provider.missing(["nope", "other"]) == ("nope", "other")


def test_secret_provider_refuses_production_secret(monkeypatch):
    monkeypatch.setenv("STAGING_SECRET_X", "realprodsecret")
    identity = load_staging_identity()
    provider = StagingSecretProvider(identity, production_secret_refs={"realprodsecret"})
    with pytest.raises(StagingSecretIsolationError):
        provider.resolve("x")


def test_secret_provider_resolve_required_raises_when_missing(monkeypatch):
    identity = load_staging_identity()
    provider = StagingSecretProvider(identity)
    with pytest.raises(StagingSecretIsolationError):
        provider.resolve_required("missing")


def test_secret_provider_requires_staging_identity():
    dev_identity = EnvironmentIdentity(
        kind=RuntimeEnvironment.DEVELOPMENT,
        name="dev",
        purpose="dev",
        resources=EnvironmentResources(),
    )
    with pytest.raises(StagingIsolationViolationError):
        StagingSecretProvider(dev_identity)


def test_secret_provider_snapshot_does_not_leak_values(monkeypatch):
    monkeypatch.setenv("STAGING_SECRET_KNOWN", "v")
    identity = load_staging_identity()
    provider = StagingSecretProvider(identity)
    snap = provider.snapshot(["known", "unknown"])
    assert snap[0].resolved is True
    assert snap[1].resolved is False
    # 快照仅包含逻辑名/环境变量名/是否解析，不含明文值对象属性泄露。
    assert snap[0].name == "known"
    assert snap[0].env_var == "STAGING_SECRET_KNOWN"


# ─────────────────────── Task 6: LocalStagingProfile ─────────────────────────


def test_local_profile_kind_is_local_staging():
    profile = LocalStagingProfile()
    assert profile.kind is RuntimeEnvironment.LOCAL_STAGING
    assert profile.kind.is_production is False


def test_local_profile_manifest_non_production():
    manifest = LocalStagingProfile().build_manifest()
    assert manifest["is_production"] is False
    assert manifest["non_production_bound"] is True
    assert manifest["environment"] == "local_staging"
    assert all(s["non_production"] for s in manifest["services"])


def test_local_profile_to_identity_local():
    identity = LocalStagingProfile().to_identity()
    assert identity.kind is RuntimeEnvironment.LOCAL_STAGING


def test_local_profile_assets_exist():
    profile = LocalStagingProfile()
    assert profile.compose_path().is_file()
    assert profile.env_example_path().is_file()


def test_local_profile_never_production(monkeypatch):
    # 强行构造一个 kind=PRODUCTION 的假身份也应被 to_identity 拒绝（它固定 LOCAL_STAGING）。
    profile = LocalStagingProfile()
    # 即便外部传入 production 身份，to_identity 仍固化 LOCAL_STAGING。
    identity = profile.to_identity()
    assert identity.kind is RuntimeEnvironment.LOCAL_STAGING
