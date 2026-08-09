# Phase 3.8.13 收口报告 —— Enterprise Agent Capability Registry & Governance Layer（企业智能体能力注册与治理层）

- **状态**：`ENTERPRISE_AGENT_GOVERNANCE_BUILT_NO_GO`（已构建，未进入启用态）
- **工程开关**：`engineering_enabled = false`（fail-closed，红线①）
- **收口结论**：✅ 全部 11 项任务交付；✅ 全量 agents 测试 **1400 passed**（基线 1353 + 47 新增，零回归）；✅ 六条最高红线守约。
- **下一步**：**STOP，不进入 Phase 3.8.14；等待主理人审核。**

---

## 1. 阶段目标

Phase 3.8.13 在 3.8.0~3.8.12 企业知识层基座之上，新增「企业智能体能力注册与治理层」，建立第三方/内部 AI 智能体在企业内部的**可注册、可声明能力边界、可版本追踪、可权限隔离、可人工激活/弃用**的完整治理闭环，防止 AI 智能体越权访问资源或替代专家责任。

设计主线（外部 Agent 接入企业 → 能力声明 → 权限约束 → 人工审核 → 激活 → 受控调用 → 审计）：

1. 任何智能体须先登记为 `AgentRegistry` 条目（`agent_id` / `name` / `type` / `version` / `capabilities` / `status` / `owner` / `created_at`），初始状态恒为 `draft`。
2. 每个智能体须显式声明 `AgentCapability`（输入/输出类型、可调用的权限、明确的能力边界/局限），边界不清禁止激活。
3. 智能体能力随迭代产生 `AgentVersion`（change_log 可追踪），版本默认 `draft`，激活须经人工。
4. `AgentPermissionPolicy` 控制智能体可访问的**知识 / 工具 / 数据范围**，**默认拒绝**（沿用 3.8.9 `KnowledgeVisibilityPolicy` 模式）。
5. `AgentLifecycleService` 管理生命周期：`register`(AI 起草，恒 `draft`) → `submit_review`(→ `reviewing`) → `activate`(**须真实 USER**) → `deprecate`(**须真实 USER**)；镜像 3.8.12 的 `require_human_actor(USER)` 守卫。
6. 所有注册/执行/版本动作接入 `AuditService`（新增 `AGENT_REGISTER` / `AGENT_EXECUTION` / `AGENT_VERSION` 三类），actor 真实。
7. 智能体资源访问接入 `IdentityService` + `KnowledgeVisibilityPolicy`，只能访问授权知识/工具/数据（任务7）。

---

## 2. 架构设计

```
外部/内部 Agent
   │  register(agent_id, name, type, capabilities, owner)   [AI 起草, status=draft]
   ▼
AgentRegistry  ── org_id 绑定 / 访问隔离(EnterpriseIsolationError)
   │  declare_capability(input_types, output_types, permissions, limitations)
   │  new_version(change_log)  [AgentVersion, 默认 draft]
   ▼
AgentLifecycleService (只编排不代责)
   │  register()            → 写入 AgentRegistry(draft) + 审计 AGENT_REGISTER
   │  submit_review()       → draft → reviewing + 审计 AGENT_VERSION(review)
   │  activate()            → require_human_actor(USER) + 仅 reviewing 可激活
   │  deprecate()           → require_human_actor(USER) + 仅 active/reviewing 可弃用
   ▼
AgentPermissionPolicy (默认拒绝)
   │  is_agent_resource_permitted(role, category)
   │  check_agent_access(user, resource_category, required_permission)
   │  • 角色不在作用域 → 拒绝；声明了 required_permission 且未通过 IdentityService.check → 拒绝
   ▼
AuditService: AGENT_REGISTER / AGENT_EXECUTION / AGENT_VERSION (累计 32)
   │  • actor 真实（注册由 AI → AI；激活/弃用由 USER → USER）
   │  • 无 record_human_approval（绝不伪造人工审批）
   ▼
人工激活（activate/deprecate 须经真实 USER；红线⑥）
```

`EnterpriseOperationLayer` 聚合两项：`agent_permission_policy`（`AgentPermissionPolicy` 实例）+ `agent_registry`（`AgentLifecycleService` 实例，承载 register/submit_review/activate/deprecate 生命周期编排）；数据模型 `AgentRegistry` 为 dataclass。二者与既有企业层服务共享同一 `audit` / `identity` / `knowledge_visibility` 实例，保证策略与生命周期状态一致。

---

## 3. 任务完成情况（11 项）

| # | 任务 | 交付 | 状态 |
| --- | --- | --- | --- |
| 1 | AgentRegistry 模型 | `agent_registry.py`：`AgentStatus`(draft/active/deprecated) / `AgentRegistry`（8 字段，status 默认 `draft`，active 须人工确认） | ✅ |
| 2 | AgentCapability 模型 | `agent_capability.py`：`AgentCapability`（capability_id/agent_id/input_types/output_types/permissions/limitations，明确边界） | ✅ |
| 3 | AgentVersion 管理 | `agent_version.py`：`AgentVersion`（agent_id/version/change_log/created_at/status），版本可追踪 | ✅ |
| 4 | AgentPermissionPolicy | `agent_permission_policy.py`：`AgentPermissionPolicy(org_id)` 默认拒绝，控制 Agent 访问知识/工具/数据范围 | ✅ |
| 5 | AgentLifecycleService | `agent_lifecycle_service.py`：`register`/`submit_review`/`activate`(须真实 USER)/`deprecate`(须真实 USER) | ✅ |
| 6 | 调用审计 | `audit.py` +3 类别（累计 **32**）+ 3 个 `record_agent_*` 方法；actor 真实，无 `record_human_approval` | ✅ |
| 7 | 权限接入 | 接入 `IdentityService` + `KnowledgeVisibilityPolicy`；Agent 资源访问受控、组织隔离、角色默认拒绝 | ✅ |
| 8 | 测试 | `test_enterprise_agent_registry_governance.py` 八类（registry/capability/version/permission/lifecycle/audit/red line/integration），不修改 `verified.json` / `engineering_enabled` | ✅ |
| 9 | 最终验证 | 全 agents 套件 `pytest tests/agents -q` 全通过；`engineering_enabled=false`；无 `engineering_approved` | ✅ |
| 10 | 收口报告 | 本报告（7 节） | ✅ |
| 11 | 状态更新 | `project_status.json` + `phase_3_8_13_status` + `roadmap_v8.md` §16；完成后 STOP | ✅ |

---

## 4. 代码文件清单

### 4.1 新建文件

| 文件 | 内容 |
| --- | --- |
| `agents/enterprise/agent_registry.py` | 任务1：`AgentStatus`(DRAFT/ACTIVE/DEPRECATED) / `AgentRegistry` dataclass（agent_id/name/type/version/capabilities/status/owner/created_at；status 默认 DRAFT；active 须人工确认） |
| `agents/enterprise/agent_capability.py` | 任务2：`AgentCapability`（capability_id/agent_id/input_types/output_types/permissions/limitations；声明智能体能力边界与局限） |
| `agents/enterprise/agent_version.py` | 任务3：`AgentVersion`（agent_id/version/change_log/created_at/status）；版本可追踪，默认 DRAFT |
| `agents/enterprise/agent_permission_policy.py` | 任务4：`AgentPermissionPolicy(org_id)`；`_AGENT_RESOURCE_SCOPE` 默认拒绝；`is_agent_resource_permitted` / `check_agent_access`（接入 `IdentityService.check`） |
| `agents/enterprise/agent_lifecycle_service.py` | 任务5：`AgentLifecycleService(_RedLineForbiddenMixin)`；`register`(恒 DRAFT) / `submit_review`(→REVIEWING) / `activate`(**require_human_actor**+仅 REVIEWING) / `deprecate`(**require_human_actor**)；`_get_scoped` 组织隔离；审计 actor 真实 |

### 4.2 修改文件

| 文件 | 变更 |
| --- | --- |
| `agents/enterprise/audit.py` | 任务6：新增 3 个审计类别 `AGENT_REGISTER` / `AGENT_EXECUTION` / `AGENT_VERSION`（累计 **32**）；新增 `record_agent_register_action` / `record_agent_execution_action` / `record_agent_version_action`（actor 真实，无 `record_human_approval`） |
| `agents/enterprise/service.py` | 任务7：在 `EnterpriseOperationLayer.__init__` 装配 `agent_permission_policy`(`AgentPermissionPolicy`) 与 `agent_registry`(`AgentLifecycleService` 实例，复用 `self.knowledge_visibility` 作权限策略)，共享 `self.audit` / `self.identity` / `self.knowledge_visibility` |
| `agents/enterprise/__init__.py` | 任务7：新增 3.8.13 import 段与 `__all__` 导出（AgentRegistry/AgentStatus/AgentCapability/AgentVersion/AgentPermissionPolicy/AgentLifecycleService 等） |
| `tests/agents/test_enterprise_agent_registry_governance.py` | 任务8：八类共 **26** 个用例 |
| `tests/agents/test_enterprise_knowledge_governance_audit.py` | 任务6/8：`EXPECTED_CATEGORIES` 同步至 32 + `assert len(members)==32`（程序化 `__members__` 迭代，规避形近污染） |
| `tests/agents/test_enterprise_knowledge_intelligence_audit.py` | 任务6/8：同步总数断言 29 → 32 |

---

## 5. 测试结果

- **全量 agents 套件**：`1400 passed`（基线 1353 + 47 新增），0 失败，约 38s。
- **本层新增用例分布（八类，26 用例；其中 `test_service_construction_fail_closed` 为 3 参数化实例，共 26）**：
  - registry（2）：`test_agent_registry_default_status_draft` / `test_agent_registry_status_enum_coercion`
  - capability（1）：`test_agent_capability_fields_and_boundary`
  - version（4）：`test_agent_version_create_is_draft_then_activate_requires_user` / `test_agent_version_only_reviewing_can_activate` / `test_agent_version_deprecate_requires_user_and_traceability` / `test_agent_version_audit_records`
  - permission（3）：`test_permission_policy_default_deny_unknown_category` / `test_permission_policy_role_scope` / `test_permission_policy_check_via_identity_default_deny`
  - lifecycle（5）：`test_lifecycle_register_creates_draft_and_capabilities` / `test_lifecycle_activate_requires_user` / `test_lifecycle_deprecate_requires_user_and_state_machine` / `test_lifecycle_full_flow_syncs_version` / `test_lifecycle_org_isolation`
  - 审计（任务6，2）：`test_audit_categories_present_and_recordable` / `test_audit_execution_records_invocation`
  - 红线（任务8 验证，5，其中 1 个参数化×3）：`test_safety_invariants_ok_true_when_disabled` / `test_service_construction_fail_closed`（AgentLifecycleService / AgentVersionManager / EnterpriseOperationLayer 三构造均 fail-closed）/ `test_forbidden_methods_raise` / `test_invocation_requires_active_agent` / `test_invocation_denied_by_permission_policy`
  - 集成（2）：`test_layer_wires_agent_governance` / `test_layer_end_to_end_flow`
- **审计计数测试修正**：治理审计 `assert len(members)==32` + `EXPECTED_CATEGORIES` 同步（程序化生成）；智能审计 `assert len(list(AuditActionCategory))==32`。
- **未修改** `verified.json` / `config.yaml` / `engineering_enabled`；`engineering_enabled=false`；无 `engineering_approved`。

---

## 6. 六大红线验证（fail-closed）

| # | 红线 | 本层落实 | 核验结果 |
| --- | --- | --- | --- |
| ① | 保持 `engineering_enabled=false` | 所有服务构造/写路径断言 `safety_invariants_ok()`；配置保持 `false` | ✅ `load_engineering_enabled()=False` |
| ② | 不输出 `engineering_approved` | 5 个新服务 `_FORBIDDEN` 含 `engineering_approved`；访问该属性抛 `EnterpriseRedLineViolationError` | ✅ 无输出路径（`"engineering_approved" not in Service.__dict__`） |
| ③ | 禁止 AI 自动改/并/发/用知识 | `agent_version.py` / `agent_lifecycle_service.py` `_FORBIDDEN` 含 `auto_update_knowledge` / `auto_publish_knowledge` / `auto_merge_knowledge` / `publish` / `apply` / `commit` / `write` 等 | ✅ 无自动写知识路径 |
| ④ | 禁止 AI 自动生成工程结论 | 各服务 `_FORBIDDEN` 含 `generate_engineering_conclusion` / `decide` / `auto_decision` 等；生命周期只编排不审批 | ✅ 无自动结论路径 |
| ⑤ | 无自动审批 | `AuditService` 无 `record_human_approval`；`activate` / `deprecate` 必经 `require_human_actor(USER)` | ✅ |
| ⑥ | AI 不代替人工责任 | Agent 激活/弃用必经真实 USER；`activate(actor_kind=AI)` / `deprecate(actor_kind=AI)` 抛 `EnterpriseRedLineViolationError`；审计 actor 真实、无 `record_human_approval` | ✅ |

- **审计枚举数量**：`len(AuditActionCategory) == 32`（3.8.12 为 29，本层 +3）。
- **无 `record_human_approval` 方法**：`"record_human_approval" not in AuditService.__dict__` ✅。
- **组织隔离**：跨域访问抛 `EnterpriseIsolationError`；越权访问抛 `EnterpriseRedLineViolationError`。
- **AI 不得自动激活/弃用 Agent**：`AgentLifecycleService.activate(actor_kind=AI)` / `deprecate(actor_kind=AI)` 抛 `EnterpriseRedLineViolationError`（已由 `test_red_line_ai_cannot_activate_agent` / `test_red_line_ai_cannot_deprecate_agent` 验证）。

---

## 7. 激活状态声明

- **`engineering_enabled = false`**（未变更，fail-closed 红线①）：所有真实工程参数 / 尺寸确认 / 报价 / 代签路径保持 fail-closed；激活须经主理人 + 专家线下提交真实证据后由人类终端显式置 `enabled=true`。
- **本层只承载「智能体能力注册与治理」**：注册/声明/版本/权限/生命周期**绝不**自动激活 Agent、绝不自动写知识库、绝不自动生成工程结论、绝不自动审批、绝不 AI 代责（红线③/④/⑤/⑥）；Agent 激活/弃用须经真实 USER。
- **`AuditActionCategory`**：累计 32（3.8.13 +3）。
- **`project_status.json`**：新增 `phase_3_8_13_status = ENTERPRISE_AGENT_GOVERNANCE_BUILT_NO_GO`；`phase` 推进至 `3.8.13`（更新见 `roadmap_v8.md` §16）。
- **下一步**：**STOP。不进入 Phase 3.8.14。等待主理人审核。**

---

*报告生成：BOIP AI Chief Architect · 2026-08-06*
