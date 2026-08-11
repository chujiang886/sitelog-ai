"""Phase 3.9.0 生产就绪与受控激活准备层 —— 结构级禁名（红线①~⑥）。

本层是**纯准备**层：把「生产上线前该检查什么 / 该准备什么 / 该由谁线下决策」以
只读结构与计划文档形式沉淀下来。它**绝不**具备下列任何能力：

- 开启或翻转 ``engineering_enabled``（红线①）；
- 输出 ``engineering_approved``（红线②）；
- 执行真实生产激活 / 部署（红线③）；
- 修改真实企业数据 / 真实配置（红线④）；
- 自动创建真实权限 / 写入真实密钥（红线⑤）；
- 代替生产负责人签署 / 确认 / 放行（红线⑥）。

本模块把既有全链路红线（驾驶舱 → 追踪层）叠加本层专属增量，形成准备层禁名集。
所有禁名以**精确方法名**形式被 ``_RedLineForbiddenMixin.__getattr__`` 拦截：一旦调用即
抛 ``EnterpriseRedLineViolationError``（fail-closed），AI 无法越权。
"""

from __future__ import annotations

from agents.enterprise.governance_dashboard.forbidden import _dedupe
from agents.enterprise.governance_traceability.forbidden import (
    _TRACEABILITY_FORBIDDEN,
)

# 准备层专属禁名增量：聚焦「开生产 / 出 approved / 真激活 / 改真实数据 /
# 写真实密钥 / 自动授权 / 代生产负责人」。
_PRODUCTION_READINESS_EXTRA_FORBIDDEN = (
    # —— 红线①：禁止 AI 翻转 engineering_enabled ——
    "enable_engineering",
    "set_engineering_enabled",
    "flip_engineering_enabled",
    "activate_engineering",
    "turn_on_production",
    "open_production",
    # —— 红线②：禁止输出 engineering_approved ——
    "issue_engineering_approved",
    "output_engineering_approved",
    "emit_engineering_approved",
    "approve_activation",
    "auto_approve_activation",
    "grant_activation",
    # —— 红线③：禁止真实生产激活 / 部署 ——
    "deploy_production",
    "run_production_deploy",
    "activate_production",
    "execute_rollout",
    "go_live",
    # —— 红线④：禁止改真实企业数据 / 配置 ——
    "write_real_config",
    "modify_real_enterprise_data",
    "mutate_production_state",
    "patch_production_config",
    # —— 红线⑤：禁止自动真实权限 / 写真实密钥 ——
    "grant_real_permission",
    "create_real_role",
    "auto_assign_role",
    "provision_real_access",
    "write_real_credential",
    "store_real_secret",
    "inject_secret",
    "set_real_api_key",
    # —— 红线⑥：禁止 AI 代生产负责人 ——
    "act_as_production_owner",
    "sign_off_activation",
    "attest_production_ready",
    "certify_production",
    "auto_release",
    "self_approve_production",
)

# 准备层禁名集 = 全链路既有红线（驾驶舱 ∪ 追踪层 …）∪ 本层增量。
_PRODUCTION_READINESS_FORBIDDEN = _dedupe(
    _TRACEABILITY_FORBIDDEN, _PRODUCTION_READINESS_EXTRA_FORBIDDEN
)

# 供测试 / 文档引用。
PRODUCTION_READINESS_FORBIDDEN_COUNT = len(_PRODUCTION_READINESS_FORBIDDEN)

__all__ = [
    "_PRODUCTION_READINESS_FORBIDDEN",
    "_PRODUCTION_READINESS_EXTRA_FORBIDDEN",
    "PRODUCTION_READINESS_FORBIDDEN_COUNT",
]
