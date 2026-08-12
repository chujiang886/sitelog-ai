"""Phase 3.9.2 企业生产发布闸门与证据包层 —— RC 冻结检查器（Release Freeze Checker）。

``ReleaseFreezeChecker.check(rc, manifest)``：fail-closed 地判定 RC 是否仍处于冻结态。

判定维度（任一不满足即 ``DRIFTED``）：
1. 组件哈希一致：重算 ``rc.components`` 各文件 SHA-256，与 manifest 记录逐项比对；
2. 清单自洽：manifest 无 ``<missing>`` / ``<unreadable>`` 组件；
3. 清单哈希自洽：重算 ``manifest.canonical()`` 的 SHA-256 与 ``manifest.manifest_sha256`` 一致；
4. 红线①：``engineering_enabled is False``；
5. 治理完整性：``scripts/check_governance_repository_integrity.py`` 通过（9/9）；
6. RC 状态：``rc.status == RELEASE_CANDIDATE_FROZEN_AWAITING_HUMAN``；
7.（可选）Git 工作树干净：``git status --porcelain`` 为空。

全部满足 → ``FROZEN``。检查器**只读**，不写任何状态、不部署、不激活。
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from agents.config_loader import load_engineering_enabled
from agents.enterprise.production_release.package import _sha256_of_file
from agents.enterprise.production_release.release_candidate import (
    RCFreezeStatus,
    ReleaseCandidate,
)
from agents.enterprise.production_release.freeze_manifest import (
    RCFreezeManifest,
    _manifest_sha256_of,
)


class FreezeCheckResultStatus(str, Enum):
    """冻结检查结果状态。"""

    FROZEN = "frozen"
    DRIFTED = "drifted"


@dataclass(frozen=True)
class FreezeCheckResult:
    """冻结检查结果（只读事实）。"""

    status: FreezeCheckResultStatus
    checks: Dict[str, bool] = field(default_factory=dict)
    missing: List[str] = field(default_factory=list)
    note: str = (
        "FREEZE_CHECK_ONLY: 只判定冻结态；不部署、不激活、不写真实数据"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "status": self.status.value,
            "checks": dict(self.checks),
            "missing": list(self.missing),
            "note": self.note,
        }

    @property
    def frozen(self) -> bool:
        return self.status == FreezeCheckResultStatus.FROZEN


def _git_workspace_clean(root_dir: str) -> bool:
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return out.returncode == 0 and out.stdout.strip() == ""
    except Exception:
        # 无法判定 git 状态时保守判为「不干净」（fail-closed）。
        return False


def _governance_integrity_ok(root_dir: str) -> bool:
    script = os.path.join(root_dir, "scripts", "check_governance_repository_integrity.py")
    if not os.path.isfile(script):
        return False
    try:
        out = subprocess.run(
            [sys.executable, script],
            cwd=root_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return out.returncode == 0
    except Exception:
        return False


class ReleaseFreezeChecker:
    """RC 冻结检查器（fail-closed，只读）。"""

    def __init__(
        self,
        root_dir: str = ".",
        *,
        check_git: bool = True,
        check_governance: bool = True,
    ) -> None:
        self.root_dir = os.path.abspath(root_dir)
        self.check_git = check_git
        self.check_governance = check_governance

    # ------------------------------------------------------------------ #
    # 核心判定
    # ------------------------------------------------------------------ #
    def check(
        self,
        rc: ReleaseCandidate,
        manifest: RCFreezeManifest,
    ) -> FreezeCheckResult:
        checks: Dict[str, bool] = {}
        missing: List[str] = []

        # 1. 组件哈希一致：重算工作树文件 SHA-256 比对 manifest 记录
        base = self.root_dir
        comp_ok = True
        for comp in manifest.components:
            full = os.path.join(base, comp.repo_path)
            cur = _sha256_of_file(full)
            if cur != comp.sha256:
                comp_ok = False
                missing.append(f"component_hash_mismatch:{comp.repo_path}")
        checks["component_hashes_match"] = comp_ok

        # 2. 清单无缺失组件
        no_missing = not manifest.has_missing()
        checks["manifest_no_missing"] = no_missing
        if not no_missing:
            missing.append("manifest_has_missing_component")

        # 3. 清单哈希自洽
        manifest_self_ok = (
            _manifest_sha256_of(manifest) == manifest.manifest_sha256
        )
        checks["manifest_self_consistent"] = manifest_self_ok
        if not manifest_self_ok:
            missing.append("manifest_sha256_inconsistent")

        # 4. 红线①：engineering_enabled 必须 False
        eng_ok = load_engineering_enabled() is False
        checks["engineering_enabled_false"] = eng_ok
        if not eng_ok:
            missing.append("engineering_enabled_true")

        # 5. 治理完整性 9/9
        if self.check_governance:
            gov_ok = _governance_integrity_ok(base)
            checks["governance_integrity_9_9"] = gov_ok
            if not gov_ok:
                missing.append("governance_integrity_failed")

        # 6. RC 状态为冻结待人工
        status_ok = rc.status == RCFreezeStatus.RELEASE_CANDIDATE_FROZEN_AWAITING_HUMAN
        checks["rc_status_frozen_awaiting_human"] = status_ok
        if not status_ok:
            missing.append(f"rc_status_not_frozen:{rc.status.value}")

        # 7. Git 工作树干净（可选）
        if self.check_git:
            git_ok = _git_workspace_clean(base)
            checks["git_workspace_clean"] = git_ok
            if not git_ok:
                missing.append("git_workspace_dirty")

        all_ok = all(checks.values())
        return FreezeCheckResult(
            status=(
                FreezeCheckResultStatus.FROZEN
                if all_ok
                else FreezeCheckResultStatus.DRIFTED
            ),
            checks=checks,
            missing=missing,
        )


__all__ = [
    "FreezeCheckResultStatus",
    "FreezeCheckResult",
    "ReleaseFreezeChecker",
]
