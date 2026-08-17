"""Phase 3.9.14 —— 九项隔离审计 fail-closed 测试（Task 16-19）。"""

from __future__ import annotations

import pytest

from agents.external_staging_runtime.isolation import (
    ISOLATION_DOMAINS,
    ExternalStagingIsolationAuditor,
    IsolationAuditReport,
)
from agents.external_staging_runtime.identity import external_staging_identity


def _report() -> IsolationAuditReport:
    return ExternalStagingIsolationAuditor().audit_all()


def test_nine_isolation_domains_present() -> None:
    assert len(ISOLATION_DOMAINS) == 9
    rep = _report()
    assert len(rep.domains) == 9


def test_all_domains_structurally_isolated() -> None:
    rep = _report()
    assert rep.passed is True
    for d in rep.domains:
        assert d.structurally_isolated is True
        assert d.production_leakage is False
        assert d.status == "STRUCTURALLY_ISOLATED_PENDING_RESOURCE"


def test_no_production_leakage() -> None:
    rep = _report()
    assert rep.production_leakage is False
    assert all(not d.production_leakage for d in rep.domains)


def test_real_external_resources_pending_track_b() -> None:
    # 真实外部资源由真人供给（Track B），本阶段恒未供给。
    rep = _report()
    assert rep.real_resources_present == 0
    assert all(d.real_resource_present is False for d in rep.domains)


def test_environment_is_external_staging_non_production() -> None:
    rep = _report()
    assert rep.environment == "external_staging"
    ident = external_staging_identity()
    assert ident.kind.is_production is False
