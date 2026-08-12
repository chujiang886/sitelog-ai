"""Phase 3.9.2 企业生产发布闸门与证据包层 —— 发布包清单与回滚引用（T6 / T7）。

``ReleasePackageBuilder``：
- ``build_manifest``：对可哈希产物计算 SHA-256，生成 ``ReleasePackageManifest``（只描述）；
- ``build_rollback_reference``：记录 last_known_good 版本 / commit / 数据库修订 / 配置基线 /
  回滚步骤与恢复校验引用，并验证引用完整性（``verified`` 仅表示引用齐全，**不执行真实回滚**）。

红线（T6 / T7 / ④ / ⑩）：
- 清单与回滚引用**只描述**，不执行部署、不执行回滚、不写真实数据；
- ``artifact_hashes`` 使用 SHA-256；缺产物文件时对应哈希标记为 ``<missing>`` 而非伪造。
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from agents.enterprise.production_release.models import (
    ReleasePackageManifest,
    ReleaseRollbackReference,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_of_file(path: str) -> str:
    if not os.path.isfile(path):
        return "<missing>"
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return "<unreadable>"


class ReleasePackageBuilder:
    """发布包清单与回滚引用构建器（只读 / 只描述）。"""

    def __init__(self, root_dir: str = ".") -> None:
        self.root_dir = os.path.abspath(root_dir)

    # ------------------------------------------------------------------ #
    # T6：发布清单（SHA-256）
    # ------------------------------------------------------------------ #
    def build_manifest(
        self,
        *,
        release_version: str,
        commit_sha: str,
        artifacts: Optional[Dict[str, str]] = None,
        migration_revision: Optional[str] = None,
        config_baseline: Optional[str] = None,
        dependency_baseline: Optional[str] = None,
        security_scan_ref: Optional[str] = None,
        test_report_ref: Optional[str] = None,
        rollback_version: Optional[str] = None,
        documentation_version: Optional[str] = None,
    ) -> ReleasePackageManifest:
        """``artifacts`` 为 {名: 仓库相对路径}；对存在文件算 SHA-256，缺失标 ``<missing>``。"""

        artifact_hashes: Dict[str, str] = {}
        for name, rel in (artifacts or {}).items():
            full = os.path.join(self.root_dir, rel)
            artifact_hashes[name] = _sha256_of_file(full)

        return ReleasePackageManifest(
            release_version=release_version,
            commit_sha=commit_sha,
            artifact_hashes=artifact_hashes,
            migration_revision=migration_revision,
            config_baseline=config_baseline,
            dependency_baseline=dependency_baseline,
            security_scan_ref=security_scan_ref,
            test_report_ref=test_report_ref,
            rollback_version=rollback_version,
            documentation_version=documentation_version,
            generated_at=_now(),
        )

    # ------------------------------------------------------------------ #
    # T7：回滚引用（只验证引用完整性，不执行回滚）
    # ------------------------------------------------------------------ #
    def build_rollback_reference(
        self,
        *,
        last_known_good_version: str,
        last_known_good_commit: str,
        database_revision: Optional[str] = None,
        config_baseline: Optional[str] = None,
        rollback_steps_reference: Optional[str] = None,
        recovery_validation_reference: Optional[str] = None,
    ) -> ReleaseRollbackReference:
        """验证引用完整性：所有引用字段非空即视为引用齐全（``verified=True``）。

        注意：``verified`` 仅代表**引用齐备**，绝不表示已执行真实回滚。
        """

        refs = [
            last_known_good_version,
            last_known_good_commit,
            database_revision,
            config_baseline,
            rollback_steps_reference,
            recovery_validation_reference,
        ]
        verified = all(bool(r) and str(r).strip() != "" for r in refs)
        return ReleaseRollbackReference(
            last_known_good_version=last_known_good_version,
            last_known_good_commit=last_known_good_commit,
            database_revision=database_revision,
            config_baseline=config_baseline,
            rollback_steps_reference=rollback_steps_reference,
            recovery_validation_reference=recovery_validation_reference,
            verified=verified,
        )
