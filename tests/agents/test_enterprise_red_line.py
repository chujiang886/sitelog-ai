"""Enterprise Operation Layer —— 测试6：红线（6 条，fail-closed，Phase 3.8.0）。

覆盖：
- safety_invariants_ok()：当前 config engineering_enabled=false → 返回 True。
- 所有 Enterprise 服务（及聚合门面）在「启用态」（伪造 engineering_enabled=True）
  下构造一律抛 EnterpriseRedLineViolationError（红线①/⑤）。
- EnterpriseOperationLayer.is_activation_safe() 只读暴露护栏状态。
注：启用态通过 monkeypatch agents.enterprise.red_line.load_engineering_enabled 注入，
**不修改** verified.json / config.yaml / engineering_enabled 文件。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditService
from agents.enterprise.expert_access import ExpertAccessService
from agents.enterprise.file_asset import FileAssetService
from agents.enterprise.identity import IdentityService
from agents.enterprise.organization import OrganizationService
from agents.enterprise.project import ProjectService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)
from agents.enterprise.review_permission import ReviewPermissionService
from agents.enterprise.resource_permission import ResourcePermissionService
from agents.enterprise.service import EnterpriseOperationLayer


def test_safety_invariants_ok_true_when_disabled() -> None:
    # 当前 config 中 engineering_enabled=false，应为 True
    assert safety_invariants_ok() is True


@pytest.mark.parametrize(
    "svc_factory",
    [
        lambda: IdentityService(org_id="org-1"),
        lambda: OrganizationService(org_id="org-1"),
        lambda: ProjectService(org_id="org-1"),
        lambda: FileAssetService(org_id="org-1"),
        lambda: AuditService(org_id="org-1"),
        lambda: ResourcePermissionService(org_id="org-1"),
        lambda: ExpertAccessService(org_id="org-1"),
        lambda: ReviewPermissionService(org_id="org-1"),
        lambda: EnterpriseOperationLayer(org_id="org-1"),
    ],
)
def test_service_construction_fail_closed(svc_factory, monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    assert safety_invariants_ok() is False
    with pytest.raises(EnterpriseRedLineViolationError):
        svc_factory()


def test_enterprise_layer_is_activation_safe() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    assert layer.is_activation_safe() is True
