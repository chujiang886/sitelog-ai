"""Phase 3.9.11 —— 8 类外部预生产资源的 Fake Adapter（Tasks 7-14）。

Track B 真实资源 PENDING → 适配器**诚实**报告 ``PENDING_EXTERNAL_STAGING_RESOURCE``，
**绝不**伪造真实验证（``CONNECTIVITY_VERIFIED`` / ``QUALIFIED_EXTERNAL_STAGING``）。

``contract_test()`` 仅验证「代码路径（fake adapter）契约自洽」——即适配器可构造、可探测、
可诚实报告 pending——**通过不代表真实资源可用**。这是 fail-closed 的「契约模拟」而非
「真实执行」。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.external_staging_qualification.models import (
    RESOURCE_TYPE_ORDER,
    ResourceQualificationStatus,
    ResourceType,
)
from agents.external_staging_execution.models import ExternalStagingExecutionError

PENDING = ResourceQualificationStatus.PENDING_EXTERNAL_STAGING_RESOURCE.value


@dataclass
class AdapterProbeResult:
    """适配器探测结果（诚实）。"""

    resource_type: str
    configured: bool = False
    verified: bool = False
    status: str = PENDING
    detail: str = ""
    contract_test_passed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "configured": self.configured,
            "verified": self.verified,
            "status": self.status,
            "detail": self.detail,
            "contract_test_passed": self.contract_test_passed,
            "is_real_execution": False,
            "contains_real_secret": False,
        }

    def is_honest(self) -> bool:
        """是否诚实：未配置、未验证、状态为 PENDING、无 Secret。"""

        return (
            self.configured is False
            and self.verified is False
            and self.status == PENDING
            and self.contract_test_passed is True
        )


class ExternalStagingExecutionAdapter:
    """单资源 Fake Adapter（诚实报告 PENDING）。"""

    def __init__(self, resource_type: ResourceType) -> None:
        self.resource_type = resource_type

    def probe(self) -> AdapterProbeResult:
        return AdapterProbeResult(
            resource_type=self.resource_type.value,
            configured=False,
            verified=False,
            status=PENDING,
            detail=(
                "No real external staging resource provisioned (Track B PENDING); "
                "fake adapter reports honestly, no fabrication of connectivity/qualification."
            ),
        )

    def contract_test(self) -> bool:
        """契约测试：fake adapter 接口契约自洽（可构造/可探测/可诚实报告 pending）。

        通过仅证明代码路径正确，不代表真实资源可用。
        """

        result = self.probe()
        return result.is_honest()


def build_adapter_registry() -> dict[ResourceType, ExternalStagingExecutionAdapter]:
    """建立 8 类资源的 Fake Adapter 登记簿。"""

    return {rtype: ExternalStagingExecutionAdapter(rtype) for rtype in RESOURCE_TYPE_ORDER}


def probe_all() -> list[AdapterProbeResult]:
    """探测全部 8 资源（诚实 PENDING）。"""

    registry = build_adapter_registry()
    return [adapter.probe() for adapter in registry.values()]


def adapters_contract_test_all_pass() -> bool:
    """全部 8 适配器的契约测试是否通过（代码路径自洽）。"""

    registry = build_adapter_registry()
    return all(adapter.contract_test() for adapter in registry.values())


def assert_no_real_execution_claimed(results: list[AdapterProbeResult]) -> None:
    """断言没有任何适配器宣称真实执行/验证（fail-closed）。"""

    for r in results:
        if r.configured or r.verified or r.status != PENDING:
            raise ExternalStagingExecutionError(
                f"资源 {r.resource_type} 宣称了真实配置/验证（status={r.status}），"
                f"违反 fail-closed：Track B 资源必须 PENDING。"
            )


__all__ = [
    "AdapterProbeResult",
    "ExternalStagingExecutionAdapter",
    "build_adapter_registry",
    "probe_all",
    "adapters_contract_test_all_pass",
    "assert_no_real_execution_claimed",
]
