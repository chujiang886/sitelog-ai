"""Phase 3.9.2 企业生产发布闸门与证据包层 —— Release Candidate 冻结模型（RC Freeze）。

本模块定义**只读冻结候选**结构：

- ``RCFreezeStatus``：冻结候选状态。AI 只可产出 ``RELEASE_CANDIDATE_FROZEN_AWAITING_HUMAN``
  （默认）/ ``DRIFTED``（冻结检查器检测到漂移）；``VERIFIED_BY_HUMAN`` / ``REJECTED_BY_HUMAN``
  只能由真实人工（主理人线下决策）产生，AI 不可进入。
- ``RCFreezeComponent``：被冻结的单个组件（名 / 仓库相对路径 / 冻结时 SHA-256 / 是否真实存在）。
- ``ReleaseCandidate``：冻结候选整体。``activation_approved`` 恒为 ``False``（fail-closed）；
  本模型**不提供** ``auto_activate`` / ``force_freeze`` / ``open_activation`` 之类能力。

本模块**不持有**任何生产状态，不执行任何真实激活 / 真实部署 / 真实数据覆盖 / 真实密钥写入。
所有放行只能源于真实人工线下签署（详见 ``human_approval`` 与 ``activation_gate``）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from agents.enterprise.production_release.package import _sha256_of_file


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RCFreezeStatus(str, Enum):
    """RC 冻结状态。

    AI 只能构造 ``RELEASE_CANDIDATE_FROZEN_AWAITING_HUMAN``（默认）/ ``DRIFTED``；
    ``VERIFIED_BY_HUMAN`` / ``REJECTED_BY_HUMAN`` 只能由真实人工产生，AI 不可进入。
    """

    RELEASE_CANDIDATE_FROZEN_AWAITING_HUMAN = "release_candidate_frozen_awaiting_human"
    DRIFTED = "drifted"
    VERIFIED_BY_HUMAN = "verified_by_human"
    REJECTED_BY_HUMAN = "rejected_by_human"


@dataclass(frozen=True)
class RCFreezeComponent:
    """被冻结的单个组件：名 / 仓库相对路径 / 冻结时刻 SHA-256 / 是否真实存在。"""

    name: str
    repo_path: str
    sha256: str  # "<missing>" / "<unreadable>" 表示文件不可达
    present: bool = True
    note: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "repo_path": self.repo_path,
            "sha256": self.sha256,
            "present": self.present,
            "note": self.note,
        }


@dataclass(frozen=True)
class ReleaseCandidate:
    """RC 冻结候选：仅描述冻结对象，不决策、不激活（fail-closed）。

    ``activation_approved`` 恒为 ``False``；``status`` 默认
    ``RELEASE_CANDIDATE_FROZEN_AWAITING_HUMAN``，进入生产前必须由真实人工核验 /
    签署推进到 ``VERIFIED_BY_HUMAN`` / ``REJECTED_BY_HUMAN``。本模型**不提供**
    ``auto_activate`` / ``force_approve`` / ``open_activation_gate`` 能力。
    """

    rc_id: str
    version: str
    commit_sha: str
    branch: str
    components: List[RCFreezeComponent] = field(default_factory=list)
    status: RCFreezeStatus = RCFreezeStatus.RELEASE_CANDIDATE_FROZEN_AWAITING_HUMAN
    activation_approved: bool = False  # fail-closed：AI 路径恒 False
    frozen_at: str = ""
    freeze_manifest_sha256: Optional[str] = None
    note: str = (
        "RC_FREEZE_ONLY: 冻结候选仅描述放行对象并与 manifest 对齐；不激活；"
        "最终放行须真实人工签署 ActivationEvidenceBundle / ReleaseSignoff"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "rc_id": self.rc_id,
            "version": self.version,
            "commit_sha": self.commit_sha,
            "branch": self.branch,
            "components": [c.to_dict() for c in self.components],
            "status": self.status.value,
            "activation_approved": self.activation_approved,
            "frozen_at": self.frozen_at,
            "freeze_manifest_sha256": self.freeze_manifest_sha256,
            "note": self.note,
        }

    def component_sha256_map(self) -> Dict[str, str]:
        """返回 {repo_path: sha256}，供冻结检查器比对漂移。"""
        return {c.repo_path: c.sha256 for c in self.components}


def create_release_candidate(
    *,
    rc_id: str,
    version: str,
    commit_sha: str,
    branch: str,
    component_specs: Dict[str, str],
    root_dir: str = ".",
) -> ReleaseCandidate:
    """冻结工厂：对 ``component_specs``（{名: 仓库相对路径}）即时计算 SHA-256，
    生成 ``ReleaseCandidate``（默认 ``RELEASE_CANDIDATE_FROZEN_AWAITING_HUMAN``）。

    缺失 / 不可读文件对应 sha256 标记为 ``<missing>`` / ``<unreadable>``，不得伪造。
    """

    base = os.path.abspath(root_dir)
    comps: List[RCFreezeComponent] = []
    for name, repo_path in component_specs.items():
        full = os.path.join(base, repo_path)
        sha = _sha256_of_file(full)
        comps.append(
            RCFreezeComponent(
                name=name,
                repo_path=repo_path,
                sha256=sha,
                present=sha not in ("<missing>", "<unreadable>"),
            )
        )
    return ReleaseCandidate(
        rc_id=rc_id,
        version=version,
        commit_sha=commit_sha,
        branch=branch,
        components=comps,
        frozen_at=_now(),
    )


__all__ = [
    "RCFreezeStatus",
    "RCFreezeComponent",
    "ReleaseCandidate",
    "create_release_candidate",
]
