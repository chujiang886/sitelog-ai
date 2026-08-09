# Phase 3.8.17 收口报告 —— Enterprise Agent Policy & Runtime Governance Layer（企业智能体策略与运行时治理层）

- **生成**：2026-08-06
- **身份**：BOIP AI Chief Architect（轩哥授权）
- **任务**：10 项（#656–#665）
- **红线**：6 条最高红线 fail-closed，全程守约
- **状态**：🟢 **ENTERPRISE_AGENT_RUNTIME_GOVERNANCE_BUILT_NO_GO**
- **依据**：`.ai/project_status.json`（`phase_3_8_17` 块 + `phase_3_8_17_status`）、`.ai/roadmap_v8.md` §20、真实源码 `agents/enterprise/agent_runtime_policy.py` + `audit.py` + `service.py` + `__init__.py`、`tests/agents/test_enterprise_agent_runtime_policy.py`
- **STOP 声明**：本报告与状态刷新完成后，**不进入 Phase 3.8.18**，等待主理人审核授权。

---

## 1. 概述

Phase 3.8.17 在 Phase 3.8.0~3.8.16 既有企业能力基座之上，构建 **Agent 策略与运行时治理层**：围绕「运行策略显式声明 → 执行前置核查 → 运行时判定事实记录 → 治理数据权限隔离 → 审计联动」的 fail-closed 主线，确保 AI **只登记事实、只检查、只记录、绝不批准、绝不修改策略、绝不自行放行工具、绝不代替管理责任**。

- **核心定位**：治理层（非激活、非工程计算）。新增 `AgentRuntimePolicy` / `AgentToolAccessPolicy` / `AgentExecutionGuard` / `RuntimeDecisionRecord` / `AgentRuntimeGovernanceService` 五个模型/服务组件（930 行，7 个导出符号 + `_RUNTIME_FORBIDDEN`）。
- **审计增强**：`AuditActionCategory` 新增 `AGENT_POLICY` / `AGENT_RUNTIME_CHECK` / `AGENT_TOOL_ACCESS`，累计 **41 → 44**；`AuditService` 新增 3 个记录方法，沿用「actor_kind 如实标注、禁止 `record_human_approval`」约定。
- **红线细化**：在 3.8.0 六条最高红线基础上，针对本层补全 ③AI 自动批准运行 / ④AI 自动修改策略 / ⑤AI 自动放行工具 / ⑥AI 代责 的 forbidden 方法名拦截清单，结构上不可达。

---

## 2. 交付物清单

| 类型 | 路径 | 说明 |
|---|---|---|
| 策略与运行时核心 | `agents/enterprise/agent_runtime_policy.py`（930 行） | `AgentRuntimePolicyStatus` / `RuntimeCheckOutcome` / `AgentRuntimePolicy` / `AgentToolAccessPolicy` / `RuntimeDecisionRecord` / `AgentExecutionGuard` / `AgentRuntimeGovernanceService` + `_RUNTIME_FORBIDDEN` |
| 审计扩展 | `agents/enterprise/audit.py`（L121–123 枚举 + L1490–1572 三方法） | `AGENT_POLICY` / `AGENT_RUNTIME_CHECK` / `AGENT_TOOL_ACCESS`（`record_agent_policy_action` / `record_agent_runtime_check_action` / `record_agent_tool_access_action`） |
| 权限基座（复用） | `agents/enterprise/agent_permission_policy.py` + `identity.py` + `organization.py` | `AgentPermissionPolicy.check_agent_access`（默认拒绝）/ `IdentityService` / `EnterpriseIsolationError` |
| 服务装配 | `agents/enterprise/service.py` + `__init__.py` | `EnterpriseOperationLayer.agent_runtime_governance` 注入共享 `audit`/`identity`/`knowledge_visibility`/`agent_permission_policy`；`__init__.py` 新增 7 符号导出 |
| 测试（本层） | `tests/agents/test_enterprise_agent_runtime_policy.py` | 七类 30 用例 |
| 测试计数修正 | `test_enterprise_knowledge_governance_audit.py` / `test_enterprise_knowledge_intelligence_audit.py` / `test_enterprise_agent_cost_resource.py` / `test_enterprise_agent_quality_governance.py` | 既有 `== 41` 审计类别计数断言刷新为 `== 44`（`EXPECTED_CATEGORIES` 同步扩充 3 项），保持套件绿 |
| 收口报告 | `.ai/reviews/phase3.8.17_agent_runtime_policy_governance_report.md` | 本报告（7 节） |
| 状态刷新 | `.ai/project_status.json`（`phase_3_8_17`） + `.ai/roadmap_v8.md` §20 | STOP 声明 |

---

## 3. 红线守约（fail-closed，6 条）

| 红线 | 机制 | 验证 |
|---|---|---|
| ① `engineering_enabled=false` | 构造/写路径断言 `safety_invariants_ok()` | `config.yaml:102` 仍为 `false`；`monkeypatch` 启用态后 `AgentRuntimeGovernanceService`/`AgentExecutionGuard` 构造即抛 `EnterpriseRedLineViolationError` |
| ② 不输出 `engineering_approved` | `_RUNTIME_FORBIDDEN` 含该名，`__getattr__` 拦截 | `getattr(svc, "engineering_approved")` 抛错；不在 `__all__` |
| ③ 禁 AI 自动批准 Agent 运行 | `approve_run`/`auto_approve_execution`/`allow_execution`/`bypass_policy`/`override_policy`/`force_run`/`grant_execution` 等被 `_RedLineForbiddenMixin` 拦截 | `AgentExecutionGuard` 只返回 `RuntimeCheckOutcome` 事实；访问 forbidden 方法名抛 `EnterpriseRedLineViolationError` |
| ④ 禁 AI 自动修改 Agent 策略 | `auto_update_policy`/`auto_apply_policy`/`auto_approve_policy`/`update_policy`/`modify_policy`/`auto_activate`/`rewrite_policy`/`activate_policy` 等被拦截；状态推进强制 `require_human_actor(USER)` | 构造期落 ACTIVE 直接抛错；`confirm_policy_active(actor_kind=AI)` 抛错；仅 `actor_kind=USER` 可推进 |
| ⑤ 禁 AI 自动放行工具访问 | `grant_tool_access`/`allow_tool_access`/`whitelist_tool`/`unlock_tool`/`elevate_tool_access`/`enable_tool` 等被拦截；`AgentToolAccessPolicy` 默认拒绝 | 空名/denied/空白名单一律 `is_tool_allowed=False`；模型无放行入口 |
| ⑥ AI 不代替管理责任 | 审计无 `record_human_approval`；人工确认节点强制 `require_human_actor(USER)`；`RuntimeDecisionRecord` 只陈述事实、缺 `source` 即拒落库 | `getattr(audit, "record_human_approval")` 抛错；`confirm_policy_active`/`confirm_policy_deprecated` 非 USER 即拒；`RuntimeDecisionRecord(source="")` 抛错 |

**结论**：六条红线在本层 10 项任务中全部以 fail-closed 方式结构性守约，无任何「AI 自动批准/修改/放行/代责」路径可达。

---

## 4. 测试（七类，30 用例）

`tests/agents/test_enterprise_agent_runtime_policy.py` 覆盖七类：

1. **policy**：构造落 ACTIVE 抛 `EnterpriseRedLineViolationError`；DRAFT/DEPRECATED 合法；`is_effective` 只读；`covers_rule`/`covers_scope` 默认拒绝。
2. **tool_access**：空名/denied 优先/空白名单一律拒绝；`check_tool` 返回 `RuntimeCheckOutcome`；模型无放行方法。
3. **guard**：`check_policy`/`check_permission`/`check_scope`/`check_tool_access` 只检查不批准、默认拒绝（无 ACTIVE 策略→FAIL；ADMIN+tool→PASS；EXPERT+tool→FAIL）。
4. **runtime_record**：缺 `source` 抛错；四项结论默认 FAIL；`all_checks_passed` 仅事实汇总≠批准；无 approve/allow/grant 方法。
5. **permission**：`_ensure_access` 对 EXPERT(data) 抛 `EnterpriseIsolationError`、对 ADMIN(data) 放行；`list_runtime_policies` 默认拒绝越权；`AgentPermissionPolicy.check_agent_access` 角色作用域校验。
6. **audit**：`AGENT_POLICY`/`AGENT_RUNTIME_CHECK`/`AGENT_TOOL_ACCESS` 三类别就位、累计 44；登记/确认生效/运行核查/工具核查均正确落审计且 `actor_kind` 如实标注；禁 `record_human_approval`。
7. **red_line**：`safety_invariants_ok()` 为 True；启用态构造 fail-closed；`confirm_policy_active(actor_kind=AI)` 抛错；forbidden 方法名（`auto_update_policy`/`grant_tool_access`/`approve_run`/`act_as_admin` 等）经 `__getattr__` 抛错；无 `engineering_approved` 输出；`EnterpriseOperationLayer` 正确装配且 `is_activation_safe()`。

**计数修正**：将 3.8.15/3.8.16 遗留的 4 处 `== 41` 审计类别断言刷新为 `== 44`（含 `EXPECTED_CATEGORIES` 集合扩充 3 项），保证历史套件同步绿。

---

## 5. 最终验证

- **命令**：`find tests -name '_tmp_drill_*' -delete; backend/.venv/bin/python -m pytest tests/agents -q`
- **结果**：**1518 passed in 35.32s，零回归**（基线 1488 + 本层 30）。
- **红线复核**：
  - `agents/config.yaml:102` → `engineering_enabled: false`（未修改）。
  - 源码中无 `engineering_approved` 取值/输出（仅 forbidden 引用）。
  - `verified.json` / `config.yaml` / `engineering_enabled` 均未改动。
- **测试解释器**：统一走 `backend/.venv/bin/python`（系统 `python` 因缺 `yaml` 模块不可用）。

---

## 6. 状态与激活态

- **本层状态**：🟢 `ENTERPRISE_AGENT_RUNTIME_GOVERNANCE_BUILT_NO_GO`（2026-08-06）。
- **激活态**：`engineering_enabled=False` 维持；ESW 窗口 `OPEN_EMPTY`；治理层只编排运行策略/核查事实，绝不开启工程计算。
- **SSOT 写入**：`project_status.json` 新增 `task_status.phase_3_8_17`（10 子任务，全 `BUILT_NO_GO`）+ 顶层 `phase_3_8_17_status=ENTERPRISE_AGENT_RUNTIME_GOVERNANCE_BUILT_NO_GO`；JSON 已校验可解析。
- **路线图**：`roadmap_v8.md` 新增 §20（任务/代码清单/红线/测试/交付物/状态结论/STOP）。

---

## 7. STOP 声明（等待主理人审核）

> **Phase 3.8.17 已收口（BUILT_NO_GO）。不进入 Phase 3.8.18。**

**未完成（人工动作，pending_verification，均待主理人+专家线下执行）**：
- 真实 Agent 运行策略录入，并由真实人工经 `confirm_policy_active(actor_kind=USER)` 确认生效；
- `verified.json` 真实化；`engineering_enabled` 显式置 `true`（须经人类终端显式操作）；
- 真实工程参数 / 报价 / 自动审批 录入与核准。

AI 在本层严格守约：**未开启 `engineering_enabled`、未输出 `engineering_approved`、未自动批准/修改策略/放行工具/代替管理责任**。审核通过后，由主理人决定是否推进 Phase 3.8.18。
