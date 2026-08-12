"""Phase 3.9.4 生产遥测接入适配与合成运维验证层 —— 结构级禁名（红线①~⑭）。

本层是**遥测适配 / 合成运维验证 / 告警路由端口 / 事故演练**层：把「遥测数据如何
被抽象接入」「合成故障如何被注入」「告警如何被路由（仅端口/仅模拟）」「事故演练如何
端到端跑通」以只读 / 事实描述 / 端口契约结构沉淀。它**绝不**具备下列任何能力：

- 开启或翻转 ``engineering_enabled``（红线①）；
- 输出 ``engineering_approved``（红线②）；
- 自动批准生产发布（红线③）；
- 自动执行生产部署（红线④）；
- 自动执行生产回滚（红线⑤）；
- 自动修改真实企业数据（红线⑥）；
- 写入真实生产密钥（红线⑦）；
- 自动授予真实生产权限（红线⑧）；
- 自动 ACK / RESOLVE / CLOSE Incident（红线⑨）；
- 代替 SRE / incident-commander / production-owner 做责任签署（红线⑩）；
- 把 Synthetic Telemetry 描述成真实生产 Telemetry（红线⑪）；
- 真实发送 PagerDuty / 企业微信 / Slack / Email 等生产告警（红线⑫）；
- 自动执行 Runbook（红线⑬）；
- 通过删安全断言 / 跳失败测试 / 降低权限 / 伪造遥测证据让门禁变绿（红线⑭）。

本模块把全链路既有红线（驾驶舱 → 追踪层 → 准备层 → 演练层 → 发布闸门层 → 可观测层）
叠加本层专属增量（遥测注入 / 端口降级伪装 / 真实告警外发 / Runbook 自动执行），形成
遥测层禁名集。所有禁名以**精确方法名**形式被 ``_RedLineForbiddenMixin.__getattr__``
拦截：一旦调用即抛 ``EnterpriseRedLineViolationError``（fail-closed）。
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
from agents.enterprise.production_observability.forbidden import (
    _PRODUCTION_OBSERVABILITY_EXTRA_FORBIDDEN,
)

# 遥测层专属禁名增量：聚焦「真实故障注入 / 端口降级伪装 / 真实告警外发 / Runbook 自动
# 执行 / 把合成当真实 / 测试 USER 绕过」。
_TELEMETRY_EXTRA_FORBIDDEN = (
    # —— 红线⑭/⑥：禁止向真实服务注入故障 / kill 进程 / 断真实网络 / 改真实库 / 污染真实配置 ——
    "inject_production_fault",
    "inject_real_fault",
    "inject_fault_into_real_service",
    "kill_real_process",
    "break_real_network",
    "modify_real_database_for_drill",
    "pollute_real_config",
    # —— 红线⑪：禁止把合成遥测伪装成真实生产遥测 / 端口降级伪装 ——
    "fallback_synthetic_as_production",
    "auto_fallback_provider",
    "promote_simulation_to_production_telemetry",
    "mark_synthetic_as_real_telemetry",
    "use_synthetic_as_production_source",
    # —— 红线⑩补充：禁止测试 USER 绕过 / 伪造 USER actor ——
    "bypass_user_actor",
    "use_test_user_as_real",
    "forge_user_actor",
    # —— 红线⑫：禁止真实外发告警（PagerDuty / Slack / 企业微信 / Email / Webhook）——
    "deliver_real_alert",
    "send_real_pagerduty",
    "send_real_slack",
    "send_real_wechat",
    "send_real_email",
    "send_real_webhook",
    "mark_delivery_real",
    # —— 红线⑬：禁止自动执行 Runbook / 修复剧本 ——
    "execute_runbook",
    "auto_run_runbook",
    "run_remediation_playbook",
    "auto_execute_runbook_step",
    # —— 红线⑨补充：禁止由合成结果自动关闭 Incident ——
    "auto_resolve_from_synthetic",
    "promote_synthetic_incident_to_production",
    "auto_close_from_telemetry",
    # —— 红线④/⑤ 防御性叠加：禁止经遥测自动部署 / 回滚 ——
    "auto_deploy_from_telemetry",
    "auto_rollback_from_telemetry",
)

# 遥测层禁名集 = 全链路既有红线（驾驶舱 ∪ 追踪层 ∪ 准备层 ∪ 演练层 ∪ 发布闸门层 ∪
# 可观测层）∪ 本层增量。
_TELEMETRY_FORBIDDEN = _dedupe(
    _TRACEABILITY_FORBIDDEN,
    _PRODUCTION_READINESS_EXTRA_FORBIDDEN,
    _STAGING_VALIDATION_EXTRA_FORBIDDEN,
    _PRODUCTION_RELEASE_EXTRA_FORBIDDEN,
    _PRODUCTION_OBSERVABILITY_EXTRA_FORBIDDEN,
    _TELEMETRY_EXTRA_FORBIDDEN,
)

# 供测试 / 文档引用。
TELEMETRY_FORBIDDEN_COUNT = len(_TELEMETRY_FORBIDDEN)

__all__ = [
    "_TELEMETRY_EXTRA_FORBIDDEN",
    "_TELEMETRY_FORBIDDEN",
    "TELEMETRY_FORBIDDEN_COUNT",
]
