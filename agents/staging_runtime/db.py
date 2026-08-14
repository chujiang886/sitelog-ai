"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— Staging DB & Migration（Task 10-13）。

本模块覆盖本地预生产数据库接入与迁移的**结构性安全**：

- Task 10 StagingDatabaseProvider：描述 staging DB 接入形态（从环境变量 DSN），
  拒绝复用 Production DSN（红线：禁止复用 Production DB）。
- Task 11 StagingDatabaseSafety：连接前安全校验（非生产、DSN 不命中生产引用）。
- Task 12 StagingMigrationValidator：校验迁移计划仅面向 staging、不面向 production。
- Task 13 StagingMigrationSafety：迁移**安全包装**——系统永不自动对任一数据库（尤其
  生产）执行迁移；``apply`` 永远抛 ``StagingMigrationForbiddenError``（红线：不真实
  DB migration）。

fail-closed：未知/未验证即拒绝；不连接、不执行、不修改任何数据库。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from agents.staging_runtime.environment import EnvironmentIdentity, RuntimeEnvironment
from agents.staging_runtime.isolation_guard import EnvironmentIsolationGuard


class StagingDatabaseError(Exception):
    """Staging DB 接入/校验违例（fail-closed）。"""


class StagingMigrationForbiddenError(Exception):
    """禁止系统自动执行迁移（红线：不真实 DB migration）。"""


@dataclass(frozen=True)
class StagingDatabaseDescriptor:
    """Staging DB 接入形态描述（不连接、不执行）。"""

    dsn_present: bool
    is_production: bool = False
    non_production: bool = True
    target: str = "local_staging"
    note: str = "系统不连接/不执行 staging DB；真实接入由人工在授权后执行。"

    def to_dict(self) -> dict[str, Any]:
        return {
            "dsn_present": self.dsn_present,
            "is_production": self.is_production,
            "non_production": self.non_production,
            "target": self.target,
            "note": self.note,
        }


class StagingDatabaseProvider:
    """本地预生产 DB 接入提供方（只描述形态，绝不连接/执行）。"""

    def __init__(
        self,
        identity: EnvironmentIdentity,
        *,
        production_dsn_refs: Iterable[str] = (),
        staging_dsn: str | None = None,
    ) -> None:
        guard = EnvironmentIsolationGuard()
        guard.assert_staging_integration_permitted(identity)
        self._identity = identity
        self._production_dsn_refs = frozenset(production_dsn_refs)
        self._staging_dsn = staging_dsn

    def describe(self) -> StagingDatabaseDescriptor:
        """描述 staging DB 接入形态（拒绝复用 Production DSN）。"""

        dsn = self._staging_dsn
        if dsn is not None and dsn in self._production_dsn_refs:
            raise StagingDatabaseError(
                "staging DSN 命中 Production DSN 引用集合，拒绝复用（红线：禁止复用 Production DB）。"
            )
        present = dsn is not None and dsn != "pending_verification"
        return StagingDatabaseDescriptor(dsn_present=present)

    def connect(self) -> StagingDatabaseDescriptor:
        """**永不**连接/执行 DB；调用即抛（红线：不真实 DB 变更）。"""

        raise StagingDatabaseError(
            "StagingDatabaseProvider.connect() 被调用：系统禁止自动连接/执行 staging DB。"
        )


class StagingDatabaseSafety:
    """连接前安全校验（Task 11）。"""

    def __init__(self, identity: EnvironmentIdentity) -> None:
        guard = EnvironmentIsolationGuard()
        guard.assert_staging_integration_permitted(identity)
        self._identity = identity

    def assert_safe_to_describe(self, dsn: str | None, production_dsn_refs: Iterable[str] = ()) -> None:
        """校验 DSN 非生产、不命中生产引用（fail-closed）。"""

        if dsn is not None and dsn in frozenset(production_dsn_refs):
            raise StagingDatabaseError(
                "DSN 命中 Production DSN 引用集合，拒绝（红线：禁止复用 Production DB）。"
            )
        if self._identity.kind.is_production:
            raise StagingDatabaseError("环境为 PRODUCTION，禁止作为 staging DB 接入。")


@dataclass(frozen=True)
class MigrationPlan:
    """迁移计划描述（用于校验，不执行）。"""

    name: str
    targets: tuple[str, ...]  # 目标环境（如 ("local_staging",)）
    operations: tuple[str, ...] = ()  # 操作类型（create_table / alter_column / drop_table ...）
    is_destructive: bool = False


@dataclass(frozen=True)
class MigrationVerdict:
    """迁移计划校验结论（结构化）。"""

    passed: bool
    plan_name: str
    violations: tuple[str, ...]

    def require_ok(self) -> None:
        if not self.passed:
            raise StagingDatabaseError(
                f"迁移计划 {self.plan_name!r} 校验未通过：" + "; ".join(self.violations)
            )


class StagingMigrationValidator:
    """迁移计划校验（Task 12）：仅面向 staging，绝不面向 production。"""

    def __init__(self, identity: EnvironmentIdentity) -> None:
        guard = EnvironmentIsolationGuard()
        guard.assert_staging_integration_permitted(identity)
        self._identity = identity

    def validate(self, plan: MigrationPlan) -> MigrationVerdict:
        """校验迁移计划不面向 production；staging 内 destructive 需显式标注。"""

        violations: list[str] = []
        if "production" in plan.targets:
            violations.append("targets_production")
        if self._identity.kind.is_production:
            violations.append("identity_is_production")
        # staging 内 destructive 允许（预生产可重建），但必须显式声明 is_destructive。
        return MigrationVerdict(
            passed=len(violations) == 0,
            plan_name=plan.name,
            violations=tuple(violations),
        )


class StagingMigrationSafety:
    """迁移安全包装（Task 13）：系统永不自动执行迁移。"""

    def __init__(self, identity: EnvironmentIdentity) -> None:
        guard = EnvironmentIsolationGuard()
        guard.assert_staging_integration_permitted(identity)
        self._identity = identity

    def apply(self, plan: MigrationPlan) -> MigrationVerdict:
        """**永不**执行迁移；调用即抛 ``StagingMigrationForbiddenError``（红线）。"""

        raise StagingMigrationForbiddenError(
            f"系统禁止自动执行迁移计划 {plan.name!r}（红线：不真实 DB migration）。"
            "迁移须由人工在授权后执行。"
        )

    def dry_run(self, plan: MigrationPlan) -> MigrationVerdict:
        """只做校验（不执行），返回是否允许该计划在 staging 形态下。"""

        validator = StagingMigrationValidator(self._identity)
        return validator.validate(plan)


__all__ = [
    "StagingDatabaseError",
    "StagingMigrationForbiddenError",
    "StagingDatabaseDescriptor",
    "StagingDatabaseProvider",
    "StagingDatabaseSafety",
    "MigrationPlan",
    "MigrationVerdict",
    "StagingMigrationValidator",
    "StagingMigrationSafety",
]
