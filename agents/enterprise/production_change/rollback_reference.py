"""Phase 3.9.7 回滚引用域（T7）。记录 last_known_good 版本 / commit / 数据库修订 /
配置基线 / 回滚步骤与恢复校验引用。不真正执行 production rollback；只验证引用完整性。
"""

from __future__ import annotations

from typing import Optional

from agents.enterprise.production_change.models import ChangeRollbackReference


def build_change_rollback_reference(
    *,
    change_id: str,
    last_known_good_version: str,
    last_known_good_commit: str,
    database_revision: Optional[str] = None,
    config_baseline: Optional[str] = None,
    rollback_steps_reference: Optional[str] = None,
    recovery_validation_reference: Optional[str] = None,
) -> ChangeRollbackReference:
    """构造回滚引用（仅记录引用，不执行真实回滚；verified 仅表示引用完整性）。"""

    return ChangeRollbackReference(
        change_id=change_id,
        last_known_good_version=last_known_good_version,
        last_known_good_commit=last_known_good_commit,
        database_revision=database_revision,
        config_baseline=config_baseline,
        rollback_steps_reference=rollback_steps_reference,
        recovery_validation_reference=recovery_validation_reference,
        verified=False,
    )


__all__ = ["build_change_rollback_reference"]
