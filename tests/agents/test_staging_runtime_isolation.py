"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— 隔离护栏测试（Task 1–3）。

验证「代码级证明 Staging != Production」三件套 + 护栏：
- ``RuntimeEnvironment`` 分类与属性
- ``EnvironmentFingerprint`` 确定性与变更敏感性
- ``EnvironmentIsolationGuard`` fail-closed 隔离断言

最高红线（fail-closed）：
① 护栏构造即断言 ``engineering_enabled is False``（monkeypatch 注入启用态 → 构造抛错）；
② 不输出 ``engineering_approved``；不把 Staging 说成 Production；不复用 Production 资源。

注：启用态通过 monkeypatch ``agents.enterprise.red_line.load_engineering_enabled`` 注入，
**不修改** config.yaml / 任何文件。
"""

from __future__ import annotations

import pytest

from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.staging_runtime import (
    classify_environment,
    compute_environment_fingerprint,
    EnvironmentFingerprint,
    EnvironmentIdentity,
    EnvironmentIsolationGuard,
    EnvironmentResources,
    EnvironmentClassificationError,
    PRODUCTION_FORBIDDEN_RESOURCE_KINDS,
    RuntimeEnvironment,
    StagingIsolationViolationError,
)


# ---- 环境分类 ----

def test_classify_explicit_production():
    assert classify_environment({"is_production": True}) is RuntimeEnvironment.PRODUCTION
    assert classify_environment({"env": "prod"}) is RuntimeEnvironment.PRODUCTION
    assert classify_environment({"runtime_environment": "production"}) is RuntimeEnvironment.PRODUCTION


def test_classify_production_substring_is_strict():
    # 未知显式值若含 "prod" 偏严判为生产（fail-closed）。
    assert classify_environment({"env": "myprodsvc"}) is RuntimeEnvironment.PRODUCTION


def test_classify_staging_local_vs_external():
    assert classify_environment({"env": "staging"}) is RuntimeEnvironment.LOCAL_STAGING
    assert classify_environment({"env": "local_staging"}) is RuntimeEnvironment.LOCAL_STAGING
    assert classify_environment({"env": "external_staging"}) is RuntimeEnvironment.EXTERNAL_STAGING


def test_classify_dev_test():
    assert classify_environment({"env": "dev"}) is RuntimeEnvironment.DEVELOPMENT
    assert classify_environment({"env": "test"}) is RuntimeEnvironment.TESTING


def test_classify_unknown_defaults_to_development():
    # 未知且非生产 → 默认 DEVELOPMENT（guard 随后拒绝真实 staging 集成）。
    assert classify_environment({"foo": "bar"}) is RuntimeEnvironment.DEVELOPMENT


def test_classify_unknown_strict_raises():
    with pytest.raises(EnvironmentClassificationError):
        classify_environment({"foo": "bar"}, strict=True)


# ---- RuntimeEnvironment 属性 ----

@pytest.mark.parametrize(
    "env,expected",
    [
        (RuntimeEnvironment.DEVELOPMENT, False),
        (RuntimeEnvironment.TESTING, False),
        (RuntimeEnvironment.LOCAL_STAGING, False),
        (RuntimeEnvironment.EXTERNAL_STAGING, False),
        (RuntimeEnvironment.PRODUCTION, True),
    ],
)
def test_is_production(env, expected):
    assert env.is_production is expected


@pytest.mark.parametrize(
    "env,expected",
    [
        (RuntimeEnvironment.DEVELOPMENT, False),
        (RuntimeEnvironment.TESTING, False),
        (RuntimeEnvironment.LOCAL_STAGING, True),
        (RuntimeEnvironment.EXTERNAL_STAGING, True),
        (RuntimeEnvironment.PRODUCTION, False),
    ],
)
def test_permits_real_staging_integration(env, expected):
    assert env.permits_real_staging_integration is expected


# ---- 指纹 ----

def _fp(kind, name, purpose, resources=None):
    return compute_environment_fingerprint(
        kind=kind, name=name, purpose=purpose,
        resources=resources or EnvironmentResources(),
    )


def test_fingerprint_deterministic():
    a = _fp(RuntimeEnvironment.LOCAL_STAGING, "stg-a", "validate")
    b = _fp(RuntimeEnvironment.LOCAL_STAGING, "stg-a", "validate")
    assert a.matches(b)
    assert a.value == b.value


def test_fingerprint_sensitive_to_any_component():
    base = _fp(RuntimeEnvironment.LOCAL_STAGING, "stg-a", "validate")
    assert not base.matches(_fp(RuntimeEnvironment.EXTERNAL_STAGING, "stg-a", "validate"))
    assert not base.matches(_fp(RuntimeEnvironment.LOCAL_STAGING, "stg-b", "validate"))
    assert not base.matches(_fp(RuntimeEnvironment.LOCAL_STAGING, "stg-a", "other"))
    assert not base.matches(
        _fp(RuntimeEnvironment.LOCAL_STAGING, "stg-a", "validate",
            EnvironmentResources(database="db_x"))
    )


def test_identity_with_fingerprint_is_idempotent():
    ident = EnvironmentIdentity(
        kind=RuntimeEnvironment.LOCAL_STAGING, name="stg-a", purpose="validate"
    )
    assert ident.fingerprint is None
    filled = ident.with_fingerprint()
    assert isinstance(filled.fingerprint, EnvironmentFingerprint)
    assert filled.with_fingerprint().fingerprint == filled.fingerprint


# ---- 护栏 fail-closed ----

def test_guard_constructs_when_engineering_disabled(monkeypatch):
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: False
    )
    guard = EnvironmentIsolationGuard()
    assert isinstance(guard, EnvironmentIsolationGuard)


def test_guard_refuses_construction_when_engineering_enabled(monkeypatch):
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        EnvironmentIsolationGuard()


def _staging(name="stg-a", resources=None):
    return EnvironmentIdentity(
        kind=RuntimeEnvironment.LOCAL_STAGING, name=name, purpose="validate",
        resources=resources or EnvironmentResources(),
    ).with_fingerprint()


def _production(name="prod", resources=None):
    return EnvironmentIdentity(
        kind=RuntimeEnvironment.PRODUCTION, name=name, purpose="serve",
        resources=resources or EnvironmentResources(),
    ).with_fingerprint()


def test_assert_staging_only_refuses_production(monkeypatch):
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: False
    )
    guard = EnvironmentIsolationGuard()
    with pytest.raises(StagingIsolationViolationError):
        guard.assert_staging_only(_production())


def test_assert_staging_integration_permitted_refuses_dev_test_prod(monkeypatch):
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: False
    )
    guard = EnvironmentIsolationGuard()
    for kind in (RuntimeEnvironment.DEVELOPMENT, RuntimeEnvironment.TESTING,
                 RuntimeEnvironment.PRODUCTION):
        bad = EnvironmentIdentity(kind=kind, name="x", purpose="y").with_fingerprint()
        with pytest.raises(StagingIsolationViolationError):
            guard.assert_staging_integration_permitted(bad)


def test_assert_staging_integration_permitted_allows_staging(monkeypatch):
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: False
    )
    guard = EnvironmentIsolationGuard()
    for kind in (RuntimeEnvironment.LOCAL_STAGING, RuntimeEnvironment.EXTERNAL_STAGING):
        ok = EnvironmentIdentity(kind=kind, name="x", purpose="y").with_fingerprint()
        guard.assert_staging_integration_permitted(ok)  # 不抛


def test_assert_resource_isolation_passes_when_disjoint(monkeypatch):
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: False
    )
    guard = EnvironmentIsolationGuard()
    staging = _staging(resources=EnvironmentResources(database="staging_db"))
    production = _production(resources=EnvironmentResources(database="prod_db"))
    guard.assert_resource_isolation(staging, production)  # 不抛


def test_assert_resource_isolation_refuses_shared_resource(monkeypatch):
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: False
    )
    guard = EnvironmentIsolationGuard()
    staging = _staging(resources=EnvironmentResources(database="same_db", secret="s1"))
    production = _production(resources=EnvironmentResources(database="same_db", secret="s2"))
    with pytest.raises(StagingIsolationViolationError) as exc:
        guard.assert_resource_isolation(staging, production)
    assert "database" in str(exc.value)


def test_assert_resource_isolation_refuses_non_production_target(monkeypatch):
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: False
    )
    guard = EnvironmentIsolationGuard()
    staging = _staging()
    not_prod = _staging(name="not-prod")
    with pytest.raises(StagingIsolationViolationError):
        guard.assert_resource_isolation(staging, not_prod)


def test_assert_fingerprint_disjoint_allows_distinct(monkeypatch):
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: False
    )
    guard = EnvironmentIsolationGuard()
    prod = _production(resources=EnvironmentResources(database="prod_db"))
    staging = _staging(resources=EnvironmentResources(database="staging_db"))
    # 指纹不同 → 不抛
    guard.assert_fingerprint_disjoint(staging, [prod.fingerprint])


def test_assert_fingerprint_disjoint_refuses_copied_production_fingerprint(monkeypatch):
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: False
    )
    guard = EnvironmentIsolationGuard()
    prod = _production(resources=EnvironmentResources(database="prod_db"))
    # 伪装：攻击者保留 staging kind，但直接抄写 production 的指纹值来伪造身份
    impostor = EnvironmentIdentity(
        kind=RuntimeEnvironment.LOCAL_STAGING, name="staging-impostor", purpose="validate",
        fingerprint=prod.fingerprint,
    )
    with pytest.raises(StagingIsolationViolationError):
        guard.assert_fingerprint_disjoint(impostor, [prod.fingerprint])


def test_validate_returns_structured_verdict(monkeypatch):
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: False
    )
    guard = EnvironmentIsolationGuard()
    # PRODUCTION 作为 staging 传入 → 不通过，且含对应违例
    bad = _production(name="pretend-staging")
    verdict = guard.validate(bad)
    assert verdict.passed is False
    assert verdict.environment is RuntimeEnvironment.PRODUCTION
    assert any(v.kind == "production_classified_as_staging" for v in verdict.violations)
    with pytest.raises(StagingIsolationViolationError):
        verdict.require_ok()

    # 合法 staging + 资源隔离 → 通过
    good = _staging(resources=EnvironmentResources(database="staging_db"))
    prod = _production(resources=EnvironmentResources(database="prod_db"))
    ok_verdict = guard.validate(good, production=prod)
    assert ok_verdict.passed is True
    ok_verdict.require_ok()  # 不抛


def test_production_forbidden_resource_kinds_complete():
    assert PRODUCTION_FORBIDDEN_RESOURCE_KINDS == {
        "database", "secret", "identity_provider", "storage", "alert"
    }
