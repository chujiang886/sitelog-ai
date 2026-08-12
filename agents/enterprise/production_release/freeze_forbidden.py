"""Phase 3.9.2 RC 冻结 / 受控激活层 —— 结构级禁名增量（红线①~⑧/⑩）。

本模块在发布闸门层禁名集之上，显式叠加「RC 冻结 / 受控激活」专属禁名：聚焦「强制冻结 /
自动核验 / 开启激活闸门 / 自动激活生产 / 绕过闸门 / 伪造人工激活签署 / 宣布激活 GO /
翻转 engineering_enabled」。所有禁名以精确方法名被 ``_RedLineForbiddenMixin.__getattr__``
拦截：一旦调用即抛 ``EnterpriseRedLineViolationError``（fail-closed），AI 无法越权。

合并进 ``_PRODUCTION_RELEASE_FORBIDDEN`` 后，受控激活闸门与人工签署服务继承同一禁名集，
无需各自维护。
"""

from __future__ import annotations

from agents.enterprise.governance_dashboard.forbidden import _dedupe
from agents.enterprise.governance_traceability.forbidden import (
    _TRACEABILITY_FORBIDDEN,
)
from agents.enterprise.production_readiness.forbidden import (
    _PRODUCTION_READINESS_EXTRA_FORBIDDEN,
)
from agents.enterprise.staging_validation.forbidden import (
    _STAGING_VALIDATION_EXTRA_FORBIDDEN,
)
from agents.enterprise.production_release.forbidden import (
    _PRODUCTION_RELEASE_EXTRA_FORBIDDEN,
)

# RC 冻结 / 受控激活层专属禁名增量。
_FREEZE_ACTIVATION_EXTRA_FORBIDDEN = (
    # —— 红线⑩：禁止强制冻结 / 自动核验（冻结须真实人工发起）——
    "force_rc_freeze",
    "auto_verify_rc_freeze",
    # —— 红线③/⑩：禁止开启激活闸门 / 自动激活生产 ——
    "open_activation_gate",
    "auto_activate_production",
    "activate_production_now",
    "execute_activation",
    # —— 红线⑧：禁止绕过闸门 / 伪造人工激活签署 / 宣布激活 GO ——
    "bypass_activation_gate",
    "forge_activation_approval",
    "forge_signature",
    "mark_activation_approved",
    "declare_activation_go",
    "auto_sign_activation",
    "create_human_activation_approval",
    # —— 红线①：禁止翻转 engineering_enabled（防御性叠加）——
    "flip_engineering_for_activation",
)

# 冻结 / 激活层禁名集 = 全链路既有红线 ∪ 发布闸门层增量 ∪ 本层增量。
_FREEZE_ACTIVATION_FORBIDDEN = _dedupe(
    _TRACEABILITY_FORBIDDEN,
    _PRODUCTION_READINESS_EXTRA_FORBIDDEN,
    _STAGING_VALIDATION_EXTRA_FORBIDDEN,
    _PRODUCTION_RELEASE_EXTRA_FORBIDDEN,
    _FREEZE_ACTIVATION_EXTRA_FORBIDDEN,
)

# 供测试 / 文档引用。
FREEZE_ACTIVATION_FORBIDDEN_COUNT = len(_FREEZE_ACTIVATION_FORBIDDEN)

__all__ = [
    "_FREEZE_ACTIVATION_EXTRA_FORBIDDEN",
    "_FREEZE_ACTIVATION_FORBIDDEN",
    "FREEZE_ACTIVATION_FORBIDDEN_COUNT",
]
