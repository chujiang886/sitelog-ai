"""Phase 3.9.2 企业生产发布闸门与证据包层 —— 结构级禁名（红线①~⑦/⑩）。

本层是**纯闸门 / 证据包 / 候选 / 清单 / 回滚引用**层：把「发布候选可否放行」
「证据是否齐备」「清单是否可哈希」「回滚引用是否完整」以只读校验结构沉淀。
它**绝不**具备下列任何能力：

- 开启或翻转 ``engineering_enabled``（红线①）；
- 输出 ``engineering_approved``（红线②）；
- 执行真实生产部署 / 激活（红线③/⑩）；
- 修改真实企业数据 / 真实配置（红线④）；
- 写入真实密钥 / 自动授予真实生产权限（红线⑤/⑥）；
- 代替 production-owner / release-manager / security-owner / auditor 签署 /
  宣布生产 GO（红线⑦/⑧）；
- 把 simulation / drill / staging validation 描述成 production verified（红线⑨）。

本模块把既有全链路红线（驾驶舱 → 追踪层 → 准备层 → 演练层）叠加本层专属增量，
形成发布闸门层禁名集。所有禁名以**精确方法名**形式被 ``_RedLineForbiddenMixin.
__getattr__`` 拦截：一旦调用即抛 ``EnterpriseRedLineViolationError``（fail-closed），
AI 无法越权。
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

# 发布闸门层专属禁名增量：聚焦「真实部署 / 真激活 / 出 approved / 自动批准 RC /
# 代生产负责人签署 / 宣布生产 GO / 把演练当生产验证」。其中准备层 / 演练层增量已覆盖
# 大部分，本层显式叠加「发布闸门专属」禁名，确保闸门只产出 READY_FOR_HUMAN_REVIEW /
# BLOCKED / PENDING_VERIFICATION，永不产出生产 GO / APPROVED。
_PRODUCTION_RELEASE_EXTRA_FORBIDDEN = (
    # —— 红线③/⑩：禁止真实生产部署 / 激活 ——
    "deploy_production_for_real",
    "release_to_production",
    "activate_production_now",
    "execute_production_rollout",
    "run_live_release",
    # —— 红线②：禁止自动批准 / 宣布 GO / 出 approved ——
    "auto_approve_release",
    "auto_go_live",
    "declare_production_go",
    "emit_release_approved",
    "conclude_gate_as_go",
    "mark_release_verified",
    "certify_production_ready",
    # —— 红线①：禁止翻转 engineering_enabled（防御性叠加）——
    "flip_engineering_for_release",
    "open_engineering_for_release",
    # —— 红线⑤：禁止真实密钥写入 ——
    "write_real_production_secret",
    "rotate_real_production_credential",
    # —— 红线⑥：禁止真实生产权限授予 ——
    "grant_real_production_permission",
    "assign_real_production_role",
    # —— 红线⑦/⑧：禁止 AI 代生产负责人 / 各签署角色签署 ——
    "sign_release_for_user",
    "sign_for_user",
    "approve_on_behalf",
    "auto_signoff",
    "create_human_signoff",
    "attest_release_ready",
)

# 发布闸门层禁名集 = 全链路既有红线（驾驶舱 ∪ 追踪层 ∪ 准备层 ∪ 演练层 …）∪ 本层增量。
_PRODUCTION_RELEASE_FORBIDDEN = _dedupe(
    _TRACEABILITY_FORBIDDEN,
    _PRODUCTION_READINESS_EXTRA_FORBIDDEN,
    _STAGING_VALIDATION_EXTRA_FORBIDDEN,
    _PRODUCTION_RELEASE_EXTRA_FORBIDDEN,
)

# 供测试 / 文档引用。
PRODUCTION_RELEASE_FORBIDDEN_COUNT = len(_PRODUCTION_RELEASE_FORBIDDEN)

__all__ = [
    "_PRODUCTION_RELEASE_EXTRA_FORBIDDEN",
    "_PRODUCTION_RELEASE_FORBIDDEN",
    "PRODUCTION_RELEASE_FORBIDDEN_COUNT",
]
