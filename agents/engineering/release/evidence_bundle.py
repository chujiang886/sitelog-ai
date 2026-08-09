"""Release Evidence Bundle — 首次 wind_pressure 灰度发布的不可变证据包。

设计原则（红线）：
- 本模块**只引用证据**（文件哈希 / CI 事实哈希），**绝不承载或生成任何真实工程参数**
  （threshold 数值、专家签名、授权记录均由人工经正式流程提供）。
- 所有采集为**只读**：不修改、不创建任何生产证据文件；不设置 ci_green / rollback_ready；
  不开启 engineering_enabled；不输出 engineering_approved；不创建 ReleaseApproval。
- 证据缺失时如实记录（hash=None / present=False / notes 说明），不伪造。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# 证据文件默认根：agents/engineering/release/evidence_bundle.py -> BOIP 仓库根
DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]

# review_log 必须存在的四类审核事件（submit / review / expert_recheck / verified）
REQUIRED_INTAKE_EVENTS = (
    "submit",
    "review",
    "expert_recheck",
    "verified",
)


def _sha256_of(path: Path) -> Optional[str]:
    """返回文件 sha256（hex）；文件不存在返回 None（证据缺失，如实记录）。"""
    if not path.exists():
        return None
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _review_chain_present(review_log: Path) -> bool:
    """review_log 是否包含完整四类审核事件（submit / review / expert_recheck / verified）。"""
    if not review_log.exists():
        return False
    present: set[str] = set()
    for line in review_log.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        action = ev.get("action")
        if action in REQUIRED_INTAKE_EVENTS:
            present.add(action)
    return set(REQUIRED_INTAKE_EVENTS).issubset(present)


def _default_paths(repo_root: Path) -> dict:
    return {
        "verified": repo_root / "agents" / "engineering" / "thresholds" / "verified.json",
        "review_log": repo_root / "agents" / "engineering" / "review_log.jsonl",
        "approval": repo_root / "agents" / "engineering" / "release" / "release_approvals.jsonl",
        "rollback_ctl": repo_root / "scripts" / "release" / "gray_release_ctl.py",
        "config": repo_root / "agents" / "config.yaml",
    }


def _bundle_id(interface: str, commit_hash: str) -> str:
    """bundle_id 由 interface + commit_hash 决定（同 commit 同 interface 固定），

    不含 created_at，保证冻结语义下同一证据集的 bundle_id 稳定可复现。
    """
    raw = f"BOIP-EB-{interface}-{commit_hash}"
    return "BOIP-EB-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class ReleaseEvidenceBundle:
    """首次灰度发布的不可变证据包（仅引用哈希，不承载真实工程数值）。"""

    bundle_id: str
    interface: str
    threshold_evidence_hash: Optional[str]
    review_log_hash: Optional[str]
    authorization_hash: Optional[str]
    ci_evidence_hash: Optional[str]
    rollback_evidence_hash: Optional[str]
    commit_hash: str
    created_at: str
    # 证据存在性标记（布尔，非数值）
    threshold_evidence_present: bool = False
    review_evidence_present: bool = False
    authorization_present: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def complete(self) -> bool:
        """G1-G6 真实证据是否齐备（不含 ci_green / rollback_ready 等运行标志）。"""
        return all(
            [
                self.threshold_evidence_present,
                self.review_evidence_present,
                self.authorization_present,
                self.ci_evidence_hash is not None,
                self.rollback_evidence_hash is not None,
            ]
        )


def collect_release_evidence_bundle(
    interface: str,
    commit_hash: str,
    ci_evidence: dict,
    repo_root: Optional[Path] = None,
) -> ReleaseEvidenceBundle:
    """只读采集既有证据的哈希，构造不可变证据包。

    - ``ci_evidence``：由调用方提供的 CI 真实事实（commit/timestamp/test result/coverage），
      本函数**不运行测试、不设置 ci_green**。
    - 绝不读取或生成任何真实工程参数（threshold 数值 / 专家签名 / 授权记录）。
    - 所有证据文件仅读取其哈希，不修改、不创建。
    """
    repo_root = repo_root or DEFAULT_REPO_ROOT
    paths = _default_paths(repo_root)

    threshold_hash = _sha256_of(paths["verified"])
    review_hash = _sha256_of(paths["review_log"])
    approval_hash = _sha256_of(paths["approval"])
    rollback_ctl_hash = _sha256_of(paths["rollback_ctl"])

    created_at = datetime.now(timezone.utc).isoformat()

    # ci_evidence_hash：对 CI 证据字典做确定性哈希（仅引用事实，不承载真实参数）
    ci_hash = hashlib.sha256(
        json.dumps(ci_evidence, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()

    notes: list[str] = []
    threshold_present = threshold_hash is not None
    review_present = review_hash is not None and _review_chain_present(paths["review_log"])
    auth_present = approval_hash is not None

    if not threshold_present:
        notes.append("threshold_evidence_missing: verified.json 不存在")
    if not review_present:
        notes.append(
            "review_evidence_incomplete: review_log 缺少完整四类审核事件链 (submit/review/expert_recheck/verified)"
            " (submit/review/expert_recheck/verified)"
        )
    if not auth_present:
        notes.append("authorization_missing: EngineeringReleaseApproval 文件不存在 (G6 缺位)")

    return ReleaseEvidenceBundle(
        bundle_id=_bundle_id(interface, commit_hash),
        interface=interface,
        threshold_evidence_hash=threshold_hash,
        review_log_hash=review_hash,
        authorization_hash=approval_hash,
        ci_evidence_hash=ci_hash,
        rollback_evidence_hash=rollback_ctl_hash,
        commit_hash=commit_hash,
        created_at=created_at,
        threshold_evidence_present=threshold_present,
        review_evidence_present=review_present,
        authorization_present=auth_present,
        notes=notes,
    )


__all__ = [
    "ReleaseEvidenceBundle",
    "collect_release_evidence_bundle",
    "REQUIRED_INTAKE_EVENTS",
]
