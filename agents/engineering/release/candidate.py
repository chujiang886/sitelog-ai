"""Release Candidate Record — 首次 wind_pressure 灰度发布候选版本（RC）的不可变快照。

设计原则（红线）：
- 本模块**只引用**既有证据（文件哈希 / 证据包 id / Runbook 哈希），**绝不承载或生成
  任何真实工程参数**（threshold 数值、专家签名、授权记录均由人工经正式流程提供）。
- 所有采集为**只读**：不修改、不创建任何生产证据文件；不设置 ci_green / rollback_ready；
  不开启 engineering_enabled；不输出 engineering_approved；不创建 ReleaseApproval。
- 证据缺失时如实记录（hash=None / present=False / decision=NO-GO），不伪造。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agents.engineering.release.evidence_bundle import (
    collect_release_evidence_bundle,
)

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]

# 首次灰度 Runbook 版本（3.2.5-H4-A 产出的执行手册）
RUNBOOK_VERSION = "3.2.5-H4-A"


def _sha256_of(path: Path) -> Optional[str]:
    """返回文件 sha256（hex）；文件不存在返回 None（证据缺失，如实记录）。"""
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate_id(interface: str, commit_hash: str) -> str:
    """candidate_id 由 interface + commit_hash 决定（同 commit 同 interface 固定），

    不含 created_at，保证冻结语义下同一 RC 的 candidate_id 稳定可复现。
    """
    raw = f"BOIP-RC-{interface}-{commit_hash}"
    return "BOIP-RC-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _runbook_path(repo_root: Path) -> Path:
    return repo_root / ".ai" / "tasks" / "phase3.2.5H4A_release_runbook.md"


@dataclass
class ReleaseCandidateRecord:
    """首次灰度发布的候选版本记录（仅引用哈希，不承载真实工程数值）。

    核心六字段（任务书要求）：candidate_id / commit_hash / config_hash /
    evidence_bundle_id / runbook_version / created_at；其余为只读绑定的引用字段。
    """

    candidate_id: str
    commit_hash: str
    config_hash: Optional[str]
    evidence_bundle_id: str
    runbook_version: str
    created_at: str
    # 绑定证据（只读引用，非数值）
    runbook_hash: Optional[str] = None
    evidence_binding: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def complete(self) -> bool:
        """候选是否齐备：证据包完整 + Runbook 已冻结（hash 存在）。"""
        binding = self.evidence_binding or {}
        return bool(
            binding.get("threshold_evidence_present")
            and binding.get("review_evidence_present")
            and binding.get("authorization_present")
            and binding.get("ci_evidence_hash") is not None
            and binding.get("rollback_evidence_hash") is not None
            and self.runbook_hash is not None
        )

    @property
    def decision(self) -> str:
        """Final Candidate Decision：证据与 Runbook 齐备方为 GO，否则 NO-GO。"""
        return "GO" if self.complete else "NO-GO"


def collect_release_candidate(
    interface: str,
    commit_hash: str,
    ci_evidence: dict,
    runbook_version: str = RUNBOOK_VERSION,
    repo_root: Optional[Path] = None,
) -> ReleaseCandidateRecord:
    """只读构造 RC 记录：绑定证据包 + 冻结 Runbook + 引用 config 哈希。

    - 证据绑定：经由 ``collect_release_evidence_bundle`` 取得五类证据哈希与存在性；
    - Runbook 冻结：对 H4-A Runbook 文件做 sha256，记录 hash / version / timestamp；
    - 不运行测试、不设置 ci_green / rollback_ready；不创建任何文件。

    红线：不生成真实参数 / 签名 / 授权；不开启 engineering_enabled；不输出 approved。
    """
    repo_root = repo_root or DEFAULT_REPO_ROOT
    config_path = repo_root / "agents" / "config.yaml"
    config_hash = _sha256_of(config_path)

    bundle = collect_release_evidence_bundle(
        interface, commit_hash, ci_evidence, repo_root=repo_root
    )

    runbook_hash = _sha256_of(_runbook_path(repo_root))
    created_at = datetime.now(timezone.utc).isoformat()

    binding: dict = {
        "threshold_evidence_hash": bundle.threshold_evidence_hash,
        "review_log_hash": bundle.review_log_hash,
        "authorization_hash": bundle.authorization_hash,
        "ci_evidence_hash": bundle.ci_evidence_hash,
        "rollback_evidence_hash": bundle.rollback_evidence_hash,
        "threshold_evidence_present": bundle.threshold_evidence_present,
        "review_evidence_present": bundle.review_evidence_present,
        "authorization_present": bundle.authorization_present,
    }

    notes: list[str] = []
    if not bundle.complete:
        notes.append("evidence_incomplete: 证据包未齐备 -> candidate_decision=NO-GO")
    if runbook_hash is None:
        notes.append("runbook_missing: H4-A Runbook 文件缺失（未冻结）")

    return ReleaseCandidateRecord(
        candidate_id=_candidate_id(interface, commit_hash),
        commit_hash=commit_hash,
        config_hash=config_hash,
        evidence_bundle_id=bundle.bundle_id,
        runbook_version=runbook_version,
        created_at=created_at,
        runbook_hash=runbook_hash,
        evidence_binding=binding,
        notes=notes,
    )


__all__ = [
    "ReleaseCandidateRecord",
    "collect_release_candidate",
    "RUNBOOK_VERSION",
]
