"""Phase 3.9.7 企业生产变更管控平面 —— 结构级禁名（红线①~⑦/⑩）。

本层是**纯变更管控 / 仿真 / 证据包 / 评审 / 回滚引用**层：把「变更请求可否进入
受控窗口」「仿真是否通过」「证据是否齐备」「回滚引用是否完整」「人工裁决是否登记」
以只读校验结构沉淀。它**绝不**具备下列任何能力：

- 开启或翻转 ``engineering_enabled``（红线①）；
- 输出 ``engineering_approved``（红线②）；
- 执行真实生产变更 / 部署 / 迁移 / 回滚 / 应用（红线③/⑩）；
- 修改真实企业数据 / 真实配置（红线④）；
- 写入真实密钥 / 自动授予真实生产权限（红线⑤/⑥）；
- 代替 production-owner / release-manager / security-owner / auditor 签署 /
  宣布生产 GO / 把仿真结果描述为真实 Production Change（红线⑦/⑧/⑨）；
- 把 simulation / drill 描述成 production verified（红线⑨）。

本模块把既有全链路红线（驾驶舱 → 追踪层 → 准备层 → 演练层 → 发布闸门 → 受控激活）
叠加本层专属增量，形成变更管控层禁名集。所有禁名以**精确方法名**形式被
``_RedLineForbiddenMixin.__getattr__`` 拦截：一旦调用即抛
``EnterpriseRedLineViolationError``（fail-closed），AI 无法越权。
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
from agents.enterprise.production_release.freeze_forbidden import (
    _FREEZE_ACTIVATION_FORBIDDEN,
)
from agents.enterprise.production_release.intake_forbidden import (
    _ACTIVATION_INTAKE_FORBIDDEN,
)

# 变更管控层专属禁名增量：聚焦「真实变更执行 / 真实部署 / 真实迁移 / 真实回滚 /
# 真实应用 / 自动完成 / 出 approved / 自动批准变更 / 代生产负责人签署 / 宣布变更 GO /
# 把仿真当生产验证 / 绕过变更闸门」。其中准备层 / 演练层 / 发布闸门 / 受控激活增量已覆盖
# 大部分，本层显式叠加「变更执行专属」禁名，确保变更管控层只产出
# HUMAN_DRAFTED / AWAITING_HUMAN_REVIEW / HUMAN_COMPLETED / HUMAN_ABORTED，
# 永不产出 AUTO_EXECUTING / AUTO_COMPLETED / AI_APPROVED / PRODUCTION_GO。
_PRODUCTION_CHANGE_EXTRA_FORBIDDEN = (
    # —— 红线③/⑩：禁止真实生产变更 / 部署 / 迁移 / 回滚 / 应用 ——
    "execute_change",
    "deploy_production",
    "rollback_production",
    "apply_change",
    "migrate_production",
    "trigger_go",
    "run_live_change",
    "activate_change_now",
    "auto_execute_change",
    "auto_apply_change",
    "schedule_automatic_change",
    "auto_complete_change",
    # —— 红线②：禁止自动批准 / 宣布 GO / 出 approved ——
    "declare_change_go",
    "emit_change_approved",
    "conclude_change_as_go",
    "mark_change_verified",
    "certify_change_ready",
    "auto_approve_change",
    # —— 红线①：禁止翻转 engineering_enabled（防御性叠加）——
    "flip_engineering_for_change",
    "open_engineering_for_change",
    # —— 红线⑤：禁止真实密钥写入 ——
    "write_real_change_secret",
    "rotate_real_change_credential",
    # —— 红线⑥：禁止真实生产权限授予 ——
    "grant_real_production_change_access",
    "assign_real_change_role",
    # —— 红线⑦/⑧：禁止 AI 代生产负责人 / 各签署角色签署 ——
    "sign_change_for_user",
    "auto_signoff_change",
    "create_human_change_signoff",
    "attest_change_ready",
    # —— 红线⑦/⑨：禁止绕过变更闸门 / 把仿真当生产验证 ——
    "bypass_change_gate",
    "skip_human_change_review",
    "release_lock_without_human",
    "promote_simulation_to_production",
    "mark_simulation_as_verified_change",
)

# 变更管控层禁名集 = 全链路既有红线（驾驶舱 ∪ 追踪层 ∪ 准备层 ∪ 演练层 ∪ 发布闸门 ∪
# 受控激活 ∪ 证据接收）∪ 本层增量。
_PRODUCTION_CHANGE_FORBIDDEN = _dedupe(
    _TRACEABILITY_FORBIDDEN,
    _PRODUCTION_READINESS_EXTRA_FORBIDDEN,
    _STAGING_VALIDATION_EXTRA_FORBIDDEN,
    _PRODUCTION_RELEASE_EXTRA_FORBIDDEN,
    _FREEZE_ACTIVATION_FORBIDDEN,
    _ACTIVATION_INTAKE_FORBIDDEN,
    _PRODUCTION_CHANGE_EXTRA_FORBIDDEN,
)

# 供测试 / 文档引用。
PRODUCTION_CHANGE_FORBIDDEN_COUNT = len(_PRODUCTION_CHANGE_FORBIDDEN)

__all__ = [
    "_PRODUCTION_CHANGE_EXTRA_FORBIDDEN",
    "_PRODUCTION_CHANGE_FORBIDDEN",
    "PRODUCTION_CHANGE_FORBIDDEN_COUNT",
]
