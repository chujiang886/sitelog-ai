"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— Staging Data Policy（Task 14）。

``StagingDataPolicy`` 规定本地预生产验证**只能**使用合成/脱敏数据，拒绝真实 PII /
生产数据落入 staging（红线：不改真实生产数据 / 不复用 Production 资源）。

fail-closed：未知数据类默认拒绝；``real_pii`` / ``production_snapshot`` 永远拒绝。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from agents.staging_runtime.environment import EnvironmentIdentity
from agents.staging_runtime.isolation_guard import EnvironmentIsolationGuard

# 允许进入 staging 的数据类（合成 / 脱敏 / 公开）。
ALLOWED_STAGING_DATA_CLASSES = frozenset(
    {
        "synthetic",
        "masked",
        "public",
        "anonymized",
    }
)

# 禁止进入 staging 的数据类（真实 PII / 生产快照）。
FORBIDDEN_STAGING_DATA_CLASSES = frozenset(
    {
        "real_pii",
        "production_snapshot",
        "real_customer_data",
        "real_financial_data",
    }
)


class StagingDataPolicyViolation(Exception):
    """数据类违反 staging 数据策略（fail-closed）。"""


@dataclass(frozen=True)
class DataClassificationVerdict:
    """数据分类结论（结构化）。"""

    data_class: str
    permitted: bool
    reason: str

    def require_permitted(self) -> None:
        if not self.permitted:
            raise StagingDataPolicyViolation(
                f"数据类 {self.data_class!r} 不允许进入 staging：{self.reason}"
            )


class StagingDataPolicy:
    """本地预生产数据策略（合成/脱敏优先，拒绝真实 PII）。"""

    def __init__(self, identity: EnvironmentIdentity) -> None:
        guard = EnvironmentIsolationGuard()
        guard.assert_staging_integration_permitted(identity)
        self._identity = identity

    def classify(self, data_class: str) -> DataClassificationVerdict:
        if data_class in FORBIDDEN_STAGING_DATA_CLASSES:
            return DataClassificationVerdict(
                data_class=data_class,
                permitted=False,
                reason="命中禁止数据类（真实 PII / 生产快照），永远拒绝进入 staging。",
            )
        if data_class in ALLOWED_STAGING_DATA_CLASSES:
            return DataClassificationVerdict(
                data_class=data_class,
                permitted=True,
                reason="显式列入允许数据类（合成/脱敏/公开/匿名）。",
            )
        return DataClassificationVerdict(
            data_class=data_class,
            permitted=False,
            reason="未知数据类默认拒绝（fail-closed）。",
        )

    def assert_permitted(self, data_class: str) -> None:
        self.classify(data_class).require_permitted()

    def allowed_classes(self) -> frozenset[str]:
        return frozenset(ALLOWED_STAGING_DATA_CLASSES)

    def forbidden_classes(self) -> frozenset[str]:
        return frozenset(FORBIDDEN_STAGING_DATA_CLASSES)


__all__ = [
    "ALLOWED_STAGING_DATA_CLASSES",
    "FORBIDDEN_STAGING_DATA_CLASSES",
    "StagingDataPolicyViolation",
    "DataClassificationVerdict",
    "StagingDataPolicy",
]
