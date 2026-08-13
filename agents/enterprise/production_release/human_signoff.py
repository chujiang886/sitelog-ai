"""Phase 3.9.6 人工签署记录与登记簿（T6 / T7）。

与 Phase 3.9.2 ``human_approval.py`` 的分工
-------------------------------------------
* ``human_approval.py`` 描述的是**最终一次**"人工激活批准"（单一汇总契约）；
* 本模块描述的是通往那一步的过程事实：**四个真实责任角色逐个签署**的
  ``HumanSignoffRecord``（T6），以及把它们 append-only 汇总的
  ``HumanSignoffRegistry``（T7）。

没有登记簿，"四角色是否齐备"只能靠人脑记；有了登记簿，缺谁、谁投了 NO_GO、
谁的签署被后续签署取代，都是可查、可审计、可 fail-closed 判定的事实。

红线（Phase 3.9.6 ③⑨）
-----------------------
* AI **不得构造**任何签署记录：工厂强制 ``actor_kind == "user"``，且必须提供
  ``signature_reference``（真实签署凭证坐标，如线下签署件编号 / 工单 / 邮件存档）；
* 登记簿**只聚合、不代签**：没有任何方法可以"补齐"缺失角色；
* ``signoff_complete`` 采用 fail-closed 语义：**四角色齐备且全部 GO** 才为真；
  任一角色缺失 / NO_GO / NEED_MORE_EVIDENCE → False；
* 即便 ``signoff_complete`` 为真，本模块也**不**宣布 Production GO、**不**翻转
  ``engineering_enabled`` —— 激活动作只能由主理人在人类终端执行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from agents.enterprise.production_release.activation_evidence import (
    REQUIRED_SIGNOFF_ROLES,
)
from agents.enterprise.production_release.models import SignoffDecision, SignoffRole


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class HumanSignoffError(Exception):
    """人工签署契约被违反（fail-closed）。"""


#: 签署者必须是真实自然人。
REQUIRED_SIGNOFF_ACTOR_KIND = "user"


# --------------------------------------------------------------------------- #
# T6：单条人工签署记录                                                           #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class HumanSignoffRecord:
    """一条真实人工签署记录（T6，只读事实）。

    ``evidence_scope_reviewed`` 记录该责任人**声明自己实际复核过**的证据提交 ID
    集合 —— 这让"签了但没看"这一治理风险变得可审计：登记簿可核对签署覆盖面是否
    覆盖了必需证据。AI 不得替签署人填充该字段。
    """

    signoff_id: str
    rc_id: str
    role: SignoffRole
    decision: SignoffDecision
    actor_id: str
    actor_kind: str
    signed_at: str
    signature_reference: str
    reason: str = ""
    evidence_scope_reviewed: Tuple[str, ...] = field(default_factory=tuple)
    note: str = (
        "HUMAN_SIGNOFF_ONLY: 真实责任人签署事实；AI 不构造、不代签；"
        "不翻转 engineering_enabled、不宣布 GO"
    )

    @property
    def signed_by_real_user(self) -> bool:
        return self.actor_kind.strip().lower() == REQUIRED_SIGNOFF_ACTOR_KIND

    @property
    def is_go(self) -> bool:
        return self.decision is SignoffDecision.GO and self.signed_by_real_user

    @property
    def is_blocking(self) -> bool:
        """是否构成阻断（NO_GO 或 要求补证据）。"""
        return self.decision in (
            SignoffDecision.NO_GO,
            SignoffDecision.NEED_MORE_EVIDENCE,
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "signoff_id": self.signoff_id,
            "rc_id": self.rc_id,
            "role": self.role.value,
            "decision": self.decision.value,
            "actor_id": self.actor_id,
            "actor_kind": self.actor_kind,
            "signed_at": self.signed_at,
            "signature_reference": self.signature_reference,
            "reason": self.reason,
            "evidence_scope_reviewed": list(self.evidence_scope_reviewed),
            "is_go": self.is_go,
            "is_blocking": self.is_blocking,
            "note": self.note,
        }


def build_human_signoff_record(
    *,
    signoff_id: str,
    rc_id: str,
    role: SignoffRole,
    decision: SignoffDecision,
    actor_id: str,
    actor_kind: str,
    signature_reference: str,
    reason: str = "",
    evidence_scope_reviewed: Sequence[str] = (),
    signed_at: Optional[str] = None,
) -> HumanSignoffRecord:
    """登记一条**已经发生**的真实人工签署。

    这不是"创建签署"，而是"如实记录签署已发生"——因此必须提供
    ``signature_reference``（真实签署凭证坐标）。缺少任一真实性要件即抛错：

    * ``actor_kind`` 必须为 ``user``（AI / SYSTEM 不得签署）；
    * ``actor_id`` 非空；
    * ``signature_reference`` 非空（无凭证的"签署"不可采信）。
    """
    if actor_kind.strip().lower() != REQUIRED_SIGNOFF_ACTOR_KIND:
        raise HumanSignoffError(
            "release signoff must be performed by a real human user "
            f"(actor_kind='user'), got {actor_kind!r}"
        )
    if not actor_id.strip():
        raise HumanSignoffError("signoff requires a real actor_id")
    if not signature_reference.strip():
        raise HumanSignoffError(
            "signoff requires a real signature_reference (offline signed document / "
            "ticket / archived approval); an unreferenced signoff is not admissible"
        )

    return HumanSignoffRecord(
        signoff_id=signoff_id,
        rc_id=rc_id,
        role=role,
        decision=decision,
        actor_id=actor_id,
        actor_kind=REQUIRED_SIGNOFF_ACTOR_KIND,
        signed_at=signed_at or _now(),
        signature_reference=signature_reference,
        reason=reason,
        evidence_scope_reviewed=tuple(evidence_scope_reviewed),
    )


# --------------------------------------------------------------------------- #
# T7：人工签署登记簿                                                             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class HumanSignoffRegistrySnapshot:
    """登记簿只读快照（供闸门 / API / 报告消费）。"""

    rc_id: str
    required_roles: Tuple[str, ...]
    signed_roles: Tuple[str, ...]
    missing_roles: Tuple[str, ...]
    blocking_roles: Tuple[str, ...]
    signoff_complete: bool
    unanimous_go: bool
    total_records: int
    effective_records: Tuple[Dict[str, object], ...]
    superseded_records: Tuple[Dict[str, object], ...]
    generated_at: str
    note: str = (
        "SIGNOFF_REGISTRY_SNAPSHOT: 只读聚合；signoff_complete 仅表示四角色真实 GO 齐备，"
        "不等于 Production GO；激活由主理人在人类终端执行"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "rc_id": self.rc_id,
            "required_roles": list(self.required_roles),
            "signed_roles": list(self.signed_roles),
            "missing_roles": list(self.missing_roles),
            "blocking_roles": list(self.blocking_roles),
            "signoff_complete": self.signoff_complete,
            "unanimous_go": self.unanimous_go,
            "total_records": self.total_records,
            "effective_records": [dict(r) for r in self.effective_records],
            "superseded_records": [dict(r) for r in self.superseded_records],
            "generated_at": self.generated_at,
            "note": self.note,
        }


class HumanSignoffRegistry:
    """人工签署登记簿（T7）：append-only 聚合，不代签、不提升状态。

    语义约定
    --------
    * **append-only**：``register()`` 只追加，永不删除、永不修改既有记录；
    * **同角色重复签署**：保留全部历史，判定时以该角色**最新一条**为有效
      （``effective``），更早的标记为 ``superseded`` 并在快照中如实呈现 ——
      既尊重"人可以改主意"，又不隐藏改主意这一事实；
    * **fail-closed**：``signoff_complete`` 要求四角色齐备且**全部 GO**。
    """

    def __init__(self, *, rc_id: str) -> None:
        if not rc_id.strip():
            raise HumanSignoffError("signoff registry requires a real rc_id")
        self._rc_id = rc_id
        self._records: List[HumanSignoffRecord] = []

    # -- 写入（仅追加真实人工签署）-------------------------------------- #

    def register(self, record: HumanSignoffRecord) -> HumanSignoffRecord:
        """追加一条真实人工签署记录。

        校验：属于同一 RC、由真实 USER 签署。AI 无法通过本方法"补齐"角色 ——
        它只能记录外部真实发生的签署。
        """
        if record.rc_id != self._rc_id:
            raise HumanSignoffError(
                f"signoff rc_id mismatch: registry={self._rc_id!r}, record={record.rc_id!r}"
            )
        if not record.signed_by_real_user:
            raise HumanSignoffError(
                "only a real human user signoff can be registered (actor_kind='user')"
            )
        self._records.append(record)
        return record

    def extend(self, records: Iterable[HumanSignoffRecord]) -> None:
        for record in records:
            self.register(record)

    # -- 只读聚合 --------------------------------------------------------- #

    @property
    def rc_id(self) -> str:
        return self._rc_id

    @property
    def records(self) -> Tuple[HumanSignoffRecord, ...]:
        """全部历史记录（append-only 顺序）。"""
        return tuple(self._records)

    def effective_by_role(self) -> Dict[str, HumanSignoffRecord]:
        """每个角色的**最新有效**签署（后签覆盖先签，历史仍保留）。"""
        latest: Dict[str, HumanSignoffRecord] = {}
        for record in self._records:
            latest[record.role.value] = record
        return latest

    def superseded(self) -> Tuple[HumanSignoffRecord, ...]:
        """被同角色后续签署取代的历史记录（如实暴露"改主意"过程）。"""
        effective = self.effective_by_role()
        return tuple(
            r for r in self._records if effective.get(r.role.value) is not r
        )

    @property
    def signed_roles(self) -> Tuple[str, ...]:
        return tuple(sorted(self.effective_by_role().keys()))

    @property
    def missing_roles(self) -> Tuple[str, ...]:
        signed = set(self.effective_by_role().keys())
        return tuple(r for r in REQUIRED_SIGNOFF_ROLES if r not in signed)

    @property
    def blocking_roles(self) -> Tuple[str, ...]:
        """有效签署中构成阻断（NO_GO / NEED_MORE_EVIDENCE）的角色。"""
        return tuple(
            sorted(
                role
                for role, record in self.effective_by_role().items()
                if record.is_blocking
            )
        )

    @property
    def unanimous_go(self) -> bool:
        """已签署的角色是否全部 GO（不代表齐备）。"""
        effective = self.effective_by_role()
        return bool(effective) and all(r.is_go for r in effective.values())

    @property
    def signoff_complete(self) -> bool:
        """四角色齐备且全部真实 GO（fail-closed）。

        缺一角色、任一 NO_GO / NEED_MORE_EVIDENCE → False。
        为真也**不**代表 Production GO，只代表签署前置已满足。
        """
        return not self.missing_roles and self.unanimous_go

    def evidence_scope_union(self) -> Tuple[str, ...]:
        """所有有效签署声明复核过的证据 ID 并集（供覆盖面核对）。"""
        scope: set[str] = set()
        for record in self.effective_by_role().values():
            scope.update(record.evidence_scope_reviewed)
        return tuple(sorted(scope))

    def roles_missing_evidence_scope(
        self, required_submission_ids: Sequence[str]
    ) -> Dict[str, Tuple[str, ...]]:
        """逐角色列出"未声明复核"的必需证据（治理可视化，不阻断、不代判）。"""
        required = list(required_submission_ids)
        gaps: Dict[str, Tuple[str, ...]] = {}
        for role, record in self.effective_by_role().items():
            reviewed = set(record.evidence_scope_reviewed)
            missing = tuple(s for s in required if s not in reviewed)
            if missing:
                gaps[role] = missing
        return gaps

    def snapshot(self) -> HumanSignoffRegistrySnapshot:
        return HumanSignoffRegistrySnapshot(
            rc_id=self._rc_id,
            required_roles=tuple(REQUIRED_SIGNOFF_ROLES),
            signed_roles=self.signed_roles,
            missing_roles=self.missing_roles,
            blocking_roles=self.blocking_roles,
            signoff_complete=self.signoff_complete,
            unanimous_go=self.unanimous_go,
            total_records=len(self._records),
            effective_records=tuple(
                r.to_dict() for r in self.effective_by_role().values()
            ),
            superseded_records=tuple(r.to_dict() for r in self.superseded()),
            generated_at=_now(),
        )


__all__ = [
    "HumanSignoffError",
    "REQUIRED_SIGNOFF_ACTOR_KIND",
    "HumanSignoffRecord",
    "build_human_signoff_record",
    "HumanSignoffRegistry",
    "HumanSignoffRegistrySnapshot",
]
