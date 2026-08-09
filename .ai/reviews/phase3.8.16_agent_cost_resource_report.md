# Phase 3.8.16 收口报告 —— Enterprise Agent Cost & Resource Intelligence Layer（企业智能体成本与资源智能层）

- **收口时间**：2026-08-06
- **状态**：🟢 BUILT_NO_GO（构建完成、fail-closed 守约、等待主理人审核）
- **授权**：BOIP AI Chief Architect（轩哥授权），11 任务 #645–#655，全程 6 条最高红线 fail-closed
- **激活态**：`engineering_enabled=false`，不输出 `engineering_approved`，不 AI 自动关闭/停止/修改/优化 Agent，不 AI 代责，单价不编造

---

## 1. 阶段目标

在 Phase 3.8.13（`AgentPermissionPolicy` + `AgentLifecycleService` + `IdentityService`）与 Phase 3.8.14（`AgentObservabilityService`）+ Phase 3.8.15（`AgentQualityGovernanceService`）基座之上，新增 **Agent 成本与资源智能层**，覆盖「资源用量 → 成本换算 → 成本归属 → 周期对比 → 成本报告」的事实治理主线：

- 只登记/换算/对比/汇编**可溯源事实**，**绝不**评价、评级、报价、审批、自动关停/停止/修改/优化 Agent（红线③/④/⑤/⑥）。
- 成本**单价必须由外部 rate_card / 财务台账提供**，AI 不得编造或臆测（红线⑥）。
- 成本**数据权限隔离**（默认拒绝），专家越界读取即被隔离（红线⑥）。
- 成本归属 / 成本报告**来源强制可追溯**，禁 AI 创造无源成本数据（红线⑥）。

---

## 2. 架构设计

```
EnterpriseOperationLayer (agents/enterprise/service.py)
├── identity            : IdentityService(org_id)
├── audit               : AuditService(org_id)            ← 共享同一实例
├── agent_permission_policy : AgentPermissionPolicy(org_id)   ← 3.8.13 基座
├── knowledge_visibility: KnowledgeVisibilityPolicy(...)  ← 复用
├── agent_observability : AgentObservabilityService(...)  ← 3.8.14 基座
├── agent_quality_governance : AgentQualityGovernanceService(...)   ← 3.8.15 基座
└── agent_cost_resource : AgentCostResourceService(   ← 本层新增聚合入口
        org_id, audit, identity, visibility,
        permission_policy=self.agent_permission_policy)
        ├── record_resource_usage / list_resource_usages → AgentResourceUsage（只记事实）
        ├── record_cost_metric   / list_cost_metrics    → AgentCostMetric（只记事实）
        ├── record_cost_attribution / list_cost_attributions → AgentCostAttribution（可追踪归属）
        ├── aggregate_usage(...)   → AgentResourceAnalyzer.aggregate_usage（只求和/计数）
        ├── calculate_cost(rate_card, ...) → AgentResourceAnalyzer.calculate_cost（单价须外部台账）
        ├── compare_period(...)    → AgentResourceAnalyzer.compare_period（只算 delta）
        └── generate_cost_report(...) → AgentCostReport（强 SourceTrace、只汇编事实）
```

### 可溯源与 fail-closed 基座
- 全部 3 模型 + 1 分析器 + 1 服务继承 `_RedLineForbiddenMixin`（`agents/enterprise/red_line.py`）：
  - 构造/写路径断言 `safety_invariants_ok()`（读 `load_engineering_enabled()` 须为 `False`，否则抛 `EnterpriseRedLineViolationError`）；
  - `_FORBIDDEN` 方法名经 `__getattr__` 拦截，**访问即抛 `EnterpriseRedLineViolationError`**（非 `AttributeError`）。本层 `_COST_RESOURCE_FORBIDDEN` 在 3.8.15 基座之上**新增红线③/④/⑤/⑥ 拦截词**：
    - **红线③**（禁自动关停/停止 Agent）：`auto_disable_agent`/`auto_stop_agent`/`disable_agent`/`stop_agent`/`auto_shutdown_agent`/`shutdown_agent`/`kill_agent`/`terminate_agent`/`auto_suspend_agent`/`suspend_agent`/`auto_deactivate`/`deactivate_agent`；
    - **红线④**（禁自动改配置）：`auto_modify_agent`/`modify_agent`/`modify_agent_config`/`auto_configure_agent`/`configure_agent`/`set_agent_config`/`update_agent_config`/`auto_update_agent`/`update_agent`/`change_agent`；
    - **红线⑤**（禁自动优化资源策略）：`auto_optimize`/`auto_optimize_resource`/`optimize_resource`/`optimize_cost`/`optimize_agent`/`auto_tune`/`tune_resource`/`auto_scale`/`scale_agent`/`auto_throttle`/`throttle_agent`/`reduce_cost`/`cut_cost`/`set_budget`/`enforce_budget`/`allocate_budget`/`auto_allocate`/`apply_resource_policy`/`set_resource_policy`；
    - **红线⑥**（禁代替管理责任）：`make_management_decision`/`recommend`/`decide`；
    - 基座保留：`approve`/`engineering_approved`/`quote`/`pricing`/`sign`/`authorize`/`record_human_approval`。
  - 成本数据读取经 `_ensure_access` → `AgentPermissionPolicy.check_agent_access(..., required_permission=Permission.READ_RESOURCE)`，**默认拒绝**（红线⑥：成本数据受控访问）。
- `SourceTrace` 范式（复用 `data_insight.py`）：`raw_refs`/`source_metric`/`source_workflow`/`source_event`；`is_traceable` getter。`AgentCostReport.__post_init__` 强制 `source_trace.is_traceable` 否则抛 `EnterpriseRedLineViolationError`；`generate_cost_report` 聚合后亦校验溯源链。
- `AgentResourceUsage.__post_init__`：归一化枚举 + 负值裁剪为 0 + 空单位按资源类型补默认单位。
- `AgentCostMetric.__post_init__`：归一化枚举 + 负值裁剪为 0。
- `AgentCostAttribution.__post_init__`：强制「至少一归属对象（project_id / task_id）」且「有来源（source 非空或 source_trace.is_traceable）」，二者缺一即抛 `EnterpriseRedLineViolationError`（禁 AI 生成无源/无对象成本分摊，红线⑥）。
- `AgentResourceAnalyzer.calculate_cost`：单价台账缺失即抛 `EnterpriseRedLineViolationError`（AI 不得编造单价或以 0 充数，红线⑥）；负单价亦拒。
- 审计只记真实 actor，无 `record_human_approval`（红线⑥：不提供「代记人工批准」入口）。

---

## 3. 代码文件清单

| 类型 | 路径 |
|---|---|
| 成本与资源核心（3 模型 + 1 分析器 + 1 报告 + 1 服务，924 行，8 导出符号） | `agents/enterprise/agent_cost_resource.py`（`AgentResourceType`/`AgentCostType`/`AgentResourceUsage`/`AgentCostMetric`/`AgentCostAttribution`/`AgentResourceAnalyzer`/`AgentCostReport`/`AgentCostResourceService`） |
| 审计扩展（任务6 #650） | `agents/enterprise/audit.py`：+3 枚举（`AGENT_RESOURCE`/`AGENT_COST`/`AGENT_COST_REPORT`，累计 38→**41**）；+3 记录方法 `record_agent_resource_action`(L1397)/`record_agent_cost_action`(L1424)/`record_agent_cost_report_action`(L1451) |
| 权限基座（任务7 #651，复用 3.8.13） | `agents/enterprise/agent_permission_policy.py`（`AgentPermissionPolicy`，默认拒绝）+ `identity.py`（`IdentityService`）+ `organization.py`（`EnterpriseIsolationError`） |
| 服务装配（任务7 #651） | `agents/enterprise/service.py`（`EnterpriseOperationLayer` 新增 `self.agent_cost_resource`，L371 之后，注入共享 `audit`/`identity`/`knowledge_visibility`/`agent_permission_policy`）+ `__init__.py`（新增 8 符号导出） |
| 测试（任务8 #652，八类 30 用例） | `tests/agents/test_enterprise_agent_cost_resource.py` |
| 测试计数修正（3 文件，因 38→41） | `tests/agents/test_enterprise_knowledge_governance_audit.py`（`EXPECTED_CATEGORIES` +3 项 / 断言 38→41）+ `tests/agents/test_enterprise_knowledge_intelligence_audit.py`（`test_total_audit_categories_38`→`_41`）+ `tests/agents/test_enterprise_agent_quality_governance.py`（`test_audit_categories_present_and_count_38`→`_41`） |

> 说明：任务1–7（模型/分析器/报告/服务、审计、装配）由 prior session 落地；本会话补完审计枚举/方法（任务6）、service/`__init__` 装配（任务7 收口）、新建测试（任务8 #652）、最终验证（任务9 #653）、收口报告（任务10 #654）、状态刷新（任务11 #655），并修正 3 处 prior-phase 过期审计计数断言（38→41）。

---

## 4. 任务完成情况（#645–#655）

| 任务 | 内容 | 状态 |
|---|---|---|
| #645 | `AgentResourceUsage` 模型（归一化枚举、负值裁剪 0、默认单位、无优化/处置字段） | ✅ 完成 |
| #646 | `AgentCostMetric` 模型（token/compute/storage/external_api 四类、负值裁剪 0、无报价/审批字段） | ✅ 完成 |
| #647 | `AgentCostAttribution` 模型（可追踪归属：缺对象或缺来源即抛错、强 `is_traceable`） | ✅ 完成 |
| #648 | `AgentResourceAnalyzer`（aggregate_usage 只聚合、calculate_cost 单价须外部台账、compare_period 只算 delta，禁自动优化） | ✅ 完成 |
| #649 | `AgentCostReport`（强 `SourceTrace`、无来源即拒、只汇编事实）+ `AgentCostResourceService` 聚合入口 | ✅ 完成 |
| #650 | 审计增强 +3 枚举（AGENT_RESOURCE/AGENT_COST/AGENT_COST_REPORT，累计 38→**41**）+ 3 记录方法 | ✅ 完成（本会话收口） |
| #651 | 权限接入 `IdentityService` + `AgentPermissionPolicy`（经 `EnterpriseOperationLayer` 聚合 `self.agent_cost_resource`，共享 `audit`/`identity`/`knowledge_visibility`/`agent_permission_policy`） | ✅ 完成（本会话装配） |
| #652 | 八类测试（resource_usage/cost_metric/cost_attribution/analyzer/report/permission/audit/red line）共 **30 用例** | ✅ 完成（本会话） |
| #653 | 最终验证 `pytest tests/agents -q` 全过 + 确认红线 | ✅ 完成（本会话：1488 passed；`engineering_enabled=false`；无 `engineering_approved`） |
| #654 | 收口报告（本文件，7 节） | ✅ 完成（本会话） |
| #655 | 更新 `project_status.json` + `roadmap_v8.md`，完成后 STOP | ✅ 完成（本会话：`phase_3_8_16_status=BUILT_NO_GO` + `roadmap_v8.md` §19 已追加） |

---

## 5. 测试结果

### 5.1 本层新增测试（`test_enterprise_agent_cost_resource.py`，30 用例全绿）
八类覆盖：
- **resource_usage（4）**：枚举归一化 + 默认单位、负值裁剪为 0、无 budget/quota/limit/optimization 字段、`record_resource_usage` 注入 `org_id` 并可列；
- **cost_metric（4）**：枚举归一化、负值裁剪为 0、无 approved/quote/pricing 字段、`record_cost_metric` 注入 `org_id` 并可列；
- **cost_attribution（3）**：缺归属对象抛违例、缺来源抛违例、有对象+有来源（`source` 或 `source_trace.is_traceable`）通过、`is_traceable` 正确；
- **analyzer（4）**：`aggregate_usage` 只求和/计数（按 agent / type 维度）、`calculate_cost` 用外部 rate_card 换算且 source 携带 usage 链、缺 rate_card / 缺单价类型即抛违例（禁编造）、`compare_period` 只算 delta 且无 recommendation/verdict/action 字段；
- **report（3）**：无/空 `SourceTrace` 抛违例、`generate_cost_report` 只汇编事实、无 approved/optimize/reduce/disable/stop/decision 字段；
- **permission（3）**：EXPERT 读成本数据默认拒绝、ADMIN 允许、`AgentPermissionPolicy.check_agent_access` EXPERT→data False / ADMIN→data True；
- **audit（3）**：三类审计各就位、`AGENT_RESOURCE`/`AGENT_COST`/`AGENT_COST_REPORT` 枚举存在且 value 正确、累计 `len(AuditActionCategory)==41`、调用后审计记录就位且审计无 `record_human_approval`；
- **red line（6）**：`safety_invariants_ok()` 启用态为 True、`engineering_enabled=true` 时构造器抛违例、44 个 forbidden 方法（含红线③关停类/④改配置类/⑤优化类/⑥管理决策类）访问即抛违例、`engineering_approved` 不可访问且不在 `__all__`、层聚合 `agent_cost_resource` 接入、端到端 用量→成本换算(外部单价)→归属→报告 全程 `safety_invariants_ok()` True。

### 5.2 全量回归（`backend/.venv/bin/python -m pytest tests/agents -q`）
- **结果：1488 passed（零失败，2026-08-06 实测约 35s）**。
- 基线：Phase 3.8.15 = 1458 passed；本层新增 30 用例 → 1488。
- 修正 3 处 prior-phase 过期断言（3.8.15 遗留 `== 38` 计数，因本层 +3 枚举变 41，已刷新为 41；含 `test_enterprise_knowledge_governance_audit.py` / `test_enterprise_knowledge_intelligence_audit.py` / `test_enterprise_agent_quality_governance.py`）。
- 未修改 `verified.json` / `config.yaml` / `engineering_enabled`；`engineering_enabled=false`；不输出 `engineering_approved`。

---

## 6. 六大红线验证（fail-closed，全程守约）

| # | 红线 | 验证方式与结果 |
|---|---|---|
| ① | 禁止开启 `engineering_enabled` | `load_engineering_enabled()` 读 `config.yaml:102` = **false**；构造/写路径断言 `safety_invariants_ok()`（False 才放行），`monkeypatch` 启用态后 `AgentCostResourceService` / `AgentResourceAnalyzer` 构造器抛 `EnterpriseRedLineViolationError`（测试已覆盖）。 |
| ② | 禁止输出 `engineering_approved` | `agent_cost_resource.py` 的 `_FORBIDDEN` 含 `engineering_approved`；`getattr(svc, "engineering_approved")` 抛 `EnterpriseRedLineViolationError`；不在 `__all__`；程序化探针确认「blocked → EnterpriseRedLineViolationError (good)」。 |
| ③ | 禁 AI 自动关闭/停止 Agent | `_COST_RESOURCE_FORBIDDEN` 覆盖 `auto_disable_agent`/`auto_stop_agent`/`disable_agent`/`stop_agent`/`auto_shutdown_agent`/`shutdown_agent`/`kill_agent`/`terminate_agent`/`auto_suspend_agent`/`suspend_agent`/`auto_deactivate`/`deactivate_agent`；成本高 ≠ AI 可关停它，访问即抛错（测试覆盖 44 个 forbidden 方法）。 |
| ④ | 禁 AI 自动修改 Agent 配置 | `_COST_RESOURCE_FORBIDDEN` 覆盖 `auto_modify_agent`/`modify_agent`/`modify_agent_config`/`auto_configure_agent`/`configure_agent`/`set_agent_config`/`update_agent_config`/`auto_update_agent`/`update_agent`/`change_agent`；成本分析绝不改动 Agent 配置。 |
| ⑤ | 禁 AI 自动优化资源策略 | `_COST_RESOURCE_FORBIDDEN` 覆盖 `auto_optimize`/`auto_optimize_resource`/`optimize_resource`/`optimize_cost`/`optimize_agent`/`auto_tune`/`tune_resource`/`auto_scale`/`scale_agent`/`auto_throttle`/`throttle_agent`/`reduce_cost`/`cut_cost`/`set_budget`/`enforce_budget`/`allocate_budget`/`auto_allocate`/`apply_resource_policy`/`set_resource_policy`；`AgentResourceAnalyzer.calculate_cost` 只换算、绝不削减/优化。 |
| ⑥ | 禁 AI 代替管理责任 | 审计只记真实 actor（USER/AI），无 `record_human_approval`；成本单价须外部台账（缺即抛 `EnterpriseRedLineViolationError`，禁编造）；成本归属/报告来源强制可追溯（禁无源数据）；成本数据读取默认拒绝（专家越界即隔离）。 |

**六红线全部 fail-closed 验证通过。**

---

## 7. 激活状态声明

- **当前激活态**：🟢 **BUILT_NO_GO**。`engineering_enabled=false`（真实读取 `agents/config.yaml:102`）；ESW 窗口维持 OPEN 态，等待主理人 + 专家线下提交真实证据后经人类终端显式置 `enabled=true`。
- **本层不产出**：不开启工程计算、不输出 `engineering_approved`、不 AI 自动关闭/停止/修改/优化 Agent、不写真实工程参数、不报价、不编造单价、不自动审批。
- **AI 角色边界**：只登记/换算/对比/汇编**可溯源事实**；成本单价须由真实财务台账/rate_card 提供；成本归属与报告来源强制可追溯；成本数据读取默认拒绝。
- **未完成（人工动作，pending_verification）**：真实 Agent 运行资源/成本数据录入、`verified.json` 真实化、`engineering_enabled` 开启、真实单价台账接入、真实成本归属/报告均待主理人 + 专家线下执行。
- **下一步**：本报告（#654）与状态/路线图刷新（#655）完成后 **STOP，不进入 Phase 3.8.17**，等待主理人审核授权。
