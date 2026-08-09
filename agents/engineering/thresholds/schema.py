"""Engineering 阈值治理 Schema（Phase 3.2 Sprint 3.2.4-A）。

定义阈值治理的**结构化类型契约**，供 ``threshold_loader`` 与后续
``ExpertBackedEngineeringValidation`` 复用，落地 Sprint 3.2.4
"阈值治理架构设计" 的 schema 层。

核心类型：
- ``ThresholdStatus``：阈值生命周期状态机（draft / review / verified / deprecated）；
- ``ThresholdSourceRef``：规范来源引用结构化（standard / clause / edition / url / retrieved_at）。

设计原则（红线）：
- 向前兼容既有 ``verified.json`` 字段（``verified`` 布尔镜像 + ``mgmt_signed``
  五字段判定零冲突）；本模块**不写入**任何 ``verified=true``、不填任何真实
  ``value``、不出现真实专家/主理人签字，所有数值保持 ``pending_verification``。
- ``threshold_status`` / ``version`` / 结构化 ``source_ref`` 均为**新增可选**
  能力，缺省时降级为"兼容态"（draft 态或不带版本），不强制既有文件改造。
- 3.2.4-E 引入 schema v2：``source_ref`` 新增 ``hash`` 字段（内容 sha256 摘要），
  新增 ``entry_schema_version`` 检测 v1/v2、``ensure_d_th_expert_sign_fields``
  补齐 D-TH 专家双签位（置 null，禁止自动填充），并导出 ``SCHEMA_VERSION_*`` 常量。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional


# 阈值生命周期四态（Sprint 3.2.4 治理设计 §2）。
# - draft：阈值录入/占位，不可用于任何工程判定；
# - review：已提交、主理人/专家审核中，仍 pending_verification；
# - verified：经双签 + 主理人核准，方可纳入工程判定（仍受 engineering_enabled 闸门约束）；
# - deprecated：已失效/被新版本取代，拒绝加载。
class ThresholdStatus(str, Enum):
    """阈值治理生命周期状态枚举（值即落库字符串）。"""

    DRAFT = "draft"
    REVIEW = "review"
    VERIFIED = "verified"
    DEPRECATED = "deprecated"

    @classmethod
    def from_raw(cls, raw: Any) -> "ThresholdStatus":
        """从原始字段（字符串或枚举）安全解析；缺省/非法 → DRAFT（最保守降级）。"""

        if isinstance(raw, ThresholdStatus):
            return raw
        if isinstance(raw, str):
            normalized = raw.strip().lower()
            for member in cls:
                if member.value == normalized:
                    return member
        # 无 threshold_status 字段或非预期值 → 视作未进入治理流程的 draft。
        return cls.DRAFT

    @property
    def is_loadable(self) -> bool:
        """是否允许被阈加载器纳入统一表：deprecated 拒绝加载。"""

        return self is not self.DEPRECATED


# 规范来源引用缺省占位（与既有 verified.json 的 "待行业专家签字填入… pending_verification" 语义一致）。
DEFAULT_SOURCE_REF_PLACEHOLDER: str = "pending_verification"


# 阈值 schema 版本（3.2.4-E 落地 v2）。
# - v1：自由文本 source_ref、无 threshold_status / version / hash（既有占位库）；
# - v2：结构化 source_ref（含 hash）+ threshold_status + version + 双签字段齐备。
SCHEMA_VERSION_V1: int = 1
SCHEMA_VERSION_V2: int = 2
CURRENT_SCHEMA_VERSION: int = SCHEMA_VERSION_V2


@dataclass(frozen=True)
class ThresholdSourceRef:
    """规范来源引用结构化（Sprint 3.2.4 治理设计 §3，3.2.4-E 升级 v2）。

    字段（全部可选，缺省空串 → 视为"引用不完整"，verified 态下将触发治理降级）：
    - standard：规范/标准名称或编号（如 "GB 50009"）；
    - clause：条款号（如 "8.1.1"）；
    - edition：版本/年号（如 "2012"）；
    - url：可溯源链接（可选，v2 增强校验要求 http(s) 可复核）；
    - retrieved_at：引用检索时间（ISO8601，可选）；
    - hash：v2 新增，引用源内容 sha256 摘要（禁止手写，由内容派生，增强校验）。
    """

    standard: str = ""
    clause: str = ""
    edition: str = ""
    url: str = ""
    retrieved_at: str = ""
    hash: str = ""

    @classmethod
    def from_raw(cls, raw: Any) -> "ThresholdSourceRef":
        """从既有 verified.json 的 ``source_ref`` 字段兼容解析。

        - 字符串（v1 自由文本）：整体落入 ``standard``，``hash`` 留空；
        - 字典：按字段映射（含 v2 新增 ``hash``），缺失字段留空；
        - 其他/缺失：返回全空占位。
        """

        if isinstance(raw, str):
            # 既有自由文本 source_ref（多为"待专家签字填入… pending_verification"）。
            text = raw.strip()
            if not text:
                return cls()
            return cls(standard=text)
        if isinstance(raw, Mapping):
            return cls(
                standard=str(raw.get("standard") or ""),
                clause=str(raw.get("clause") or ""),
                edition=str(raw.get("edition") or ""),
                url=str(raw.get("url") or ""),
                retrieved_at=str(raw.get("retrieved_at") or ""),
                hash=str(raw.get("hash") or ""),
            )
        return cls()

    def is_complete(self) -> bool:
        """引用完整性判定（v1/v2 一致）：standard 与 clause 双要素齐全。

        note：仅 standard 自由文本（旧形态）或任一缺失 → 不完整，触发 verified
        态治理降级。``hash`` / ``url`` / ``edition`` 属增强校验，不计入基础完整性。
        """

        return bool(self.standard.strip()) and bool(self.clause.strip())

    def as_dict(self) -> dict[str, str]:
        """结构化回写（供未来 verified.json 升级 schema_version 使用，含 v2 hash）。"""

        return {
            "standard": self.standard,
            "clause": self.clause,
            "edition": self.edition,
            "url": self.url,
            "retrieved_at": self.retrieved_at,
            "hash": self.hash,
        }


def entry_schema_version(entry: Mapping[str, Any] | None) -> int:
    """检测单条阈值条目所处 schema 版本（v1 / v2）。

    v2 标记：含 ``threshold_status`` / ``version`` 任一字段，或 ``source_ref``
    为结构化字典（v2）。否则视作 v1（自由文本 source_ref、无治理字段）。
    用于迁移工具识别待升级条目与向后兼容解析。
    """

    if not isinstance(entry, Mapping):
        return SCHEMA_VERSION_V1
    if "threshold_status" in entry or "version" in entry:
        return SCHEMA_VERSION_V2
    if isinstance(entry.get("source_ref"), Mapping):
        return SCHEMA_VERSION_V2
    return SCHEMA_VERSION_V1


# D-TH 双签字段（方案 A 方向，待最终授权）：缺省 null，禁止自动填充真实签字。
D_TH_EXPERT_SIGN_FIELDS: tuple[str, ...] = ("expert_verified_by", "expert_verified_at")


def ensure_d_th_expert_sign_fields(entry: Mapping[str, Any]) -> dict[str, Any]:
    """为 D-TH 条目补齐专家双签位（方案 A）：仅补字段、置 None，**禁止自动填充**。

    - E-TH 已具备该字段位则保留原值（含真实签字时也原样保留，不在此处变更）；
    - D-TH 缺位则补 ``expert_verified_by`` / ``expert_verified_at`` = None；
    - 红线：绝不写入任何真实专家签字值，仅补齐"可填"的结构位。
    """

    out: dict[str, Any] = dict(entry)
    for field_name in D_TH_EXPERT_SIGN_FIELDS:
        out.setdefault(field_name, None)
    return out


# 阈值条目治理元数据的极简运行时视图（供 threshold_loader 增强判定复用）。
@dataclass
class ThresholdGovernanceView:
    """单条阈值条目的治理视图：聚合 status / version / source_ref / 双签状态。

    纯运行时聚合，不落盘；从既有 verified.json 条目 + 上述枚举/结构类型派生。
    """

    threshold_id: str
    status: ThresholdStatus = ThresholdStatus.DRAFT
    version: str = ""
    source_ref: ThresholdSourceRef = field(default_factory=ThresholdSourceRef)
    verified: bool = False
    verified_by: Optional[str] = None
    verified_at: Optional[str] = None
    expert_verified_by: Optional[str] = None
    expert_verified_at: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_entry(cls, threshold_id: str, entry: Mapping[str, Any]) -> "ThresholdGovernanceView":
        """从既有 verified.json 单条目构建治理视图（向后兼容解析）。"""

        if not isinstance(entry, Mapping):
            entry = {}
        return cls(
            threshold_id=threshold_id,
            status=ThresholdStatus.from_raw(entry.get("threshold_status")),
            version=str(entry.get("version") or ""),
            source_ref=ThresholdSourceRef.from_raw(entry.get("source_ref")),
            verified=bool(entry.get("verified")),
            verified_by=entry.get("verified_by"),
            verified_at=entry.get("verified_at"),
            expert_verified_by=entry.get("expert_verified_by"),
            expert_verified_at=entry.get("expert_verified_at"),
            raw=dict(entry),
        )

    def mgmt_signed(self) -> bool:
        """主理人核准完整：verified=true 且 verified_by / verified_at 俱全。"""

        return bool(self.verified) and bool(self.verified_by) and bool(self.verified_at)

    def expert_signed(self) -> bool:
        """行业专家签字完整：expert_verified_by / expert_verified_at 俱全。"""

        return bool(self.expert_verified_by) and bool(self.expert_verified_at)

    def governance_ok(self) -> bool:
        """治理准入：仅当 status=VERIFIED 且 引用完整 且 双签齐全 才视为治理完备。

        draft / review 态或未带完整结构化引用或缺任一签字 → 不满足治理条件，
        由 threshold_loader 自动降级为 pending_verification。
        """

        return (
            self.status is ThresholdStatus.VERIFIED
            and self.source_ref.is_complete()
            and self.mgmt_signed()
            and self.expert_signed()
        )


# 治理拒绝加载的显式原因（供测试与日志可追溯）。
GOV_REASON_DEPRECATED = "threshold_status=deprecated 拒绝加载"
GOV_REASON_NOT_VERIFIED = "threshold_status 非 verified（draft/review）不纳入工程判定"
GOV_REASON_SOURCE_REF_INCOMPLETE = "verified 态 source_ref 结构化引用不完整"
GOV_REASON_EXPERT_MISSING = "verified 态缺行业专家签字（expert_verified_by/at）"
GOV_REASON_MGMT_MISSING = "verified 态缺主理人核准（verified_by/at 或 verified=false）"


__all__ = [
    "ThresholdStatus",
    "ThresholdSourceRef",
    "ThresholdGovernanceView",
    "DEFAULT_SOURCE_REF_PLACEHOLDER",
    "SCHEMA_VERSION_V1",
    "SCHEMA_VERSION_V2",
    "CURRENT_SCHEMA_VERSION",
    "entry_schema_version",
    "D_TH_EXPERT_SIGN_FIELDS",
    "ensure_d_th_expert_sign_fields",
    "GOV_REASON_DEPRECATED",
    "GOV_REASON_NOT_VERIFIED",
    "GOV_REASON_SOURCE_REF_INCOMPLETE",
    "GOV_REASON_EXPERT_MISSING",
    "GOV_REASON_MGMT_MISSING",
]
