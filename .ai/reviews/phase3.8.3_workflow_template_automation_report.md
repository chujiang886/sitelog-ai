# BOIP Phase 3.8.3 —— Enterprise Workflow Template & Automation Layer（企业流程模板与自动化层）收口报告

- **范围**：Phase 3.8.3（企业流程模板与自动化层）
- **身份**：BOIP AI Chief Architect
- **日期**：2026-08-04
- **状态**：`ENTERPRISE_WORKFLOW_TEMPLATE_AUTOMATION_BUILT_NO_GO`
- **前置**：Phase 3.7 ✅ Engineering Intelligence Complete；Phase 3.8.0 ✅ Enterprise Operation Layer；Phase 3.8.1 ✅ Enterprise Access & Permission Intelligence；Phase 3.8.2 ✅ Enterprise Collaboration & Task Workflow Layer

---

## 0. 红线总闸（6 条，fail-closed，全部保持）

| # | 红线 | 本层落地 |
|---|------|----------|
| ① | 禁止开启 `engineering_enabled` | 全部 5 个新服务构造/写路径首行断言 `safety_invariants_ok()`；启用态（伪造 `True`）构造即抛 `EnterpriseRedLineViolationError` |
| ② | 禁止输出 `engineering_approved` | 新服务不含 `approve` / `engineering_approved`；`WorkflowTriggerService` 经 `_RedLineForbiddenMixin` 结构性拦截 |
| ③ | 禁止自动报价 | 新服务不含 `quote` / `pricing` |
| ④ | 禁止自动审批 | 新服务不含 `approve` / `sign` / `authorize`（`mixin` 拦截）；**触发规则 fire 只登记 pending 流程，不触发审批** |
| ⑤ | 禁止绕过 `UnifiedActivationGate` | 以 `safety_invariants_ok()` 作为统一前置护栏（只读 `load_engineering_enabled()`） |
| ⑥ | 禁止 AI 代替人工决策 | `AuditService` 仍禁止 `record_human_approval`；触发事件 `status` 恒为 `pending`；SLA `status` 为纯时间推导无审批语义；指标 `completion_rate` 为如实聚合，无审批结论 |

**结果**：全 agents 套件 **917 → 964 passed（+47）零回归**；未修改 `verified.json` / `config.yaml` / `engineering_enabled`；`engineering_enabled=false`（config.yaml:102）；未输出 `engineering_approved`。

---

## 1. 任务1：工作流模板模型（`agents/enterprise/workflow_template.py`，NEW）

- 新增 `WorkflowTemplateType`（DOOR_WINDOW_DESIGN / AFTER_SALES / PROJECT——门窗设计流程 / 售后流程 / 项目流程三类）。
- 新增 `WorkflowTemplateStatus`（DRAFT / ACTIVE / ARCHIVED）。
- 新增 `WorkflowTemplate` dataclass，字段严格对应指令：`template_id` / `name` / `type` / `stages` / `version` / `status` / `created_by`，并强制 `org_id`（组织隔离）。`stages` 仅描述流程阶段定义（如 `["需求确认","方案设计","人工审核","交付"]），不携带任何审批结论或工程参数。
- 新增 `WorkflowTemplateService(org_id, audit=None)`：`create_template` / `update_status` / `get` / `list_templates`（可按 type / status 过滤）。
  - 构造与写路径首行 `safety_invariants_ok()` 断言（红线①/⑤）。
  - 跨域访问（org 不一致）抛 `EnterpriseIsolationError`（组织隔离，fail-closed）。
  - 可选联动 `AuditService.record_workflow_event`（actor 真实；creator 为真实发起方）。
  - 本服务**不**持有 `approve` / `engineering_approved` / `quote` / `pricing` / `sign` / `authorize`（红线②/③/④）。

## 2. 任务2：流程版本管理（`agents/enterprise/workflow_version.py`，NEW）

- 新增 `WorkflowVersionEffectiveStatus`（DRAFT / EFFECTIVE / SUPERSEDED / RETIRED）。
- 新增 `WorkflowVersion` dataclass：关联 `template_id`；记录 `version` / `change_log` / `effective_status`（仅元数据，不携带审批结论）。
- 新增 `WorkflowVersionService(org_id, audit=None)`：`create_version` / `set_effective_status` / `get` / `list_versions`（可按 template 过滤）。
  - 写路径断言红线①/⑤；跨域抛 `EnterpriseIsolationError`。
  - 可选联动 `AuditService.record_workflow_event`（actor 真实）。
  - 版本生效状态由真实人工在外部决定（红线⑥）；本服务不持有任何审批/批准方法。

## 3. 任务3：自动触发规则（`agents/enterprise/workflow_trigger.py`，NEW，红线③ 重点）

- 新增 `WorkflowTriggerEventType`（PROJECT_CREATED / FILE_UPLOADED / TASK_COMPLETED 三类事件）。
- 新增 `WorkflowTriggerRule` dataclass：仅描述「当某事件发生时启动某模板流程」（rule_id / org_id / template_id / event_type / enabled / created_by），**不**包含任何审批动作。
- 新增 `WorkflowTriggerEvent` dataclass：`status` 恒为 `"pending"`（待真实人工执行，系统**不**自动推进到 approved）。
- 新增 `WorkflowTriggerService(org_id, audit=None)`（继承 `_RedLineForbiddenMixin`）：
  - `register_rule`：登记 event → template 启动关系（不含审批）。
  - `evaluate(event_type, context)`：**只读匹配**，返回当前组织下启用且命中事件的规则列表，不执行任何写动作。
  - `fire(event_type, event_id, context)`：**只触发流程，不触发审批**——对每条命中规则登记一条 `WorkflowTriggerEvent`（status=pending），并如实写入审计（`record_workflow_event`，`actor_kind=SYSTEM` 标注为自动化触发，**绝不**标注为 human approval）。
  - **红线③ 结构性加固**：`_FORBIDDEN` 在红线②/④/⑥基础上**额外**拦截 `auto_approve` / `auto_sign_off` / `confirm` / `trigger_approval` / `request_approval`，从结构上杜绝「自动触发审批」能力。系统**不提供**任何 approve / confirm 入口。
  - 写路径断言红线①/⑤；跨域抛 `EnterpriseIsolationError`。

## 4. 任务4：SLA 管理（`agents/enterprise/workflow_sla.py`，NEW）

- 新增 `WorkflowSLAStatus`（ON_TRACK / WARNING / OVERDUE）。
- 新增 `WorkflowSLA` dataclass：记录 `deadline` / `warning` / `status`（org_id 隔离；可关联 template_id / workflow_id）。
- 新增纯函数 `compute_sla_status(deadline, warning, now)`：依据当前时间推导状态（OVERDUE > deadline / WARNING > warning / ON_TRACK 其余；warning 为 deadline 之前的预警，仅当 deadline 存在时生效）。**纯函数无副作用、无审批语义**，status **不**因任何自动逻辑变为 approved。
- 新增 `WorkflowSLAService(org_id, audit=None)`：`create_sla` / `refresh_status` / `get` / `list_slas`（可按 workflow / status 过滤）。
  - 写路径断言红线①/⑤；跨域抛 `EnterpriseIsolationError`。
  - 可选联动 `AuditService.record_workflow_event`（actor 真实）。
  - 本服务**不**持有任何审批/批准方法（红线②/③/④）。

## 5. 任务5：流程统计（`agents/enterprise/workflow_metrics.py`，NEW）

- 新增 `WorkflowMetrics` dataclass：记录 `duration`（总耗时）/ `stage_time`（各阶段耗时映射）/ `completion_rate`（0~1）/ `sample_size`（参与统计实例数）；仅为如实汇总，不携带审批结论或工程参数。
- 新增 `WorkflowMetricsService(org_id, audit=None)`：`record_metrics` / `aggregate` / `get` / `list_metrics`（可按 template 过滤）。
  - `record_metrics`：`completion_rate` 钳制在 `[0,1]`（数据规整，非审批）。
  - `aggregate`：对一组指标做均值聚合（duration / completion_rate 均值，stage_time 求和），返回汇总的 `WorkflowMetrics`（仅统计值，不含审批语义）。
  - 写路径断言红线①/⑤；跨域抛 `EnterpriseIsolationError`。
  - 可选联动 `AuditService.record_workflow_event`（actor 真实）。
  - 本服务**不**持有任何审批/批准/报价方法（红线②/③/④/⑥）。

## 6. 任务6：测试（六类，47 用例，全绿）

- 新增测试（tests/agents）：
  - `test_enterprise_workflow_template.py`（9 用例）：三类模板类型创建、字段严格对应、状态流转仅登记、跨域隔离、审计联动、构造 fail-closed、无 forbidden 方法。
  - `test_enterprise_workflow_version.py`（6 用例）：版本登记、生效状态流转仅登记、按 template 过滤、跨域隔离、审计联动、构造 fail-closed。
  - `test_enterprise_workflow_trigger.py`（7 用例）：三类事件注册/匹配、fire 仅登记 pending 不审批、审计如实标记 SYSTEM 非 human approval、disabled 规则不触发、forbidden 审批方法全部拦截（红线③）、跨域隔离、构造 fail-closed。
  - `test_enterprise_workflow_sla.py`（7 用例）：SLA 登记、纯函数 on_track/warning/overdue、refresh 仅登记、过滤、跨域隔离、审计联动、构造 fail-closed。
  - `test_enterprise_workflow_metrics.py`（8 用例）：指标登记、completion_rate 钳制、聚合均值与 stage 求和、空聚合、过滤、跨域隔离、审计联动、构造 fail-closed。
  - `test_enterprise_template_red_line.py`（10 用例，含 parametrize×6）：safety_invariants_ok 为真、5 个新服务 + 聚合门面启用态构造全 fail-closed（红线①/⑤）、触发服务启用态下不可能触发（红线③）、聚合层暴露 5 个子服务、is_activation_safe 只读为真。
- **全 agents 套件 964 passed（917 基线 + 47）零回归**；未修改 `verified.json` / `config.yaml` / `engineering_enabled`。

## 7. 聚合装配与导出

- `agents/enterprise/service.py`：`EnterpriseOperationLayer.__init__` 新增装配 5 个子服务，共享同一 `audit` 实例：
  - `self.workflow_templates = WorkflowTemplateService(...)`
  - `self.workflow_versions = WorkflowVersionService(...)`
  - `self.workflow_triggers = WorkflowTriggerService(...)`
  - `self.workflow_slas = WorkflowSLAService(...)`
  - `self.workflow_metrics = WorkflowMetricsService(...)`
- `agents/enterprise/__init__.py`：导出 5 个服务的全部符号（类型/枚举/服务类）至包顶层。

## 8. 交付物清单（3.8.3）

| 类型 | 路径 |
|---|---|
| 工作流模板 | `agents/enterprise/workflow_template.py` |
| 流程版本 | `agents/enterprise/workflow_version.py` |
| 自动触发规则 | `agents/enterprise/workflow_trigger.py` |
| SLA 管理 | `agents/enterprise/workflow_sla.py` |
| 流程统计 | `agents/enterprise/workflow_metrics.py` |
| 聚合/导出 | `agents/enterprise/service.py`、`agents/enterprise/__init__.py` |
| 测试×6 | `tests/agents/test_enterprise_{workflow_template,workflow_version,workflow_trigger,workflow_sla,workflow_metrics,template_red_line}.py` |
| 收口报告 | `.ai/reviews/phase3.8.3_workflow_template_automation_report.md` |
| 状态刷新 | `.ai/project_status.json`（`phase_3_8_3` 块 + 顶层 `phase_3_8_3_status=ENTERPRISE_WORKFLOW_TEMPLATE_AUTOMATION_BUILT_NO_GO`） |
| 路线刷新 | `.ai/roadmap_v8.md`（新增第 6 节：阶段 3.8.3） |

---

## 9. 结语

Phase 3.8.3 在 3.8.2 协作与任务工作流层之上，补齐了企业流程的「模板化、版本化、自动化触发、SLA、统计」五大能力。所有新增服务严格复用 3.8.0 自包含 fail-closed 红线基座，构造/写路径零例外断言 `safety_invariants_ok()`；**自动触发规则重点守红线③**——`fire` 仅登记 pending 流程事件并如实写审计，**绝不**代人工审批/确认/签署，且结构上拦截 `approve`/`auto_approve`/`confirm`/`trigger_approval`/`request_approval`。

本轮**未开启 `engineering_enabled`、未输出 `engineering_approved`、未修改 `verified.json`**，全 agents 套件 **964 passed 零回归**，待主理人线下验收后由真实人工显式解锁后续阶段。
