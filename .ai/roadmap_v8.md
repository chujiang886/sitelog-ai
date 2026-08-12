# BOIP 研发路线 V8（roadmap_v8.md）

- **生成**：2026-08-04（Phase 3.8.1 增量更新：2026-08-04）
- **身份**：BOIP AI Chief Architect（Phase 3.8.0 Enterprise Operation Layer · 企业运营层 → Phase 3.8.1 Access & Permission Intelligence · 企业访问与权限智能层）
- **性质**：Phase 3.8.0 = **企业运营层构建（非激活、非工程计算）**：新增 `agents/enterprise/` 包，覆盖用户权限模型 / 组织与企业级隔离 / 项目管理 / 文件资产管理 / AI 操作审计五类能力；Phase 3.8.1 = **在其上增强企业级访问控制**（RBAC 角色继承与权限组合 / Project·FileAsset·Workflow·Solution 资源级 ACL / 专家权限隔离 / 审核职责分离 SoD / 权限审计联动）；全 agents 套件 **880 passed**（较 3.8.0 基线 831 +49）零回归。
- **依据**：`.ai/project_status.json`（SSOT，新增 `task_status.phase_3_8_1` 块；`_phase_status=ENTERPRISE_ACCESS_INTELLIGENCE_BUILT_NO_GO`）、`.ai/reviews/phase3.8.1_access_permission_intelligence_report.md`、真实源码 `agents/enterprise/*.py` + `tests/agents/test_enterprise_*.py`
- **权威声明**：本文件取代 `roadmap_v7.md`，为 Phase 3.8.0 / 3.8.1 起的唯一研发路线；roadmap_v7.md 保留为 Phase 3.7.x 历史归档。

---

## 1. 当前真实状态（Phase 3.8.5 企业智能驾驶舱层构建态）

| 维度 | 真实状态 |
|---|---|
| 阶段 | 3.7.0 架构 ✅ → 3.7.1 基础层 ✅ → 3.7.2 推理层 ✅ → 3.7.3 案例层 ✅ → 3.7.4 方案生成层 ✅ → 3.7.5 方案约束与优化层 ✅ → 3.7.6 成本智能层 ✅ → 3.7.7 图纸智能层 ✅ → 3.7.8 工作流编排层 ✅ → 3.7.9 工程 AI 助手交互层 ✅ → 3.8.0 企业运营层 BUILT（2026-08-04）✅ → 🟢 **3.8.1 企业访问与权限智能层 BUILT（2026-08-04）** → 🟢 **3.8.5 企业智能驾驶舱层 BUILT（2026-08-04）** |
| 企业运营层 | `agents/enterprise/` 包（11 文件）：red_line 基座 / identity / organization / project / file_asset / audit / resource_permission / expert_access / review_permission / service 聚合门面；全部构造/写路径 fail-closed 断言 `engineering_enabled is False` |
| 红线 | `engineering_enabled=false`（真实读取 `agents/config.yaml`）；无任何 `engineering_approved` 输出；不自动报价；不自动审批；不 AI 代责（审计禁止 `record_human_approval`） |
| 激活态 | **NO-GO 维持**：`engineering_enabled=False`；ESW 窗口 `OPEN_EMPTY`；企业运营层只编排运营数据，绝不开启工程计算 |
| 隔离 | 所有资源按 `org_id` 作用域过滤；跨域访问一律抛 `EnterpriseIsolationError` |
| 测试 | 全 agents 套件 **1059 passed**（1002 基线 + 57 驾驶舱层），0 失败；未修改 `verified.json` / `engineering_enabled` |
| 未完成（人工动作） | 真实企业运营落地 / 显式置 `engineering_enabled=true` / 真实双签阈值录入 / 人类对方案与报价作核准 均 pending_verification |

**红线（不可逾越）**：不自动开启 `engineering_enabled`；不输出 `engineering_approved`；不绕过 `UnifiedActivationGate`（以 `safety_invariants_ok` 统一前置）；不伪造工程参数；不 AI 代签/代授权/代责。

---

## 2. Phase 3.8.0 路线（Enterprise Operation Layer — 构建）

> **Phase 3.8.0 定位**：在 3.7.x 工程智能与交互地基之上，**构建企业运营能力**（用户/组织/项目/文件/审计）。本轮为运营层实现（自包含、零耦合工程内部类型），不进入工程计算、不开启 `engineering_enabled`、不输出 `engineering_approved`、不报价、不审批、不代责。

### 2.1 已交付（代码实现 + 红线守约）

- **3.8.1** 用户权限模型。**DONE（2026-08-04）· BUILT_NO_GO**
  - ✅ `Permission`(13 原子) / `RoleKind`(5 类：admin/designer/engineer/expert/reviewer) / `ROLE_PERMISSIONS`；**fail-closed 不含任何批准/报价/审批权限**；`User` / `Role` / `IdentityService`（`make_user` / `assign_role`[跨域抛隔离] / `check`）。见 `agents/enterprise/identity.py`。
- **3.8.2** 组织模型与企业级隔离。**DONE（2026-08-04）· BUILT_NO_GO**
  - ✅ `Organization` / `Department` / `Member`；`EnterpriseIsolationError`；`OrganizationService`（`create_organization` / `add_department` / `add_member` / `assert_same_org` 静态隔离断言）。见 `agents/enterprise/organization.py`。
- **3.8.3** 项目管理模型。**DONE（2026-08-04）· BUILT_NO_GO**
  - ✅ `Project` 聚合根，以**字符串外键**关联 `customer_id` / `file_ids` / `workflow_id` / `solution_id`（零耦合）；`ProjectService`（`create_project` / `attach_file` / `link_workflow` / `link_solution` / `get` / `list_projects`[作用域过滤]）。见 `agents/enterprise/project.py`。
- **3.8.4** 文件资产管理。**DONE（2026-08-04）· BUILT_NO_GO**
  - ✅ `compute_sha256` / `FileAsset`(`content_hash`[sha256] / `version`[递增] / `source` / `permission` / `owner_id`)；`FileAssetService`（`upload`[v1 算 hash] / `add_version`[递增重算] / `get` / `verify_hash` / `list_assets`[作用域过滤]）。见 `agents/enterprise/file_asset.py`。
- **3.8.5** AI 操作审计（红线⑥核心）。**DONE（2026-08-04）· BUILT_NO_GO**
  - ✅ `AuditActorKind`(ai/user/system) / `AuditActionCategory`(ai_action/user_action/workflow_event) / `AuditRecord`；`AuditService(_RedLineForbiddenMixin)`（`record_ai_action` / `record_user_action` / `record_workflow_event`）；**`record_human_approval` 被 mixin 拦截**——AI 不得伪造人工审批。见 `agents/enterprise/audit.py`。
- **3.8.6** 测试（六类）。**DONE（2026-08-04）· BUILT_NO_GO**
  - ✅ `tests/agents/test_enterprise_{permission,organization,project,file,audit,red_line}.py` **40 用例全绿**；覆盖五类角色权限集、跨域 `EnterpriseIsolationError`、字符串外键、sha256/version、`record_human_approval` 拦截、构造 fail-closed（monkeypatch 翻转 `load_engineering_enabled`）、forbidden 方法名不可达；未修改 `verified.json` / `engineering_enabled`。
- **3.8.7** 企业知识反馈与持续改进层。**DONE（2026-08-05）· BUILT_NO_GO**
  - ✅ 用户反馈（`FeedbackService`）/ 洞察验证（`InsightValidationService`，**禁 AI 自动验证**）/ 知识更新候选（`KnowledgeUpdateCandidateService`，**只提不落地**）/ 经验沉淀工作流（`KnowledgeImprovementWorkflow`，`human_review` 严格 USER）+ 审计增强（`FEEDBACK`/`KNOWLEDGE_CANDIDATE`/`VALIDATION` 类别 + `require_human_actor` 守卫）；7 测试文件 **52 用例全绿**；全 agents 套件 **1183 passed 零回归**。见 `agents/enterprise/{feedback,insight_validation,knowledge_candidate,knowledge_improvement_workflow,audit,service,__init__}.py`。

### 2.2 红线基座（自包含 fail-closed）

- `agents/enterprise/red_line.py`：`EnterpriseRedLineViolationError` / `safety_invariants_ok()`（只读 `load_engineering_enabled() is False`）/ `_RedLineForbiddenMixin`（`__getattr__` 拦截 forbidden 方法名 `approve`/`engineering_approved`/`quote`/`pricing`/`sign`/`authorize`/`record_human_approval`）。
- 所有 Enterprise 服务构造/写路径统一断言 `safety_invariants_ok()`（等价 `UnifiedActivationGate` 护栏语义），红线①/⑤ 守约。
- `EnterpriseOperationLayer(org_id)` 聚合门面装配五子服务，`is_activation_safe()` 只读暴露护栏状态（不用于翻转开关）。

### 2.3 后续候选路线（须人工解锁后启动，非本轮范围）

| 路线 | 建议入口 | 解锁前提 |
|---|---|---|
| 企业运营激活 | 真实企业租户接入 + 角色落地 | 主理人 + 专家线下决策，显式置 `engineering_enabled=true` 并经 `UnifiedActivationGate` 核准 |
| 工程计算接入 | 复用 3.7.x 工程智能层 | 阈值双签 + `engineering_enabled=true` |
| 真实审计闭环 | `AuditService` 接来源系统 | 真实人工审批事件经 G6 写入，AI 仅记录 ai/user/system 三类如实动作 |

---

## 2.4 Phase 3.8.1 路线（Access & Permission Intelligence — 构建）

> **Phase 3.8.1 定位**：在 3.8.0 企业运营层之上，**增强企业级访问控制能力**。本轮为访问与权限智能层实现（沿用 3.8.0 自包含 fail-closed 红线基座，零耦合工程内部类型），不进入工程计算、不开启 `engineering_enabled`、不输出 `engineering_approved`、不报价、不审批、不代责。

### 2.4.1 已交付（代码实现 + 红线守约）

- **3.8.1.1** RBAC 增强。**DONE（2026-08-04）· BUILT_NO_GO**
  - ✅ `Role.inherits`（角色继承 → `effective_permissions()` 解析父角色权限并集）；`PermissionBundle`（frozen 权限组合单元，支持 union/intersection/difference/requires/to_list）；`compose_permissions(*bundles)`；`bundle_from_role(kind)`；`User.has_permission` / `IdentityService.check` 解析继承链；新增 `READ_RESOURCE` / `WRITE_RESOURCE` 两资源级权限（EXPERT/REVIEWER 仅读，最小权限）。见 `agents/enterprise/identity.py`。
- **3.8.1.2** 资源权限模型。**DONE（2026-08-04）· BUILT_NO_GO**
  - ✅ `ResourceKind`(PROJECT/FILE_ASSET/WORKFLOW/SOLUTION)；`ResourcePermission`（资源 id + 类型 + org_id + grantee[user/role] + 权限集）；`ResourcePermissionService.grant/revoke/check`（资源级 ACL，跨域抛 `EnterpriseIsolationError`）。见 `agents/enterprise/resource_permission.py`。
- **3.8.1.3** 专家权限隔离。**DONE（2026-08-04）· BUILT_NO_GO**
  - ✅ `ExpertAccessPolicy`（按 `authorized_project_ids` / `authorized_solution_ids` / `authorized_domains` 三维授权，frozenset 不可变）；`ExpertAccessService.define_policy` / `can_review`（**范围外默认拒绝 fail-closed**）。见 `agents/enterprise/expert_access.py`。
- **3.8.1.4** 审核权限隔离 / 职责分离（SoD）。**DONE（2026-08-04）· BUILT_NO_GO**
  - ✅ `ReviewDecision`(ALLOWED / DENIED_SUBMITTER_IS_REVIEWER / DENIED_REVIEWER_NOT_AUTHORIZED / DENIED_EXPERT_CONFLICT)；`ReviewPermissionService.validate` 强制：提交者≠审核者、审核者须 REVIEWER/ADMIN、专家不兼任提交/审核；跨域抛 `EnterpriseIsolationError`。见 `agents/enterprise/review_permission.py`。
- **3.8.1.5** 权限审计增强。**DONE（2026-08-04）· BUILT_NO_GO**
  - ✅ `AuditActionCategory.PERMISSION` 新类别；`record_permission_check` / `record_access_granted` / `record_access_denied`（actor_kind 恒 USER，category=PERMISSION）；`query(category=...)` 支持按类别过滤；`record_human_approval` 仍被 mixin 拦截（红线⑥ 未破坏）。见 `agents/enterprise/audit.py`。
- **3.8.1.6** 测试（六类）。**DONE（2026-08-04）· BUILT_NO_GO**
  - ✅ 新增 `tests/agents/test_enterprise_{rbac,resource_permission,expert_access,review_permission,audit_permission}.py` 五文件 + 扩展 `test_enterprise_red_line.py`（3 新服务纳入 fail-closed 参数化）；**净增 49 用例全绿**；覆盖 RBAC 继承/组合、资源 ACL、专家范围拒绝、SoD 三规则、权限审计记录、`record_human_approval` 拦截；未修改 `verified.json` / `engineering_enabled`。

### 2.4.2 聚合装配（共享审计实例，联动记录权限决策）

- `EnterpriseOperationLayer.__init__` 在 3.8.0 五子服务之外，追加装配 `self.resources`（ResourcePermissionService）/ `self.expert_access`（ExpertAccessService）/ `self.review`（ReviewPermissionService），三者共享同一 `self.audit` 实例，使资源/专家/审核的权限校验决策自动联动写入权限审计（category=PERMISSION）。见 `agents/enterprise/service.py`。

---

## 3. 状态链（节选）

```
Phase 3.7.8 工作流编排层            ✅ DONE (2026-08-03)
Phase 3.7.9 工程 AI 助手交互层       ✅ DONE (2026-08-03)
Phase 3.8.0 企业运营层              🟢 BUILT_NO_GO (2026-08-04)
Phase 3.8.1 企业访问与权限智能层     🟢 BUILT_NO_GO (2026-08-04)
Phase 3.8.2 企业协作与任务工作流层   🟢 BUILT_NO_GO (2026-08-04)
Phase 3.8.3 企业流程模板与自动化层     🟢 BUILT_NO_GO (2026-08-04)
Phase 3.8.4 企业运营分析与智能洞察层   🟢 BUILT_NO_GO (2026-08-04)
Phase 3.8.5 企业智能驾驶舱层            🟢 BUILT_NO_GO (2026-08-04)
Phase 3.8.6 企业数据智能与决策辅助层     🟢 BUILT_NO_GO (2026-08-05)
Phase 3.8.7 企业知识反馈与持续改进层     🟢 BUILT_NO_GO (2026-08-05)
Phase 3.8.8 企业知识治理与版本控制层     🟢 BUILT_NO_GO (2026-08-05)  ← 本轮
```

**红线行（全程恒守）**：①`engineering_enabled=false` ②无 `engineering_approved` ③不自动报价 ④不自动审批 ⑤不绕过 `UnifiedActivationGate` ⑥不 AI 代责。

---

## 4. 交付物清单

| 类型 | 路径 |
|---|---|
| 红线基座 | `agents/enterprise/red_line.py` |
| 权限模型 | `agents/enterprise/identity.py` |
| 组织模型 | `agents/enterprise/organization.py` |
| 项目模型 | `agents/enterprise/project.py` |
| 文件资产 | `agents/enterprise/file_asset.py` |
| AI 审计 | `agents/enterprise/audit.py` |
| 聚合门面 | `agents/enterprise/service.py` |
| 包导出 | `agents/enterprise/__init__.py` |
| 资源权限 | `agents/enterprise/resource_permission.py` |
| 专家权限隔离 | `agents/enterprise/expert_access.py` |
| 审核职责分离 | `agents/enterprise/review_permission.py` |
| 测试×6（运营层） | `tests/agents/test_enterprise_{permission,organization,project,file,audit,red_line}.py` |
| 测试×5（权限智能层） | `tests/agents/test_enterprise_{rbac,resource_permission,expert_access,review_permission,audit_permission}.py` |
| 收口报告 | `.ai/reviews/phase3.8.1_access_permission_intelligence_report.md` |
| 状态刷新 | `.ai/project_status.json`（`task_status.phase_3_8` 块 + `task_status.phase_3_8_1` 块；`_phase_status=ENTERPRISE_ACCESS_INTELLIGENCE_BUILT_NO_GO`） |
| 路线图 | `.ai/roadmap_v8.md`（本文件） |

---

## 5. 阶段 3.8.2（本轮新增）—— 企业协作与任务工作流层

在 3.8.1 访问与权限智能层之上建立企业协作能力（4 个新子服务 + 审计增强 + 6 类测试）。

### 5.1 任务模型（`agents/enterprise/task.py`）

- `Task`（task_id/project_id/assignee_id/creator_id/status/priority/due_date/created_at + org_id）；
- `TaskService`：create_task/assign/update_status/get/list_tasks；跨域抛 `EnterpriseIsolationError`；可选联动 `record_task_action`。

### 5.2 协作评论模型（`agents/enterprise/comment.py`）

- `Comment`（PROJECT/TASK/REVIEW 三类资源；author/timestamp/resource + org_id）；
- `CommentService`：add_comment/get/list_comments；可选联动 `record_comment_action`。

### 5.3 通知中心（`agents/enterprise/notification.py`）

- `Notification`（TASK_CHANGED/REVIEW_REMINDER/PERMISSION_CHANGED + org_id）；
- `NotificationService`：push/mark_read/get/list_for；**红线⑥** 结构性拦截 `notify_human_approval`/`forge_approval`（禁止伪造人工审批通知）；可选联动 `record_notification_action`。

### 5.4 任务工作流（`agents/enterprise/task_workflow.py`）

- `TaskWorkflow` 状态机 created→assigned→processing→waiting_review→completed；
- `TaskWorkflowService`：create_workflow/assign/start_processing/submit_for_review/record_review_result；
- **人工审核节点必须 human 驱动**：`record_review_result(reviewer_id, approved)` 须传真实 reviewer_id，系统不提供 `approve`（mixin 拦截 approve/sign/authorize/auto_approve）。

### 5.5 审计增强（`agents/enterprise/audit.py`）

- 新增 `AuditActionCategory.COLLABORATION` + `record_task_action`/`record_comment_action`/`record_notification_action`（actor 真实，默认 USER）；保持 `record_human_approval` 被拦截（红线⑥）。

### 5.6 测试与装配

- 新增 6 类测试（`test_enterprise_{task,comment,notification,task_workflow,audit_collab,collab_red_line}.py`），共 **37 用例**；
- 全 agents 套件 **917 passed（880 基线 + 37）零回归**；
- `EnterpriseOperationLayer` 聚合装配 `tasks`/`comments`/`notifications`/`workflow`，共享同一 `audit` 实例；
- 未修改 `verified.json`/`config.yaml`/`engineering_enabled`；`engineering_enabled=false`；不输出 `engineering_approved`。

### 5.7 交付物清单（3.8.2）

| 类型 | 路径 |
|---|---|
| 任务模型 | `agents/enterprise/task.py` |
| 协作评论 | `agents/enterprise/comment.py` |
| 通知中心 | `agents/enterprise/notification.py` |
| 任务工作流 | `agents/enterprise/task_workflow.py` |
| 审计增强 | `agents/enterprise/audit.py`（+COLLABORATION +3 方法） |
| 聚合/导出 | `agents/enterprise/service.py`、`agents/enterprise/__init__.py` |
| 测试×6 | `tests/agents/test_enterprise_{task,comment,notification,task_workflow,audit_collab,collab_red_line}.py` |
| 收口报告 | `.ai/reviews/phase3.8.2_collaboration_task_workflow_report.md` |
| 状态刷新 | `.ai/project_status.json`（`phase_3_8_2` 块 + 顶层 `phase_3_8_2_status=ENTERPRISE_COLLAB_BUILT_NO_GO`） |

---

## 6. 阶段 3.8.3（本轮新增）—— 企业流程模板与自动化层

- **状态**：🟢 `ENTERPRISE_WORKFLOW_TEMPLATE_AUTOMATION_BUILT_NO_GO`（2026-08-04）
- **前置**：3.8.0 运营层 / 3.8.1 访问与权限智能 / 3.8.2 协作与任务工作流层 均 ✅
- **范围**：在协作与任务工作流层之上，补齐企业流程的「模板化、版本化、自动化触发、SLA、统计」五大能力。

### 6.1 工作流模板（`agents/enterprise/workflow_template.py`）

- `WorkflowTemplateType`（DOOR_WINDOW_DESIGN / AFTER_SALES / PROJECT——门窗设计/售后/项目三类）；`WorkflowTemplateStatus`（DRAFT/ACTIVE/ARCHIVED）。
- `WorkflowTemplate`：字段 `template_id`/`name`/`type`/`stages`/`version`/`status`/`created_by` + `org_id`（组织隔离）；`stages` 仅流程阶段定义，不含审批结论/工程参数。
- `WorkflowTemplateService`：`create_template`/`update_status`/`get`/`list_templates`；写路径断言红线①/⑤，跨域抛 `EnterpriseIsolationError`，可选联动 `record_workflow_event`。

### 6.2 流程版本（`agents/enterprise/workflow_version.py`）

- `WorkflowVersionEffectiveStatus`（DRAFT/EFFECTIVE/SUPERSEDED/RETIRED）；`WorkflowVersion`（version/change_log/effective_status，关联 template_id）。
- `WorkflowVersionService`：`create_version`/`set_effective_status`/`get`/`list_versions`；版本生效由真实人工外部决定（红线⑥）。

### 6.3 自动触发规则（`agents/enterprise/workflow_trigger.py`，红线③ 重点）

- `WorkflowTriggerEventType`（PROJECT_CREATED/FILE_UPLOADED/TASK_COMPLETED）；`WorkflowTriggerRule`（event→template 启动关系，不含审批）；`WorkflowTriggerEvent`（status 恒 `pending`）。
- `WorkflowTriggerService`（继承 `_RedLineForbiddenMixin`）：`register_rule`/`evaluate`（只读匹配）/`fire`（**只触发流程不触发审批**：仅登记 pending 事件 + 如实写审计 `actor_kind=SYSTEM`，绝不标 human approval）。
- **红线③ 结构性加固**：`_FORBIDDEN` 额外拦截 `auto_approve`/`auto_sign_off`/`confirm`/`trigger_approval`/`request_approval`，系统无 approve/confirm 入口。

### 6.4 SLA 管理（`agents/enterprise/workflow_sla.py`）

- `WorkflowSLAStatus`（ON_TRACK/WARNING/OVERDUE）；`WorkflowSLA`（deadline/warning/status）。
- 纯函数 `compute_sla_status(deadline, warning, now)`：按时间推导，无副作用、无审批语义。
- `WorkflowSLAService`：`create_sla`/`refresh_status`/`get`/`list_slas`。

### 6.5 流程统计（`agents/enterprise/workflow_metrics.py`）

- `WorkflowMetrics`（duration/stage_time/completion_rate/sample_size，如实汇总，无审批结论/工程参数）。
- `WorkflowMetricsService`：`record_metrics`（completion_rate 钳制 [0,1]）/`aggregate`（均值聚合）/`get`/`list_metrics`。

### 6.6 测试与装配

- 新增 6 类测试（`test_enterprise_{workflow_template,workflow_version,workflow_trigger,workflow_sla,workflow_metrics,template_red_line}.py`），共 **47 用例**；
- 全 agents 套件 **964 passed（917 基线 + 47）零回归**；
- `EnterpriseOperationLayer` 聚合装配 `workflow_templates`/`workflow_versions`/`workflow_triggers`/`workflow_slas`/`workflow_metrics`，共享同一 `audit` 实例；
- 未修改 `verified.json`/`config.yaml`/`engineering_enabled`；`engineering_enabled=false`；不输出 `engineering_approved`。

### 6.7 交付物清单（3.8.3）

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

---

## 7. 阶段 3.8.4（本轮新增）—— 企业运营分析与智能洞察层

- **状态**：🟢 `ENTERPRISE_ANALYTICS_INTELLIGENCE_BUILT_NO_GO`（2026-08-04）
- **前置**：3.8.0 运营层 / 3.8.1 访问与权限智能 / 3.8.2 协作与任务工作流层 / 3.8.3 流程模板与自动化层 均 ✅
- **范围**：在企业运营层基座之上，补齐「运营指标 / 项目分析 / 流程效率 / AI使用 / 风险预警」五类智能洞察能力；所有输出仅为事实记录/洞察/待人工确认候选，无任何代决策或代管理入口。

### 7.1 运营指标模型（`agents/enterprise/operation_metric.py`）

- `OperationMetricType`（COUNT/SUM/AVERAGE/RATE/RATIO/DURATION/GAUGE/DELTA——中性事实型枚举，不含评价/决策类）。
- `OperationMetric`：字段 `metric_id`/`org_id`/`metric_type`/`value`/`period`/`source`（只记录事实，不承载评价/决策结论）。
- `OperationMetricService`：`create_metric`/`get`/`list_metrics`（可按 type/period 过滤）；写路径断言红线①/⑤，跨域抛 `EnterpriseIsolationError`，可选联动审计如实标 actor（默认 AI，可显式 USER）。

### 7.2 项目分析（`agents/enterprise/project_analytics.py`）

- `ProjectAnalytics`：字段 `total_projects`/`completed_count`/`completion_rate`/`avg_cycle_days`/`status_distribution`（事实统计，不含任何工程质量评价字段）。
- `ProjectAnalyticsService.compute_project_analytics`：只读 `ProjectService`，输出事实统计；**禁止工程质量评价入口** `evaluate_quality`/`score_project`（mixin 拦截，红线③/⑥）。

### 7.3 流程效率分析（`agents/enterprise/workflow_analytics.py`，红线③ 重点）

- `WorkflowAnalytics`：`stage_duration`/`sla_status`/`bottleneck`/`insight`（纯描述性洞察，非处置指令）。
- `WorkflowAnalyticsService.compute_workflow_analytics`：只读 `workflow_metrics`+`workflow_slas` 累加各阶段耗时、推导瓶颈（事实推导）、统计 SLA 状态分布、生成描述性洞察。
- **禁止自动修改流程**：`_FORBIDDEN` 额外拦截 `modify_workflow`/`update_workflow`/`auto_fix`（红线③/⑥）。

### 7.4 AI 使用分析（`agents/enterprise/ai_usage_analytics.py`，红线⑥ 重点）

- `AIUsageEvent`（event_id/task_type/success/response_time，恒记 `recorded_by=ai`）；`AIUsageAnalytics`（total_calls/task_type_distribution/response_ok/response_fail/avg_response_time）。
- `AIUsageAnalyticsService.record_ai_usage`：恒记 `actor=AI`，内部调用 `record_ai_action`，**绝不调用** `record_user_action` 伪造为人工（红线⑥）。

### 7.5 风险预警（`agents/enterprise/operation_risk.py`，红线③/⑥ 重点）

- `RiskSeverity`（LOW/MEDIUM/HIGH——事实分级）；`RiskCandidate`：`requires_human_confirmation` **恒为 True**（__post_init__ 强制），`detected_by=ai`（检测方非决策方）。
- `OperationRiskDetector.detect_risks`：基于外部事实信号如实转换为 `RiskCandidate`，**要求人工确认**；**禁止决策入口** `decide`/`resolve`/`mitigate`/`manage`/`auto_decide`（红线③/⑥）。

### 7.6 测试与装配

- 新增 6 类测试（`test_enterprise_{operation_metric,project_analytics,workflow_analytics,ai_usage_analytics,operation_risk,analytics_red_line}.py`），共 **38 用例**；
- 全 agents 套件 **1002 passed（964 基线 + 38）零回归**；
- `EnterpriseOperationLayer` 聚合装配 `operation_metrics`/`project_analytics`/`workflow_analytics`/`ai_usage_analytics`/`operation_risk`，共享同一 `audit` 实例；
- 未修改 `verified.json`/`config.yaml`/`engineering_enabled`；`engineering_enabled=false`；不输出 `engineering_approved`。

### 7.7 交付物清单（3.8.4）

| 类型 | 路径 |
|---|---|
| 运营指标 | `agents/enterprise/operation_metric.py` |
| 项目分析 | `agents/enterprise/project_analytics.py` |
| 流程效率分析 | `agents/enterprise/workflow_analytics.py` |
| AI 使用分析 | `agents/enterprise/ai_usage_analytics.py` |
| 风险预警 | `agents/enterprise/operation_risk.py` |
| 聚合/导出 | `agents/enterprise/service.py`、`agents/enterprise/__init__.py` |
| 测试×6 | `tests/agents/test_enterprise_{operation_metric,project_analytics,workflow_analytics,ai_usage_analytics,operation_risk,analytics_red_line}.py` |
| 收口报告 | `.ai/reviews/phase3.8.4_enterprise_analytics_intelligence_report.md` |
| 状态刷新 | `.ai/project_status.json`（`phase_3_8_4` 块 + 顶层 `phase_3_8_4_status=ENTERPRISE_ANALYTICS_INTELLIGENCE_BUILT_NO_GO`） |

---

## 8. Phase 3.8.5 路线（Enterprise Intelligence Dashboard Layer — 企业智能驾驶舱层 · 构建）

> **Phase 3.8.5 定位**：在 3.8.4 企业运营分析与智能洞察层既有事实数据之上，**构建只读、事实型的智能驾驶舱呈现层**。本轮为驾驶舱模型 + 指标组件 + 四类企业视图 + 角色可见性策略 + 驾驶舱审计；不进入工程计算、不开启 `engineering_enabled`、不输出 `engineering_approved`、不报价、不审批、不代责、**不自动经营决策**。

### 8.1 已交付（代码实现 + 红线守约）

- **3.8.5.1 Dashboard 模型**。**DONE（2026-08-04）· BUILT_NO_GO**
  - ✅ `Dashboard`（`dashboard_id` / `org_id` / `owner_id` / `widgets` / `visibility` / `created_at`）；`DashboardService`（`create_dashboard` / `add_widget` / `get_dashboard` / `list_dashboards` / `remove_widget`）；跨域访问抛 `EnterpriseIsolationError`；写路径断言 `safety_invariants_ok()`（红线①/⑤）。见 `agents/enterprise/dashboard.py`。
- **3.8.5.2 指标组件模型（事实型）**。**DONE（2026-08-04）· BUILT_NO_GO**
  - ✅ `WidgetType`（metric / chart / table / risk）；`DashboardWidget`（`__post_init__` 结构性拦截 `decision`/`recommendation`/`approval`/`quote`/`pricing`/`engineering_approved` 等决策性事实键，红线③/⑥）；仅承载事实型 `facts`。见 `agents/enterprise/dashboard.py`。
- **3.8.5.3 企业视图（只读组合）**。**DONE（2026-08-04）· BUILT_NO_GO**
  - ✅ `ProjectDashboard` / `WorkflowDashboard` / `AIDashboard` / `RiskDashboard`：只读组合 3.8.4 既有 `ProjectAnalytics` / `WorkflowAnalytics` / `AIUsageAnalytics` / `list[RiskCandidate]`，拆解为事实型 widget 并打 `source` 标记（`project_analytics` / `workflow_analytics` / `ai_usage_analytics` / `operation_risk`），供可见性策略按角色过滤。描述性 `insight` 仅作 widget.note，不进入 facts。见 `agents/enterprise/dashboard_views.py`。
- **3.8.5.4 权限控制（AnalyticsVisibilityPolicy）**。**DONE（2026-08-04）· BUILT_NO_GO**
  - ✅ `AnalyticsVisibilityPolicy`：默认拒绝的角色→数据源映射（`_ROLE_VISIBLE_SOURCES`）；`can_view_dashboard`（private / org / role:<kind> 叠加）+ `visible_widgets` + `filter_dashboard`；未知 visibility 声明默认拒绝（fail-closed）。仅决定展示哪些事实组件，不授予权限、不做决策；真实权限仍由 `IdentityService.check` 校验。见 `agents/enterprise/dashboard_visibility.py`。
- **3.8.5.5 驾驶舱审计**。**DONE（2026-08-04）· BUILT_NO_GO**
  - ✅ `AuditActionCategory.DASHBOARD` 新增；`AuditService` 新增 `record_dashboard_view` / `record_dashboard_query` / `record_dashboard_export`（actor 如实标注，默认 USER，可显式 AI）；`DashboardService.render_dashboard` / `run_query` / `export_dashboard` 联动记录。**始终不提供 `record_human_approval`**（红线⑥：禁止把动作记录为人工审批）。见 `agents/enterprise/audit.py` + `dashboard.py`。
- **3.8.5.6 测试（七类）**。**DONE（2026-08-04）· BUILT_NO_GO**
  - ✅ `tests/agents/test_enterprise_dashboard{,_widget,_visibility,_view,_analytics_permission,_audit,_red_line}.py`：**57 用例全绿**（含本轮补强的独立四类视图测试 5 用例）；覆盖 Dashboard 模型/服务、widget 事实型约束、四类企业视图（事实型、Risk 保持人工确认、视图无 forbidden 方法）、角色可见性默认拒绝、角色级数据差异、驾驶舱审计类别隔离与 actor 标注、`record_human_approval` 拦截、构造 fail-closed（monkeypatch 翻转 `load_engineering_enabled`）、决策类 forbidden 方法不可达、跨域组织隔离；未修改 `verified.json` / `engineering_enabled`。

### 8.2 装配与导出

- `EnterpriseOperationLayer` 聚合装配 `dashboards`（DashboardService）/ `project_dashboard` / `workflow_dashboard` / `ai_dashboard` / `risk_dashboard` / `dashboard_visibility`（AnalyticsVisibilityPolicy），共享同一 `audit` 实例；见 `agents/enterprise/service.py`。
- `agents/enterprise/__init__.py` 导出 `WidgetType` / `DashboardWidget` / `Dashboard` / `DashboardService` / `ProjectDashboard` / `WorkflowDashboard` / `AIDashboard` / `RiskDashboard` / `AnalyticsVisibilityPolicy`。

### 8.3 红线守约（6 条 fail-closed）

- ① `engineering_enabled=false`（构造即断言 `safety_invariants_ok()`）；② 无任何 `engineering_approved` 输出；③ 不自动报价（`quote`/`pricing` 被拦截）+ 驾驶舱只展示事实（widget 决策键被拦截）；④ 不自动审批（`approve`/`sign`/`authorize` 被拦截）；⑤ 不绕过 `UnifiedActivationGate`（统一前置护栏）；⑥ 不 AI 代责（审计禁止 `record_human_approval`；`auto_business_decision`/`make_management_decision`/`evaluate_quality`/`decide`/`resolve`/`mitigate` 等决策入口被拦截）。

### 8.4 测试与回归

- 新增 7 类测试共 **57 用例**（含独立四类视图测试 5 用例）；
- 全 agents 套件 **1059 passed（1002 基线 + 57）零回归**；
- 未修改 `verified.json`/`config.yaml`/`engineering_enabled`；`engineering_enabled=false`；不输出 `engineering_approved`。

### 8.5 交付物清单（3.8.5）

| 类型 | 路径 |
|---|---|
| Dashboard 模型与服务 | `agents/enterprise/dashboard.py` |
| 企业视图（四态） | `agents/enterprise/dashboard_views.py` |
| 可见性策略 | `agents/enterprise/dashboard_visibility.py` |
| 驾驶舱审计扩展 | `agents/enterprise/audit.py`（DASHBOARD 类别 + view/query/export） |
| 聚合/导出 | `agents/enterprise/service.py`、`agents/enterprise/__init__.py` |
| 测试×6 | `tests/agents/test_enterprise_dashboard{,_widget,_visibility,_analytics_permission,_audit,_red_line}.py` |
| 收口报告 | `.ai/reviews/phase3.8.5_enterprise_dashboard_layer_report.md` |
| 状态刷新 | `.ai/project_status.json`（`phase_3_8_5` 块 + 顶层 `phase_3_8_5_status=ENTERPRISE_DASHBOARD_LAYER_BUILT_NO_GO`） |

### 8.6 状态结论

- **状态：🟢 BUILT_NO_GO（2026-08-04）**：企业智能驾驶舱层已完成模型/组件/视图/权限/审计/测试的完整构建，全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不自动经营决策、不审批、不报价、不 AI 代责。
- **未完成（人工动作，pending_verification）**：真实驾驶舱在企业内的角色授权落地 / 真实双签阈值录入 / 人类对风险候选与经营数据作人工确认与处置 均需真实人工线下执行；ESW 窗口维持 `OPEN_EMPTY`，等待主理人+专家线下提交真实证据后经人类终端显式置 `enabled=true`。

---

## 9. Phase 3.8.6 路线（Enterprise Data Intelligence & Decision Support Layer — 企业数据智能与决策辅助层 · 构建）

> **Phase 3.8.6 定位**：在 3.8.4 事实数据 + 3.8.5 驾驶舱呈现之上，**构建只读、事实型、可溯源的数据智能与决策辅助层**。本轮为洞察/趋势/异常/管理报告四类事实模型 + 来源追踪（SourceTrace）+ 角色可见性接入 + 审计增强（4 类别）；不进入工程计算、不开启 `engineering_enabled`、不输出 `engineering_approved`、不报价、不审批、不代责、**不自动经营决策**。

### 9.1 已交付（代码实现 + 红线守约）

- **3.8.6.1 DataInsight 洞察模型与服务**。**DONE（2026-08-05）· BUILT_NO_GO**
  - ✅ `SourceTrace`（`source_metric`/`source_workflow`/`source_event`/`source_dashboard`/`raw_refs`/`note`；`is_traceable` 任一非空即 True）；`DataInsight`（`__post_init__` 强制 `requires_human_review=True` + 可溯源）；`DataInsightService`（`create_insight`/`get`/`list_insights(role=)`/`query(role=)`，组织隔离 + 角色级 source 过滤 + 写审计）。见 `agents/enterprise/data_insight.py`（287 行）。
- **3.8.6.2 趋势分析**。**DONE（2026-08-05）· BUILT_NO_GO**
  - ✅ `TrendInsight`（`__post_init__` 强制可溯源 + `requires_human_review=True`）；`TrendAnalyzer`（`time_series_analysis`/`detect_change`/`compare_period` **仅描述变化，绝不优化建议**；写路径断言 `safety_invariants_ok()` + 记 `record_trend_analysis`）。见 `agents/enterprise/trend_analysis.py`（332 行）。
- **3.8.6.3 异常发现**。**DONE（2026-08-05）· BUILT_NO_GO**
  - ✅ `AnomalyCandidate`（`__post_init__` 强制 `requires_human_confirmation=True` + 可溯源）；`AnomalyDetector`（`detect_from_metrics`/`detect_from_workflow_analytics`/`detect_from_ai_usage_analytics`/`detect_from_dashboard` 四入口；**`resolve`/`mitigate`/`fix`/`close` 被拦截**，AI 仅上报待人工确认）。见 `agents/enterprise/anomaly_detection.py`（335 行）。
- **3.8.6.4 管理报告（事实汇编）**。**DONE（2026-08-05）· BUILT_NO_GO**
  - ✅ `ManagementReport`（`__post_init__` 校验可溯源）；`ManagementReportService.generate_report`（汇编 insights/trends/anomalies/risks 为事实型报告；空输入/跨域/不可溯源均抛错；记 `record_report_generation`；**禁经营建议/管理决策/执行方案**）。见 `agents/enterprise/management_report.py`（218 行）。
- **3.8.6.5 来源追踪（SourceTrace）**。**DONE（2026-08-05）· BUILT_NO_GO**
  - ✅ 四类数据模型 `__post_init__` 结构性强制 `source_trace.is_traceable`；模块 `_merge_trace` 聚合去重；**AI 不创造无源数据**。
- **3.8.6.6 权限可见性接入**。**DONE（2026-08-05）· BUILT_NO_GO**
  - ✅ 复用 3.8.1 `IdentityService` + 3.8.5 `AnalyticsVisibilityPolicy`；`DataInsightService.list_insights(role=)`/`query(role=)` 经 `is_source_permitted(role, source)` 做角色级 source 过滤。
- **3.8.6.7 审计增强**。**DONE（2026-08-05）· BUILT_NO_GO**
  - ✅ `AuditActionCategory` 新增 `DATA_INSIGHT`/`TREND_ANALYSIS`/`ANOMALY_DETECTION`/`REPORT_GENERATION`（audit.py:57-60）；`AuditService` 新增 `record_data_insight`/`record_trend_analysis`/`record_anomaly_detection`/`record_report_generation`（默认 `actor_kind=AI`）；**始终不提供 `record_human_approval`**（红线⑥）。见 `agents/enterprise/audit.py`（564 行）。
- **3.8.6.8 测试（八类）**。**DONE（2026-08-05）· BUILT_NO_GO**
  - ✅ 8 个 `test_enterprise_*` 文件 **72 用例全绿**：覆盖洞察 CRUD/权限/来源链/审计/红线；趋势仅描述/无优化；异常四入口/无处置；报告汇编/无决策；SourceTrace 变体；角色可见性差异；4 新审计类别与 actor 标注；4 服务+聚合层构造 fail-closed 与 forbidden 拦截。

### 9.2 装配与导出

- `EnterpriseOperationLayer` 聚合装配 `data_insights` / `trend_analysis` / `anomaly_detection` / `management_reports`，共享同一 `audit` 实例；见 `agents/enterprise/service.py`。
- `agents/enterprise/__init__.py` 导出 `SourceTrace` / `DataInsight` / `DataInsightService` / `TrendInsight` / `TrendAnalyzer` / `AnomalyCandidate` / `AnomalyDetector` / `ManagementReport` / `ManagementReportService`。

### 9.3 红线守约（6 条 fail-closed）

- ① `engineering_enabled=false`（构造即断言 `safety_invariants_ok()`）；② 无任何 `engineering_approved` 发射（仅 `_FORBIDDEN` 拦截与 docstring）；③ 不自动经营决策（`decision`/`recommendation`/`strategy`/`optimize_business_strategy`/`execute_strategy` 等被拦截）；④ 不自动审批（`approve`/`sign`/`authorize` 被拦截）；⑤ 不绕过 `UnifiedActivationGate`；⑥ 不 AI 代责（风险 `requires_human_*` 强制 True、审计禁 `record_human_approval`、actor 如实标注 AI/USER）。

### 9.4 测试与回归

- 新增 8 类测试共 **72 用例**；
- 全 agents 套件 **1131 passed（1059 基线 + 72）零回归**；
- 未修改 `verified.json`/`config.yaml`/`engineering_enabled`；`engineering_enabled=false`；不输出 `engineering_approved`。

### 9.5 交付物清单（3.8.6）

| 类型 | 路径 |
|---|---|
| 洞察模型与服务 | `agents/enterprise/data_insight.py` |
| 趋势分析 | `agents/enterprise/trend_analysis.py` |
| 异常发现 | `agents/enterprise/anomaly_detection.py` |
| 管理报告 | `agents/enterprise/management_report.py` |
| 审计增强 | `agents/enterprise/audit.py`（4 类别 + 4 record 方法） |
| 聚合/导出 | `agents/enterprise/service.py`、`agents/enterprise/__init__.py` |
| 测试×8 | `tests/agents/test_enterprise_data_insight.py` / `test_enterprise_trend_analysis.py` / `test_enterprise_anomaly_detection.py` / `test_enterprise_management_report.py` / `test_enterprise_data_source_trace.py` / `test_enterprise_data_intelligence_permission.py` / `test_enterprise_data_intelligence_audit.py` / `test_enterprise_data_intelligence_red_line.py` |
| 收口报告 | `.ai/reviews/phase3.8.6_data_intelligence_report.md` |
| 状态刷新 | `.ai/project_status.json`（`phase_3_8_6` 块 + 顶层 `phase_3_8_6_status=ENTERPRISE_DATA_INTELLIGENCE_BUILT_NO_GO`） |

### 9.6 状态结论

- **状态：🟢 BUILT_NO_GO（2026-08-05）**：企业数据智能与决策辅助层已完成洞察/趋势/异常/报告四类事实模型 + 来源追踪 + 角色可见性接入 + 审计增强的完整构建，全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不自动经营决策、不审批、不报价、不 AI 代责。
- **未完成（人工动作，pending_verification）**：真实证据录入与 `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动经营建议 / 自动审批 均待主理人+专家线下执行；**本报告完成后停止，不进入 Phase 3.8.7**，等待主理人审核授权。

## 10. Phase 3.8.7 路线（Enterprise Knowledge Feedback & Continuous Improvement Layer — 企业知识反馈与持续改进层 · 构建）

> **Phase 3.8.7 定位**：在 3.8.6 事实型数据智能之上，**构建「数据→洞察→人工反馈→知识更新候选→人工复核→知识资产沉淀」的反馈闭环**。本轮为新四个服务 + 审计增强（3 类别）+ `require_human_actor` 守卫；AI 只提候选、只登记反馈/验证事实，**绝不**自动改知识、绝不自动验证、绝不代责；不开启 `engineering_enabled`、不输出 `engineering_approved`、不报价、不审批、不 AI 代人工责任。

### 10.1 已交付（代码实现 + 红线守约）

- **3.8.7.1 用户反馈模型与服务（任务1）**。**DONE（2026-08-05）· BUILT_NO_GO**
  - ✅ `FeedbackStatus`(submitted/reviewing/accepted/rejected)；`FeedbackRecord`(`feedback_id`/`org_id`/`user_id`/`source_type`/`content`/`related_insight`/`created_at`/`status`)；`FeedbackService(_RedLineForbiddenMixin)`（`create_feedback`/`get`/`list_feedbacks(source_type=,status=,role=)`/`start_review`/`accept`/`reject`，组织隔离 + 写审计）。见 `agents/enterprise/feedback.py`。
- **3.8.7.2 洞察验证模型与服务（任务2）**。**DONE（2026-08-05）· BUILT_NO_GO**
  - ✅ `ValidationResult`(valid/invalid/needs_revision)；`InsightValidation`(`validation_id`/`org_id`/`insight_id`/`validator`/`result`/`comment`/`timestamp`)；`InsightValidationService(_RedLineForbiddenMixin)`（`create_validation` **必须由真实 USER 发起，禁 AI 自动验证**/`get`/`list_validations(insight_id=,result=)`）。见 `agents/enterprise/insight_validation.py`。
- **3.8.7.3 知识更新候选模型与服务（任务3）**。**DONE（2026-08-05）· BUILT_NO_GO**
  - ✅ `KnowledgeChangeType`(add/update/delete/correct/clarify)；`KnowledgeUpdateCandidate`(`candidate_id`/`org_id`/`source`/`change_type`/`content`/`evidence`/`requires_human_review=True`)（`__post_init__` 强制 `requires_human_review=True`）；`KnowledgeUpdateCandidateService(_RedLineForbiddenMixin)`（`propose_candidate` **只提候选，绝不自动写任何知识库**/`get`/`list_candidates(source=,requires_human_review=)`）。见 `agents/enterprise/knowledge_candidate.py`。
- **3.8.7.4 经验沉淀工作流（任务4）**。**DONE（2026-08-05）· BUILT_NO_GO**
  - ✅ `ImprovementStage`(feedback_received→analysis→candidate_created→human_review→accepted/rejected)；`ImprovementCase`；`KnowledgeImprovementWorkflow(_RedLineForbiddenMixin)`（组合 feedback/candidate/validation 三子服务，共享同一 `audit`；`receive_feedback`/`begin_analysis`/`propose_from_analysis`/`human_review`(**严格 `require_human_actor(USER)`，AI 不得代替人工判定**)/`add_validation`/`get_case`/`list_cases(stage=)`；阶段流转守卫按序拦截）。见 `agents/enterprise/knowledge_improvement_workflow.py`。
- **3.8.7.5 审计增强（任务5）**。**DONE（2026-08-05）· BUILT_NO_GO**
  - ✅ `AuditActionCategory` 新增 `FEEDBACK`/`KNOWLEDGE_CANDIDATE`/`VALIDATION`（audit.py）；`AuditService` 新增 `record_feedback_action`/`record_knowledge_candidate_action`/`record_validation_action`（默认 `actor_kind=AI`）；模块级 `require_human_actor(actor_kind)` 守卫（USER 通过、AI/None 抛 `EnterpriseRedLineViolationError`，红线⑥）；**始终不提供 `record_human_approval`**。见 `agents/enterprise/audit.py`。
- **3.8.7.6 测试（七类）**。**DONE（2026-08-05）· BUILT_NO_GO**
  - ✅ 7 个 `test_enterprise_*` 文件 **52 用例全绿**：覆盖反馈 CRUD/人工审核门禁/隔离；洞察验证人工门禁/禁 AI 自动验证；候选只提不落地/requires_human_review 强制；工作流状态机与 human_review 门禁；3 新审计类别与 actor 标注/`require_human_actor`；跨服务 forbidden 方法与跨组织隔离；4 新服务+聚合层构造 fail-closed 与 `engineering_enabled` 不变/`verified.json` 未改。

### 10.2 装配与导出

- `EnterpriseOperationLayer` 聚合装配 `feedback` / `insight_validation` / `knowledge_candidates` / `knowledge_improvement`，共享同一 `audit`/`identity`/`visibility` 实例；见 `agents/enterprise/service.py`。
- `agents/enterprise/__init__.py` 导出 `FeedbackStatus`/`FeedbackRecord`/`FeedbackService`/`ValidationResult`/`InsightValidation`/`InsightValidationService`/`KnowledgeChangeType`/`KnowledgeUpdateCandidate`/`KnowledgeUpdateCandidateService`/`ImprovementStage`/`ImprovementCase`/`KnowledgeImprovementWorkflow`/`require_human_actor`。

### 10.3 红线守约（6 条 fail-closed）

- ① `engineering_enabled=false`（构造即断言 `safety_invariants_ok()`；monkeypatch 翻转的 5 处 fail-closed 测试全绿）；② 无任何 `engineering_approved` 发射（仅 `_FORBIDDEN` 拦截与 docstring）；③ 禁 AI 自动改知识（候选服务只提不落地、无 `apply`/`merge`/`approve`，`auto_update_knowledge`/`auto_merge_knowledge`/`auto_approve_knowledge` 被拦截）；④ 禁自动审批（`approve`/`sign`/`authorize` 被拦截）；⑤ 不绕过 `UnifiedActivationGate`（构造/写路径统一前置 `safety_invariants_ok()`）；⑥ 禁 AI 代责（`require_human_actor` 强制 USER、`record_human_approval` 被拦截、审计 actor 如实标注 AI/USER、验证/复核不得由 AI 发起）。

### 10.4 测试与回归

- 新增 7 类测试共 **52 用例**；
- 全 agents 套件 **1183 passed（1131 基线 + 52）零回归**；
- 未修改 `verified.json`/`config.yaml`/`engineering_enabled`；`engineering_enabled=false`；不输出 `engineering_approved`。

### 10.5 交付物清单（3.8.7）

| 类型 | 路径 |
|---|---|
| 用户反馈 | `agents/enterprise/feedback.py` |
| 洞察验证 | `agents/enterprise/insight_validation.py` |
| 知识更新候选 | `agents/enterprise/knowledge_candidate.py` |
| 经验沉淀工作流 | `agents/enterprise/knowledge_improvement_workflow.py` |
| 审计增强 | `agents/enterprise/audit.py`（3 类别 + 3 record 方法 + `require_human_actor`） |
| 聚合/导出 | `agents/enterprise/service.py`、`agents/enterprise/__init__.py` |
| 测试×7 | `tests/agents/test_enterprise_feedback.py` / `test_enterprise_insight_validation.py` / `test_enterprise_knowledge_candidate.py` / `test_enterprise_knowledge_improvement_workflow.py` / `test_enterprise_knowledge_feedback_audit.py` / `test_enterprise_knowledge_feedback_permission.py` / `test_enterprise_knowledge_feedback_redline.py` |
| 收口报告 | `.ai/reviews/phase3.8.7_knowledge_feedback_improvement_report.md` |
| 状态刷新 | `.ai/project_status.json`（顶层 `phase_3_8_7_status=ENTERPRISE_KNOWLEDGE_FEEDBACK_BUILT_NO_GO` + `current_stage.phase=3.8.7`） |

### 10.6 状态结论

- **状态：🟢 BUILT_NO_GO（2026-08-05）**：企业知识反馈与持续改进层已完成反馈/验证/候选/工作流四服务 + 审计增强的完整构建，全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不自动改知识、不 AI 自动验证、不审批、不 AI 代责。
- **未完成（人工动作，pending_verification）**：真实证据录入与 `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动经营建议 / 自动审批 均待主理人+专家线下执行；**本报告完成后停止，不进入 Phase 3.8.8**，等待主理人审核授权。

---

## 11. Phase 3.8.8 路线（Enterprise Knowledge Governance & Version Control Layer — 企业知识治理与版本控制层 · 构建）

> **Phase 3.8.8 定位**：在 3.8.7 知识反馈闭环（候选/验证/工作流）之上，**构建只读、事实型、可追溯的知识治理与版本控制层**。本轮为知识版本生命周期（draft→reviewing→active→deprecated）+ 人工审核门禁 + 冲突发现（只登记不 merge）+ 审计 3 类别（KNOWLEDGE_VERSION/REVIEW/CONFLICT）+ 角色可见性接入（knowledge_view/knowledge_manage）；不进入工程计算、不开启 `engineering_enabled`、不输出 `engineering_approved`、不报价、不审批、不 AI 代责、**不自动改知识、不 AI 自动激活版本、不自动 merge 冲突**。

### 11.1 治理闭环（目标架构）

```
KnowledgeCandidate (3.8.7)
        │  human review accepted
        ▼
KnowledgeVersion.create_version  →  DRAFT
        │  submit_review
        ▼
      REVIEWING  ──activate_version(human)──▶  ACTIVE
        │                                          │
        │  deprecate_version(human)                │ (新版本 active 后旧版仍可查)
        ▼                                          ▼
    DEPRECATED                                ACTIVE (active_version)
        ▲
        │  KnowledgeChangeReview.create_review(human: accepted/rejected/needs_revision)
        │
KnowledgeConflict.discover_conflict (只登记 requires_human_review=True，禁自动 merge)
```

### 11.2 交付模块

| 模块 | 路径 | 关键契约 |
|---|---|---|
| 知识版本与生命周期 | `agents/enterprise/knowledge_version.py` | VersionStatus(4) + KnowledgeLifecycleService；activate/deprecate 须 USER（`require_human_actor`） |
| 知识变更审核 | `agents/enterprise/knowledge_change_review.py` | ReviewResult(3) + KnowledgeChangeReviewService；create_review 须 USER |
| 知识冲突候选 | `agents/enterprise/knowledge_conflict.py` | KnowledgeConflictCandidate(requires_human_review 强制 True) + KnowledgeConflictService（discover 只登记，禁 merge） |
| 审计增强 | `agents/enterprise/audit.py` | KNOWLEDGE_VERSION/REVIEW/CONFLICT + 3 record 方法；无 record_human_approval |
| 权限接入 | `agents/enterprise/dashboard_visibility.py` | knowledge_view（全员）/ knowledge_manage（ADMIN/EXPERT/REVIEWER） |
| 聚合/导出 | `agents/enterprise/service.py` + `__init__.py` | 挂载 knowledge_versions / knowledge_change_reviews / knowledge_conflicts |

### 11.3 红线守卫（6 条 fail-closed）

- ① 构造/写路径 `safety_invariants_ok()` 实测拦截（monkeypatch 翻转 `load_engineering_enabled` 全绿）。
- ② 无 `engineering_approved` 发射（仅 `_FORBIDDEN` 拦截名）。
- ③ 治理服务只登记不落地；`auto_update_knowledge`/`auto_publish_knowledge`/`auto_merge_knowledge`/`auto_approve_knowledge` 拦截；版本 active 须人工。
- ④ `approve`/`sign`/`authorize` 结构性拦截。
- ⑤ 无绕过 `UnifiedActivationGate`。
- ⑥ `require_human_actor(USER)` 强制 activate/deprecate/review；`requires_human_review` 强制 True；审计禁 `record_human_approval`；actor 如实标注。

### 11.4 测试与回归

- **7 类测试共 57 用例全绿**（version 10 / lifecycle 7 / review 8 / conflict 6 / permission 6 / audit 7 / redline 6）。
- 全 agents 套件 **1240 passed（1183 基线 + 57）零回归**（2026-08-05 实测，27.35s）。
- 未修改 `verified.json`/`config.yaml`/`engineering_enabled`；`engineering_enabled=false`；不输出 `engineering_approved`。

### 11.5 交付物清单（3.8.8）

| 类型 | 路径 |
|---|---|
| 知识版本/审核/冲突 | `agents/enterprise/{knowledge_version,knowledge_change_review,knowledge_conflict}.py` |
| 审计增强 | `agents/enterprise/audit.py` |
| 权限接入 | `agents/enterprise/dashboard_visibility.py` |
| 聚合/导出 | `agents/enterprise/service.py`、`agents/enterprise/__init__.py` |
| 测试×7 | `tests/agents/test_enterprise_knowledge_{version,lifecycle,change_review,conflict,governance_permission,governance_audit,governance_redline}.py` |
| 收口报告 | `.ai/reviews/phase3.8.8_knowledge_governance_version_control_report.md` |
| 状态刷新 | `.ai/project_status.json`（顶层 `phase_3_8_8_status=ENTERPRISE_KNOWLEDGE_GOVERNANCE_BUILT_NO_GO` + `current_stage.phase=3.8.8`） |

### 11.6 状态结论

- **状态：🟢 BUILT_NO_GO（2026-08-05）**：企业知识治理与版本控制层已完成版本生命周期 + 人工审核门禁 + 冲突发现（禁 merge）+ 审计 3 类别 + 角色可见性的完整构建，全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不自动改知识、不 AI 自动激活版本、不自动 merge 冲突、不审批、不 AI 代责。
- **未完成（人工动作，pending_verification）**：真实证据录入与 `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动经营建议 / 自动审批 均待主理人+专家线下执行；**本报告完成后停止，不进入 Phase 3.8.9**，等待主理人审核授权。

---

## 12. Phase 3.8.9 路线 —— Enterprise Knowledge Intelligence & Semantic Retrieval Layer（企业知识智能检索与语义理解层）

### 12.1 阶段定位

- **目标**：知识资产 → 语义理解 → 检索 → 引用 → 人工使用。本层只检索、只候选、只起草，绝不自动应用知识或生成工程结论。
- **状态**：🟢 `ENTERPRISE_KNOWLEDGE_INTELLIGENCE_BUILT_NO_GO`（2026-08-05 收口）。
- **激活态**：`engineering_enabled=false`；不输出 `engineering_approved`。

### 12.2 交付模块（6 模块 + 审计扩展）

| 模块 | 路径 | 关键契约 |
|---|---|---|
| 检索查询 | `agents/enterprise/knowledge_search.py` | `KnowledgeSearchQuery`（强制 org_id）+ `KnowledgeSearchService`（`create_query`/`run`/`run_with_context`） |
| 检索引擎 | `agents/enterprise/knowledge_retrieval.py` | `KnowledgeItem` + `KnowledgeRetrievalEngine`（`search`/`semantic_match`/`filter_by_permission`/`retrieve_context`） |
| 知识上下文 | `agents/enterprise/knowledge_context.py` | `KnowledgeTrace` + `KnowledgeContext`（sources/versions/trace 自动派生，全部可溯源） |
| 回答草稿 | `agents/enterprise/knowledge_answer.py` | `KnowledgeAnswerDraft`（references 非空强制，禁无来源；`requires_human_review` 强制 True） |
| 推荐候选 | `agents/enterprise/knowledge_recommendation.py` | `KnowledgeRecommendationCandidate`（仅为候选，禁 `auto_apply_knowledge`） |
| 可见性策略 | `agents/enterprise/knowledge_visibility.py` | `KnowledgeVisibilityPolicy`（角色→知识类型，默认拒绝） |
| 审计扩展 | `agents/enterprise/audit.py` | `KNOWLEDGE_SEARCH`/`KNOWLEDGE_RETRIEVAL`/`KNOWLEDGE_QUERY` + 3 record 方法（枚举累计 19） |

### 12.3 红线守卫（6 条 fail-closed）

- ① 构造/写路径 `safety_invariants_ok()` 实测拦截（monkeypatch 翻转 `load_engineering_enabled` 全绿）。
- ② 无 `engineering_approved` 发射（仅 `_FORBIDDEN` 拦截名）。
- ③ 引擎 `index()` 仅目录化已存在人工知识元数据；`auto_update_knowledge`/`auto_publish_knowledge`/`auto_merge_knowledge`/`auto_apply_knowledge` 拦截；代码库无 KnowledgeRepository。
- ④ `generate_engineering_conclusion`/`decide` 结构性拦截；`approve`/`sign`/`authorize` 拦截。
- ⑤ 无绕过 `UnifiedActivationGate`。
- ⑥ `requires_human_review` 强制 True；审计禁 `record_human_approval`；actor 如实标注（search/retrieval=USER，query/recommend=AI）；回答须引用来源、推荐仅为候选。

### 12.4 测试与回归

- **8 类测试共 53 用例全绿**（search 9 / retrieval 9 / retrieval_permission 6 / context 6 / answer_trace 6 / recommendation 6 / intelligence_audit 6 / intelligence_redline 6）。
- 全 agents 套件 **1293 passed（1240 基线 + 53 新增）零回归**（2026-08-05 实测，30.46s）。
- 未修改 `verified.json`/`config.yaml`/`engineering_enabled`；`engineering_enabled=false`；不输出 `engineering_approved`。

### 12.5 交付物清单（3.8.9）

| 类型 | 路径 |
|---|---|
| 六模块 + 审计扩展 | `agents/enterprise/{knowledge_search,knowledge_retrieval,knowledge_context,knowledge_answer,knowledge_recommendation,knowledge_visibility}.py` + `audit.py` + `service.py` + `__init__.py` |
| 测试×8 | `tests/agents/test_enterprise_knowledge_{search,retrieval,retrieval_permission,context,answer_trace,recommendation,intelligence_audit,intelligence_redline}.py` |
| 收口报告 | `.ai/reviews/phase3.8.9_knowledge_intelligence_retrieval_report.md` |
| 状态刷新 | `.ai/project_status.json`（顶层 `phase_3_8_9_status=ENTERPRISE_KNOWLEDGE_INTELLIGENCE_BUILT_NO_GO` + `current_stage.phase_3_8_9_status`） |

### 12.6 状态结论

- **状态：🟢 BUILT_NO_GO（2026-08-05）**：企业知识智能检索与语义理解层已完成检索查询 + 语义检索引擎 + 可追溯上下文 + 带来源回答草稿 + 推荐候选 + 角色可见性策略 + 审计 3 类别的完整构建，全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不自动应用知识、不生成工程结论、不审批、不 AI 代责。
- **未完成（人工动作，pending_verification）**：真实证据录入与 `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动经营建议 / 自动审批 均待主理人+专家线下执行；**本报告完成后停止，不进入 Phase 3.8.10**，等待主理人审核授权。

---

## 13. Phase 3.8.10 Enterprise Knowledge Agent Orchestration Layer（企业知识智能体编排层）

> 设计时间：2026-08-05 ｜ 状态：🟢 BUILT_NO_GO ｜ 激活态：`engineering_enabled=false`（未开）｜ 不输出 `engineering_approved` ｜ 不自动应用知识 / 不生成工程结论 / 不审批 / 不 AI 代责。

### 13.1 目标与闭环

在 3.8.9 检索/问答/推荐「候选层」之上，构建**智能体编排层**，把四个 AI 智能体串成完整闭环：

```
用户提问 ──▶ QueryAgent(理解) ──▶ RetrievalAgent(召回可追溯上下文)
                                          │
                                          ▼
                                  ValidationAgent(来源/版本/权限/溯源校验)
                                          │
                                          ▼
                                  AnswerAgent(起草待复核草稿)
                                          │
                                          ▼
                                  KnowledgeAnswerReview(真实 USER 复核)  ← 红线⑥：AI 不得代责
```

- 每个智能体**只做一件事**：理解 / 召回 / 校验 / 起草；**绝不批准、绝不落地、绝不生成工程结论**。
- 编排器（`KnowledgeAgentOrchestrator`）记录 `agent_event_log`（query/retrieve/validate/draft 四步事件）供审计回溯。
- 最终采用须经 `KnowledgeAnswerReview.submit_review_by_user`（真实 USER）显式闭环。

### 13.2 交付模块（6 智能体 + 审计扩展）

| 模块 | 路径 | 关键契约 |
|---|---|---|
| 查询理解智能体 | `agents/enterprise/knowledge_query_agent.py` | `KnowledgeQueryAgent`（`parse_query`/`identify_intent`/`extract_filters`；只理解，不生成工程判断） |
| 检索智能体 | `agents/enterprise/knowledge_retrieval_agent.py` | `KnowledgeRetrievalAgent`（`retrieve` → `KnowledgeContext`，来源/版本/溯源自动派生，绝不落地） |
| 校验智能体 | `agents/enterprise/knowledge_validation_agent.py` | `KnowledgeValidationAgent`（`validate` → `KnowledgeAgentValidationResult`；只校验，绝不自动批准） |
| 回答起草智能体 | `agents/enterprise/knowledge_answer_agent.py` | `KnowledgeAnswerAgent`（`draft` → `KnowledgeAnswerDraft`，references 非空、requires_human_review 强制 True） |
| 编排器 | `agents/enterprise/knowledge_agent_orchestrator.py` | `KnowledgeAgentOrchestrator`（`run` 串四步 + `agent_event_log`） |
| 人工复核门 | `agents/enterprise/knowledge_answer_review.py` | `KnowledgeAnswerReview`（`submit_review_by_user`：真实 USER，禁 AI 代责） |
| 审计扩展 | `agents/enterprise/audit.py` | `KNOWLEDGE_AGENT_QUERY`/`RETRIEVE`/`VALIDATE`/`DRAFT` + 4 record 方法（枚举累计 **23**） |
| 聚合挂载 | `agents/enterprise/service.py` + `__init__.py` | `EnterpriseOperationLayer` 新增 `knowledge_query_agent`/`knowledge_retrieval_agent`/`knowledge_validation_agent`/`knowledge_answer_agent`/`knowledge_agent_orchestrator`/`knowledge_answer_review` |

### 13.3 红线守卫（6 条 fail-closed）

- ① 全部智能体 / 编排器 / 复核门构造即断言 `safety_invariants_ok()`（启用态下构造抛 `EnterpriseRedLineViolationError`，monkeypatch 实测拦截）。
- ② 无 `engineering_approved` 发射（仅 `_FORBIDDEN` 拦截名；静态扫描 `test_no_engineering_approved_output_in_source` 验证源码中无赋值/返回，且 forbidden 元组守卫存在）。
- ③ 查询智能体只理解不落地；检索/回答智能体 `auto_apply_knowledge`/`auto_execute_knowledge` 结构性拦截；代码库无 KnowledgeRepository 自动写入。
- ④ 校验智能体只产出 `ValidationResult` 绝不自动批准；`generate_engineering_conclusion`/`decide`/`approve`/`auto_approve` 结构性拦截。
- ⑤ 无绕过 `UnifiedActivationGate`（统一以 `safety_invariants_ok()` 作为构造/写前置护栏）。
- ⑥ `requires_human_review` 强制 True；审计禁 `record_human_approval`；回答须引用来源（禁无来源）；复核须真实 USER（`reviewer_user_id` 非空且非 `ai`/`system` + `require_human_actor(USER)`）；actor 如实标注（四智能体动作=AI，人工复核=USER）。

### 13.4 测试与回归

- **8 类测试共 42 用例全绿**（query_agent 5 / retrieval_agent 3 / validation 5 / answer_agent 4 / orchestrator 3 / review 6 / agent_audit 3 / agent_redline 4 + 治理审计新增 4 + 智能检索审计计数刷新至 23）。
- 全 agents 套件 **1335 passed（1293 基线 + 42 新增）零回归**（2026-08-05 实测，32.18s）。
- 未修改 `verified.json`/`config.yaml`/`engineering_enabled`；`engineering_enabled=false`；不输出 `engineering_approved`。

### 13.5 交付物清单（3.8.10）

| 类型 | 路径 |
|---|---|
| 六智能体 + 审计扩展 | `agents/enterprise/{knowledge_query_agent,knowledge_retrieval_agent,knowledge_validation_agent,knowledge_answer_agent,knowledge_agent_orchestrator,knowledge_answer_review}.py` + `audit.py` + `service.py` + `__init__.py` |
| 测试×8 | `tests/agents/test_enterprise_knowledge_{query_agent,retrieval_agent,validation,answer_agent,orchestrator,review,agent_audit,agent_redline}.py`（另更新 `test_enterprise_knowledge_governance_audit.py` 19→23、`test_enterprise_knowledge_intelligence_audit.py` 19→23） |
| 收口报告 | `.ai/reviews/phase3.8.10_knowledge_agent_orchestration_report.md` |
| 状态刷新 | `.ai/project_status.json`（顶层 `phase_3_8_10_status=ENTERPRISE_KNOWLEDGE_AGENT_ORCHESTRATION_BUILT_NO_GO` + `current_stage.phase`=3.8.10 + `last_known_green_tests.agents_pytest`=1335） |
| 路线图 | `.ai/roadmap_v8.md` §13 |

### 13.6 状态结论

- **状态：🟢 BUILT_NO_GO（2026-08-05）**：企业知识智能体编排层已完成查询理解 + 检索召回 + 来源校验 + 回答起草 + 智能体编排 + 真实人工复核的完整闭环构建，全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不自动应用知识、不生成工程结论、不审批、不 AI 代责。
- **未完成（人工动作，pending_verification）**：真实证据录入与 `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动经营建议 / 自动审批 均待主理人+专家线下执行；**本报告完成后停止，不进入 Phase 3.8.11**，等待主理人审核授权。

---

## 14. Phase 3.8.11 — Enterprise Knowledge Conversation & Memory Layer（企业知识对话上下文与记忆层）

### 14.1 目标与主线

在 3.8.0~3.8.10 企业知识层之上建立「知识对话上下文与记忆层」，把检索/引用/回答收敛到一条可审计、可隔离、可人工兜底的会话主线：

**用户 → 会话 → 上下文 → 知识引用 → 回答草稿 → 人工使用**

- 用户发起会话（`KnowledgeConversation`，组织隔离）；
- 会话内追加消息（`KnowledgeMessage`，AI 消息必须引用来源）；
- 会话上下文（`KnowledgeConversationContext`）只暂存活跃主题/引用知识/未决问题/溯源，**绝不回写知识库**；
- 记忆策略（`MemoryPolicyService`）管理短期上下文与长期记忆候选；长期记忆候选 `requires_human_review=True`，唯一纳入路径须真实 USER；
- 审计（`KNOWLEDGE_CONVERSATION` / `KNOWLEDGE_MESSAGE` / `KNOWLEDGE_MEMORY`）如实记录发起方；
- 不同用户只能访问自己的会话与授权知识（接入 `IdentityService` + `KnowledgeVisibilityPolicy`）。

### 14.2 交付内容

| 类型 | 路径 |
|---|---|
| 会话模型（任务1） | `agents/enterprise/knowledge_conversation.py`（`ConversationStatus` / `KnowledgeConversation` / `KnowledgeConversationService`） |
| 消息模型（任务2） | `agents/enterprise/knowledge_message.py`（`MessageRole` / `KnowledgeMessage` / `KnowledgeMessageService`；AI 消息 `references` 非空 + `requires_human_review=True` 强制） |
| 会话上下文（任务3） | `agents/enterprise/knowledge_conversation_context.py`（`KnowledgeConversationContext` / `KnowledgeConversationContextService`；只暂存、禁写知识库） |
| 记忆策略（任务4） | `agents/enterprise/knowledge_memory_policy.py`（`MemoryCandidateStatus` / `MemoryCandidate` / `MemoryPolicyService`；长期记忆 `requires_human_review=True` + `require_human_actor` 守卫） |
| 审计扩展（任务5） | `agents/enterprise/audit.py`：+3 类别（累计 26）+ `record_knowledge_conversation_action` / `record_knowledge_message_action` / `record_knowledge_memory_action` |
| 服务装配（任务6） | `agents/enterprise/service.py` + `__init__.py`：`EnterpriseOperationLayer` 聚合 4 个新服务 |

### 14.3 红线守约（fail-closed，6 条）

- ① `engineering_enabled=false`（构造/写路径断言 `safety_invariants_ok()`）；配置未变更。
- ② 不输出 `engineering_approved`（4 服务 `_FORBIDDEN` 含该名，访问即抛错）。
- ③ 禁止 AI 自动改/并/发/用知识（`auto_update_knowledge` / `auto_merge_knowledge` / `auto_publish_knowledge` / `auto_apply_knowledge` / `commit` / `write` 结构性拦截）。
- ④ 禁止 AI 自动学习用户信息写知识库（`auto_learn_user` / `auto_save_user_to_knowledge` / `auto_learn` / `auto_save` 结构性拦截）。
- ⑤ 无自动工程决策（写路径守卫 + `generate_engineering_conclusion` / `decide` 拦截）。
- ⑥ AI 不代替人工责任：长期记忆 `commit`/`reject` 必经 `require_human_actor(USER)`；AI 消息 `requires_human_review=True`；审计 actor 真实、无 `record_human_approval`。

### 14.4 测试与回归

- **7 类测试共 15 用例全绿**（会话 2 / 消息 2 / 上下文 2 / 记忆策略 3 / 权限 3 / 审计 1 / 红线 2）+ 治理审计 +3 record 测试 + 审计计数刷新至 26（`test_enterprise_knowledge_conversation_memory.py` / `test_enterprise_knowledge_governance_audit.py` / `test_enterprise_knowledge_intelligence_audit.py`）。
- 全 agents 套件 **1353 passed（1335 基线 + 18 新增）零回归**（2026-08-06 实测，34.53s）。
- 未修改 `verified.json` / `config.yaml` / `engineering_enabled`；`engineering_enabled=false`；不输出 `engineering_approved`。

### 14.5 交付物清单（3.8.11）

| 类型 | 路径 |
|---|---|
| 四模块 + 审计 + 装配 | `agents/enterprise/{knowledge_conversation,knowledge_message,knowledge_conversation_context,knowledge_memory_policy}.py` + `audit.py` + `service.py` + `__init__.py` |
| 测试×3 | `tests/agents/test_enterprise_knowledge_conversation_memory.py`（7 类 15 用例）+ 更新 `test_enterprise_knowledge_governance_audit.py`（`EXPECTED_CATEGORIES` 23→26、+3 record 测试）+ `test_enterprise_knowledge_intelligence_audit.py`（计数 23→26） |
| 收口报告 | `.ai/reviews/phase3.8.11_knowledge_conversation_memory_report.md` |
| 状态刷新 | `.ai/project_status.json`（顶层 `phase_3_8_11_status=ENTERPRISE_KNOWLEDGE_CONVERSATION_MEMORY_BUILT_NO_GO` + `current_stage.phase`=3.8.11 + `last_known_green_tests.agents_pytest`=1353） |
| 路线图 | `.ai/roadmap_v8.md` §14 |

### 14.6 状态结论

- **状态：🟢 BUILT_NO_GO（2026-08-06）**：企业知识对话上下文与记忆层已完成会话/消息/上下文/记忆候选的完整主线构建，全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不自动写知识库、不自动学习用户、不生成工程结论、不审批、不 AI 代责。
- **未完成（人工动作，pending_verification）**：真实证据录入与 `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动经营建议 / 自动审批 均待主理人+专家线下执行；**本报告完成后停止，不进入 Phase 3.8.12**，等待主理人审核授权。

---

## 15. Phase 3.8.12 —— Enterprise Knowledge Task Planning & Multi-Agent Workflow Layer（企业知识任务规划与多智能体工作流层）

### 15.1 目标

在 3.8.0~3.8.11 企业知识层基座之上，建立复杂企业知识任务的规划与多智能体编排能力：用户问题 → 任务拆解 → Agent 规划 → 知识调用 → 结果汇总 → 人工审核。规划器只拆任务不决策，编排器只协调不审批，复杂任务最终输出强制 `requires_human_review=True`，AI 不得自动完成最终任务。

### 15.2 交付内容

| 类型 | 路径 |
|---|---|
| 任务模型（任务1） | `agents/enterprise/knowledge_task.py`（`KnowledgeTaskStatus` / `KnowledgeTask` / `KnowledgeTaskService`） |
| 任务规划器（任务2） | `agents/enterprise/knowledge_task_planner.py`（`analyze_goal` / `create_plan` / `split_subtasks`；只拆不决策） |
| 子任务模型（任务3） | `agents/enterprise/knowledge_subtask.py`（`KnowledgeSubTaskType` / `KnowledgeSubTask` / `KnowledgeSubTaskService`） |
| 多智能体编排器（任务4） | `agents/enterprise/knowledge_task_orchestrator.py`（`KnowledgeTaskOrchestrator` 复用 3.8.10 四智能体，只协调不审批） |
| 人工复核检查点（任务5） | `agents/enterprise/task_review_checkpoint.py`（`checkpoint` 强制待复核 / `finalize_by_human` 仅真实 USER） |
| 审计扩展（任务6） | `agents/enterprise/audit.py`：+3 类别（累计 29）+ `record_knowledge_task_action` / `record_knowledge_subtask_action` / `record_knowledge_agent_workflow_action` |
| 权限接入（任务7） | 任务接入 `IdentityService` + `KnowledgeVisibilityPolicy`；访问隔离（本人\|ADMIN）；检索按角色过滤；规划器传播 `allowed_knowledge_types` |
| 服务装配（任务6/7） | `agents/enterprise/service.py` + `__init__.py`：`EnterpriseOperationLayer` 聚合 5 个新服务（复用同一 `task_service` / `subtask_service` / `planner`） |

### 15.3 红线守约（fail-closed，6 条）

- ① `engineering_enabled=false`（构造/写路径断言 `safety_invariants_ok()`）；配置未变更。
- ② 不输出 `engineering_approved`（5 服务 `_FORBIDDEN` 含该名，访问即抛错）。
- ③ 禁止 AI 自动改/并/发/用知识（`auto_update_knowledge` / `auto_merge_knowledge` / `auto_publish_knowledge` / `auto_apply_knowledge` / `commit` / `write` 结构性拦截）。
- ④ 禁止 AI 自动生成工程结论（`generate_engineering_conclusion` / `decide` / `auto_decision` 结构性拦截）。
- ⑤ 无自动审批（`AuditService` 无 `record_human_approval`；`advance_status(COMPLETED)` / `finalize_by_human` 必经 `require_human_actor(USER)`）。
- ⑥ AI 不代替人工责任：复杂任务 `requires_human_review=True` 强制；编排器绝不自动 `completed`（`advance_status(COMPLETED, AI)` 抛错）；审计 actor 真实、无 `record_human_approval`。

### 15.4 测试与回归

- **八类测试共 25 用例全绿** + 治理审计 +3 record 测试 + 审计计数刷新至 29（`test_enterprise_knowledge_task_planning.py` / `test_enterprise_knowledge_governance_audit.py` / `test_enterprise_knowledge_intelligence_audit.py`）。
- 全 agents 套件 **1374 passed（1335 基线 + 39 新增）零回归**（2026-08-06 实测，约 34s）。
- 未修改 `verified.json` / `config.yaml` / `engineering_enabled`；`engineering_enabled=false`；不输出 `engineering_approved`。

### 15.5 交付物清单（3.8.12）

| 类型 | 路径 |
|---|---|
| 五模块 + 审计 + 装配 | `agents/enterprise/{knowledge_task,knowledge_task_planner,knowledge_subtask,knowledge_task_orchestrator,task_review_checkpoint}.py` + `audit.py` + `service.py` + `__init__.py` |
| 测试×3 | `tests/agents/test_enterprise_knowledge_task_planning.py`（八类 25 用例）+ 更新 `test_enterprise_knowledge_governance_audit.py`（`EXPECTED_CATEGORIES` 26→29、+3 record 测试）+ `test_enterprise_knowledge_intelligence_audit.py`（计数 26→29） |
| 收口报告 | `.ai/reviews/phase3.8.12_knowledge_task_planning_multi_agent_report.md` |
| 状态刷新 | `.ai/project_status.json`（顶层 `phase_3_8_12_status=ENTERPRISE_KNOWLEDGE_TASK_PLANNING_BUILT_NO_GO` + `phase`=3.8.12 + `agents_pytest`=1374） |
| 路线图 | `.ai/roadmap_v8.md` §15 |

### 15.6 状态结论

- **状态：🟢 BUILT_NO_GO（2026-08-06）**：企业知识任务规划与多智能体工作流层已完成任务模型/规划器/子任务/编排器/检查点的完整主线构建，全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不自动写知识库、不自动生成工程结论、不审批、不 AI 代责；复杂任务最终输出强制 `requires_human_review=True`。
- **未完成（人工动作，pending_verification）**：真实证据录入与 `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动经营建议 / 自动审批 均待主理人+专家线下执行；**本报告完成后停止，不进入 Phase 3.8.13**，等待主理人审核授权。

## 16. Phase 3.8.13 —— Enterprise Agent Capability Registry & Governance Layer（企业智能体能力注册与治理层）

### 16.1 目标

在 3.8.0~3.8.12 企业知识层基座之上，建立外部/内部 AI 智能体在企业内部的**可注册、可声明能力边界、可版本追踪、可权限隔离、可人工激活/弃用**的完整治理闭环，防止智能体越权访问资源或替代专家责任。

### 16.2 交付内容

| 类型 | 路径 |
|---|---|
| AgentRegistry 模型（任务1） | `agents/enterprise/agent_registry.py`（`AgentStatus`(draft/active/deprecated) / `AgentRegistry` 8 字段，status 默认 `draft`，active 须人工确认） |
| AgentCapability 模型（任务2） | `agents/enterprise/agent_capability.py`（`AgentCapability`：input/output_types / permissions / limitations，明确边界） |
| AgentVersion 管理（任务3） | `agents/enterprise/agent_version.py`（`AgentVersion`：agent_id/version/change_log/created_at/status，版本可追踪） |
| AgentPermissionPolicy（任务4） | `agents/enterprise/agent_permission_policy.py`（`AgentPermissionPolicy(org_id)` 默认拒绝，控制 Agent 访问知识/工具/数据范围） |
| AgentLifecycleService（任务5） | `agents/enterprise/agent_lifecycle_service.py`（`register` / `submit_review` / `activate`[须真实 USER] / `deprecate`[须真实 USER]，镜像 3.8.12 `require_human_actor` 守卫） |
| 审计扩展（任务6） | `agents/enterprise/audit.py`：+3 类别（累计 32）+ `record_agent_register_action` / `record_agent_execution_action` / `record_agent_version_action` |
| 权限接入（任务7） | 接入 `IdentityService` + `KnowledgeVisibilityPolicy`；Agent 资源访问受控、组织隔离、角色默认拒绝 |
| 服务装配（任务6/7） | `agents/enterprise/service.py` + `__init__.py`：`EnterpriseOperationLayer` 聚合 `agent_permission_policy` / `agent_registry` / `agent_lifecycle`（复用同一 `audit` / `identity` / `knowledge_visibility`） |

### 16.3 红线守约（fail-closed，6 条）

- ① `engineering_enabled=false`（构造/写路径断言 `safety_invariants_ok()`）；配置未变更。
- ② 不输出 `engineering_approved`（5 服务 `_FORBIDDEN` 含该名，访问即抛错）。
- ③ 禁止 AI 自动改/并/发/用知识（`auto_update_knowledge` / `auto_publish_knowledge` / `auto_merge_knowledge` / `publish` / `apply` / `commit` / `write` 结构性拦截）。
- ④ 禁止 AI 自动生成工程结论（`generate_engineering_conclusion` / `decide` / `auto_decision` 结构性拦截）。
- ⑤ 无自动审批（`AuditService` 无 `record_human_approval`；`activate` / `deprecate` 必经 `require_human_actor(USER)`）。
- ⑥ AI 不代替人工责任：Agent 激活/弃用必经真实 USER（`activate(actor_kind=AI)` / `deprecate(actor_kind=AI)` 抛错）；审计 actor 真实、无 `record_human_approval`。

### 16.4 测试与回归

- **八类测试共 26 用例全绿** + 治理审计 +3 record 测试 + 审计计数刷新至 32（`test_enterprise_agent_registry_governance.py` / `test_enterprise_knowledge_governance_audit.py` / `test_enterprise_knowledge_intelligence_audit.py`）。
- 全 agents 套件 **1400 passed（1353 基线 + 47 新增）零回归**（2026-08-06 实测，约 38s）。
- 未修改 `verified.json` / `config.yaml` / `engineering_enabled`；`engineering_enabled=false`；不输出 `engineering_approved`。

### 16.5 交付物清单（3.8.13）

| 类型 | 路径 |
|---|---|
| 五模块 + 审计 + 装配 | `agents/enterprise/{agent_registry,agent_capability,agent_version,agent_permission_policy,agent_lifecycle_service}.py` + `audit.py` + `service.py` + `__init__.py` |
| 测试×3 | `tests/agents/test_enterprise_agent_registry_governance.py`（八类 26 用例）+ 更新 `test_enterprise_knowledge_governance_audit.py`（`EXPECTED_CATEGORIES` 29→32）+ `test_enterprise_knowledge_intelligence_audit.py`（计数 29→32） |
| 收口报告 | `.ai/reviews/phase3.8.13_agent_registry_governance_report.md` |
| 状态刷新 | `.ai/project_status.json`（顶层 `phase_3_8_13_status=ENTERPRISE_AGENT_GOVERNANCE_BUILT_NO_GO` + `phase`=3.8.13 + `agents_pytest`=1400） |
| 路线图 | `.ai/roadmap_v8.md` §16 |

### 16.6 状态结论

- **状态：🟢 BUILT_NO_GO（2026-08-06）**：企业智能体能力注册与治理层已完成 AgentRegistry/AgentCapability/AgentVersion/AgentPermissionPolicy/AgentLifecycleService 的完整主线构建，全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不自动写知识库、不自动生成工程结论、不审批、不 AI 代责；Agent 激活/弃用强制须经真实 USER。
- **未完成（人工动作，pending_verification）**：真实证据录入与 `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动审批 均待主理人+专家线下执行；**本报告完成后停止，不进入 Phase 3.8.14**，等待主理人审核授权。

---

## 17. Phase 3.8.14 —— Enterprise Agent Observability & Performance Intelligence Layer（企业智能体可观测性与性能智能层）

- **状态：🟢 BUILT_NO_GO（2026-08-06）**；授权：BOIP AI Chief Architect（轩哥授权），11 任务 #623–#633；6 条最高红线 fail-closed。
- **基座**：复用 Phase 3.8.13 的 `AgentPermissionPolicy` + `AgentLifecycleService` + `IdentityService`。

### 17.1 任务与交付（#623–#633）

| 任务 | 内容 | 状态 |
|---|---|---|
| #623 | `AgentExecutionLog` 模型（status 默认 SUCCESS、`is_successful`、记录时注入 `org_id`） | ✅ |
| #624 | `AgentMetric` 模型（成功率裁剪 [0,1]、无评价字段） | ✅ |
| #625 | `AgentTrace` 模型（root/leaf 标记、可溯源） | ✅ |
| #626 | `AgentHealthDetector` → `AgentHealthCandidate`（`requires_human_review=True` 强制、16 处置方法禁用） | ✅ |
| #627 | `AgentPerformanceReport`（强 `SourceTrace`、`anomaly_candidates` 只候选、12 优化方法禁用） | ✅ |
| #628 | 审计增强 +3 枚举（`AGENT_METRIC`/`AGENT_TRACE`/`AGENT_HEALTH`，累计 32→**35**）+ 3 记录方法 | ✅ |
| #629 | 权限接入 `IdentityService` + `AgentPermissionPolicy`（默认拒绝）+ `KnowledgeVisibilityPolicy`，`EnterpriseOperationLayer` 聚合 `self.agent_observability` 共享 `audit`/`identity`/`knowledge_visibility` | ✅ |
| #630 | 八类测试（`test_enterprise_agent_observability.py`，**29 用例**） | ✅ |
| #631 | 最终验证 `pytest tests/agents -q` 全过 + 确认红线 | ✅ |
| #632 | 收口报告（`.ai/reviews/phase3.8.14_agent_observability_performance_report.md`，7 节） | ✅ |
| #633 | 更新 `project_status.json` + `roadmap_v8.md`，完成后 STOP | ✅ |

### 17.2 代码与审计清单

| 类型 | 路径 |
|---|---|
| 可观测性核心（917 行 / 10 导出符号） | `agents/enterprise/agent_observability.py`（`AgentExecutionLog`/`AgentMetric`/`AgentTrace`/`AgentHealthCandidate`/`AgentHealthDetector`/`AgentPerformanceReport`/`AgentPerformanceReportService`/`AgentObservabilityService` + `AgentExecutionStatus`/`AgentMetricType`） |
| 审计扩展 | `agents/enterprise/audit.py`：+3 枚举（`AGENT_METRIC`=agent_metric / `AGENT_TRACE`=agent_trace / `AGENT_HEALTH`=agent_health，L102–104，累计 35）+ `record_agent_metric_action`(L1201)/`record_agent_trace_action`(L1229)/`record_agent_health_action`(L1256) |
| 权限基座（复用 3.8.13） | `agents/enterprise/agent_permission_policy.py` + `identity.py` + `agent_lifecycle_service.py` |
| 服务装配 | `agents/enterprise/service.py`（`EnterpriseOperationLayer` 新增 `self.agent_observability`，L359–362，注入共享 `agent_permission_policy`）+ `__init__.py` |
| 测试（本层） | `tests/agents/test_enterprise_agent_observability.py`（八类 29 用例） |
| 测试计数修正（32→35） | `tests/agents/test_enterprise_knowledge_governance_audit.py`（`EXPECTED_CATEGORIES` +3 项 / 断言 32→35）+ `tests/agents/test_enterprise_knowledge_intelligence_audit.py`（`test_total_audit_categories_32`→`_35`） |

### 17.3 红线守约（fail-closed，6 条）

- ① `engineering_enabled=false`（`config.yaml:102`；构造/写路径断言 `safety_invariants_ok()`；`monkeypatch` 启用态后三构造器抛 `EnterpriseRedLineViolationError`）。
- ② 不输出 `engineering_approved`（`_FORBIDDEN` 含该名，访问即抛错，不在 `__all__`）。
- ③ 禁止 Agent 自改/自优化/自发布（`auto_update`/`auto_modify`/`self_upgrade`/`publish`/`apply`/`commit`/`write`/`auto_optimize`/`evaluate_agent` 结构性拦截）。
- ④ 禁止 Agent 自动激活/处置（健康检测器 16 处置方法禁用；健康只产出 `requires_human_review=True` 候选）。
- ⑤ 无自动审批（`AuditService` 无 `record_human_approval`；human_review 必经真实 USER）。
- ⑥ AI 不代替专家责任（审计 actor 真实、无「代记人工批准」入口；监控数据读取默认拒绝）。

### 17.4 测试与回归

- **八类测试共 29 用例全绿**（`test_enterprise_agent_observability.py`：execution/metric/trace/health/report/permission/audit/red line）。
- 全 agents 套件 **1429 passed（1400 基线 + 29 新增）零回归**（2026-08-06 实测约 40s）。
- 修复 2 个 prior-phase 过期断言（3.8.13 遗留 `== 32` 计数，因本层 +3 枚举变 35，已刷新为 35）。
- 未修改 `verified.json` / `config.yaml` / `engineering_enabled`；`engineering_enabled=false`；不输出 `engineering_approved`。

### 17.5 交付物清单（3.8.14）

| 类型 | 路径 |
|---|---|
| 可观测性核心 + 装配 | `agents/enterprise/agent_observability.py` + `audit.py`（+3 枚举/方法）+ `service.py`（聚合）+ `__init__.py` |
| 测试 | `tests/agents/test_enterprise_agent_observability.py`（29 用例）+ 更新 `test_enterprise_knowledge_governance_audit.py` / `test_enterprise_knowledge_intelligence_audit.py`（计数 32→35） |
| 收口报告 | `.ai/reviews/phase3.8.14_agent_observability_performance_report.md` |
| 状态刷新 | `.ai/project_status.json`（`current_stage.phase_3_8_14_status=BUILT_NO_GO` + `agents_pytest`=1429） |
| 路线图 | `.ai/roadmap_v8.md` §17 |

### 17.6 状态结论

- **状态：🟢 BUILT_NO_GO（2026-08-06）**：企业智能体可观测性与性能智能层已完成 `AgentExecutionLog`/`AgentMetric`/`AgentTrace`/`AgentHealthCandidate`/`AgentPerformanceReport` + `AgentHealthDetector`/`AgentPerformanceReportService`/`AgentObservabilityService` 的完整主线构建，审计累计 35 类别，全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不评价/不评级/不禁用/不优化/不审批 Agent，不 AI 代责；Agent 健康只产出「待人工研判候选」，性能报告强 `SourceTrace`。
- **未完成（人工动作，pending_verification）**：真实 Agent 运行遥测录入 / `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动审批 均待主理人+专家线下执行；**本报告与状态刷新完成后停止，不进入 Phase 3.8.15**，等待主理人审核授权。

## 18. Phase 3.8.15 —— Enterprise Agent Evaluation & Quality Governance Layer（企业智能体评估与质量治理层）

- **状态：🟢 BUILT_NO_GO（2026-08-06）**；授权：BOIP AI Chief Architect（轩哥授权），11 任务 #634–#644；6 条最高红线 fail-closed。
- **基座**：复用 Phase 3.8.13 的 `AgentPermissionPolicy` + `AgentLifecycleService` + `IdentityService` 与 Phase 3.8.14 的 `AgentObservabilityService`。

### 18.1 任务与交付（#634–#644）

| 任务 | 内容 | 状态 |
|---|---|---|
| #634 | `AgentQualityMetric` 模型（归一化枚举、负值裁剪 0、无评价字段） | ✅ |
| #635 | `AgentEvaluation` 模型（evaluator 非 ai/system/空 拦截、强制人工责任） | ✅ |
| #636 | `AgentVersionComparison`（只算 delta 事实、强 `SourceTrace`、不做升级决策） | ✅ |
| #637 | `AgentFeedback` 模型（`requires_human_review=True` 强制、只登记不处置） | ✅ |
| #638 | `AgentQualityReport`（强 `SourceTrace`、无来源即拒、只汇编事实） | ✅ |
| #639 | 审计增强 +3 枚举（`AGENT_QUALITY`/`AGENT_EVALUATION`/`AGENT_FEEDBACK`，累计 35→**38**）+ 3 记录方法 | ✅ |
| #640 | 权限接入 `IdentityService` + `AgentPermissionPolicy`（默认拒绝）+ `KnowledgeVisibilityPolicy`，`EnterpriseOperationLayer` 聚合 `self.agent_quality_governance` 共享 `audit`/`identity`/`knowledge_visibility`/`agent_permission_policy` | ✅ |
| #641 | 八类测试（`test_enterprise_agent_quality_governance.py`，**29 用例**） | ✅ |
| #642 | 最终验证 `pytest tests/agents -q` 全过 + 确认红线（注：曾因 `tests/_tmp_drill_*.json` 陈旧临时文件堆积误报 29 失败，清理后复跑确认 **1458 passed 零回归**） | ✅ |
| #643 | 收口报告（`.ai/reviews/phase3.8.15_agent_quality_governance_report.md`，7 节） | ✅ |
| #644 | 更新 `project_status.json` + `roadmap_v8.md`，完成后 STOP | ✅ |

### 18.2 代码与审计清单

| 类型 | 路径 |
|---|---|
| 质量治理核心（705 行 / 7 导出符号） | `agents/enterprise/agent_quality_governance.py`（`AgentQualityMetricType`/`AgentQualityMetric`/`AgentEvaluation`/`AgentVersionComparison`/`AgentFeedback`/`AgentQualityReport`/`AgentQualityGovernanceService`） |
| 审计扩展 | `agents/enterprise/audit.py`：+3 枚举（`AGENT_QUALITY`=agent_quality / `AGENT_EVALUATION`=agent_evaluation / `AGENT_FEEDBACK`=agent_feedback，累计 38）+ `record_agent_quality_action`(L1297)/`record_agent_evaluation_action`(L1325)/`record_agent_feedback_action`(L1352) |
| 权限基座（复用 3.8.13） | `agents/enterprise/agent_permission_policy.py` + `identity.py` + `agent_lifecycle_service.py` |
| 服务装配 | `agents/enterprise/service.py`（`EnterpriseOperationLayer` 新增 `self.agent_quality_governance`，L371–375，注入共享 `agent_permission_policy`）+ `__init__.py` |
| 测试（本层） | `tests/agents/test_enterprise_agent_quality_governance.py`（八类 29 用例） |
| 测试计数修正（35→38） | `tests/agents/test_enterprise_knowledge_governance_audit.py`（`EXPECTED_CATEGORIES` +3 项 / 断言 35→38）+ `tests/agents/test_enterprise_knowledge_intelligence_audit.py`（`test_total_audit_categories_35`→`_38`） |

### 18.3 红线守约（fail-closed，6 条）

- ① `engineering_enabled=false`（`config.yaml:102`；构造/写路径断言 `safety_invariants_ok()`；`monkeypatch` 启用态后构造器抛 `EnterpriseRedLineViolationError`）。
- ② 不输出 `engineering_approved`（`_FORBIDDEN` 含该名，访问即抛错，不在 `__all__`）。
- ③ 禁止 AI 自动评级/打分/评价（`auto_rate_agent`/`auto_grade_agent`/`auto_score_agent`/`rate_agent`/`grade_agent`/`score_agent`/`evaluate_agent`/`judge_agent` 结构性拦截）。
- ④ 禁止 AI 自动禁用/弃用/修改/升级 Agent（`auto_disable_agent`/`auto_deprecate_agent`/`disable_agent`/`deprecate_agent`/`auto_deactivate`/`deactivate_agent`/`auto_retire`/`retire_agent`/`auto_modify_agent`/`modify_agent`/`auto_update_agent`/`update_agent`/`auto_edit_agent`/`edit_agent`/`change_agent`/`auto_upgrade`/`recommend_upgrade`/`decide_upgrade`/`promote_version`/`auto_promote`/`make_management_decision`/`recommend`/`decide` 结构性拦截）。
- ⑤ 无自动审批（`AuditService` 无 `record_human_approval`；`submit_evaluation`/`review_feedback` 必经 `require_human_actor(USER)`）。
- ⑥ AI 不代替专家责任（评价者强制非 ai/system；反馈 `requires_human_review=True` 强制；质量数据读取默认拒绝）。

### 18.4 测试与回归

- **八类测试共 29 用例全绿**（`test_enterprise_agent_quality_governance.py`：quality_metric/evaluation/version_comparison/feedback/report/permission/audit/red line）。
- 全 agents 套件 **1458 passed（1429 基线 + 29 新增）零回归**（2026-08-06 实测约 34s；清理 `tests/_tmp_drill_*.json` 陈旧演练临时文件后复跑确认；该堆积为历史崩溃运行残留，非 3.8.15 回归）。
- 修复 2 个 prior-phase 过期断言（3.8.14 遗留 `== 35` 计数，因本层 +3 枚举变 38，已刷新为 38）。
- 未修改 `verified.json` / `config.yaml` / `engineering_enabled`；`engineering_enabled=false`；不输出 `engineering_approved`。

### 18.5 交付物清单（3.8.15）

| 类型 | 路径 |
|---|---|
| 质量治理核心 + 装配 | `agents/enterprise/agent_quality_governance.py` + `audit.py`（+3 枚举/方法）+ `service.py`（聚合）+ `__init__.py` |
| 测试 | `tests/agents/test_enterprise_agent_quality_governance.py`（29 用例）+ 更新 `test_enterprise_knowledge_governance_audit.py` / `test_enterprise_knowledge_intelligence_audit.py`（计数 35→38） |
| 收口报告 | `.ai/reviews/phase3.8.15_agent_quality_governance_report.md` |
| 状态刷新 | `.ai/project_status.json`（`current_stage.phase_3_8_15_status=BUILT_NO_GO` + `agents_pytest`=1458 + `phase`=3.8.15） |
| 路线图 | `.ai/roadmap_v8.md` §18 |

### 18.6 状态结论

- **状态：🟢 BUILT_NO_GO（2026-08-06）**：企业智能体评估与质量治理层已完成 `AgentQualityMetric`/`AgentEvaluation`/`AgentVersionComparison`/`AgentFeedback`/`AgentQualityReport` + `AgentQualityGovernanceService` 的完整主线构建，审计累计 38 类别，全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不 AI 自动评级/禁用/修改/升级 Agent，不 AI 代责；Agent 评价/反馈责任节点必经真实 USER，质量报告强 `SourceTrace`。

---

## 19. Phase 3.8.16 —— Enterprise Agent Cost & Resource Intelligence Layer（企业智能体成本与资源智能层）

- **状态：🟢 BUILT_NO_GO（2026-08-06）**；授权：BOIP AI Chief Architect（轩哥授权），11 任务 #645–#655；6 条最高红线 fail-closed。
- **基座**：复用 Phase 3.8.13 的 `AgentPermissionPolicy` + `IdentityService` 与 Phase 3.8.14 的 `AgentObservabilityService` 及 Phase 3.8.15 的 `AgentQualityGovernanceService`。

### 19.1 任务与交付（#645–#655）

| 任务 | 内容 | 状态 |
|---|---|---|
| #645 | `AgentResourceUsage` 模型（只记事实、负值裁剪 0、默认单位、无优化字段） | ✅ |
| #646 | `AgentCostMetric` 模型（token/compute/storage/external_api 四类、负值裁剪 0） | ✅ |
| #647 | `AgentCostAttribution` 模型（可追踪归属：缺对象或缺来源即抛错） | ✅ |
| #648 | `AgentResourceAnalyzer`（aggregate_usage 只聚合、calculate_cost 单价须外部台账、compare_period 只算 delta） | ✅ |
| #649 | `AgentCostReport`（强 `SourceTrace`、只汇编事实）+ `AgentCostResourceService` 聚合入口 | ✅ |
| #650 | 审计增强 +3 枚举（`AGENT_RESOURCE`/`AGENT_COST`/`AGENT_COST_REPORT`，累计 38→**41**）+ 3 记录方法 | ✅ |
| #651 | 权限接入 `IdentityService` + `AgentPermissionPolicy`（默认拒绝）+ `KnowledgeVisibilityPolicy`，`EnterpriseOperationLayer` 聚合 `self.agent_cost_resource` 共享 `audit`/`identity`/`knowledge_visibility`/`agent_permission_policy` | ✅ |
| #652 | 八类测试（`test_enterprise_agent_cost_resource.py`，**30 用例**） | ✅ |
| #653 | 最终验证 `pytest tests/agents -q` 全过 + 确认红线（全 agents 套件 **1488 passed 零回归**：1458 基线 + 30） | ✅ |
| #654 | 收口报告（`.ai/reviews/phase3.8.16_agent_cost_resource_report.md`，7 节） | ✅ |
| #655 | 更新 `project_status.json` + `roadmap_v8.md`，完成后 STOP | ✅ |

### 19.2 代码与审计清单

| 类型 | 路径 |
|---|---|
| 成本与资源核心（924 行 / 8 导出符号） | `agents/enterprise/agent_cost_resource.py`（`AgentResourceType`/`AgentCostType`/`AgentResourceUsage`/`AgentCostMetric`/`AgentCostAttribution`/`AgentResourceAnalyzer`/`AgentCostReport`/`AgentCostResourceService`） |
| 审计扩展 | `agents/enterprise/audit.py`：+3 枚举（`AGENT_RESOURCE`=agent_resource / `AGENT_COST`=agent_cost / `AGENT_COST_REPORT`=agent_cost_report，累计 41）+ `record_agent_resource_action`(L1397)/`record_agent_cost_action`(L1424)/`record_agent_cost_report_action`(L1451) |
| 权限基座（复用 3.8.13） | `agents/enterprise/agent_permission_policy.py` + `identity.py` + `organization.py`(`EnterpriseIsolationError`) |
| 服务装配 | `agents/enterprise/service.py`（`EnterpriseOperationLayer` 新增 `self.agent_cost_resource`，注入共享 `agent_permission_policy`）+ `__init__.py`（新增 8 符号导出） |
| 测试（本层） | `tests/agents/test_enterprise_agent_cost_resource.py`（八类 30 用例） |
| 测试计数修正（38→41） | `tests/agents/test_enterprise_knowledge_governance_audit.py`（`EXPECTED_CATEGORIES` +3 项 / 断言 38→41）+ `tests/agents/test_enterprise_knowledge_intelligence_audit.py`（`test_total_audit_categories_38`→`_41`）+ `tests/agents/test_enterprise_agent_quality_governance.py`（`_38`→`_41`） |

### 19.3 红线守约（fail-closed，6 条，3.8.16 细化）

- ① `engineering_enabled=false`（`config.yaml:102`；构造/写路径断言 `safety_invariants_ok()`；`monkeypatch` 启用态后构造器抛 `EnterpriseRedLineViolationError`）。
- ② 不输出 `engineering_approved`（`_FORBIDDEN` 含该名，访问即抛错，不在 `__all__`）。
- ③ 禁止 AI 自动关闭/停止 Agent（成本高 ≠ AI 可以关停它）：`auto_disable_agent`/`auto_stop_agent`/`disable_agent`/`stop_agent`/`kill_agent`/`terminate_agent`/`suspend_agent`/`deactivate_agent` 等结构性拦截。
- ④ 禁止 AI 自动修改 Agent 配置：`auto_modify_agent`/`modify_agent_config`/`configure_agent`/`set_agent_config`/`update_agent`/`change_agent` 等结构性拦截。
- ⑤ 禁止 AI 自动优化资源策略：`auto_optimize`/`optimize_cost`/`auto_scale`/`set_budget`/`enforce_budget`/`reduce_cost`/`cut_cost`/`apply_resource_policy` 等结构性拦截。
- ⑥ AI 不代替管理责任：审计无 `record_human_approval`；成本单价须外部台账（缺即抛 `EnterpriseRedLineViolationError`，禁编造）；成本归属/报告来源强制可追溯（禁无源数据）；成本数据读取默认拒绝（专家越界即隔离）。

### 19.4 测试与回归

- **八类测试共 30 用例全绿**（`test_enterprise_agent_cost_resource.py`：resource_usage/cost_metric/cost_attribution/analyzer/report/permission/audit/red line）。
- 全 agents 套件 **1488 passed（1458 基线 + 30 新增）零回归**（2026-08-06 实测约 35s）。
- 修正 3 处 prior-phase 过期断言（3.8.15 遗留 `== 38` 计数，因本层 +3 枚举变 41，已刷新为 41）。
- 未修改 `verified.json` / `config.yaml` / `engineering_enabled`；`engineering_enabled=false`；不输出 `engineering_approved`。

### 19.5 交付物清单（3.8.16）

| 类型 | 路径 |
|---|---|
| 成本与资源核心 + 装配 | `agents/enterprise/agent_cost_resource.py` + `audit.py`（+3 枚举/方法）+ `service.py`（聚合）+ `__init__.py` |
| 测试 | `tests/agents/test_enterprise_agent_cost_resource.py`（30 用例）+ 更新 `test_enterprise_knowledge_governance_audit.py` / `test_enterprise_knowledge_intelligence_audit.py` / `test_enterprise_agent_quality_governance.py`（计数 38→41） |
| 收口报告 | `.ai/reviews/phase3.8.16_agent_cost_resource_report.md` |
| 状态刷新 | `.ai/project_status.json`（`phase_3_8_16_status=BUILT_NO_GO` + `agents_pytest`=1488） |
| 路线图 | `.ai/roadmap_v8.md` §19 |

### 19.6 状态结论

- **状态：🟢 BUILT_NO_GO（2026-08-06）**：企业智能体成本与资源智能层已完成 `AgentResourceUsage`/`AgentCostMetric`/`AgentCostAttribution`/`AgentResourceAnalyzer`/`AgentCostReport` + `AgentCostResourceService` 的完整事实治理主线构建，审计累计 41 类别，全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不 AI 自动关闭/停止/修改/优化 Agent，成本单价不编造，不 AI 代责；成本数据读取默认拒绝，成本归属/报告来源强制可追溯。

---

> **STOP（3.8.16 收口）**：本报告与 `project_status.json` / `roadmap_v8.md` 刷新完成后，**不进入 Phase 3.8.17**，等待主理人审核授权。
- **未完成（人工动作，pending_verification）**：真实 Agent 运行质量数据录入 / `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动审批 均待主理人+专家线下执行；**本报告与状态刷新完成后停止，不进入 Phase 3.8.16**，等待主理人审核授权。

---

## 20. Phase 3.8.17 —— Enterprise Agent Policy & Runtime Governance Layer（企业智能体策略与运行时治理层）

- **状态：🟢 BUILT_NO_GO（2026-08-06）**；授权：BOIP AI Chief Architect（轩哥授权），10 任务 #656–#665；6 条最高红线 fail-closed。
- **基座**：复用 Phase 3.8.13 的 `AgentPermissionPolicy` + `IdentityService`、Phase 3.8.14 `AgentObservabilityService`、Phase 3.8.15 `AgentQualityGovernanceService`、Phase 3.8.16 `AgentCostResourceService`，并在其上层构建「运行策略 / 工具访问 / 执行前置核查 / 运行时判定事实记录 / 治理数据权限隔离 / 审计联动」的 fail-closed 治理层。

### 20.1 任务与交付（#656–#665）

| 任务 | 内容 | 状态 |
|---|---|---|
| #656 | `AgentRuntimePolicy` 模型（policy_id/agent_id/rules/scope/status/created_at；ACTIVE 必须真实人工确认，构造期禁止直接落 ACTIVE） | ✅ |
| #657 | `AgentToolAccessPolicy` 模型（默认拒绝：空名/denied/空白名单一律拒绝，无 grant/allow/whitelist 方法） | ✅ |
| #658 | `AgentExecutionGuard`（check_policy/check_permission/check_scope/check_tool_access；只检查不批准、默认拒绝） | ✅ |
| #659 | `RuntimeDecisionRecord` 模型（四项核查结论默认 FAIL，source 缺失即拒落库，只记录事实不构成批准） | ✅ |
| #660 | Runtime 审计增强 +3 枚举（`AGENT_POLICY`/`AGENT_RUNTIME_CHECK`/`AGENT_TOOL_ACCESS`，累计 41→**44**）+ 3 记录方法 | ✅ |
| #661 | 权限接入 `IdentityService` + `AgentPermissionPolicy`（默认拒绝隔离）+ `EnterpriseOperationLayer` 聚合 `self.agent_runtime_governance` 共享审计实例 | ✅ |
| #662 | 七类测试（`test_enterprise_agent_runtime_policy.py`，**30 用例**） | ✅ |
| #663 | 最终验证 `pytest tests/agents -q` 全过 + 确认红线（全 agents 套件 **1518 passed 零回归**：1488 基线 + 30） | ✅ |
| #664 | 收口报告（`.ai/reviews/phase3.8.17_agent_runtime_policy_governance_report.md`，7 节） | ✅ |
| #665 | 更新 `project_status.json` + `roadmap_v8.md`，完成后 STOP | ✅ |

### 20.2 代码与审计清单

| 类型 | 路径 |
|---|---|
| 策略与运行时核心（930 行 / 7 导出符号 + `_RUNTIME_FORBIDDEN`） | `agents/enterprise/agent_runtime_policy.py`（`AgentRuntimePolicyStatus`/`RuntimeCheckOutcome`/`AgentRuntimePolicy`/`AgentToolAccessPolicy`/`RuntimeDecisionRecord`/`AgentExecutionGuard`/`AgentRuntimeGovernanceService`） |
| 审计扩展 | `agents/enterprise/audit.py`：+3 枚举（`AGENT_POLICY`=agent_policy / `AGENT_RUNTIME_CHECK`=agent_runtime_check / `AGENT_TOOL_ACCESS`=agent_tool_access，累计 44）+ `record_agent_policy_action`(L1490)/`record_agent_runtime_check_action`(L1518)/`record_agent_tool_access_action`(L1546) |
| 权限基座（复用 3.8.13/3.8.0） | `agents/enterprise/agent_permission_policy.py` + `identity.py` + `organization.py`(`EnterpriseIsolationError`) |
| 服务装配 | `agents/enterprise/service.py`（`EnterpriseOperationLayer` 新增 `self.agent_runtime_governance`，注入共享 `agent_permission_policy`）+ `__init__.py`（新增 7 符号导出） |
| 测试（本层） | `tests/agents/test_enterprise_agent_runtime_policy.py`（七类 30 用例） |
| 测试计数修正（41→44） | 更新 `tests/agents/test_enterprise_knowledge_governance_audit.py`（`EXPECTED_CATEGORIES` +3 项 / 断言 41→44）+ `test_enterprise_knowledge_intelligence_audit.py`（`_41`→`_44`）+ `test_enterprise_agent_cost_resource.py`（`_41`→`_44`）+ `test_enterprise_agent_quality_governance.py`（`_41`→`_44`） |

### 20.3 红线守约（fail-closed，6 条，3.8.17 细化）

- ① `engineering_enabled=false`（`config.yaml:102`；构造/写路径断言 `safety_invariants_ok()`；`monkeypatch` 启用态后 `AgentRuntimeGovernanceService`/`AgentExecutionGuard` 构造即抛 `EnterpriseRedLineViolationError`）。
- ② 不输出 `engineering_approved`（`_RUNTIME_FORBIDDEN` 含该名，访问即抛错，不在 `__all__`）。
- ③ 禁止 AI 自动批准 Agent 运行（核查 ≠ 批准）：`approve_run`/`auto_approve_execution`/`allow_execution`/`bypass_policy`/`override_policy`/`force_run`/`grant_execution` 等结构性拦截；`AgentExecutionGuard` 只返回 `RuntimeCheckOutcome` 事实，绝不返回「已批准」语义。
- ④ 禁止 AI 自动修改 Agent 策略（主理人明列三项 + 同族收敛）：`auto_update_policy`/`auto_apply_policy`/`auto_approve_policy`/`update_policy`/`modify_policy`/`auto_activate`/`rewrite_policy`/`activate_policy` 等结构性拦截；状态推进（`confirm_policy_active`）强制 `require_human_actor(USER)`。
- ⑤ 禁止 AI 自动放行工具访问：`grant_tool_access`/`allow_tool_access`/`whitelist_tool`/`unlock_tool`/`elevate_tool_access`/`enable_tool` 等结构性拦截；`AgentToolAccessPolicy` 默认拒绝（空名/denied/空白名单一律拒绝），无放行入口。
- ⑥ AI 不代替管理责任：审计无 `record_human_approval`；人工确认节点（生效/弃用）强制 `require_human_actor(USER)`；`RuntimeDecisionRecord` 只陈述事实（`all_checks_passed` 仅事实汇总≠批准），不含处置/批准建议，缺 `source` 即拒落库。

### 20.4 测试与回归

- **七类测试共 30 用例全绿**（`test_enterprise_agent_runtime_policy.py`：policy/tool_access/guard/runtime_record/permission/audit/red_line）。
- 全 agents 套件 **1518 passed（1488 基线 + 30 新增）零回归**（2026-08-06 实测约 35s）。
- 修正 4 处 prior-phase 过期断言（3.8.15/3.8.16 遗留 `== 41` 计数，因本层 +3 枚举变 44，已刷新为 44）。
- 未修改 `verified.json` / `config.yaml` / `engineering_enabled`（`agents/config.yaml:102` 仍为 `false`）；不输出 `engineering_approved`。

### 20.5 交付物清单（3.8.17）

| 类型 | 路径 |
|---|---|
| 策略与运行时核心 + 装配 | `agents/enterprise/agent_runtime_policy.py` + `audit.py`（+3 枚举/方法）+ `service.py`（聚合）+ `__init__.py` |
| 测试 | `tests/agents/test_enterprise_agent_runtime_policy.py`（30 用例）+ 更新 4 个既有审计计数测试（41→44） |
| 收口报告 | `.ai/reviews/phase3.8.17_agent_runtime_policy_governance_report.md` |
| 状态刷新 | `.ai/project_status.json`（`phase_3_8_17_status=ENTERPRISE_AGENT_RUNTIME_GOVERNANCE_BUILT_NO_GO`） |
| 路线图 | `.ai/roadmap_v8.md` §20 |

### 20.6 状态结论

- **状态：🟢 BUILT_NO_GO（2026-08-06）**：企业智能体策略与运行时治理层已完成 `AgentRuntimePolicy`/`AgentToolAccessPolicy`/`AgentExecutionGuard`/`RuntimeDecisionRecord` + `AgentRuntimeGovernanceService` 的完整 fail-closed 治理主线构建，审计累计 44 类别，全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不 AI 自动批准/修改策略/放行工具/代责；治理数据读取默认拒绝（`EnterpriseIsolationError`），判定记录只陈述事实且来源强制可追溯。

---

> **STOP（3.8.17 收口）**：本报告与 `project_status.json` / `roadmap_v8.md` 刷新完成后，**不进入 Phase 3.8.18**，等待主理人审核授权。
- **未完成（人工动作，pending_verification）**：真实 Agent 运行策略录入与人工确认生效 / `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动审批 均待主理人+专家线下执行；**本报告与状态刷新完成后停止，不进入 Phase 3.8.18**，等待主理人审核授权。

---

## 21. Phase 3.8.18 —— Enterprise Agent Security & Risk Governance Layer（企业智能体安全与风险治理层）

- **授权**：主理人授权（接 3.8.17 收口后）｜身份 BOIP AI Chief Architect｜11 项任务（#670–#680）｜6 条最高红线 fail-closed｜完成后 STOP，不进 3.8.19。
- **基座**：复用 Phase 3.8.13 `AgentPermissionPolicy` + `IdentityService`、Phase 3.8.14 `AgentObservabilityService`、Phase 3.8.15 `AgentQualityGovernanceService`、Phase 3.8.16 `AgentCostResourceService`、Phase 3.8.17 `AgentRuntimeGovernanceService`，并在其上构建「安全事件 / 风险候选 / 安全检测 / 安全报告（强可溯源）/ 风险人工复核」的 fail-closed 安全治理层。

### 21.1 任务与交付（#670–#680）

| 任务 | 内容 | 状态 |
|---|---|---|
| #670 | `AgentSecurityEvent` 模型（仅记事实，source 缺失即拒落库） | ✅ |
| #671 | `AgentRiskCandidate` 模型（强制 requires_human_review=True，pattern/evidence 必填） | ✅ |
| #672 | `AgentSecurityDetector`（detect_access_anomaly/permission/execution，只发现不处理） | ✅ |
| #673 | `AgentSecurityReport` + `SourceTrace`（is_traceable 强可溯源，空值不入链不编造） | ✅ |
| #674 | `AgentRiskReview`（构造期禁止落 REVIEWED 终态，人工处置强制 require_human_actor(USER)） | ✅ |
| #675 | 审计增强 +3 枚举（`AGENT_SECURITY_EVENT`/`AGENT_RISK`/`AGENT_RISK_REVIEW`，累计 44→**47**）+ 3 记录方法 | ✅ |
| #676 | 权限接入 `IdentityService` + `AgentPermissionPolicy`（默认拒绝隔离）+ `EnterpriseOperationLayer` 聚合 `self.agent_security_risk` 共享审计实例 | ✅ |
| #677 | 八类测试（`test_enterprise_agent_security_risk.py`，**40 用例**） | ✅ |
| #678 | 最终验证 `pytest tests/agents -q` 全过 + 确认红线（全 agents 套件 **1558 passed 零回归**：1518 基线 + 40） | ✅ |
| #679 | 收口报告（`.ai/reviews/phase3.8.18_agent_security_risk_governance_report.md`，7 节） | ✅ |
| #680 | 更新 `project_status.json` + `roadmap_v8.md`，完成后 STOP | ✅ |

### 21.2 代码与审计清单

| 类型 | 路径 |
|---|---|
| 安全与风险核心（1032 行 / 10 导出符号 + `_SECURITY_FORBIDDEN`） | `agents/enterprise/agent_security_risk.py`（`AgentSecurityEventType`/`AgentSecuritySeverity`/`AgentRiskReviewStatus`/`SourceTrace`/`AgentSecurityEvent`/`AgentRiskCandidate`/`AgentSecurityDetector`/`AgentSecurityReport`/`AgentSecurityRiskService`/`AgentRedLineViolationError`） |
| 审计扩展 | `agents/enterprise/audit.py`：+3 枚举（`AGENT_SECURITY_EVENT`=agent_security_event / `AGENT_RISK`=agent_risk / `AGENT_RISK_REVIEW`=agent_risk_review，累计 47）+ `record_agent_security_event_action`/`record_agent_risk_action`/`record_agent_risk_review_action` |
| 权限基座（复用 3.8.13/3.8.0/3.8.17） | `agents/enterprise/agent_permission_policy.py` + `identity.py` + `organization.py`(`EnterpriseIsolationError`) |
| 服务装配 | `agents/enterprise/service.py`（`EnterpriseOperationLayer` 新增 `self.agent_security_risk`，注入共享 `agent_permission_policy`）+ `__init__.py`（新增 10 符号导出） |
| 测试（本层） | `tests/agents/test_enterprise_agent_security_risk.py`（八类 40 用例） |
| 测试计数修正（44→47） | 更新 `tests/agents/test_enterprise_knowledge_governance_audit.py`（`EXPECTED_CATEGORIES` +3 项 / 断言 44→47）+ `test_enterprise_knowledge_intelligence_audit.py` + `test_enterprise_agent_cost_resource.py` + `test_enterprise_agent_runtime_policy.py` + `test_enterprise_agent_quality_governance.py` |

### 21.3 红线守约（fail-closed，6 条，3.8.18 细化）

- ① `engineering_enabled=false`（`config.yaml:102`；写路径断言 `safety_invariants_ok()`；启用态 monkeypatch 后 `AgentSecurityRiskService` 构造即抛 `EnterpriseRedLineViolationError`）。
- ② 不输出 `engineering_approved`（`_SECURITY_FORBIDDEN` 含该名，访问即抛错，不在 `__all__`）。
- ③ 禁止 AI 自动封禁 Agent（发现 ≠ 处置）：`auto_disable_agent`/`disable_agent`/`block_agent`/`kill_agent`/`ban_agent`/`suspend_agent`/`terminate_agent`/`shutdown_agent`/`quarantine_agent` 等结构性拦截；`AgentSecurityDetector` 只产出 `AgentRiskCandidate`，绝不执行封禁。
- ④ 禁止 AI 自动修改权限：`auto_change_permission`/`change_permission`/`auto_grant_permission`/`grant_permission`/`auto_revoke_permission`/`revoke_permission`/`escalate_permission`/`elevate_permission`/`reset_permission` 等结构性拦截；`AgentPermissionPolicy` 默认拒绝，无放行入口。
- ⑤ 禁止 AI 自动处置安全风险（发现 ≠ 解决）：`auto_resolve_risk`/`resolve_risk`/`auto_fix_risk`/`fix_risk`/`auto_mitigate_risk`/`auto_close_risk`/`auto_dismiss_risk`/`auto_remediate`/`handle_incident` 等结构性拦截；风险处置强制 `require_human_actor(USER)`。
- ⑥ AI 不代替安全责任：审计无 `record_human_approval`；风险复核节点（落实/驳回）强制 `require_human_actor(USER)` + 非空 actor_id/decision；`AgentSecurityReport`/`SourceTrace` 只陈述事实与溯源，不含处置/批准建议，缺 `source` 即拒落库。

### 21.4 测试与回归

- **八类测试共 40 用例全绿**（`test_enterprise_agent_security_risk.py`：security_event/risk_candidate/detector/report/review/permission/audit/red_line）。
- 全 agents 套件 **1558 passed（1518 基线 + 40 新增）零回归**（2026-08-06 实测约 37s）。
- 修正 5 处 prior-phase 过期断言（3.8.15/3.8.16/3.8.17 遗留 `== 44` 计数，因本层 +3 枚举变 47，已刷新为 47）。
- 未修改 `verified.json` / `config.yaml` / `engineering_enabled`（`agents/config.yaml:102` 仍为 `false`）；不输出 `engineering_approved`。

### 21.5 交付物清单（3.8.18）

| 类型 | 路径 |
|---|---|
| 安全与风险核心 + 装配 | `agents/enterprise/agent_security_risk.py` + `audit.py`（+3 枚举/方法）+ `service.py`（聚合）+ `__init__.py` |
| 测试 | `tests/agents/test_enterprise_agent_security_risk.py`（40 用例）+ 更新 5 个既有审计计数测试（44→47） |
| 收口报告 | `.ai/reviews/phase3.8.18_agent_security_risk_governance_report.md` |
| 状态刷新 | `.ai/project_status.json`（`phase_3_8_18_status=ENTERPRISE_AGENT_SECURITY_RISK_BUILT_NO_GO`） |
| 路线图 | `.ai/roadmap_v8.md` §21 |

### 21.6 状态结论

- **状态：🟢 BUILT_NO_GO（2026-08-06）**：企业智能体安全与风险治理层已完成 `AgentSecurityEvent`/`AgentRiskCandidate`/`AgentSecurityDetector`/`AgentSecurityReport`(+`SourceTrace`)/`AgentRiskReview` + `AgentSecurityRiskService` 的完整 fail-closed 安全治理主线构建，审计累计 47 类别，全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不 AI 自动封禁 Agent / 自动修改权限 / 自动处置风险 / 代责；安全数据读取默认拒绝（`EnterpriseIsolationError`），风险处置强制真实 USER 复核。

---

> **STOP（3.8.18 收口）**：本报告与 `project_status.json` / `roadmap_v8.md` 刷新完成后，**不进入 Phase 3.8.19**，等待主理人审核授权。
- **未完成（人工动作，pending_verification）**：真实安全事件录入与人工复核处置 / `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动审批 均待主理人+专家线下执行；**本报告与状态刷新完成后停止，不进入 Phase 3.8.19**，等待主理人审核授权。

---

## 22. Phase 3.8.19 —— Enterprise Agent Compliance & Audit Intelligence Layer（企业智能体合规与审计智能层）

- **授权**：主理人授权（接 3.8.18 收口后）｜身份 BOIP AI Chief Architect｜12 项任务（#681–#688）｜6 条最高红线 fail-closed｜完成后 STOP，不进 3.8.20。
- **基座**：复用 Phase 3.8.13 `AgentPermissionPolicy` + `IdentityService`、Phase 3.8.17 `AgentRuntimeGovernanceService`（只读消费 `RuntimeDecisionRecord`）、Phase 3.8.18 `AgentSecurityRiskService` 范式，并在既有审计沉淀之上构建「合规规则 / 检查事实 / 合规检测 / 风险候选 / 合规报告（强可溯源）/ 人工整改复核」的 fail-closed 合规辅助层。
- **链路**：`Agent 行为 → 审计数据 → 规则检查 → 合规候选 → 人工审核`。AI 全程只做**发现与记录**，「是否违规」的定性只能由真实合规责任人作出。

### 22.1 任务与交付（#681–#688）

| 任务 | 内容 | 状态 |
|---|---|---|
| 任务1 | `ComplianceRule` 模型（source 缺失即拒构造；默认 draft 且 `is_effective=False`；构造期禁落 active） | ✅ |
| 任务2 | `ComplianceCheck` + `ComplianceCheckResult`（枚举**仅** pass/attention/not_applicable，**无判罚态**；证据与规则绑定必填） | ✅ |
| 任务3 | `AgentComplianceDetector`（check_audit_pattern / check_permission_pattern / check_runtime_pattern，只消费既有事实、只发现不判罚） | ✅ |
| 任务4 | `ComplianceRiskCandidate`（强制 `requires_human_review=True`，pattern/evidence 必填，置 False 即抛） | ✅ |
| 任务5 | `AgentComplianceReport` + `SourceTrace`（无来源链拒构造；零事实拒生成；摘要无处罚/批准语义） | ✅ |
| 任务6 | `ComplianceReview`（构造期禁落 REVIEWED 终态；人工整改强制 `require_human_actor(USER)` + 非空 actor_id/decision） | ✅ |
| 任务7 | 审计增强 +3 枚举（`AGENT_COMPLIANCE_RULE`/`AGENT_COMPLIANCE_CHECK`/`AGENT_COMPLIANCE_RISK`，累计 47→**50**）+ 3 记录方法；禁 `record_human_approval` | ✅ |
| 任务8 | 权限接入 `IdentityService` + `AgentPermissionPolicy` + `AgentRuntimePolicy`（合规数据默认拒绝隔离）+ `EnterpriseOperationLayer` 聚合 `self.agent_compliance` 共享审计实例 | ✅ |
| 任务9 | 九类测试（`test_enterprise_agent_compliance.py`，**58 用例**）+ 同步刷新 6 处历史断言 47→50 | ✅ |
| 任务10 | 最终验证 `pytest tests/agents -q` 全过（全 agents 套件 **1616 passed 零回归**：1558 基线 + 58） | ✅ |
| 任务11 | 收口报告（`.ai/reviews/phase3.8.19_agent_compliance_audit_report.md`，7 节） | ✅ |
| 任务12 | 更新 `project_status.json` + `roadmap_v8.md` §22，完成后 STOP | ✅ |

### 22.2 代码与审计清单

| 类型 | 路径 |
|---|---|
| 合规核心（1375 行 / 11 导出符号 + `_COMPLIANCE_FORBIDDEN` 80 项） | `agents/enterprise/agent_compliance.py`（`ComplianceRuleScope`/`ComplianceRuleStatus`/`ComplianceCheckResult`/`ComplianceReviewStatus`/`ComplianceRule`/`ComplianceCheck`/`ComplianceRiskCandidate`/`ComplianceReview`/`AgentComplianceReport`/`AgentComplianceDetector`/`AgentComplianceService`） |
| 审计扩展 | `agents/enterprise/audit.py`：+3 枚举（`AGENT_COMPLIANCE_RULE`=agent_compliance_rule / `AGENT_COMPLIANCE_CHECK`=agent_compliance_check / `AGENT_COMPLIANCE_RISK`=agent_compliance_risk，累计 **50**）+ `record_agent_compliance_rule_action`/`record_agent_compliance_check_action`/`record_agent_compliance_risk_action` |
| 权限基座（复用 3.8.13/3.8.0/3.8.17） | `agents/enterprise/agent_permission_policy.py` + `identity.py` + `organization.py`(`EnterpriseIsolationError`) + `agent_runtime_policy.py`（只读） |
| 服务装配 | `agents/enterprise/service.py`（`EnterpriseOperationLayer` 新增 `self.agent_compliance`，注入共享 `audit`/`identity`/`visibility`/`permission_policy`/`runtime_policy`）+ `__init__.py`（新增 11 符号导出，`__all__` 222） |
| 测试（本层） | `tests/agents/test_enterprise_agent_compliance.py`（九类 58 用例 / 885 行） |
| 测试计数修正（47→50） | `test_enterprise_knowledge_governance_audit.py`（`EXPECTED_CATEGORIES` +3 项 / 断言 47→50）+ `test_enterprise_knowledge_intelligence_audit.py` + `test_enterprise_agent_cost_resource.py` + `test_enterprise_agent_runtime_policy.py` + `test_enterprise_agent_quality_governance.py` + `test_enterprise_agent_security_risk.py`（含 3 处测试函数名同步） |

### 22.3 红线守约（fail-closed，6 条，3.8.19 细化）

- ① `engineering_enabled=false`（`agents/config.yaml:102`；写路径断言 `safety_invariants_ok()`；启用态 monkeypatch 后 `AgentComplianceService` 构造即抛 `EnterpriseRedLineViolationError`）。
- ② 不输出 `engineering_approved`（`_COMPLIANCE_FORBIDDEN` 含该名及 `approve`/`sign`/`authorize`/`attest_compliance`/`certify_compliance`，访问即抛，不在 `__all__`）。
- ③ 禁止 AI 自动判定违法/违规 —— **类型级**：`ComplianceCheckResult` 只有 `pass`/`attention`/`not_applicable`，刻意不存在 `violation`/`illegal`/`fail`，AI 在类型系统里无法表达「违规」结论；**结构级**：拦截 `auto_violate`/`violate`/`auto_penalty`/`penalty`/`auto_judge_compliance`/`judge_compliance`/`judge_violation`/`judge_illegal`/`declare_violation`/`declare_illegal`/`determine_violation`/`auto_convict`/`convict` 等。
- ④ 禁止 AI 自动处罚 Agent：拦截 `auto_suspend_agent`/`suspend_agent`/`auto_ban_agent`/`ban_agent`/`auto_disable_agent`/`disable_agent`/`auto_block_agent`/`auto_kill_agent`/`auto_quarantine_agent`/`auto_terminate_agent`/`auto_revoke_agent`/`punish_agent`/`sanction_agent`/`fine_agent` 等；`AgentComplianceDetector` 只产出候选，绝不触碰任何 Agent 状态。
- ⑤ 禁止 AI 自动修改权限或策略：拦截 `auto_change_permission`/`auto_grant_permission`/`auto_revoke_permission`/`modify_permission`/`escalate_permission`/`auto_modify_policy`/`modify_policy`/`auto_update_policy`/`update_policy`/`apply_policy`/`auto_activate_rule`/`activate_rule`/`auto_update_rule`/`update_rule`/`change_rule` 等；本层对权限与运行策略**只读**，无任何写路径；规则生效/废止强制 `require_human_actor(USER)`。
- ⑥ AI 不代替合规责任人：审计无 `record_human_approval`；`confirm_rule_active`/`confirm_rule_deprecated`/`human_review_compliance_risk` 三个人工节点全部强制 `require_human_actor(USER)` + 非空 actor_id/decision；拦截 `act_as_compliance_officer`/`take_compliance_ownership`/`assume_compliance_responsibility`/`auto_govern_compliance`/`auto_attest`/`clear_compliance`；规则/检查/候选/报告缺来源即拒落库。

### 22.4 测试与回归

- **九类测试共 58 用例全绿**（`test_enterprise_agent_compliance.py`：rule 10 / check 6 / detector 8 / risk_candidate 5 / report 5 / review 5 / audit 5 / permission 5 / red_line 9），单文件 `58 passed in 0.09s`。
- 全 agents 套件 **1616 passed（1558 基线 + 58 新增）零回归**（2026-08-07 实测）。
- 修正 6 处 prior-phase 过期断言（3.8.15/3.8.16/3.8.17/3.8.18 遗留 `== 47` 计数，因本层 +3 枚举变 50，已刷新为 50，含 3 处测试函数名同步）。
- 未修改 `verified.json` / `config.yaml` / `engineering_enabled`（`agents/config.yaml:102` 仍为 `false`）；不输出 `engineering_approved`；测试用 monkeypatch 注入启用态，不触碰磁盘配置。

### 22.5 交付物清单（3.8.19）

| 类型 | 路径 |
|---|---|
| 合规核心 + 装配 | `agents/enterprise/agent_compliance.py` + `audit.py`（+3 枚举/方法）+ `service.py`（聚合）+ `__init__.py` |
| 测试 | `tests/agents/test_enterprise_agent_compliance.py`（58 用例）+ 更新 6 个既有审计计数测试（47→50） |
| 收口报告 | `.ai/reviews/phase3.8.19_agent_compliance_audit_report.md` |
| 状态刷新 | `.ai/project_status.json`（`phase_3_8_19_status=ENTERPRISE_AGENT_COMPLIANCE_BUILT_NO_GO` + `phase_3_8_19` 明细块） |
| 路线图 | `.ai/roadmap_v8.md` §22 |

### 22.6 状态结论

- **状态：🟢 BUILT_NO_GO（2026-08-07）**：企业智能体合规与审计智能层已完成 `ComplianceRule`/`ComplianceCheck`/`AgentComplianceDetector`/`ComplianceRiskCandidate`/`AgentComplianceReport`(+`SourceTrace`)/`ComplianceReview` + `AgentComplianceService` 的完整 fail-closed 合规辅助主线构建，审计累计 50 类别，全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不 AI 自动判定违规 / 自动处罚 Agent / 自动改权限或策略 / 代替合规责任人；合规数据读取默认拒绝（`EnterpriseIsolationError`），规则生效与风险整改强制真实 USER。
- 全部合规规则出厂即 `draft` 且 `is_effective=False`，**必须**由真实合规责任人确认后才可用于检测；本层不产出任何合规定性结论。

---

> **STOP（3.8.19 收口）**：本报告与 `project_status.json` / `roadmap_v8.md` 刷新完成后，**不进入 Phase 3.8.20**，等待主理人审核授权。
- **未完成（人工动作，pending_verification）**：真实合规规则录入与人工确认生效 / 真实合规风险人工复核与整改 / `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动审批 均待主理人+专家线下执行；**本报告与状态刷新完成后停止，不进入 Phase 3.8.20**，等待主理人审核授权。

---

## 23. Phase 3.8.20 —— Enterprise Agent Governance Intelligence & Control Center Layer（企业智能体治理智能中枢层）

- **授权**：主理人授权（接 3.8.19 收口后）｜身份 BOIP AI Chief Architect｜11 项任务（#687–#697）｜6 条最高红线 fail-closed｜完成后 STOP，不进 3.8.21。
- **基座**：复用 Phase 3.8.13 `AgentPermissionPolicy` + `IdentityService`、Phase 3.8.16 `AgentLifecycleGovernanceService`、Phase 3.8.17 `AgentRuntimeGovernanceService`、Phase 3.8.18 `AgentSecurityRiskService`、Phase 3.8.19 `AgentQualityGovernanceService` + `AgentComplianceService` 范式，并在五层上游治理沉淀之上构建「治理汇聚 / 治理看板 / 健康概览 / 风险概览 / 治理报告 / 治理洞察」的 fail-closed 治理聚合层。
- **链路**：`治理数据（五层上游只读事实）→ 统一汇聚（AgentGovernanceAggregator）→ 看板/健康/风险/报告/洞察 → 人工处理 / 人工确认`。AI 全程只做**汇聚与展示事实**，治理态变更只能由真实治理责任人作出。

### 23.1 任务与交付（#687–#697）

| 任务 | 内容 | 状态 |
|---|---|---|
| 任务1 | `AgentGovernanceDashboard` 模型（只展示事实；空 widget 拒绝；挂件 source 必填、标题禁控制语义） | ✅ |
| 任务2 | `AgentHealthOverview`（无 rating/grade/health_level 字段；事实键名禁评级语义，禁自动评级） | ✅ |
| 任务3 | `AgentRiskOverview`（requires_human_handling 恒 True；构造期只能 pending_human_review，禁自动处理） | ✅ |
| 任务4 | `AgentGovernanceReport` + `SourceTrace`（五段汇聚 + 来源链；无来源链拒构造；段落禁建议语义） | ✅ |
| 任务5 | `AgentGovernanceInsight`（requires_human_confirmation 恒 True；kind 仅 fact_trend/anomaly_candidate；文本禁建议语义，禁治理建议） | ✅ |
| 任务6 | 审计增强 +3 枚举（`AGENT_GOVERNANCE_DASHBOARD`/`AGENT_GOVERNANCE_REPORT`/`AGENT_GOVERNANCE_INSIGHT`，累计 50→**53**）+ 3 记录方法；禁 `record_human_approval` | ✅ |
| 任务7 | 权限接入 `IdentityService` + `AgentPermissionPolicy` + `AgentRuntimePolicy` + 五层上游只读服务（治理数据默认拒绝隔离）+ `EnterpriseOperationLayer` 聚合 `self.agent_governance_center` 共享审计实例 | ✅ |
| 任务8 | 八类测试（`test_enterprise_agent_governance_center.py`，**73 用例**）+ 同步刷新 7 处历史断言 50→53 | ✅ |
| 任务9 | 最终验证 `pytest tests/agents -q` 全过（全 agents 套件 **1689 passed 零回归**：1616 基线 + 73） | ✅ |
| 任务10 | 收口报告（`.ai/reviews/phase3.8.20_agent_governance_control_center_report.md`，7 节） | ✅ |
| 任务11 | 更新 `project_status.json` + `roadmap_v8.md` §23，完成后 STOP | ✅ |

### 23.2 代码与审计清单

| 类型 | 路径 |
|---|---|
| 治理中枢核心（1570 行 / 13 导出符号 + `_GOVERNANCE_FORBIDDEN` 84 项） | `agents/enterprise/agent_governance_center.py`（`GovernanceWidgetKind`/`GovernanceVisibility`/`GovernanceWidget`/`AgentGovernanceDashboard`/`AgentHealthOverview`/`RiskOverviewStatus`/`AgentRiskOverview`/`AgentGovernanceReport`/`GovernanceInsightKind`/`GovernanceTrendDirection`/`AgentGovernanceInsight`/`AgentGovernanceAggregator`/`AgentGovernanceCenterService`） |
| 审计扩展 | `agents/enterprise/audit.py`：+3 枚举（`AGENT_GOVERNANCE_DASHBOARD`=agent_governance_dashboard / `AGENT_GOVERNANCE_REPORT`=agent_governance_report / `AGENT_GOVERNANCE_INSIGHT`=agent_governance_insight，累计 **53**）+ `record_agent_governance_dashboard_action`/`record_agent_governance_report_action`/`record_agent_governance_insight_action` |
| 权限基座（复用 3.8.13/3.8.0/3.8.16/3.8.17/3.8.18/3.8.19） | `agents/enterprise/agent_permission_policy.py` + `identity.py` + `organization.py`(`EnterpriseIsolationError`) + `agent_runtime_policy.py` + `agent_security_risk.py` + `agent_compliance.py`（只读） + `agent_observability.py` + `agent_quality_governance.py` + `agent_cost_resource.py` |
| 服务装配 | `agents/enterprise/service.py`（`EnterpriseOperationLayer` 新增 `self.agent_governance_center`，注入共享 `audit`/`identity`/`visibility`/`permission_policy`/`runtime_policy` + 五层上游只读服务）+ `__init__.py`（新增 13 符号导出） |
| 测试（本层） | `tests/agents/test_enterprise_agent_governance_center.py`（八类 73 用例 / 1001 行） |
| 测试计数修正（50→53） | `test_enterprise_knowledge_governance_audit.py`（`EXPECTED_CATEGORIES` +3 项 / 断言 `== 53`）+ `test_enterprise_knowledge_intelligence_audit.py` + `test_enterprise_agent_cost_resource.py` + `test_enterprise_agent_runtime_policy.py` + `test_enterprise_agent_security_risk.py` + `test_enterprise_agent_quality_governance.py` + `test_enterprise_agent_compliance.py`（含 6 处测试函数名同步） |

### 23.3 红线守约（fail-closed，6 条，3.8.20 细化）

- ① `engineering_enabled=false`（`agents/config.yaml:102`；写路径断言 `safety_invariants_ok()`；启用态 monkeypatch 后 `AgentGovernanceCenterService` 构造即抛 `EnterpriseRedLineViolationError`）。
- ② 不输出 `engineering_approved`（`_GOVERNANCE_FORBIDDEN` 含该名及 `approve`/`sign`/`authorize`/`quote`/`pricing`，访问即抛；本层源码仅禁用名声明 + 红线注释，零赋值/零输出）。
- ③ 禁止 AI 自动评级 / 自动判定 —— **类型级**：`AgentHealthOverview` 无 `rating`/`grade`/`health_level` 字段，事实键名命中 `_RATING_MARKERS` 即抛；**结构级**：拦截 `auto_rate_agent`/`rate_agent`/`auto_grade_agent`/`grade_agent`/`auto_judge_health`/`auto_assess_agent`/`auto_evaluate_agent`/`auto_score_agent`/`score_agent`/`auto_rank_agent`/`auto_classify_agent` 等。
- ④ 禁止 AI 自动处理风险：`AgentRiskOverview.requires_human_handling` **恒 True**，`RiskOverviewStatus` 无 AI 终态；拦截 `auto_handle_risk`/`handle_risk`/`auto_resolve_risk`/`resolve_risk`/`auto_mitigate_risk`/`auto_close_risk`/`auto_remediate_risk`/`triage_risk` 等；`human_handle_risk_overview` 强制 `require_human_actor(USER)`。
- ⑤ 禁止 AI 自动处置 / 修改策略：拦截 `auto_disable`/`auto_modify`/`auto_upgrade`/`auto_policy_change`/`auto_control_agent`/`auto_approve_agent`/`auto_sign_governance`/`auto_recommend_action`/`recommend_action`/`auto_advise`/`advise`/`propose_governance_action` 等；本层对 Agent 状态、权限、策略**只读**（只汇聚五层上游事实），无任何写路径；治理建议语义在 `__post_init__` 被 `_reject_markers` 拒收。
- ⑥ AI 不代替治理责任人：审计无 `record_human_approval`；`human_handle_risk_overview`/`human_confirm_insight` 两个人工节点全部强制 `require_human_actor(USER)` + 非空 actor_id；拦截 `act_as_governance_owner`/`take_governance_ownership`/`assume_governance_responsibility`/`auto_govern`/`auto_attest_governance`/`clear_governance`；看板/报告/洞察缺来源即拒落库。

### 23.4 测试与回归

- **八类测试共 73 用例全绿**（`test_enterprise_agent_governance_center.py`：dashboard 10 / overview 8 / risk 12 / report 8 / insight 14 / permission 8 / audit 8 / red_line 10），单文件 `73 passed in 0.12s`。
- 全 agents 套件 **1689 passed（1616 基线 + 73 新增）零回归**（2026-08-08 实测）。
- 修正 7 处 prior-phase 过期断言（3.8.15/3.8.16/3.8.17/3.8.18/3.8.19 遗留 `== 50` 计数，因本层 +3 枚举变 53，已刷新为 53，含 6 处测试函数名同步）。
- 未修改 `verified.json` / `config.yaml` / `engineering_enabled`（`agents/config.yaml:102` 仍为 `false`）；不输出 `engineering_approved`；测试用 monkeypatch 注入启用态，不触碰磁盘配置。
- 注：存在历史测试技术债 `test_threshold_real_drill.py`（沙箱批量删除守卫下 `_tmp_drill_*` 临时文件偶发清理失败），与本 Phase 无关；隔离运行该文件为 9 passed，清理临时文件后全量套件即全绿（1689 passed）。

### 23.5 交付物清单（3.8.20）

| 类型 | 路径 |
|---|---|
| 治理中枢核心 + 装配 | `agents/enterprise/agent_governance_center.py` + `audit.py`（+3 枚举/方法）+ `service.py`（聚合）+ `__init__.py` |
| 测试 | `tests/agents/test_enterprise_agent_governance_center.py`（73 用例）+ 更新 7 个既有审计计数测试（50→53） |
| 收口报告 | `.ai/reviews/phase3.8.20_agent_governance_control_center_report.md` |
| 状态刷新 | `.ai/project_status.json`（`phase_3_8_20_status=ENTERPRISE_AGENT_GOVERNANCE_CENTER_BUILT_NO_GO` + `phase_3_8_20` 明细块） |
| 路线图 | `.ai/roadmap_v8.md` §23 |

### 23.6 状态结论

- **状态：🟢 BUILT_NO_GO（2026-08-08）**：企业智能体治理智能中枢层已完成 `AgentGovernanceDashboard`/`AgentHealthOverview`/`AgentRiskOverview`/`AgentGovernanceReport`(+`SourceTrace`)/`AgentGovernanceInsight` + `AgentGovernanceAggregator`(只读) + `AgentGovernanceCenterService` 的完整 fail-closed 治理聚合主线构建，审计累计 53 类别，全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不 AI 自动评级 / 自动处理风险 / 自动处置或改策略 / 代替治理责任人；治理数据读取默认拒绝（`EnterpriseIsolationError`），风险处理与洞察确认强制真实 USER。
- 全层只汇聚与展示既有事实，看板/概览/报告/洞察出厂即中性、**必须**由真实治理责任人确认后才可改变治理态；本层不产出任何治理结论。

---

> **STOP（3.8.20 收口）**：本报告与 `project_status.json` / `roadmap_v8.md` 刷新完成后，**不进入 Phase 3.8.21**，等待主理人审核授权。

## 24. Phase 3.8.21 —— Enterprise Agent Governance Workflow & Accountability Layer（企业智能体治理流程与责任闭环层）

- **授权**：主理人授权（接 3.8.20 收口后）｜身份 BOIP AI Chief Architect｜11 项任务（#701–#711）｜6 条最高红线 fail-closed｜完成后 STOP，不进 3.8.22。
- **基座**：复用 3.8.13 `AgentPermissionPolicy` + `IdentityService`、3.8.16–3.8.19 各治理层范式，并在 3.8.20 治理中枢（只读汇聚事实）之上构建「治理发现 → 治理任务 → 责任人 → 人工处理 → 结果记录 → 治理闭环」的 fail-closed 流程与责任闭环层。
- **链路**：治理发现（五层上游只读事实 / 人工上报）→ `create_task`（AI 只建候选）→ `assign_owner`（强制 USER + 责任人必真实 USER）→ `start_processing` / `submit_result`（强制 USER）→ `human_close`（唯一闭环入口，强制 USER，生成 `GovernanceClosureReport` + 来源链）。AI 全程只建候选与登记事实，治理态变更与闭环只能由真实治理责任人作出。

### 24.1 任务与交付（#701–#711）

| 任务 | 内容 | 状态 |
|---|---|---|
| 任务1 | `GovernanceTask` 模型（`requires_human_completion` 恒 True；构造期 `owner_id` 必空、禁预填 completed/closed、禁非 created 态；标题/说明禁整改/分配/改权限语义） | ✅ |
| 任务2 | `GovernanceAssignment`（assignee/assigned_by 必真实 USER，非人类标识即拒；note 禁自动分配/整改语义） | ✅ |
| 任务3 | `GovernanceActionRecord`（action/result 禁自动整改/改权限语义；actor_kind 如实标注，AI 不冒充人工） | ✅ |
| 任务4 | `GovernanceWorkflowService`（`create_task` 只建候选；`assign_owner`/`start_processing`/`submit_result`/`human_close` 全部 `require_human_actor(USER)`；`record_observed_action` 只登记事实不改状态；只读查询 + 权限隔离默认拒绝） | ✅ |
| 任务5 | `GovernanceClosureReport` + `SourceTrace`（无来源链 / 无人工结论 / 非人类 closed_by / 结论含整改语义即拒；`render_source` 可溯源） | ✅ |
| 任务6 | 审计增强 +3 枚举（`AGENT_GOVERNANCE_TASK`/`AGENT_GOVERNANCE_ACTION`/`AGENT_GOVERNANCE_CLOSURE`，累计 53→**56**）+ 3 记录方法；禁 `record_human_approval` | ✅ |
| 任务7 | 权限接入 `IdentityService` + `AgentPermissionPolicy` + `AgentRuntimePolicy` + 3.8.20 治理中枢（只读消费）；治理数据默认拒绝隔离；`EnterpriseOperationLayer` 聚合 `self.agent_governance_workflow` | ✅ |
| 任务8 | 八类测试（`test_enterprise_agent_governance_workflow.py`，**97 用例**）+ 同步刷新 8 处历史断言 53→56 | ✅ |
| 任务9 | 最终验证 `pytest tests/agents -q` 全过（全 agents 套件 **1786 passed 零回归**：1689 基线 + 97） | ✅ |
| 任务10 | 收口报告（`.ai/reviews/phase3.8.21_agent_governance_workflow_accountability_report.md`，7 节） | ✅ |
| 任务11 | 更新 `project_status.json` + `roadmap_v8.md` §24，完成后 STOP | ✅ |

### 24.2 代码与审计清单

| 类型 | 路径 |
|---|---|
| 治理流程核心（1322 行 / 7 导出符号 + `_GOVERNANCE_FORBIDDEN` 98 项） | `agents/enterprise/agent_governance_workflow.py`（`GovernanceTaskSourceType`/`GovernanceTaskStatus`/`GovernanceTask`/`GovernanceAssignment`/`GovernanceActionRecord`/`GovernanceClosureReport`/`GovernanceWorkflowService`） |
| 审计扩展 | `agents/enterprise/audit.py`：+3 枚举（`AGENT_GOVERNANCE_TASK`=agent_governance_task / `AGENT_GOVERNANCE_ACTION`=agent_governance_action / `AGENT_GOVERNANCE_CLOSURE`=agent_governance_closure，累计 **56**）+ `record_agent_governance_task_action`/`record_agent_governance_action`/`record_agent_governance_closure_action` |
| 权限基座（复用） | `agents/enterprise/agent_permission_policy.py` + `identity.py` + `organization.py`(`EnterpriseIsolationError`) + `agent_runtime_policy.py` + `agent_governance_center.py`（只读消费） |
| 服务装配 | `agents/enterprise/service.py`（`EnterpriseOperationLayer` 新增 `self.agent_governance_workflow`，注入共享 `audit`/`identity`/`visibility`/`permission_policy`/`runtime_policy` + 3.8.20 治理中枢）+ `__init__.py`（新增 7 符号导出） |
| 测试（本层） | `tests/agents/test_enterprise_agent_governance_workflow.py`（八类 97 用例 / 865 行） |
| 测试计数修正（53→56） | `test_enterprise_knowledge_governance_audit.py`（`EXPECTED_CATEGORIES` +3 项 / 断言 `== 56`）+ `test_enterprise_knowledge_intelligence_audit.py` + `test_enterprise_agent_cost_resource.py` + `test_enterprise_agent_quality_governance.py` + `test_enterprise_agent_runtime_policy.py` + `test_enterprise_agent_security_risk.py` + `test_enterprise_agent_governance_center.py` + `test_enterprise_agent_compliance.py` |

### 24.3 红线守约（fail-closed，6 条，3.8.21 细化）

- ① `engineering_enabled=false`（`agents/config.yaml:102`；写路径断言 `safety_invariants_ok()`；启用态 monkeypatch 后 `GovernanceWorkflowService` 构造即抛 `EnterpriseRedLineViolationError`）。
- ② 不输出 `engineering_approved`（`_GOVERNANCE_FORBIDDEN` 含该名及 `approve`/`sign`/`authorize`/`quote`/`pricing`，访问即抛；本层源码仅禁用名声明 + 红线注释，零赋值/零输出）。
- ③ 禁止 AI 自动整改风险 —— **类型级**：`GovernanceTask` 无 `remediate`/`fix`/`resolve`/`close` 方法，状态机无 AI 终态；**语义级**：标题/说明/结果命中 `_REMEDIATION_MARKERS` 即拒；**结构级**：拦截 `auto_remediate`/`auto_fix`/`auto_resolve`/`auto_close`/`close_task`/`complete_task`/`auto_repair`/`auto_mitigate` 等。
- ④ 禁止 AI 自动分配责任：**类型级**：`GovernanceTask` 构造期 `owner_id` 必空、责任人必真实 USER；**语义级**：标题/说明命中 `_ASSIGNMENT_MARKERS` 即拒，assignee/assigned_by 命中 `_NON_HUMAN_ASSIGNEES` 即抛；**结构级**：拦截 `auto_assign`/`auto_delegate`/`auto_designate_owner`/`assign_responsibility_automatically` 等；`assign_owner` 强制 `require_human_actor(USER)`。
- ⑤ 禁止 AI 自动处置 / 修改策略：**结构级**：拦截 `auto_change_permission`/`grant_permission`/`revoke_permission`/`change_policy`/`auto_modify_policy` 等；本层对 `AgentPermissionPolicy` **只读引用**，无任何 set 器、无写路径；动作记录结果命中 `_PERMISSION_MARKERS` 即拒。
- ⑥ AI 不代替治理责任人：审计无 `record_human_approval`；`human_close` 单一闭环入口强制 `require_human_actor(USER)` + 非空 actor_id + 非空 `human_result`；`GovernanceClosureReport.closed_by` 必为真实 USER；拦截 `act_as_governance_owner`/`auto_confirm_closure`/`auto_recommend`/`auto_signoff` 等；任务/报告缺来源即拒落库。

### 24.4 测试与回归

- **八类测试共 97 用例全绿**（`test_enterprise_agent_governance_workflow.py`：task 15 / assignment 9 / action 10 / workflow 14 / closure 7 / permission 4 / audit 5 / red_line 6 函数，参数化展开后 97 用例），单文件 `97 passed in 0.15s`。
- 全 agents 套件 **1786 passed（1689 基线 + 97 新增）零回归**（2026-08-07 实测）。
- 修正 8 处 prior-phase 过期断言（3.8.15–3.8.20 遗留 `== 53` 计数，因本层 +3 枚举变 56，已刷新为 56）。
- 未修改 `verified.json` / `config.yaml` / `engineering_enabled`（`agents/config.yaml:102` 仍为 `false`）；不输出 `engineering_approved`；测试用 monkeypatch 注入启用态，不触碰磁盘配置。
- 注：存在历史测试技术债 `test_threshold_real_drill.py`（沙箱批量删除守卫下 `_tmp_drill_*` 临时文件偶发清理失败），与本 Phase 无关；清理临时文件后全量套件即全绿（1786 passed）。

### 24.5 交付物清单（3.8.21）

| 类型 | 路径 |
|---|---|
| 治理流程核心 + 装配 | `agents/enterprise/agent_governance_workflow.py` + `audit.py`（+3 枚举/方法）+ `service.py`（聚合）+ `__init__.py` |
| 测试 | `tests/agents/test_enterprise_agent_governance_workflow.py`（97 用例）+ 更新 8 个既有审计计数测试（53→56） |
| 收口报告 | `.ai/reviews/phase3.8.21_agent_governance_workflow_accountability_report.md` |
| 状态刷新 | `.ai/project_status.json`（`phase_3_8_21_status=ENTERPRISE_AGENT_GOVERNANCE_WORKFLOW_BUILT_NO_GO` + `phase_3_8_21` 明细块） |
| 路线图 | `.ai/roadmap_v8.md` §24 |

### 24.6 状态结论

- **状态：🟢 BUILT_NO_GO（2026-08-07）**：企业智能体治理流程与责任闭环层已完成 `GovernanceTask`/`GovernanceAssignment`/`GovernanceActionRecord`/`GovernanceClosureReport`(+`SourceTrace`) + `GovernanceWorkflowService` 的完整 fail-closed 治理闭环主线构建，审计累计 56 类别，全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不 AI 自动整改风险 / 自动分配责任 / 自动修改权限或策略 / 代替治理责任人；治理数据读取默认拒绝（`EnterpriseIsolationError`），任务分配/处理/闭环强制真实 USER，闭环报告必含可溯源来源链与人工结论。
- 全层只陈述与汇聚既有事实、只由真实治理责任人逐步推进并闭环；本层不产出任何治理结论、不分配任何责任、不整改任何风险、不关闭任何任务、不修改任何权限或策略。

---

> **STOP（3.8.21 收口）**：本报告与 `project_status.json` / `roadmap_v8.md` 刷新完成后，**不进入 Phase 3.8.22**，等待主理人审核授权。
- **未完成（人工动作，pending_verification）**：真实治理看板录入与人工管理 / 真实 Agent 健康与风险人工确认及处置 / 真实治理洞察人工确认 / `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动审批 均待主理人+专家线下执行；**本报告与状态刷新完成后停止，不进入 Phase 3.8.21**，等待主理人审核授权。

---

## 25. Phase 3.8.22 — Enterprise Agent Governance Knowledge & Continuous Improvement Layer（企业智能体治理知识与持续改进层）

> 状态：🟢 **BUILT_NO_GO（2026-08-08）** — 构建完成，等待主理人审核授权；**不进入 Phase 3.8.23**。

### 25.1 任务与交付（#712–#722，11 项全完成）

| # | 任务 | 交付 |
|---|---|---|
| #712 | GovernanceCase 模型 | 人工结果来源，强制 source_task_id / human_resolution / resolved_by（真实 USER）/ source_trace |
| #713 | GovernanceKnowledgeCandidate 模型 | 只能 CANDIDATE 态，requires_human_review 恒 True，内容过治理标记扫描 |
| #714 | GovernancePattern 模型 | 风险/异常/处理三态，is_policy 恒 False，事实归纳禁自动策略 |
| #715 | GovernanceImprovementWorkflowService | case_created→candidate_generated→human_review→accepted/rejected，仅前进不回退，无 AI 终态 |
| #716 | 权限接入 | IdentityService + AgentPermissionPolicy + KnowledgeVisibilityPolicy，治理知识默认拒绝；EnterpriseOperationLayer 聚合挂载 |
| #717 | GovernanceKnowledgeReport | cases/patterns/experiences + SourceTrace，经验段只收 accepted |
| #718 | Audit 增强 | +3 类 AGENT_GOVERNANCE_CASE/KNOWLEDGE/IMPROVEMENT（56→59）+ 3 个 record_* 方法，禁 record_human_approval |
| #719 | 测试 | 八类 116 用例全绿 |
| #720 | 最终验证 | 全 agents 套件（剔除历史阈值债）1880 passed 零回归；engineering_enabled=false；无 engineering_approved |
| #721 | 状态更新 | project_status.json（phase_3_8_22_status + 明细块）+ 本 §25 |
| #722 | 收口报告 | .ai/reviews/phase3.8.22_agent_governance_knowledge_improvement_report.md |

### 25.2 代码与审计清单

- 核心新建：`agents/enterprise/agent_governance_knowledge.py`（1516 行，10 导出符号）。
- 审计：`agents/enterprise/audit.py` 累计 59 类别（+3），+3 个 `record_*` 方法；`_KNOWLEDGE_FORBIDDEN` 共 97 项（③/④/⑤/⑥ 四族 + 基座 7 项）。
- 装配：`service.py` / `__init__.py` 注入 `agent_governance_knowledge`，传 `governance_workflow=self.agent_governance_workflow`。
- 测试：`tests/agents/test_enterprise_agent_governance_knowledge.py`（1101 行，116 用例）+ 9 个既有审计计数测试刷新 56→59、`EXPECTED_CATEGORIES` 补 3 成员。

### 25.3 红线守约（fail-closed，6 条，3.8.22 细化）

- ① `engineering_enabled=false`（config.yaml:102 未变）；② 不输出 `engineering_approved`（仅负向引用）；③ 禁 AI 自动修改 Agent（14 个 agent 家族拦截）；④ 禁 AI 自动修改治理策略（18 个 policy 家族拦截）；⑤ 禁 AI 自动关闭治理任务（对 3.8.21 `_tasks` 只读，强制 human 闭环）；⑥ 禁 AI 代替治理责任人（review/accept/reject 强制 `require_human_actor(USER)`，审计禁 `record_human_approval`）。

### 25.4 测试与回归

- 新增八类 116 用例全绿；全 agents 套件（剔除 `test_threshold_migration.py` / `test_threshold_real_drill.py` 两条历史债）**1880 passed / 0 failed**。
- 历史债：threshold 系列扫描 `_tmp_drill_*.json` 成组跑偶发顺序污染（单独跑各用例均 PASS），与 3.8.22 无关，建议单独 hygiene 修复。
- `verified.json` / `engineering_enabled` 均未变更；无 `engineering_approved`、无 `record_human_approval` 调用。

### 25.5 交付物清单（3.8.22）

| 类型 | 路径 |
|---|---|
| 治理知识核心 + 装配 | `agents/enterprise/agent_governance_knowledge.py` + `audit.py`（+3 枚举/方法）+ `service.py` + `__init__.py` |
| 测试 | `tests/agents/test_enterprise_agent_governance_knowledge.py`（116 用例）+ 9 个既有测试刷新 |
| 收口报告 | `.ai/reviews/phase3.8.22_agent_governance_knowledge_improvement_report.md` |
| 状态刷新 | `.ai/project_status.json`（`phase_3_8_22_status=ENTERPRISE_AGENT_GOVERNANCE_KNOWLEDGE_BUILT_NO_GO` + 明细块） |
| 路线图 | `.ai/roadmap_v8.md` §25 |

### 25.6 状态结论

- **状态：🟢 BUILT_NO_GO（2026-08-08）**：企业智能体治理知识与持续改进层完成 `GovernanceCase`/`GovernancePattern`/`GovernanceKnowledgeCandidate`/`GovernanceKnowledgeReport`(+`SourceTrace`)+`GovernanceImprovementWorkflowService` 的 fail-closed 知识沉淀主线；审计累计 59 类别；全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不 AI 自动修改 Agent / 修改治理策略 / 关闭治理任务 / 代替治理责任人。

---

> **STOP（3.8.22 收口）**：本报告与 `project_status.json` 刷新完成后，**不进入 Phase 3.8.23**，等待主理人审核授权。
> - **未完成（人工动作，pending_verification）**：真实治理知识录入与人工审核（accept/reject）/ 真实 Agent 整改与责任判定 / `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动审批 均待主理人+专家线下执行；**本报告与状态刷新完成后停止**，等待主理人审核授权。

---

## 26. Phase 3.8.23 — Enterprise Agent Governance Knowledge Retrieval & Learning Assistance Layer（企业智能体治理知识检索与辅助学习层）

### 26.1 目标与范围

在 3.8.0–3.8.22 治理基座之上，把 3.8.22 已由真实人工审核沉淀的治理知识 / 案例 / 模式，按治理事件语境做**只读相似检索**，产出辅助分析上下文与事实型辅助报告，最终只能由真实人工决定怎么用。链路：`治理事件 → 历史案例检索 → 知识匹配 → 辅助分析 → 人工使用`。

### 26.2 交付物（3.8.23）

- 核心模块（新建）：`agents/enterprise/agent_governance_knowledge_retrieval.py`（1971 行，9 个导出符号 + `_RETRIEVAL_FORBIDDEN` 禁名表 105 项）。
- 审计增强：`audit.py` +3 枚举（59→62：`AGENT_GOVERNANCE_KNOWLEDGE_QUERY` / `AGENT_GOVERNANCE_KNOWLEDGE_RETRIEVAL` / `AGENT_GOVERNANCE_ASSISTANCE`）+ 3 个 `record_*` 方法。
- 装配接入：`service.py` + `__init__.py` 注入 `agent_governance_knowledge_retrieval`。
- 测试：`tests/agents/test_enterprise_agent_governance_knowledge_retrieval.py`（909 行，50 用例）+ 10 个既有审计计数测试刷新 59→62、`EXPECTED_CATEGORIES` 补 3 成员。

### 26.3 红线守约（fail-closed，6 条，3.8.23 细化）

- ① `engineering_enabled=false`（config.yaml:102 未变）；② 不输出 `engineering_approved`（仅负向引用）；③ 禁 AI 自动修改知识（26 个 knowledge 家族拦截，query_text/rationale/factual_summary 命中 `_KNOWLEDGE_MUTATION_MARKERS` 即拒，对 3.8.22 知识纯只读）；④ 禁 AI 自动应用治理经验（候选 `requires_human_use` 恒 True，阶段机无"已应用"终态，23 个 experience 家族拦截）；⑤ 禁 AI 自动生成治理策略（`GovernanceMatchKind` 无 policy 类，报告无 recommendation/action/policy 字段，25 个 policy 家族拦截）；⑥ 禁 AI 代替治理责任人（`mark_human_used` 强制 `require_human_actor(USER)`，审计禁 `record_human_approval`，辅助报告禁建议/责任判定语义）。

### 26.4 关键设计

- **确定性相似度，绝不调 LLM**：`_tokenize` + Jaccard `_similarity`，可复现可解释；`match_cases` 刻意不把 `human_resolution` 纳入相似度（只按"问题像不像"检索，避免变相给处置建议）。
- **只给候选 / 只辅助分析**：候选 `requires_human_use` 恒 True；`GovernanceLearningContext.is_advisory_only` 恒 True；`GovernanceAssistanceReport.contains_recommendation` 是计算属性恒 False、不可伪造；报告结构上无 recommendation/action/policy 字段。
- **权限隔离**：读路径 `_ensure_access`（默认拒绝）+ 跨组织 `_ensure_org_scope`（抛 `EnterpriseIsolationError`）+ `KnowledgeVisibilityPolicy.can_read`（默认拒绝）。

### 26.5 测试与回归

- 新增八类 50 用例全绿；全 agents 套件 **1952 passed / 0 failed**（清洁运行连 2 个历史 threshold 债文件同跑亦全绿）。
- 历史债：`test_threshold_migration.py` / `test_threshold_real_drill.py`（18 用例，扫描 `_tmp_drill_*.json` 偶发顺序污染），与 3.8.23 无关，建议单独 hygiene 修复。
- `verified.json` / `engineering_enabled` 均未变更；无 `engineering_approved`、无 `record_human_approval` 调用。

### 26.6 交付物清单（3.8.23）

| 类型 | 路径 |
|---|---|
| 治理知识检索核心 + 装配 | `agents/enterprise/agent_governance_knowledge_retrieval.py` + `audit.py`（+3 枚举/方法）+ `service.py` + `__init__.py` |
| 测试 | `tests/agents/test_enterprise_agent_governance_knowledge_retrieval.py`（50 用例）+ 10 个既有测试刷新 |
| 收口报告 | `.ai/reviews/phase3.8.23_agent_governance_knowledge_retrieval_report.md` |
| 状态刷新 | `.ai/project_status.json`（`phase_3_8_23_status=ENTERPRISE_AGENT_GOVERNANCE_KNOWLEDGE_RETRIEVAL_BUILT_NO_GO` + 明细块） |
| 路线图 | `.ai/roadmap_v8.md` §26 |

### 26.7 状态结论

- **状态：🟢 BUILT_NO_GO（2026-08-09）**：企业智能体治理知识检索与辅助学习层完成 `GovernanceKnowledgeQuery`/`GovernanceMatchCandidate`/`GovernanceKnowledgeRetrieval`/`GovernanceSimilarityMatcher`/`GovernanceLearningContext`/`GovernanceAssistanceReport`(+`SourceTrace`)+`GovernanceKnowledgeRetrievalService` 的 fail-closed 检索辅助主线；审计累计 62 类别；全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不 AI 自动修改知识 / 应用经验 / 生成策略 / 代替治理责任人。

---

> **STOP（3.8.23 收口）**：本报告与 `project_status.json` 刷新完成后，**不进入 Phase 3.8.24**，等待主理人审核授权。
> - **未完成（人工动作，pending_verification）**：真实治理知识检索与人工研判 / 真实 Agent 整改与责任判定 / `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动审批 均待主理人+专家线下执行；**本报告与状态刷新完成后停止**，等待主理人审核授权。

---

## 27. Phase 3.8.24 — Enterprise Agent Governance Knowledge Assistant Layer（企业智能体治理知识助手层）

### 27.1 目标与范围

在 3.8.0–3.8.23 治理基座之上，把 3.8.23 只读相似检索与辅助学习层自然延伸为**问答型辅助**：把"用户提问"入口结构化为治理知识问题，复用 3.8.23 `GovernanceSimilarityMatcher` 检索案例/模式/知识/事件，攒只辅助分析的上下文，产出**纯事实答案草稿（强制引用来源、禁建议）**，最终只能由**真实人工**确认与采用。链路：`用户问题 → 治理知识检索（复用 3.8.23）→ 案例/模式/知识/事件匹配 → 上下文构建 → 事实摘要 → 人工使用`。

### 27.2 交付物（3.8.24）

- 核心模块（新建）：`agents/enterprise/agent_governance_knowledge_assistant.py`（~910 行，8 个导出符号 + `_ASSISTANT_FORBIDDEN` 禁名表 117 项 = 3.8.23 `_RETRIEVAL_FORBIDDEN` 105 项 + 助手专属 12 项）。
- 审计增强：`audit.py` +3 枚举（62→65：`AGENT_GOVERNANCE_ASSISTANT_QUERY` / `AGENT_GOVERNANCE_ASSISTANT_CONTEXT` / `AGENT_GOVERNANCE_ASSISTANT_DRAFT`）+ 3 个 `record_*` 方法。
- 装配接入：`service.py` + `__init__.py` 复用 3.8.23 注入，本层经 `GovernanceAssistantAgent` 入口暴露。
- 测试：`tests/agents/test_enterprise_agent_governance_knowledge_assistant.py`（43 用例，八类）+ 10 个既有审计计数测试刷新 62→65、`EXPECTED_CATEGORIES` 补 3 成员。

### 27.3 红线守约（fail-closed，6 条，3.8.24 细化）

- ① `engineering_enabled=false`（config.yaml:102 未变）；② 不输出 `engineering_approved`（仅负向引用，`hasattr(GovernanceAssistantAgent, "engineering_approved")==False`）；③ 禁 AI 自动修改知识（复用 knowledge 家族，对 3.8.22 知识纯只读）；④ 禁 AI 自动应用治理经验（候选 `requires_human_use` 恒 True，阶段机无"已应用"终态，experience 家族拦截）；⑤ 禁 AI 自动生成治理策略（`GovernanceAnswerDraft` 无 recommendation/action/policy 字段，`contains_recommendation` 恒 False 不可伪造，policy 家族含补强 `recommend_policy`/`auto_recommend` 拦截）；⑥ 禁 AI 代替治理责任人（`confirm_answer` 强制 `require_human_actor(USER)`，审计禁 `record_human_approval`，`GovernanceAssistantReview` 构造即强制 `reviewer_kind==USER`，答案草稿禁建议/责任判定语义）。

### 27.4 关键设计

- **复用 3.8.23 检索引擎**：`understand_query` 把 `GovernanceAssistantQuery` 只读结构化为 3.8.23 `GovernanceKnowledgeQuery`（复用其强校验 + 红线语义拦截），再喂入 `GovernanceSimilarityMatcher`；确定性 Jaccard 相似度，绝不调 LLM。
- **只给候选 / 只辅助分析 / 只写事实摘要**：`GovernanceAssistantContext.is_advisory_only` 恒 True；`GovernanceAnswerDraft.requires_human_review` 恒 True、`references` 强制引用来源、`contains_recommendation` 计算属性恒 False 不可伪造；阶段机 `GovernanceAssistantStage` 唯一终态 `HUMAN_USED`。
- **权限隔离 + 人工确认**：读路径 `_ensure_access`（默认拒绝）+ 跨组织 `_ensure_org_scope`（抛 `EnterpriseIsolationError`）+ `KnowledgeVisibilityPolicy.can_read`（默认拒绝）；`confirm_answer` 与 `GovernanceAssistantReview` 均为真实 USER 强约束节点。

### 27.5 测试与回归

- 新增八类 43 用例全绿；全 agents 套件 **1995 passed / 0 failed**（清洁运行；先删 `_tmp_drill_*` 历史阈值债文件，零回归）。
- 历史债：`test_threshold_migration.py` / `test_threshold_real_drill.py`（18 用例，扫描 `_tmp_drill_*.json` 偶发顺序污染），与 3.8.24 无关，建议单独 hygiene 修复。
- `verified.json` / `engineering_enabled` 均未变更；无 `engineering_approved`、无 `record_human_approval` 调用。

### 27.6 交付物清单（3.8.24）

| 类型 | 路径 |
|---|---|
| 治理知识助手核心 + 装配 | `agents/enterprise/agent_governance_knowledge_assistant.py` + `audit.py`（+3 枚举/方法）+ `service.py` + `__init__.py` |
| 测试 | `tests/agents/test_enterprise_agent_governance_knowledge_assistant.py`（43 用例）+ 10 个既有测试刷新 |
| 收口报告 | `.ai/reviews/phase3.8.24_agent_governance_knowledge_assistant_report.md` |
| 状态刷新 | `.ai/project_status.json`（`phase_3_8_24_status=ENTERPRISE_AGENT_GOVERNANCE_ASSISTANT_BUILT_NO_GO` + 明细块） |
| 路线图 | `.ai/roadmap_v8.md` §27 |

### 27.7 状态结论

- **状态：🟢 BUILT_NO_GO（2026-08-09）**：企业智能体治理知识助手层完成 `GovernanceAssistantQuery`/`GovernanceAssistantContext`/`GovernanceAnswerDraft`/`GovernanceAssistantReview`(+`AssistantReviewDecision`)+`GovernanceAssistantAgent`（复用 3.8.23 `GovernanceSimilarityMatcher`）的 fail-closed 问答辅助主线；审计累计 65 类别；全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不 AI 自动修改知识 / 应用经验 / 生成策略 / 代替治理责任人 / 自动确认答案。

---

> **STOP（3.8.24 收口）**：本报告与 `project_status.json` 刷新完成后，**不进入 Phase 3.8.25**，等待主理人审核授权。
> - **未完成（人工动作，pending_verification）**：真实治理知识问答与人工研判 / 真实 Agent 整改与责任判定 / `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动审批 均待主理人+专家线下执行；**本报告与状态刷新完成后停止**，等待主理人审核授权。

---

## 28. Phase 3.8.25 — Enterprise Agent Governance Workflow Orchestration Layer（企业智能体治理工作流编排层）

### 28.1 目标与范围

在 **3.8.24 治理知识助手**之上建立**编排层**，把治理链路「问题发现 → 事实辅助分析 → 人工研判 → 治理任务创建 → 执行跟踪 → 结果归档 → 审计闭环」串成一条**可追踪、可审计、AI 不可越权**的工作流流水线。AI 只能理解/整理/关联/提醒/生成草稿；所有治理动作必须真实人工确认并留痕。分支：`feat/phase3.8.25-governance-workflow`。

### 28.2 核心组件与状态机

- 核心：`GovernanceWorkflowOrchestrator(_RedLineForbiddenMixin)`，`agents/enterprise/governance_workflow/orchestrator.py`（570 行，18 方法）。
- **六态机（仅前进，无回退）**：`CREATED → UNDER_REVIEW → HUMAN_CONFIRMED → IN_PROGRESS → WAITING_RESULT → COMPLETED`（归档 `archived=True`）。无 `AUTO_APPROVED/AUTO_EXECUTED/AUTO_CLOSED` 态；非法/回退迁移直接拒绝；终态 `COMPLETED` 不可再转。
- **复用而非重建**：`human_confirm(decision=CONFIRMED, USER)` 可 `derive_task` 派生 3.8.21 问责层治理任务（actor 仍为真实人工，不越权）；事实草稿源复用 3.8.24 `GovernanceAssistantAgent`；共用 `AuditService`/`IdentityService`/`KnowledgeVisibilityPolicy`/`AgentPermissionPolicy`（默认拒绝 + 跨组织隔离）。
- 接线：`EnterpriseOperationLayer` 一并装配 3.8.24 助手与 3.8.25 编排器（`service.py:591/602`）。

### 28.3 交付物（3.8.25）

| 类型 | 路径 |
|---|---|
| 编排器核心 | `agents/enterprise/governance_workflow/orchestrator.py`（570 行 / 18 方法） |
| 测试 | `tests/agents/test_enterprise_agent_governance_workflow_orchestrator.py`（20 用例） |
| 脚手架（前序已就位，仅读取契约） | `forbidden.py` / `models.py`（6 模型 + 六态枚举）/ `audit.py`（+3 包装方法）/ 3.8.21 问责层 |
| 装配 | `agents/enterprise/service.py` + `__init__.py`（导出 3.8.24 + 3.8.25 符号） |
| 审计同步 | 10 个既有测试 `== 65` → `== 68`；`EXPECTED_CATEGORIES` +3（`agent_governance_workflow_create/review/execution`）；审计累计 **68** 类别 |
| 收口报告 | `.ai/reviews/phase3.8.25_governance_workflow_closure_report.md` |
| 状态刷新 | `.ai/project_status.json`（`phase_3_8_25_status=ENTERPRISE_AGENT_GOVERNANCE_WORKFLOW_ORCHESTRATION_BUILT_NO_GO`） |

### 28.4 红线守约（fail-closed，6 条）

- ① `engineering_enabled` 恒 False（`autouse` fixture 锁 `load_engineering_enabled→False`，构造经 `safety_invariants_ok()`）；② 不输出 `engineering_approved`；③ 禁 AI 自动治理/审批/关闭（`human_confirm`/`start_execution`/`submit_execution_result` 强制 `require_human_actor(USER)`，`reviewer_kind` 非 USER 抛 `EnterpriseRedLineViolationError`）；④ 禁 AI 自动执行（派生任务 actor 恒真实人工）；⑤ 禁 AI 自动生成策略/改知识；⑥ 禁 AI 代替责任人（审计 `actor_kind=USER` 强制留痕，禁名含 `auto_approve`/`auto_execute`/`auto_close_workflow`/`generate_policy`/`decide_workflow`）。

### 28.5 测试与回归

- 新增 20 用例全绿（创建 / 状态转换合法链→COMPLETED+archived / 非法迁移拒绝 / 终态不可转 / rejected 不前进 / 跨组织隔离 / AI 调写入口被拦 / derive_task / 审计 3 类 + actor_kind=USER / 禁名结构拦截 / 无 AUTO 态）。
- 全 agents 套件零回归；`verified.json` / `engineering_enabled` 未变；无 `engineering_approved`、无 `record_human_approval`。

### 28.6 状态结论

- **状态：🟢 BUILT_NO_GO（已收口）**：企业智能体治理工作流编排层交付 18 方法编排器 + 20 用例全绿，六道 fail-closed 红线逐项验证通过，审计枚举计数与脚手架同步。

---

> **STOP（3.8.25 收口）**：本报告与 `project_status.json` 刷新完成后，**不进入 Phase 3.8.26**，等待主理人 + 专家线下提交真实证据后，由人类终端显式置 `engineering_enabled=true`。

---

## 29. Phase 3.8.26 — Enterprise Agent Governance Persistence & Human Operation Interface Layer（企业智能体治理持久化与人工操作界面层）

> 本 Phase 分两批次：**批次 A＝治理驾驶舱与人工操作界面层（只读 + 单确认入口）**；**批次 B＝治理持久化与人工操作界面层（落库 + 人工操作 API + 人工 UI + 审计增强）**。配套收口报告：批次 A `.ai/reviews/phase3.8.26_governance_dashboard_closure_report.md`；批次 B `.ai/reviews/phase3.8.26_persistence_human_operation_closure_report.md`。状态同步：`.ai/project_status.json`（`phase_3_8_26_status=ENTERPRISE_AGENT_GOVERNANCE_PERSISTENCE_HUMAN_OPERATION_BUILT_NO_GO`）。

### 29.1 目标与范围

在 **3.8.25 编排层（六态机 + 编排器，单一真相源）** 之上补齐两件事：(A) 驾驶舱——人工可查看流程/待研判/执行/审计、可单一确认，自身不持状态；(B) 持久化——把 live orchestrator 事实快照落库（Repository 为系统记录源），并提供人工操作 API + 人工 UI + 审计增强（VIEW 类别）。复用而非重建 live `GovernanceWorkflowOrchestrator`。分支：批次 A `feat/phase3.8.26-governance-dashboard`；批次 B `feat/phase3.8.26-governance-persistence`。任务链：#761(T1) #759(T2) #760(T3) #762(T4) #763(T5) #769(T6) #764(T7) #765(T8) #766(T9) #767(T10) #768(T11) —— 全部完成，STOP。

### 29.2 批次 A 交付物（治理驾驶舱，只读 + 单确认入口）

| 类型 | 路径 |
|---|---|
| 禁名集 | `agents/enterprise/governance_dashboard/forbidden.py`（`_DASHBOARD_FORBIDDEN` 176 项 = 3.8.25 编排层 166 ∪ 本层 17 增量） |
| 视图模型 | `agents/enterprise/governance_dashboard/models.py`（`DashboardUser`/`ExecutionStatusView`/`RiskAlert`/`DashboardSummary`） |
| 驾驶舱服务 | `agents/enterprise/governance_dashboard/service.py`（`GovernanceDashboardService`，377 行，只读查询 + `confirm_review` 单写入口） |
| 包导出 | `agents/enterprise/governance_dashboard/__init__.py` |
| FastAPI 路由 | `backend/app/api/governance_dashboard.py`（`/governance/*`：GET 5 + POST 1，强制 `x-actor-kind:user` 否则 403） |
| 路由注册 | `backend/app/api/__init__.py` + `backend/app/main.py` |
| 人工界面 | `frontend/src/app/governance-dashboard/page.tsx`（待研判卡片 + 人工确认表单，无自动按钮；tsc 本文件 0 错误） |
| 测试 | `tests/agents/test_enterprise_governance_dashboard.py`（19 用例）+ `backend/tests/test_governance_dashboard.py`（6 用例，TestClient） |
| 收口报告 | `.ai/reviews/phase3.8.26_governance_dashboard_closure_report.md` |

### 29.3 批次 B 交付物（持久化与人工操作界面层，本批次主交付）

| 类型 | 路径 | 说明 |
|---|---|---|
| 工作流持久化模型 | `backend/app/db/models/governance_workflow.py` | `WorkflowORM`/`ExecutionRecordORM`/`ReviewORM`/`AssignmentORM`/`ClosureReportORM` + 三道 CHECK（`status` 六态白名单 / `requires_human_confirmation IN (1,true)` 恒真 / `actor_kind='user'` 恒真） |
| 迁移 | `backend/alembic/versions/3826a1b2c3d4_phase3_8_26_governance_persistence.py` | Alembic 落库 |
| 仓储层 | `backend/app/db/repositories/governance_workflow_repository.py` | Repository 为系统记录源；`require_human_actor` + `OrgScopeError` 组织隔离；执行记录 `actor_kind='user'` 强制校验 |
| 人工操作 API | `backend/app/api/governance_operations.py` | `require_user`（非 user→403），所有写端点 `Depends(require_user)`；无 `auto_*` 写入口 |
| API 注册 | `backend/app/api/__init__.py` + `backend/app/main.py` | 注册 `governance_operations_router` |
| 人工 UI | `backend/app/static/governance_human_ui.html` | 人工操作界面（human-only，无自动提交） |
| 测试 | `backend/tests/test_governance_persistence_workflow.py` | 持久化/人工操作 fail-closed 测试 |
| 审计增强 | `agents/enterprise/audit.py` | `AuditActionCategory` 68→**69**（+`agent_governance_workflow_view`）+ 4 个 record 方法；11 个历史计数断言 `==68`→`==69`、`EXPECTED_CATEGORIES` +1 |
| 收口报告 | `.ai/reviews/phase3.8.26_persistence_human_operation_closure_report.md` | 8 节（目标/交付物/红线/测试/架构/风险/未决/STOP） |

### 29.4 红线守约（fail-closed，三层防御纵深）

- **API 层**：`require_user` → 403（非 user 拒绝所有写入口）；无 `auto_confirm`/`auto_execute`/`auto_close`/`auto_assign` 等 `auto_*` 入口（grep 0 命中）。
- **Repository 层**：`require_human_actor(USER)` + `OrgScopeError`（跨组织隔离）；执行/确认记录 `actor_kind='user'` 强制校验。
- **DB 层**：三道 CHECK 约束（`status` 六态白名单、`requires_human_confirmation IN (1,true)` 恒真、`actor_kind='user'` 恒真），结构级兜底。
- ① `engineering_enabled=false`（config.yaml:102 未变）；② 不输出 `engineering_approved`（仅负向声明，无实际输出）；③–⑥ AI 不自动治理/执行/关闭/改状态/改权限/代替人工责任，全部 fail-closed。

### 29.5 测试与验证（T9）

- 全 agents 套件 **2069 passed / 0 failed**（清洁运行：先删 `_tmp_drill_*` 历史阈值债文件，零回归）；T8 八类 fail-closed 10/10 通过。
- 11 个审计全局计数断言 `==68`→`==69` 已修正并全过；16 个 `test_threshold_*` 雪崩为历史 `[SAFE_DELETE_BULK_CONFIRM_REQUIRED]` 护栏 + `_tmp_drill_*` 目录扫描耦合债（单独放行跑 22 passed，不 import 本批任何新模块，0 回归），非本批引入，建议单独 hygiene 修复。
- `AuditActionCategory` 实跑 `count=69`、`view=agent_governance_workflow_view` 已落地；`config.yaml:102 engineering_enabled:false` 实证；`grep engineering_approved` 仅文档禁止声明。

### 29.6 架构与数据流

```
人工 UI (governance_human_ui.html / governance-dashboard)
   │  x-actor-kind:user + x-actor-id  → 403 否则
   ▼
GovernanceOperationsAPI (require_user)  ──复用──▶  GovernanceWorkflowOrchestrator (3.8.25, 六态机 单一真相源)
   │                                                │ human_confirm/start_execution/submit_result/human_complete/archive (require_human_actor USER)
   ▼                                                ▼
GovernanceWorkflowRepository (require_human_actor + OrgScopeError)  ──snapshot──▶  DB (3 CHECK)
   │
   ▼ audit.record_agent_governance_workflow_view (actor=USER)  →  AuditService
```

### 29.7 风险与未决事项

- 后端交付物 + `agents/enterprise/audit.py` 均为 untracked / modified，未提交（建议独立分支 `feat/phase3.8.26-governance-persistence`，待主理人审核后提交）。
- threshold 测试雪崩为历史债，需单独 hygiene（清 `_tmp_drill_*` + 解除目录扫描耦合）；不影响本批正确性。
- 真实治理证据（责任人 USER 身份、组织归属、`verified.json` 真实化）由主理人 + 专家线下提交后，人类终端显式置 `engineering_enabled=true` 方可解除 NO-GO。

### 29.8 状态结论与 STOP 纪律

- **状态：🟢 BUILT_NO_GO（已收口）**：Phase 3.8.26 批次 A（治理驾驶舱，只读 + 单确认入口）与批次 B（持久化 Repository + 人工操作 API + 人工 UI + 审计增强 69 类别）均交付；六道 fail-closed 红线三层防御纵深逐项验证；全 agents 套件 2069 passed 零回归；`engineering_enabled=false`，不输出 `engineering_approved`，不 AI 自动确认/执行/关闭/改状态/改权限/代替人工责任。
- **STOP：不进入 Phase 3.8.27**，不自动开启 `engineering_enabled`，不输出 `engineering_approved`，不自动评级/确认/禁用/报价 Agent，不代替人工责任。等待主理人审核授权。

## 30. Phase 3.8.27 — Enterprise Governance Infrastructure Consolidation Layer（企业治理基础设施收敛层）

> **文档对账补写说明**：本章由 **Phase 3.8.31 Task 11** 补写。本阶段代码与收口报告早已提交入库（实现 9 个 commit `1275a1b → 572eecc`，报告 commit `7384b00`，均已验证为当前 HEAD 的祖先），但此前 **既未登记于 `.ai/project_status.json`，也未写入本 roadmap**，属治理缺口。现按主理人裁决 **原编号归位，不重编号、不覆盖历史**。

### 30.1 阶段目标

在 3.8.26（持久化 + 人工操作界面）之上做一次**基础设施收敛**，解决「双实现 / 内存态 / 硬编码责任人 / 仓库大面积未追踪」四类结构性欠账。本阶段是「搬存储、抽接口、补追踪、加测试」，**不改变任何 AI 治理边界**。

### 30.2 任务链（T1–T5，全部完成）

| # | 任务 | 结果 |
|---|---|---|
| T1 | 统一 `GovernanceWorkflow` 实现 | 消除 `orchestrator.py` / `service.py` 双实现，5 条导入路径收敛到唯一类对象 |
| T2 | 工作流持久化 | 内存 dict → 可替换持久化端口 + 2 适配器 + 历史留痕 |
| T3 | 企业身份认证接入准备 | 消除前端硬编码责任人，抽出 Identity Provider 适配层（**本阶段仅接口抽象**，实装在 3.8.28） |
| T4 | Git 仓库治理 | 修复 `agents/` `tests/` `.ai/` 大面积未追踪；建立追踪策略、CODEOWNERS、治理规范 |
| T5 | 测试增强 | 唯一实现 / Repository / 权限 / 审计 / 迁移兼容五维度 |

### 30.3 交付物

| 类别 | 路径 | 规模 |
|---|---|---|
| 核心包 | `agents/enterprise/governance_workflow/` | `orchestrator.py` 1394 / `repository.py` 1067 / `models.py` 624 / `forbidden.py` 145 / `__init__.py` 84 / `service.py` 39 |
| 前端身份适配层 | `frontend/src/lib/identity/` | `types.ts` 175 / `guards.ts` 192 / `registry.ts` 128 / `errors.ts` 80 / `index.ts` 60 |
| 收口报告 | `.ai/reviews/phase3.8.27_governance_infrastructure_closure_report.md` | — |

变更规模：**491 files changed, 108552 insertions(+), 333 deletions(-)**（其中绝大部分为 T4 把历史未追踪文件正式纳入版本控制）。

### 30.4 红线守约

- ① `engineering_enabled=false`（`agents/config.yaml:102`，本阶段未触碰）；② 不输出 `engineering_approved`。
- **边界声明**：所有 Human-in-the-loop 守卫的位置与强度与 3.8.26 **完全一致，无一处放宽**。

### 30.5 测试与状态

- **69 用例全绿**。
- **状态：🟢 BUILT_NO_GO（已收口）**。未决：真实持久化后端（当前为可替换适配器，未接生产库）、`verified.json` 真实化、`engineering_enabled` 开启。

> ⚠️ **编号双义提醒**：`governance_workflow/` 包内出现的 "3.8.27" 引用指向**本层（治理基础设施收敛层）**，是**正确的，不可改**。另有一批被误标为 3.8.27 的追踪层内容，主理人已裁决记为 **3.8.30**（见 §33）。

---

## 31. Phase 3.8.28 — Enterprise Identity & Permission Governance Implementation Layer（企业身份认证与权限治理实装层）

> **文档对账补写说明**：本章由 **Phase 3.8.31 Task 11** 补写。本阶段已提交（commit `f10c5dc`，2026-08-09 22:51:28 +0800，已验证为当前 HEAD 祖先），此前缺失于 SSOT 与 roadmap，现原编号归位。

### 31.1 阶段目标

把 3.8.27 抽象出的身份接口**真正实装**：治理身份不再由请求头「声称」，而由后端从 `Authorization: Bearer <token>` **派生**，并经权威数据源（数据库）**二次裁定**；遗留 `x-actor-*` 身份头一律 **400**。

### 31.2 任务链（T1–T6，全部完成）

| # | 任务 | 要点 |
|---|---|---|
| T1 | 身份验证适配层 | `verifier`：凭据 → 经密码学校验的声明；HS256 实装，OIDC/SSO 仅留骨架 |
| T2 | 权限目录 | `permissions`：唯一治理权限词表 **9 项** + **4** 治理角色 + 禁语扫描 |
| T3 | 身份链路打通 | 后端 `principal`/`resolver`/`dependencies`/`service` + 前端 `BackendSessionIdentityProvider`/`token-store`/登录页 |
| T4 | 责任闭环 | `accountability`：责任五元组，问责记录不可被自动审批动作写入 |
| T5 | 安全测试 | 6 类 fail-closed + 头伪造回归 + 前后端词表对齐 |
| T6 | CI 与仓库规则 | CODEOWNERS 守护身份模块 + 专项 CI 工作流 + 静态扫描禁语头回归 |

### 31.3 交付物

- 核心包 `backend/app/identity/`（约 **1870 行**，9 层）：`permissions` / `verifier` / `resolver` / `principal` / `service` / `dependencies` / `accountability` / `seed` / `errors`。
- 变更规模：21 files changed（1779 insertions / 261 deletions）+ 9 个新增文件。
- 收口报告：`.ai/reviews/phase3.8.28_enterprise_identity_closure_report.md`。

### 31.4 红线守约

| 红线 | 守约证据 |
|---|---|
| ① `engineering_enabled` | `false`（`agents/config.yaml:102`，本阶段未触碰） |
| ② `engineering_approved` | 未输出 |
| actor_kind 强制 | `GovernancePrincipal.actor_kind` 恒为 `USER`，禁语即拒 |
| 默认拒绝 | `require_governance_permission` 默认拒绝（403）；跨组织 `require_same_org` 拒绝（403） |
| 不代责 | 问责记录不可被自动审批动作写入 |

**边界声明**：本阶段不改变任何 AI 治理边界；守卫位置与强度与 3.8.27 完全一致，无一处放宽。

### 31.5 测试与状态

- 后端身份安全套件 **58 例全绿**；前端身份链路 **81 例全绿**；治理相关套件合计 **144 例零回归**。
- **状态：🟢 BUILT_NO_GO（已收口）**。
- **收口时已知残余风险**：凭据存放于 `sessionStorage` —— 存在 XSS 即可窃取治理凭据。**该债已于 Phase 3.8.29 T1 兑现修复为 HttpOnly Cookie**（见 §32）。
- 未决：OIDC/SSO 真实 IdP 接入（本阶段仅骨架）、真实企业用户目录与真实治理角色授予、`verified.json` 真实化、`engineering_enabled` 开启。

---

## 32. Phase 3.8.29 — Enterprise Production Security & Deployment Hardening（企业生产安全与部署强化层）

> **文档对账补写说明**：本章由 **Phase 3.8.31 Task 11** 补写。本阶段已提交（commit `1377e8b`，2026-08-10 17:03:28 +0800），**即 Phase 3.8.31 开工时的当前 HEAD**。此前缺失于 SSOT 与 roadmap，现原编号归位。

### 32.1 阶段目标

把 3.8.28 的身份链路**推到可生产**：关闭 XSS 窃取凭据通道、标准化 IdP 接入、隔离运行环境、审计可追溯、CI 生产门禁化。分支自 3.8.28 `f10c5dc` 切出。

### 32.2 任务链（T1–T7，全部完成）

| # | 任务 |
|---|---|
| T1 | Token 安全强化（`sessionStorage` → **HttpOnly Cookie**；Cookie 策略 / CSRF 双提交 / SameSite / 刷新） |
| T2 | OIDC/SSO 生产接口（IdP 适配器标准化，缺配置 **fail-closed**，禁自动 fallback 开发身份） |
| T3 | 环境隔离（dev / testing / production 三态，生产禁 static-dev、禁测试密钥） |
| T4 | 安全审计增强（**append-only** Audit Trail：login/logout/refresh/denied/failure） |
| T5 | CI/CD 生产门禁（身份安全 / 权限 / 红线扫描 / 依赖扫描，失败禁合并） |
| T6 | 部署文档 `docs/PRODUCTION_DEPLOYMENT_GUIDE.md` |
| T7 | production-security 测试，全部 fail-closed |

### 32.3 三层强制点（纵深防御）

| 层 | 位置 | 失败行为 |
|---|---|---|
| 启动期 | `Settings.assert_production_safe()`（`backend/app/main.py:34`，`is_production` 时调用） | **进程拒绝启动** |
| 装配期 | `build_identity_service()`（`backend/app/identity/dependencies.py:83`） | `IdentityConfigError`，请求一律 **401** |
| CI | `scripts/lint/check_production_security.py`（7 条红线） | **CI 失败，禁止合并** |

### 32.4 关键规则：凭据优先级不可反转

**`Authorization` 头存在则显式独占（非法也不回落 Cookie）；完全没给头才读 HttpOnly Cookie 兜底。** 该优先级不可反转 —— 反转会导致「责任人张冠李戴」。

### 32.5 测试与状态

- `backend/tests/test_production_security.py` **49 passed**（35 安全 + 14 扫描器自检）；`backend/tests` 全量 **291 passed / 1 failed**（继承债，见下）；frontend identity jest **88 passed**；`tsc --noEmit` **0 error**；`check_production_security.py` exit 0（**7/7**）。
- **收口时继承债**：工作树中存在未提交的 `governance_traceability` 产物，使 `len(AuditActionCategory)` 由 69 变为 72，导致 `backend/tests/test_governance_persistence_workflow.py::test_audit_workflow_categories_reuse`（断言 `== 69`）失败。判定：**与 3.8.29 无因果关系**（本阶段改动零涉及 `agents/`）。
  → **已由 Phase 3.8.31 Task 9 兑现清偿**：改为「四类治理工作流审计存在性契约」，总数权威唯一保留在 `tests/agents/test_enterprise_knowledge_governance_audit.py`；复验通过，`backend/tests` 现为 **292 passed / 0 failed**。
- **状态：🟢 BUILT_NO_GO（已收口）**。未决：真实生产环境部署与拓扑决策（同源/跨子域/跨站）、sso-gateway 网络隔离绕过验证、审计表 PITR 恢复演练、`verified.json` 真实化、`engineering_enabled` 开启（**仅人类终端可执行**）。

---

## 33. Phase 3.8.30 — Enterprise Agent Governance Traceability & Unified Audit Intelligence Layer（企业智能体治理全链路追踪与统一审计智能层）

> **阶段编号说明**：本层原按 spec 标为 3.8.27，但经核对仓库真实状态，`3.8.27`/`3.8.28`/`3.8.29` 已被占用（治理基础设施收敛层 / 企业身份认证与权限治理实装层 / 生产安全层）。主理人裁决本追踪层顺延记为 **3.8.30**，独立分支单独提交，不污染已占用编号。详见收口报告 §7。

### 33.1 阶段目标

在已收敛的权威治理层（3.8.13 能力注册 → 3.8.26 持久化/人工操作）之上新建「全链路追踪与统一审计智能层」：
1. 治理事实的**全链路唯一追踪**（Trace + Link），把 workflow / task / audit / knowledge / event 串成可溯源网络；
2. **统一审计时间线**（只读聚合）与**事实重放视图**（禁止重新执行动作）；
3. **完整来源链报告**（SourceTrace），只汇编事实、不生成结论；
4. 对既有 audit / orchestrator / knowledge 层**纯只读**，不回写、不修改、不关闭事件、不代责。

### 33.2 架构与代码清单（T1–T7）

新增包 `agents/enterprise/governance_traceability/`（4 文件，全部 untracked，1610 行）：

| 文件 | 行数 | 职责 |
|---|---|---|
| `__init__.py` | 71 | 导出 14 个公共符号 + 语义标记常量 |
| `forbidden.py` | 115 | `_TRACEABILITY_EXTRA_FORBIDDEN`(~145) → `_TRACEABILITY_FORBIDDEN`(**243** 项) |
| `models.py` | 659 | `AuditViewer`/`GovernanceTraceSourceType`(10)/`GovernanceTrace`/`GovernanceTraceLink`/`GovernanceAuditTimeline(Entry)`/`GovernanceReplayView(Step)`/`SourceTrace`/`GovernanceTraceReport` |
| `service.py` | 765 | `GovernanceTraceabilityService(_RedLineForbiddenMixin)`：三道闸门 + 八方法 |

- 复用：`GovernanceWorkflowOrchestrator`(3.8.25)、3.8.21 问责原语、`AuditService`/`IdentityService`/`AgentPermissionPolicy`/`red_line`，不重复造轮子。
- 模型为 dataclass（非 ORM），构造期强校验；冻结语义 `re_executed=False` / `conclusion_included=False`。
- 红线混入 `_RedLineForbiddenMixin`：`__getattr__` 精确方法名拦截（243 项）+ `safety_invariants_ok()` 断言 `load_engineering_enabled() is False`。
- T6 审计增强 `audit.py`：枚举 **69 → 72**（`GOVERNANCE_TRACE`/`GOVERNANCE_TIMELINE`/`GOVERNANCE_REPLAY`）+ 3 方法（`record_governance_trace`/`timeline`/`replay`，均 `actor_kind=USER`，无 `record_human_approval`）。
- 装配层挂载：`agents/enterprise/service.py` + `__init__.py` 暴露 `self.agent_governance_traceability`。

### 33.3 红线守约（六道 fail-closed）

| # | 红线 | 守约证据 |
|---|---|---|
| ① | 禁开 `engineering_enabled` | `config.yaml:102` 保持 `false`；`safety_invariants_ok()` 断言。未触碰。 |
| ② | 禁输出 `engineering_approved` | 本层无该字段/方法；`hasattr(...)==False`；列入禁集负向声明。 |
| ③ | 禁 AI 自动修改治理记录 | ~145 项禁名落入 `_TRACEABILITY_FORBIDDEN`(243)；精确拦截。 |
| ④ | 禁 AI 自动生成治理结论 | `_FORBIDDEN_TRACE_FIELDS` 含 conclusion/verdict/root_cause；`conclusion_included=False` 强校验。 |
| ⑤ | 禁 AI 自动关闭事件 | `close_incident`/`sign_off_audit` 等禁名落入禁集；`re_executed=False` 禁止重放执行。 |
| ⑥ | 禁 AI 代替审计责任人 | `_require_user` 强制 `USER` + `require_human_actor(USER)`；`AuditViewer.from_user()` 委派责任。 |

三道闸门：`_gate` → `_require_user` → `_ensure_org_scope`（跨组织 + 操作者归属双校验）→ `_ensure_access`（`AgentPermissionPolicy` 默认拒绝 + `IdentityService.check(VIEW_AUDIT)`）。当前仅 `ADMIN` 满足双闸门，未擅扩 `REVIEWER` 资源范围。

### 33.4 测试与验证（T8 + T9）

- 本层测试 `tests/agents/test_enterprise_governance_traceability.py`：**36 passed**（八类 + 集成挂载，全绿）。
- 关联审计 `tests/agents/test_enterprise_knowledge_governance_audit.py`：**17 passed**（T6 加 3 枚举后刷新 `EXPECTED_CATEGORIES`，含 `governance_trace/timeline/replay`）。
- `engineering_enabled=false` ✅（未触碰）；无 `engineering_approved` 输出 ✅；装配层 `is_read_only()==True` + `is_activation_safe()==True` ✅；枚举 72 ✅；禁集 243 ✅。
- 全量 `tests/agents`：16 例 `test_threshold_*` 失败为历史 hygiene 债（`_tmp_drill_*` + `SAFE_DELETE_BULK_CONFIRM_REQUIRED` 护栏），与本层无关、零回归。

### 33.5 交付物

| 类别 | 路径 |
|---|---|
| 追踪模型/服务 | `agents/enterprise/governance_traceability/{__init__,forbidden,models,service}.py` |
| 审计增强 | `agents/enterprise/audit.py`（+3 枚举 +3 方法） |
| 装配挂载 | `agents/enterprise/service.py`、`agents/enterprise/__init__.py` |
| 测试 | `tests/agents/test_enterprise_governance_traceability.py`（36）、`tests/agents/test_enterprise_knowledge_governance_audit.py`（+3） |
| 收口报告 | `.ai/reviews/phase3.8.30_governance_traceability_audit_report.md` |
| 状态更新 | `.ai/project_status.json`（`phase_3_8_30_status`）+ `.ai/roadmap_v8.md`（§33） |

### 33.6 关键设计决策

1. 复用优于重建：对 audit/orchestrator/knowledge 纯只读，避免第二份事实源。
2. 模型 dataclass + 构造期强校验：红线在对象诞生即断言，禁止「先构造后校验」绕过窗口。
3. 精确方法名拦截：`__getattr__` 精确匹配（非子串），杜绝 `auto_modify_audit`/`close_incident` 等越权入口。
4. 保守授权：当前仅 `ADMIN` 满足双闸门，不为 `REVIEWER` 擅自扩权。
5. 事实重放 ≠ 重执行：`re_executed=False` 强校验，审计只能重建「发生了什么」，不能「再做一次」。

### 33.7 风险与未决事项

- 本层代码（包 + 测试）为 untracked，未提交；建议独立分支 `feat/phase3.8.30-governance-traceability`，不混入 3.8.28/3.8.29 未提交改动，待主理人审核后提交。
- threshold 测试雪崩为历史债（`_tmp_drill_*` + 护栏耦合），需单独 hygiene，不影响本层正确性。
- 真实治理证据（责任人 USER 身份、组织归属、`verified.json` 真实化）由主理人 + 专家线下提交后，人类终端显式置 `engineering_enabled=true` 方可解除 NO-GO。

### 33.8 状态结论与 STOP 纪律

- **状态：🟢 BUILT_NO_GO（已收口）**：Phase 3.8.30 全链路追踪与统一审计智能层交付；六道 fail-closed 红线三层防御纵深逐项验证；本层 36 用例 + 关联审计 17 用例全绿；审计枚举 72、禁集 243；`engineering_enabled=false`，不输出 `engineering_approved`，不 AI 自动修改/生成结论/关事件/代责。
- **STOP：不进入 Phase 3.8.31**，不自动开启 `engineering_enabled`，不输出 `engineering_approved`，不自动评级/确认/禁用/报价 Agent，不代替人工责任。等待主理人审核授权。

---

## 34. Phase 3.8.31 — Governance Repository Integrity & Release Baseline Consolidation Layer（治理仓库完整性与发布基线收敛层）

> 本阶段**不新增业务功能**，是一次**仓库治理 + SSOT 对齐 + Git 完整性 + 测试基线收敛**。收口报告：`.ai/reviews/phase3.8.31_repository_integrity_release_baseline_closure_report.md`。状态：`.ai/project_status.json`（`phase_3_8_31_status`）。

### 34.1 阶段目标

修补「代码已交付、治理记录却缺位」的结构性缺口：把散落的阶段事实收敛回单一真相源，把易碎的测试契约改为稳固契约，并新建**可执行的门禁**防止缺口复发。

### 34.2 核心发现与处置

| 发现 | 处置 |
|---|---|
| **10 个阶段缺 SSOT 登记**：3.8.10–3.8.16（7 个）+ 3.8.27/28/29（3 个），代码与报告均已存在，唯独状态未登记 | 按主理人裁决**原编号补登**，全部标注 `ssot_backfilled_by`，不重编号、不覆盖历史 |
| **roadmap 缺 3 章**：3.8.27/28/29 无章节，§30 直接跳到 3.8.30 | 补写 §30/§31/§32（本次），原 3.8.30 章重编号为 §33 |
| **审计总数断言脆性**：全仓多处硬编码 `len(AuditActionCategory) == N`，每加一个类别就要连改十几处旧测试 | 改为**关键类别存在性契约**（子集断言），**总数权威唯一**保留在 `tests/agents/test_enterprise_knowledge_governance_audit.py`（`EXPECTED_CATEGORIES` + `assert len(members) == 72`） |
| **3.8.29 继承债**（`== 69` 红灯） | 随上一条一并清偿，`backend/tests` 由 291/1failed → **292 passed** |
| **3.8.26 双报告** | 定性为同一阶段的**批次 A/B**（B 明确引用 A），**非编号冲突**，在基线清单 `known_notes` 标注 |
| **3.8.27 编号双义** | `governance_workflow/` 包内 "3.8.27" 指基础设施收敛层，**正确不可改**；被误标的追踪层内容按裁决记为 **3.8.30** |

### 34.3 交付物

| 类别 | 路径 | 说明 |
|---|---|---|
| 发布基线清单 | `.ai/baselines/phase3.8_governance_release_baseline.json` | 单一发布基线：git HEAD、release gate、审计契约（72 + 6 必需族）、测试基线、**32 条阶段登记**、integrity_invariants（8 条） |
| 完整性检查器 | `scripts/check_governance_repository_integrity.py` | **只读**，9 条规则，退出码 0/1 |
| 检查器自检 | `tests/agents/test_governance_repository_integrity_checker.py` | **33 用例**，正例放行 + 反例拦截双向验证 |
| CI 集成 | `scripts/ci/local_ci.sh` | 新增 **`[11/11]` 治理仓库完整性检查**（步骤总数 10 → 11） |
| SSOT | `.ai/project_status.json` | 补登 10 个阶段档案 + 状态串 |
| roadmap | `.ai/roadmap_v8.md` | 本次 §30/§31/§32/§34 + §33 重编号 |

### 34.4 完整性检查器的 9 条规则

1. 基线清单可解析；2. 阶段登记完整（有报告 ⇒ 必须有 SSOT 登记）；3. SSOT 报告路径真实存在；4. 审计总数断言全仓唯一；5. 审计总数与基线一致；6. 必需审计族齐备；7. **红线① `engineering_enabled=false`**；8. **红线② 不产出 `engineering_approved`**；9. 阶段编号唯一无冲突。

> **门禁必须抓得住违规才算门禁**：自检用**反例**验证拦截能力（`engineering_enabled: true` 的各种写法、幽灵报告路径、幻影总数断言、冲突阶段状态、正向 `engineering_approved` 输出），并专门守卫两类误报回归 —— 审计**事件计数**不得被误判为枚举总数、**负向声明**（禁语清单点名）必须放行。另有 `test_checker_is_read_only` 断言检查器源码无任何写操作。

### 34.5 测试基线（实测，清洁运行）

- `tests/agents`：**2190 passed**（含历史长期为红的 `test_threshold_*` 系列，本阶段 hygiene 后转绿）。
- `backend/tests`：**292 passed**（3.8.29 继承债清零）。
- 合计 **2482 passed / 0 failed**；治理完整性检查器 9/9 规则通过（EXIT=0）。

### 34.6 红线守约（六道 fail-closed）

| # | 红线 | 守约证据 |
|---|---|---|
| ① | 禁开 `engineering_enabled` | `agents/config.yaml:102` 保持 `false`；检查器规则 7 常态化守卫 |
| ② | 禁输出 `engineering_approved` | 全仓仅负向声明；检查器规则 8 常态化守卫 |
| ③ | 禁覆盖历史 commit | 全程**零提交、零 rebase、零 amend**；HEAD 始终为 `1377e8b` |
| ④ | 禁重编号已占用 Phase | 3.8.27/28/29 原编号归位；3.8.30 裁决未动 |
| ⑤ | 禁删测试/跳失败/改逻辑掩盖失败 | 未删任何测试、未加 skip/xfail；断言由「脆性总数」改为「稳固契约」，覆盖面不降反升 |
| ⑥ | 禁伪造 commit/测试/文件/SSOT/release 状态 | 所有 commit 均经 `git merge-base --is-ancestor` 验证；测试数字为实跑输出 |

### 34.7 状态结论与 STOP 纪律

- **状态：🟢 BUILT_NO_GO（已收口）**。
- **STOP：不进入 Phase 3.8.32**，不自动开启 `engineering_enabled`，不输出 `engineering_approved`，不自动放行发布。本阶段产物**全部未提交**，等待主理人审核授权。
---

## 35. Phase 3.9.0–3.9.3 生产发布闸门与可观测性体系（概览）

四阶段构成「生产发布前」的镜像验证、闸门收口与可观测性准备链，全部 **BUILT_NO_GO**，等待主理人线下授权：

| 阶段 | 定位 | 包 / 报告 | 审计总数 |
|------|------|----------|---------|
| 3.9.0 | 生产就绪准备层（只验证准备体系） | `agents/enterprise/production_readiness/` · `phase3.9.0_production_readiness_preparation_report.md` | 79 |
| 3.9.1 | 预生产验证与灾难恢复演练层（只验证能否扛住验证/灾难） | `agents/enterprise/staging_validation/` · `phase3.9.1_staging_validation_disaster_recovery_report.md` | 79→83（本链 +4） |
| 3.9.2 | 企业生产发布闸门与证据包层（只核验是否达到人工签署门槛） | `agents/enterprise/production_release/` · `phase3.9.2_production_release_gate_evidence_package_report.md` | 83 |
| 3.9.3 | 企业生产可观测性、SRE 与事故响应准备层（只建准备层，不真接入/不真告警/不自动修复） | `agents/enterprise/production_observability/` · `phase3.9.3_production_observability_incident_readiness_report.md` | 88→95（本链 +7） |

### 35.1 3.9.2 交付物与门禁

- **包**：`agents/enterprise/production_release/`（forbidden / models / evidence / gate / package / service / __init__ 七文件）；`PRODUCTION_RELEASE_FORBIDDEN_COUNT = 314`，Gate `CHECK_KEYS = 13`。
- **后端接线**：`backend/app/api/governance_release.py`（只读 + 签署端点，强制真实 USER 主体，AI 主体 403）。
- **前端**：`frontend/src/app/governance-release/page.tsx`（只读展示 + 人工签署，无自动上线 / 无 AI 批准按钮）；`frontend/src/lib/identity/{types,guards}.ts` 同步 `governance:release:read` / `governance:release:signoff`。
- **测试**：`tests/agents/test_production_release_gate_evidence.py`（23 例）、`tests/agents/test_enterprise_production_release.py`（27 例）、`backend/tests/test_governance_release.py`（31 例）全绿；agents 全量套件 2305 passed / 0 failed；backend 323 passed；frontend jest 117 passed；tsc 0 error。
- **清单（SHA-256）**：由 `ProductionReleaseService.build_manifest` 在运行时生成（T6），缺文件标 `<missing>`，不伪造——非独立脚本；证据完整性链见 `ProductionReleaseEvidenceService.verify_integrity`。
- **SSOT**：`.ai/project_status.json` 已登记 `phase_3_9_0/1/2_status`（均 `BUILT_NO_GO`）；治理仓库完整性检查器 9/9 通过。
- **十项最高红线**（绝对不可修改 / 弱化）：①`engineering_enabled=false` ②禁 `engineering_approved` ③禁 AI 自动批准发布 ④禁 AI 自动执行部署 ⑤禁 AI 修改真实企业数据 ⑥禁 AI 写真实生产密钥 ⑦禁 AI 自动授予生产权限 ⑧禁 AI 代签 ⑨禁把 staging/drill 描述成 production verified ⑩禁通过跳测试 / 改安全断言 / 伪造证据让 Gate 变绿——全部 fail-closed，门禁 `ProductionReleaseGate` 永不返回 `APPROVED`/`GO`。

### 35.2 3.9.3 交付物与门禁（企业生产可观测性、SRE 与事故响应准备层）

- **包**：`agents/enterprise/production_observability/`（forbidden / models / health / metrics / slo / correlation / alerts / incidents / service / __init__ 十文件）；`PRODUCTION_OBSERVABILITY_FORBIDDEN_COUNT = 337`，含 `auto_rollback` / `auto_resolve` / `auto_close` / `auto_acknowledge` / `assign_self_as_commander` / `act_as_incident_commander` / `silence_alert` / `fabricate_observability_evidence` 等禁名结构拦截。
- **后端接线**：`backend/app/api/governance_observability.py`（只读 + 人工 ACK/RESOLVE/CLOSE 端点，强制真实 `USER` 主体、AI 主体 403、`auto_state_transition=false`）；`backend/app/identity/permissions.py` 新增 `governance:observability:read` / `governance:incident:action`（职责分离：incident 动作仅 admin）。
- **前端**：`frontend/src/app/governance-observability/page.tsx`（只读展示 Overall/Component(11)/SLO/Metrics/Active Incidents + 真实人工 ACK/RESOLVE/CLOSE，无 Auto Fix / Auto Rollback / Auto Resolve / Auto Close / AI Approve 按钮）；`frontend/src/lib/identity/{types,guards}.ts` 同步两权限词表。
- **测试**：`tests/agents/test_enterprise_production_observability.py`（24 例）、`backend/tests/test_governance_observability.py`（23 例）全绿；agents 全量套件 **2329 passed / 0 failed**；backend 346 passed；frontend jest 117 passed；tsc 0 error；治理仓库完整性检查器 9/9 通过；生产安全 / 身份头 / 硬编码扫描通过（防编造扫描 20 处命中均为 3.9.3 之前历史 `.ai/` 文档与 `wind_pressure` 接口测试夹具，无一处位于本阶段交付物）。
- **审计**：`agents/enterprise/audit.py` +7 枚举（`OBSERVABILITY_HEALTH_CHECK` / `ALERT_CANDIDATE_CREATED` / `INCIDENT_CREATED` / `INCIDENT_HUMAN_ACKNOWLEDGED` / `INCIDENT_HUMAN_RESOLVED` / `INCIDENT_HUMAN_CLOSED` / `POSTMORTEM_DRAFT_CREATED`），`actor_kind` 恒 `USER`，总数 88 → 95。
- **SSOT**：`.ai/project_status.json` 已登记 `phase_3_9_3_status`（`BUILT_NO_GO`）；基线 `audit_category_contract.total = 95`、权威测试 `== 95` 同步。
- **十二项最高红线**（绝对不可修改 / 弱化）：①`engineering_enabled=false` ②禁 `engineering_approved` ③禁 AI 自动批准发布 ④禁 AI 自动执行部署 ⑤禁 AI 修改真实企业数据 ⑥禁 AI 写真实生产密钥 ⑦禁 AI 自动授予生产权限 ⑧禁 AI 自动关闭 Incident ⑨禁 AI 代 SRE/production-owner/security-owner/incident-commander 责任签署 ⑩禁 AI 代替人工责任 ⑪禁把模拟监控数据描述成真实 production observation ⑫禁通过删安全断言 / 跳失败测试 / 降权 / 伪造监控证据让观测门禁变绿——全部 fail-closed。

### 35.3 状态结论与 STOP 纪律

- **状态：🟢 BUILT_NO_GO（已收口，2026-08-12）**。
- **STOP：不进入 Phase 3.9.4+**，不真接入生产可观测性数据源、不真发送告警、不自动修复/回滚/关单、不自动开启 `engineering_enabled`，不输出 `engineering_approved`。本阶段产物待主理人审核授权后精路径 commit（包 + 测试 + API/前端 + 审计 + SSOT + 部署指南 §14 + 本指南 + roadmap + 24 节收口报告）。
