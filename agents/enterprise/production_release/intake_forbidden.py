"""Phase 3.9.6 激活证据接收与人工签署治理层 —— 结构级禁名增量（红线①~⑩）。

本模块在 RC 冻结 / 受控激活禁名集之上，显式叠加「证据接收 / 人工签署治理」专属禁名。
与前序阶段的区别在于本阶段第一次让 AI **接触真实人工签署与真实激活证据**——因此
必须把"AI 可能越权的动词"逐个钉死在方法名层面：

* AI 代签 / 补签 / 伪造签署（红线③）；
* AI 把证据自行标记为 approved（红线④）；
* AI 宣布 PRODUCTION_GO（红线⑤）；
* AI 覆盖 / 篡改 / 撤销真实人工决策（红线⑨）；
* AI 跳过校验 / 强制评审包完整 / 绕过受控激活闸门（红线⑩）；
* AI 落盘证据原文或真实密钥（红线⑦，同时是 T13 存储安全的结构保障）；
* AI 自动授予真实生产权限（红线⑧）。

所有禁名由 ``_RedLineForbiddenMixin.__getattr__`` 拦截：一旦被调用即抛
``EnterpriseRedLineViolationError``（fail-closed）。这是**结构性**防线——不依赖
调用方自觉，也不依赖注释约束：方法根本不存在，且访问即抛错。
"""

from __future__ import annotations

from agents.enterprise.governance_dashboard.forbidden import _dedupe
from agents.enterprise.production_release.freeze_forbidden import (
    _FREEZE_ACTIVATION_FORBIDDEN,
)

# 激活证据接收 / 人工签署治理层专属禁名增量（Phase 3.9.6）。
_ACTIVATION_INTAKE_EXTRA_FORBIDDEN = (
    # —— 红线③：禁止 AI 构造 / 代签 / 补齐真实人工签署 ——
    "sign_off_as_human",
    "create_human_signoff_record",
    "fabricate_signoff",
    "auto_complete_signoffs",
    "fill_missing_signoff",
    "synthesize_human_signature",
    # —— 红线④：禁止 AI 自动把证据标记为已批准 / 已采信 ——
    "approve_evidence",
    "auto_approve_evidence",
    "mark_evidence_approved",
    "accept_evidence_as_human",
    "promote_validated_to_approved",
    # —— 红线⑤：禁止 AI 宣布生产 GO ——
    "declare_production_go",
    "announce_production_go",
    "mark_production_ready",
    # —— 红线⑨：禁止 AI 覆盖 / 篡改 / 撤销真实人工决策 ——
    "override_human_decision",
    "modify_human_signoff",
    "delete_human_signoff",
    "revoke_human_signoff",
    "amend_human_decision",
    "rewrite_signoff_history",
    # —— 红线⑩：禁止 AI 跳过校验 / 强制完整 / 绕过受控激活闸门 ——
    "skip_evidence_validation",
    "force_review_package_complete",
    "bypass_evidence_intake",
    "bypass_signoff_requirement",
    # —— 红线⑦：禁止落盘证据原文 / 真实生产密钥（T13 存储安全结构保障）——
    "store_evidence_content",
    "persist_evidence_payload",
    "store_production_secret",
    "write_production_credential",
    # —— 红线⑧：禁止自动授予真实生产权限 ——
    "grant_production_access",
    "auto_grant_activation_permission",
)

# 接收层禁名集 = 冻结 / 激活层全集 ∪ 本层增量。
_ACTIVATION_INTAKE_FORBIDDEN = _dedupe(
    _FREEZE_ACTIVATION_FORBIDDEN,
    _ACTIVATION_INTAKE_EXTRA_FORBIDDEN,
)

# 供测试 / 收口文档引用。
ACTIVATION_INTAKE_EXTRA_FORBIDDEN_COUNT = len(_ACTIVATION_INTAKE_EXTRA_FORBIDDEN)
ACTIVATION_INTAKE_FORBIDDEN_COUNT = len(_ACTIVATION_INTAKE_FORBIDDEN)

__all__ = [
    "_ACTIVATION_INTAKE_EXTRA_FORBIDDEN",
    "_ACTIVATION_INTAKE_FORBIDDEN",
    "ACTIVATION_INTAKE_EXTRA_FORBIDDEN_COUNT",
    "ACTIVATION_INTAKE_FORBIDDEN_COUNT",
]
