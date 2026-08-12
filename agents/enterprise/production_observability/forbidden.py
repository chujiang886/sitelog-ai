"""Phase 3.9.3 企业生产可观测性、SRE 与事故响应准备层 —— 结构级禁名（红线①~⑫）。

本层是**纯可观测 / 被动监测 / 事故候选 / 响应草稿 / 复盘草稿**层：把「组件健康如何」
「指标为何异常」「告警候选是否生成」「事故候选是否关联」「根因是否待验证」以只读 /
事实描述结构沉淀。它**绝不**具备下列任何能力：

- 开启或翻转 ``engineering_enabled``（红线①）；
- 输出 ``engineering_approved``（红线②）；
- 自动批准生产发布（红线③）；
- 自动执行生产部署（红线④，3.9.2 已覆盖，防御性叠加）；
- 自动执行生产回滚（红线⑤）；
- 自动修改真实企业数据（红线⑥）；
- 写入真实生产密钥（红线⑦，3.9.2 已覆盖，防御性叠加）；
- 自动授予真实生产权限（红线⑧，3.9.2 已覆盖，防御性叠加）；
- 自动关闭生产 Incident（红线⑨）；
- 代替 SRE / production-owner / security-owner / incident-commander 做责任签署
  （红线⑩）；
- 把模拟监控数据描述成真实 production observation（红线⑪）；
- 通过删除安全断言 / 跳过失败测试 / 降权 / 伪造监控证据让观测门禁变绿（红线⑫）。

本模块把既有全链路红线（驾驶舱 → 追踪层 → 准备层 → 演练层 → 发布闸门层）叠加本层
专属增量，形成可观测性层禁名集。所有禁名以**精确方法名**形式被
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

# 可观测性层专属禁名增量：聚焦「自动修复 / 自动回滚 / 自动 ACK / 自动 RESOLVE /
# 自动 CLOSE / 自动指派指挥官 / AI 代指挥 / 把模拟数据当真实观测」。其中准备层 /
# 演练层 / 发布闸门层增量已覆盖大部分部署 / 批准类，本层显式叠加「事故响应专属」禁名，
# 确保事故只能由真实 USER 在 API 层 ACK / RESOLVE / CLOSE，永不出 AUTO_* 状态。
_PRODUCTION_OBSERVABILITY_EXTRA_FORBIDDEN = (
    # —— 红线⑤：禁止自动生产回滚 ——
    "auto_rollback_incident",
    "execute_production_rollback",
    "rollback_to_last_known_good",
    # —— 红线⑨：禁止自动关闭 / 解决 Incident ——
    "auto_resolve_incident",
    "auto_close_incident",
    "auto_acknowledge_alert",
    "auto_acknowledge_incident",
    "auto_heal_incident",
    "auto_mitigate_incident",
    "silence_alert",
    # —— 红线⑩：禁止 AI 代指挥 / 代签 ——
    "assign_self_as_commander",
    "auto_assign_incident_commander",
    "act_as_incident_commander",
    "sign_incident_for_user",
    "auto_signoff_incident",
    "resolve_on_behalf",
    "close_on_behalf",
    "declare_incident_resolved",
    # —— 红线⑩补充：禁止代替 SRE / owner 签署责任节点 ——
    "approve_incident_postmortem",
    "auto_publish_postmortem",
    # —— 红线⑪：禁止把模拟监控数据描述成真实观测 ——
    "promote_simulation_to_production_observation",
    "mark_synthetic_as_real_metric",
    "fabricate_observability_evidence",
    # —— 红线④：禁止自动生产部署（防御性叠加）——
    "deploy_fix_to_production",
    "auto_remediate_production",
)

# 可观测性层禁名集 = 全链路既有红线（驾驶舱 ∪ 追踪层 ∪ 准备层 ∪ 演练层 ∪ 发布闸门层）∪ 本层增量。
_PRODUCTION_OBSERVABILITY_FORBIDDEN = _dedupe(
    _TRACEABILITY_FORBIDDEN,
    _PRODUCTION_READINESS_EXTRA_FORBIDDEN,
    _STAGING_VALIDATION_EXTRA_FORBIDDEN,
    _PRODUCTION_RELEASE_EXTRA_FORBIDDEN,
    _PRODUCTION_OBSERVABILITY_EXTRA_FORBIDDEN,
)

# 供测试 / 文档引用。
PRODUCTION_OBSERVABILITY_FORBIDDEN_COUNT = len(_PRODUCTION_OBSERVABILITY_FORBIDDEN)

__all__ = [
    "_PRODUCTION_OBSERVABILITY_EXTRA_FORBIDDEN",
    "_PRODUCTION_OBSERVABILITY_FORBIDDEN",
    "PRODUCTION_OBSERVABILITY_FORBIDDEN_COUNT",
]
