# BOIP 企业生产可观测性、SRE 与事故响应准备层 —— 治理指南

> 对应阶段：**Phase 3.9.3**（`agents/enterprise/production_observability/`）
> 收口状态：**BUILT_NO_GO**（已建成、已验证，未真接入生产、未发送真实告警、未进入自动修复）
> 配套文档：`.ai/reviews/phase3.9.3_production_observability_incident_readiness_report.md`、`.ai/roadmap_v8.md` §35.2、`docs/PRODUCTION_DEPLOYMENT_GUIDE.md` §14

---

## 1. 总览与定位

本层为「生产发布闸门体系」之后的**可观测性 / SRE / 事故响应准备层**。它回答一个问题：**当真实生产上线后，BOIP 是否具备「看得清、报得准、应得对、复盘得出」的工程准备能力**。

本阶段只验证「准备体系是否可靠」，**不真接入数据源、不真发送告警、不自动修复、不自动回滚、不自动关单**。所有健康 / 指标 / SLI 均显式标记为 `simulation_only=true` 或状态 `UNKNOWN`，绝不描述成真实 production observation（红线⑪）。

---

## 2. 架构与组件关系

```
ProductionObservabilityService            （_RedLineForbiddenMixin，构造断言 safety_invariants_ok）
 ├─ ServiceHealthService      （T2 服务健康，overall_status 聚合）
 ├─ MetricsService            （T3 指标聚合，simulation_only）
 ├─ SLOService                （T4 SLI/SLO + T5 错误预算）
 ├─ AlertService              （T6 告警候选 + T7 去重关联，_RedLineForbiddenMixin）
 ├─ IncidentService           （T8–T16 事故全生命周期，_RedLineForbiddenMixin）
 └─ CorrelationEngine          （T7 告警关联 / T19 发布关联 / T20 安全关联）
        │
        ├─ backend/app/api/governance_observability.py   （只读 + 人工 ACK/RESOLVE/CLOSE）
        ├─ frontend/src/app/governance-observability/     （只读看板 + 人工动作）
        └─ agents/enterprise/audit.py                      （+7 OBSERVABILITY_* 审计枚举）
```

`ProductionObservabilityService` 由 `agents/enterprise/service.py` 在 `agent_production_release` 之后装配为 `self.agent_production_observability`，统一 `org_id` + `audit` + `identity` 注入。

---

## 3. 领域模型

| 概念 | 类型 / 枚举 | 关键不变量 |
|------|------------|-----------|
| 服务健康状态 | `ServiceHealthStatus`：`HEALTHY/DEGRADED/UNHEALTHY/UNKNOWN` | `is_operational` 中 `UNKNOWN` **不**当 `HEALTHY` |
| 可观测组件 | `ObservableComponent`（11 类）：backend/frontend/database/identity/governance_workflow/audit/release_gate/voice_runtime/llm_provider/asr/tts | 覆盖 BOIP 全栈 |
| 指标类别 | `MetricCategory`：AVAILABILITY/LATENCY/IDENTITY/GOVERNANCE/AI_RUNTIME/RELEASE | `MetricSnapshot.simulation_only=True` |
| SLI / SLO | `SLIDefinition` / `SLOKind` / `SLODefinition` / `SLOStatus`：`MET/AT_RISK/BREACHED/PENDING_VERIFICATION` | 阈值未验证 → `PENDING_VERIFICATION` |
| 错误预算 | `ErrorBudget`（`remaining` / `warning`） | 只计算，不触停发布/回滚 |
| 告警 | `AlertCandidate` / `AlertStatus`：`DETECTED/ACKNOWLEDGEMENT_REQUIRED/ACKNOWLEDGED_BY_HUMAN/RESOLVED_BY_HUMAN` | 无 `AUTO_*` 态 |
| 事故 | `IncidentCandidate` / `ProductionIncident` / `IncidentStatus`（8 态） | 无 `AUTO_*` 态 |
| 事故严重度 | `IncidentSeverity`：`SEV0/SEV1/SEV2/SEV3` | class 级显式枚举 |
| 事故时间线 | `IncidentTimelineEvent` | 构造校验 `actor_kind == "user"`，append-only |
| 事故指挥 | `IncidentCommanderAssignment` | `actor_kind == "user"` |
| Runbook | `IncidentRunbookReference` | 只引用，不执行 |
| 响应草稿 | `IncidentResponseDraft` | `requires_human_review=True` |
| 恢复校验 | `IncidentRecoveryValidation` | `actor_kind == "user"` |
| Postmortem | `IncidentPostmortemDraft` | `root_cause_status == IDENTIFIED` 时 `root_cause` 不得空 |
| 整改关联 | `IncidentFollowUpCandidate` | 挂治理整改单 |
| 安全信号 | `SecurityAlertCandidate` | 关联不自动关 Incident |

---

## 4. 服务健康（Service Health）

`ServiceHealthService.overall_status` 聚合语义（**fail-closed 核心**）：

- 任一组件 `UNHEALTHY` → 整体 `UNHEALTHY`
- 否则任一 `DEGRADED` → 整体 `DEGRADED`
- 否则任一 `UNKNOWN` → 整体 `UNKNOWN`（**绝不回退为 HEALTHY**）
- 全部 `HEALTHY` → 整体 `HEALTHY`

设计原则：**探测缺失 = 不健康（宁错杀）**。准备层合成 11 组件默认全 `UNKNOWN`，因此聚合结果必然为 `UNKNOWN`，明确表达「尚未真接入、不可断言健康」。

---

## 5. 指标与 SLI/SLO

- `MetricsService.aggregate_availability` / `aggregate_latency`（分位算法）/ `by_component`：全部基于 `simulation_only` 快照。
- `SLOService.define_sli` / `define_slo`：阈值若未经真实验证（如真实 SLO 目标、真实窗口），`SLOStatus` 落 `PENDING_VERIFICATION`，不自动放行、不自动标 `MET`。
- `summarize` 输出供看板只读展示。

---

## 6. 错误预算（Error Budget）

`ErrorBudget.remaining` / `warning` 仅为**计算值**：展示「若按当前 SLI 消耗，预算还剩多少」。本层**不**基于错误预算触发任何停发布 / 回滚 / 关单动作——这些动作的决策权只属于人类终端的生产负责人（红线④⑤）。

---

## 7. 告警与去重关联（Alerts & Correlation）

- `AlertService`（`_RedLineForbiddenMixin`）：`create_alert` / `correlate` / `acknowledge`（仅 USER）/ `resolve`（仅 USER）/ `get` / `all`。
- `CorrelationEngine.should_merge`：仅当**同组织 + 同组件 + 同指纹 + 同时间窗**才合并；`correlate` 按指纹分组，`merged = len(group) > 1`。
- `ObservabilityCorrelation` 记录关联依据，供事故种子去重（`distinct_incident_seeds`）。
- 去重只影响「是否归并到同一事故候选」，绝不静默丢弃（`silence_alert` 为禁名）。

---

## 8. 事故生命周期（Incident Lifecycle）

- **创建**：`create_incident` / `from_candidate`，初始态 `DETECTED`。
- **时间线**：`append_timeline`——校验 `actor_kind == "user"`，append-only，返回不可变拷贝。
- **ACK**：`acknowledge`（仅 USER），进入 `ACKNOWLEDGED_BY_HUMAN`。
- **指挥**：`assign_commander`（仅 USER）——AI 自派指挥（`assign_self_as_commander` / `act_as_incident_commander`）为禁名。
- **Runbook**：`reference_runbook`——只引用 Runbook 文本，绝不自动执行步骤。
- **响应草稿**：`build_response_draft`——`requires_human_review=True`，AI 不替指挥决策。
- **恢复校验**：`record_recovery_validation`（仅 USER）——通过后仅置 `RECOVERY_VALIDATION`，**不**自动置 `RESOLVED`。
- **解决 / 关闭**：`resolve` / `close`（仅 USER）——AI 主体一律抛 `EnterpriseRedLineViolationError`。
- **Postmortem**：`create_postmortem`（仅 USER）——`root_cause_status == IDENTIFIED` 时 `root_cause` 必填。
- **整改关联**：`create_follow_up_candidate`——挂治理整改单，形成闭环。

---

## 9. 发布与安全信号关联（Release & Security Correlation）

- `correlate_release`：只向事故注入 `rollback_reference`（「若需回滚参照此路径」），显式 `auto_rollback=False`；**绝不**自动执行回滚。
- `correlate_security_signals`：关联安全告警指纹，但 `threshold_verified=False`——**绝不**依据关联自动关闭 Incident，关单只能源于人类终端安全负责人 / incident-commander。
- 两条关联路径共同构成「事故 ↔ 发布 / 安全」的溯源准备，但所有执行动作保持人工唯一。

---

## 10. 审计集成（Audit Integration）

`agents/enterprise/audit.py` 新增 **7** 个审计类（总数 88 → 95），所有 `record_*` 方法 `_append(actor_kind=AuditActorKind.USER)`：

`OBSERVABILITY_HEALTH_CHECK` / `ALERT_CANDIDATE_CREATED` / `INCIDENT_CREATED` / `INCIDENT_HUMAN_ACKNOWLEDGED` / `INCIDENT_HUMAN_RESOLVED` / `INCIDENT_HUMAN_CLOSED` / `POSTMORTEM_DRAFT_CREATED`。

权威断言仅保留在 `tests/agents/test_enterprise_knowledge_governance_audit.py`（`len(members) == 95` + `EXPECTED_CATEGORIES` 集合），其余测试一律改用存在性契约，避免重复硬编码破坏全仓唯一性。

---

## 11. API 与前端（只读 + 人工动作）

**后端** `backend/app/api/governance_observability.py`（`prefix=/governance/observability`，依赖 `csrf_protect`）：

- 只读：`GET /health`（合成 11 组件全 `UNKNOWN` + `simulation_only=true`）、`/metrics`、`/slo`、`/incidents`（空列表）、`/incidents/{id}`、`/incidents/{id}/timeline`、`/incidents/{id}/evidence`、`/incidents/{id}/postmortem`（准备层无真实事故 → 404）。
- 人工动作（须 `governance:incident:action` 且 `_require_user_principal` 校验 `actor_kind == "user"`）：`POST /incidents/{id}/acknowledge` / `assign-commander` / `resolve` / `close`，经 `_record_human_action` 落审计，返回 `auto_state_transition: false`。

**前端** `frontend/src/app/governance-observability/page.tsx`（只读看板 + 真实人工 ACK/RESOLVE/CLOSE 按钮，须填 `incident_id` + 理由；**无** Auto Fix / Auto Rollback / Auto Resolve / Auto Close / AI Approve 按钮）。

**权限**：`governance:observability:read`（所有治理角色可读）、`governance:incident:action`（仅 admin，职责分离）；词表由 `backend/app/identity/permissions.py` 与 `frontend/src/lib/identity/{types,guards}.ts` 三处对齐、测试钉死。

---

## 12. 红线与 fail-closed 禁名（337 项）

`forbidden.py` 的 `PRODUCTION_OBSERVABILITY_FORBIDDEN_COUNT = 337`（含治理历史禁集并集 + 本层新增）。结构级由 `_RedLineForbiddenMixin.__getattr__` 拦截，调用即抛 `EnterpriseRedLineViolationError`。

本层新增关键禁名（节选）：`auto_rollback_incident` / `auto_resolve_incident` / `auto_close_incident` / `auto_acknowledge_alert` / `assign_self_as_commander` / `act_as_incident_commander` / `silence_alert` / `fabricate_observability_evidence` / `auto_deploy_on_incident` / `promote_simulation_to_production`。

**十二项最高红线**（绝对不可修改 / 弱化）：①`engineering_enabled=false` ②禁 `engineering_approved` ③禁 AI 自动批准发布 ④禁 AI 自动执行部署 ⑤禁 AI 修改真实企业数据 ⑥禁 AI 写真实生产密钥 ⑦禁 AI 自动授予生产权限 ⑧禁 AI 自动关闭 Incident ⑨禁 AI 代 SRE/production-owner/security-owner/incident-commander 责任签署 ⑩禁 AI 代替人工责任 ⑪禁把模拟监控数据描述成真实 production observation ⑫禁通过删安全断言 / 跳失败测试 / 降权 / 伪造监控证据让观测门禁变绿。

---

## 13. 收口状态与 STOP 纪律

- 状态：**🟢 BUILT_NO_GO（2026-08-12 收口）**。
- 验证：agents 全量 **2329 passed / 0 failed**；backend 346 passed；frontend jest 117 passed；tsc 0 error；治理仓库完整性检查器 9/9；生产安全 / 身份头 / 硬编码扫描通过（防编造扫描 20 处命中均为本阶段之前历史 `.ai/` 文档与 `wind_pressure` 接口测试夹具，无一处位于本阶段交付物）。
- **STOP**：不进入 Phase 3.9.4+；不真接入生产可观测性数据源、不真发送告警、不自动修复/回滚/关单、不自动开启 `engineering_enabled`、不输出 `engineering_approved`。真实接入与故障指挥只能源于主理人 / SRE / incident-commander 在人类终端的线下决策。
