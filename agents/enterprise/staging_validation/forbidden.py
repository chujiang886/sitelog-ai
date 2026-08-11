"""Phase 3.9.1 预生产验证与灾难恢复演练层 —— 结构级禁名（红线①~⑦）。

本层是**纯验证 / 演练**层：把「生产准备体系是否可靠」以只读验证、模拟演练、恢复
校验结构沉淀下来。它**绝不**具备下列任何能力：

- 开启或翻转 ``engineering_enabled``（红线①）；
- 输出 ``engineering_approved``（红线②）；
- 执行真实生产部署（红线③）；
- 修改真实企业数据 / 真实配置（红线④）；
- 写入真实密钥（红线⑤）；
- 自动授予真实权限（红线⑥）；
- 代替生产负责人签署 / 确认 / 放行（红线⑦）。

本模块把既有全链路红线（驾驶舱 → 追踪层 → 准备层）叠加本层专属增量，形成
演练层禁名集。所有禁名以**精确方法名**形式被 ``_RedLineForbiddenMixin.__getattr__``
拦截：一旦调用即抛 ``EnterpriseRedLineViolationError``（fail-closed），AI 无法越权。
"""

from __future__ import annotations

from agents.enterprise.governance_dashboard.forbidden import _dedupe
from agents.enterprise.governance_traceability.forbidden import (
    _TRACEABILITY_FORBIDDEN,
)
from agents.enterprise.production_readiness.forbidden import (
    _PRODUCTION_READINESS_EXTRA_FORBIDDEN,
)

# 演练层专属禁名增量：聚焦「开生产 / 出 approved / 真部署 / 改真实数据 /
# 写真实密钥 / 自动授权 / 代生产负责人」。其中准备层增量已覆盖大部分，本层显式
# 叠加「真实部署 / 真实数据覆盖 / 真实恢复覆盖」等演练专属禁名，确保模拟动作
# 无法被误升级为真实动作。
_STAGING_VALIDATION_EXTRA_FORBIDDEN = (
    # —— 红线③：禁止真实生产部署（演练只模拟，不真部署）——
    "deploy_production_for_real",
    "run_real_deployment",
    "execute_live_rollout",
    # —— 红线④：禁止真实企业数据修改（演练只记录，不写真实数据）——
    "overwrite_real_data",
    "restore_real_data",
    "mutate_real_enterprise_record",
    "patch_real_production_config",
    # —— 红线⑤：禁止真实密钥写入（演练绝不写密钥）——
    "write_real_secret_key",
    "rotate_real_credential",
    # —— 红线⑥：禁止真实权限授予（演练只登记，不授权）——
    "grant_real_staging_permission",
    "assign_real_role_in_staging",
    # —— 红线⑦：禁止 AI 代生产负责人（演练结论只供人工采纳）——
    "sign_off_staging_validation",
    "certify_recovery_ready",
    "auto_conclude_drill",
)

# 演练层禁名集 = 全链路既有红线（驾驶舱 ∪ 追踪层 ∪ 准备层 …）∪ 本层增量。
_STAGING_VALIDATION_FORBIDDEN = _dedupe(
    _TRACEABILITY_FORBIDDEN,
    _PRODUCTION_READINESS_EXTRA_FORBIDDEN,
    _STAGING_VALIDATION_EXTRA_FORBIDDEN,
)

# 供测试 / 文档引用。
STAGING_VALIDATION_FORBIDDEN_COUNT = len(_STAGING_VALIDATION_FORBIDDEN)

__all__ = [
    "_STAGING_VALIDATION_EXTRA_FORBIDDEN",
    "_STAGING_VALIDATION_FORBIDDEN",
    "STAGING_VALIDATION_FORBIDDEN_COUNT",
]
