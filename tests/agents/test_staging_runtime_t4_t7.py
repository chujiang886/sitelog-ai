"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— T4-T7 测试（Task 10-25）。

覆盖：
- Task 10-13 Staging DB Provider / Safety / Migration Validator / Safety
- Task 14-16 Staging Data Policy / Identity Provider / Token Isolation
- Task 17-21 Staging Observability（health/telemetry/metrics/logs/trace）
- Task 22-25 Staging Alert/On-call / LLM/Voice Validation

红线约定：不修改 engineering_enabled；需要模拟启用态时 monkeypatch red_line 函数。
"""

from __future__ import annotations

import pytest

from agents.staging_runtime.config import load_staging_identity
from agents.staging_runtime.db import (
    StagingDatabaseProvider,
    StagingDatabaseSafety,
    StagingMigrationValidator,
    StagingMigrationSafety,
    StagingMigrationForbiddenError,
    MigrationPlan,
    StagingDatabaseError,
)
from agents.staging_runtime.data_policy import (
    StagingDataPolicy,
    StagingDataPolicyViolation,
    ALLOWED_STAGING_DATA_CLASSES,
    FORBIDDEN_STAGING_DATA_CLASSES,
)
from agents.staging_runtime.identity_provider import (
    StagingIdentityProvider,
    StagingIdentityProviderError,
)
from agents.staging_runtime.token_isolation import (
    StagingTokenIsolation,
    StagingTokenIsolationError,
)
from agents.staging_runtime.observability import StagingTelemetry, StagingRuntimeHealth
from agents.staging_runtime.alerting import StagingAlertChannel, StagingOnCallSandbox
from agents.staging_runtime.llm_voice import (
    StagingLLMValidation,
    StagingVoiceValidation,
    StagingLLMVoiceError,
)
from agents.staging_runtime.environment import RuntimeEnvironment, EnvironmentIdentity, EnvironmentResources


@pytest.fixture
def identity():
    return load_staging_identity()


# ─────────────────────── Task 10-13: DB & Migration ───────────────────────


def test_db_provider_describe_non_production(identity):
    provider = StagingDatabaseProvider(identity, staging_dsn="staging-dsn")
    desc = provider.describe()
    assert desc.dsn_present is True
    assert desc.is_production is False
    assert desc.non_production is True


def test_db_provider_refuses_production_dsn(identity):
    provider = StagingDatabaseProvider(
        identity, production_dsn_refs={"prod-dsn"}, staging_dsn="prod-dsn"
    )
    with pytest.raises(StagingDatabaseError):
        provider.describe()


def test_db_provider_connect_always_forbidden(identity):
    provider = StagingDatabaseProvider(identity, staging_dsn="staging-dsn")
    with pytest.raises(StagingDatabaseError):
        provider.connect()


def test_db_safety_assert_safe(identity):
    safety = StagingDatabaseSafety(identity)
    safety.assert_safe_to_describe("staging-dsn", production_dsn_refs={"prod-dsn"})
    with pytest.raises(StagingDatabaseError):
        safety.assert_safe_to_describe("prod-dsn", production_dsn_refs={"prod-dsn"})


def test_migration_validator_rejects_production_target(identity):
    validator = StagingMigrationValidator(identity)
    plan = MigrationPlan(name="m1", targets=("production",), operations=("create_table",))
    verdict = validator.validate(plan)
    assert verdict.passed is False
    assert "targets_production" in verdict.violations


def test_migration_validator_allows_staging(identity):
    validator = StagingMigrationValidator(identity)
    plan = MigrationPlan(
        name="m2", targets=("local_staging",), operations=("create_table",), is_destructive=True
    )
    assert validator.validate(plan).passed is True


def test_migration_safety_apply_always_forbidden(identity):
    safety = StagingMigrationSafety(identity)
    plan = MigrationPlan(name="m3", targets=("local_staging",))
    with pytest.raises(StagingMigrationForbiddenError):
        safety.apply(plan)


# ─────────────────────── Task 14-16: Data / IdP / Token ───────────────────────


def test_data_policy_allows_synthetic(identity):
    policy = StagingDataPolicy(identity)
    policy.assert_permitted("synthetic")
    assert policy.classify("synthetic").permitted is True


def test_data_policy_rejects_real_pii(identity):
    policy = StagingDataPolicy(identity)
    verdict = policy.classify("real_pii")
    assert verdict.permitted is False
    with pytest.raises(StagingDataPolicyViolation):
        policy.assert_permitted("real_pii")


def test_data_policy_denies_unknown_fail_closed(identity):
    policy = StagingDataPolicy(identity)
    assert policy.classify("weird_class").permitted is False


def test_data_policy_sets_disjoint():
    assert ALLOWED_STAGING_DATA_CLASSES.isdisjoint(FORBIDDEN_STAGING_DATA_CLASSES)


def test_identity_provider_refuses_production_issuer(identity):
    provider = StagingIdentityProvider(
        identity, production_issuer_refs={"prod-idp"}, staging_issuer="prod-idp"
    )
    with pytest.raises(StagingIdentityProviderError):
        provider.describe()


def test_identity_provider_describe_non_production(identity):
    provider = StagingIdentityProvider(identity, staging_issuer="staging-idp")
    desc = provider.describe()
    assert desc.issuer_present is True
    assert desc.non_production is True


def test_token_isolation_refuses_production_token(identity):
    iso = StagingTokenIsolation(identity, production_token_refs={"prod-token"})
    with pytest.raises(StagingTokenIsolationError):
        iso.assert_isolated("t", "prod-token")
    assert iso.check_token("t", "staging-token").isolated is True


# ─────────────────────── Task 17-21: Observability ───────────────────────


def test_observability_health_checks_non_production(identity):
    checks = StagingRuntimeHealth(identity).describe_checks()
    assert all(c.non_production for c in checks)
    assert len(checks) >= 1


def test_observability_telemetry_manifest_non_production(identity):
    manifest = StagingTelemetry(identity).to_manifest()
    assert manifest["is_production"] is False
    assert manifest["collects_real_data"] is False
    assert all(t["non_production"] for t in manifest["telemetry"])


# ─────────────────────── Task 22-25: Alert/On-call + LLM/Voice ───────────────────────


def test_alert_channel_refuses_production_alert(identity):
    channel = StagingAlertChannel(
        identity, production_alert_refs={"prod-alert"}, staging_channel="prod-alert"
    )
    with pytest.raises(Exception):
        channel.describe()


def test_alert_channel_describe_non_production(identity):
    channel = StagingAlertChannel(identity, staging_channel="staging-alert")
    desc = channel.describe()
    assert desc.channel_present is True
    assert desc.non_production is True


def test_alert_channel_trigger_forbidden(identity):
    channel = StagingAlertChannel(identity, staging_channel="staging-alert")
    with pytest.raises(Exception):
        channel.trigger()


def test_oncall_sandbox_non_production(identity):
    sandbox = StagingOnCallSandbox(identity).describe()
    assert sandbox["is_production"] is False
    assert sandbox["sandbox"] is True


def test_llm_validation_refuses_production_endpoint(identity):
    llm = StagingLLMValidation(
        identity, production_endpoint_refs={"prod-llm"}, staging_endpoint="prod-llm"
    )
    with pytest.raises(StagingLLMVoiceError):
        llm.describe()


def test_llm_validation_describe_non_production(identity):
    llm = StagingLLMValidation(identity, staging_endpoint="staging-llm")
    assert llm.describe().non_production is True
    with pytest.raises(StagingLLMVoiceError):
        llm.invoke()


def test_voice_validation_describe_non_production(identity):
    voice = StagingVoiceValidation(identity, staging_voice="staging-voice")
    assert voice.describe().non_production is True
    with pytest.raises(StagingLLMVoiceError):
        voice.synthesize()


def test_non_staging_identity_rejected_everywhere():
    dev = EnvironmentIdentity(
        kind=RuntimeEnvironment.DEVELOPMENT, name="d", purpose="p",
        resources=EnvironmentResources(),
    )
    from agents.staging_runtime.isolation_guard import StagingIsolationViolationError

    with pytest.raises(StagingIsolationViolationError):
        StagingDatabaseProvider(dev)
    with pytest.raises(StagingIsolationViolationError):
        StagingDataPolicy(dev)
    with pytest.raises(StagingIsolationViolationError):
        StagingTokenIsolation(dev)
    with pytest.raises(StagingIsolationViolationError):
        StagingTelemetry(dev)
    with pytest.raises(StagingIsolationViolationError):
        StagingAlertChannel(dev)
    with pytest.raises(StagingIsolationViolationError):
        StagingLLMValidation(dev)
