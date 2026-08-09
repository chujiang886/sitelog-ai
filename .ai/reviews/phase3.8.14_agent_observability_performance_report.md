# Phase 3.8.14 收口报告 —— Enterprise Agent Observability & Performance Intelligence Layer（企业智能体可观测性与性能智能层）

- **收口时间**：2026-08-06
- **状态**：🟢 BUILT_NO_GO（构建完成、fail-closed 守约、等待主理人审核）
- **授权**：BOIP AI Chief Architect（轩哥授权），11 任务 #623–#633，全程 6 条最高红线 fail-closed
- **激活态**：`engineering_enabled=false`，不输出 `engineering_approved`，不自动审批、不 AI 代责、不 Agent 自改/自激活

---

## 1. 阶段目标

在 Phase 3.8.13（Agent 能力注册与治理层）建立的 `AgentPermissionPolicy` + `AgentLifecycleService` + `IdentityService` 基座之上，新增 **Agent 执行可观测性与性能智能层**，覆盖：

1. Agent 执行日志（`AgentExecutionLog`）的可追踪登记与读取；
2. Agent 运行指标（`AgentMetric`）与指标派生（`derive_metrics`）——只算事实（调用次数 / 成功率 / 平均耗时），不评价、不打分、不评级；
3. Agent 调用链追踪（`AgentTrace`）——记录父子 span，可溯源；
4. Agent 健康检测（`AgentHealthCandidate`）——异常模式只产出「待人工研判候选」，恒 `requires_human_review=True`，绝不自动处置（禁 disable/auto_fix/restart/kill 等）；
5. Agent 性能报告（`AgentPerformanceReport`）——强 `SourceTrace` 可溯源，无来源即抛错，报告只汇编事实、不优化、不决策；
6. 审计增强（+3 枚举 `AGENT_METRIC`/`AGENT_TRACE`/`AGENT_HEALTH`，累计 32→35）；
7. 权限接入（`IdentityService` + `AgentPermissionPolicy` + 知识可见性策略做监控数据权限隔离，默认拒绝）；
8. 在 `EnterpriseOperationLayer` 聚合装配（`self.agent_observability`），与既有 `agent_permission_policy`/`agent_registry` 共享同一 `audit`/`identity`/`knowledge_visibility` 实例。

**边界（红线）**：本层只登记、读取、派生、报告**事实**，绝不评价/评级/禁用/优化/审批 Agent，绝不开启工程计算、绝不输出 `engineering_approved`。

---

## 2. 架构设计

```
EnterpriseOperationLayer (agents/enterprise/service.py)
├── identity            : IdentityService(org_id)
├── audit               : AuditService(org_id)            ← 共享同一实例
├── agent_permission_policy : AgentPermissionPolicy(org_id)   ← 3.8.13 基座
├── agent_registry      : AgentLifecycleService(...)      ← 3.8.13 基座
├── knowledge_visibility: KnowledgeVisibilityPolicy(...)  ← 复用
└── agent_observability : AgentObservabilityService(      ← 本层新增聚合入口
        org_id, audit, identity, visibility,
        permission_policy=self.agent_permission_policy)
        ├── record_execution / list_executions   → AgentExecutionLog
        ├── record_metric  / list_metrics        → AgentMetric
        ├── record_trace    / list_traces          → AgentTrace
        ├── derive_metrics(agent_id, period, ids)  → 事实三算
        ├── detect_health(...)                     → AgentHealthDetector
        │     └── AgentHealthCandidate(requires_human_review=True 强制)
        └── generate_report(...)                   → AgentPerformanceReportService
              └── AgentPerformanceReport(__post_init__ 强 SourceTrace)
```

### 可溯源与 fail-closed 基座
- 全部 5 模型 + 3 服务/检测器继承 `_RedLineForbiddenMixin`（`agents/enterprise/red_line.py`）：
  - 构造/写路径断言 `safety_invariants_ok()`（读 `load_engineering_enabled()` 须为 `False`，否则抛 `EnterpriseRedLineViolationError`）；
  - `_FORBIDDEN` 方法名经 `__getattr__` 拦截，**访问即抛 `EnterpriseRedLineViolationError`**（非 `AttributeError`），覆盖 `approve`/`engineering_approved`/`quote`/`pricing`/`sign`/`authorize`/`record_human_approval` + 禁用类方法（如 `disable_agent`/`auto_optimize`/`evaluate_agent`/`resolve`/`fix`/`close` 等）；
  - 监控数据读取经 `_ensure_access` → `AgentPermissionPolicy.check_agent_access(..., required_permission=Permission.READ_RESOURCE)`，**默认拒绝**。
- `SourceTrace` 范式（复用 `data_insight.py`）：`raw_refs`/`source_metric`/`source_workflow`/`source_event`；`is_traceable` getter；`summary()`。`AgentPerformanceReport.__post_init__` 强制 `source_trace.is_traceable` 否则抛 `EnterpriseRedLineViolationError`。
- `AgentHealthCandidate.__post_init__` 强制 `requires_human_review=True`（即便传入 `False` 也被改回 `True`）。
- 审计只记真实 actor（默认 `AI_ACTION`/`USER_ACTION`），无 `record_human_approval`（红线⑥：不提供「代记人工批准」入口）。

---

## 3. 代码文件清单

| 类型 | 路径 |
|---|---|
| 可观测性核心（5 模型 + 3 服务/检测器，917 行，10 导出符号） | `agents/enterprise/agent_observability.py` |
| 审计扩展（任务6） | `agents/enterprise/audit.py`：+3 枚举（`AGENT_METRIC`/`AGENT_TRACE`/`AGENT_HEALTH`，L102–104）→ 累计 **35**；+3 记录方法 `record_agent_metric_action`(L1201)/`record_agent_trace_action`(L1229)/`record_agent_health_action`(L1256) |
| 权限基座（任务7，复用 3.8.13） | `agents/enterprise/agent_permission_policy.py`（`AgentPermissionPolicy`，默认拒绝）+ `identity.py`（`IdentityService`）+ `agent_lifecycle_service.py`（`AgentLifecycleService`） |
| 服务装配（任务7） | `agents/enterprise/service.py`（`EnterpriseOperationLayer` 新增 `self.agent_observability`，L359–362，注入共享 `agent_permission_policy`）+ `__init__.py`（`EnterpriseOperationLayer` 导出不变） |
| 测试（任务8，八类 29 用例） | `tests/agents/test_enterprise_agent_observability.py` |
| 测试计数修正（2 文件，因 32→35） | `tests/agents/test_enterprise_knowledge_governance_audit.py`（`EXPECTED_CATEGORIES` 32→35 项 + 断言 32→35）、`tests/agents/test_enterprise_knowledge_intelligence_audit.py`（`test_total_audit_categories_32` → `_35`，断言 32→35） |

> 说明：`agent_observability.py` 由 prior session 落地（任务1–5 + 聚合），本会话仅做只读复核 + 红线核对；任务8 测试为本会话新建并修复（详见 §5）。

---

## 4. 任务完成情况（#623–#633）

| 任务 | 内容 | 状态 |
|---|---|---|
| #623 | `AgentExecutionLog` 模型（status 默认 SUCCESS、`is_successful` getter、字符串归一枚举、记录时注入 `org_id`） | ✅ 完成 |
| #624 | `AgentMetric` 模型（成功率裁剪 [0,1]、无 verdict/score/rating/grade 评价字段） | ✅ 完成 |
| #625 | `AgentTrace` 模型（root/leaf 标记、可溯源） | ✅ 完成 |
| #626 | `AgentHealthDetector` → `AgentHealthCandidate`（异常模式只产出候选、`requires_human_review=True` 强制、16 个处置方法禁用） | ✅ 完成 |
| #627 | `AgentPerformanceReport`（强 `SourceTrace`、`anomaly_candidates` 只候选、12 个优化方法禁用） | ✅ 完成 |
| #628 | 审计增强 +3 枚举（AGENT_METRIC/AGENT_TRACE/AGENT_HEALTH，累计 32→**35**）+ 3 记录方法 | ✅ 完成 |
| #629 | 权限接入 `IdentityService` + `AgentPermissionPolicy`（经 `EnterpriseOperationLayer` 聚合 `self.agent_observability`，共享 `audit`/`identity`/`knowledge_visibility`） | ✅ 完成 |
| #630 | 八类测试（execution/metric/trace/health/report/permission/audit/red line）共 **29 用例** | ✅ 完成（本会话） |
| #631 | 最终验证 `pytest tests/agents -q` 全过 + 确认红线 | ✅ 完成（本会话：1429 passed；`engineering_enabled=false`；无 `engineering_approved`） |
| #632 | 收口报告（本文件，7 节） | ✅ 完成（本会话） |
| #633 | 更新 `project_status.json` + `roadmap_v8.md`，完成后 STOP | ✅ 完成（本会话：`current_stage.phase_3_8_14_status=BUILT_NO_GO` + `agents_pytest=1429`；`roadmap_v8.md` §17 已追加） |

---

## 5. 测试结果

### 5.1 本层新增测试（`test_enterprise_agent_observability.py`，29 用例全绿）
八类覆盖：
- **execution（3）**：默认 SUCCESS/`is_successful`、字符串归一枚举、记录时 `org_id` 注入；
- **metric（4）**：成功率裁剪 [0,1]、无评价字段、`derive_metrics` 四日志算出 call_count=4/success_rate≈0.75/avg_duration≈2.5、无日志抛红线违例；
- **trace（2）**：root/leaf 标记、记录后可列（含 org）；
- **health（5）**：`requires_human_review` 恒 True、`detect_health` 五日志三失败产出候选（evidence 含 failed=3）、需日志、跨 org 隔离抛错、16 个处置方法访问即抛违例；
- **report（3）**：无/空 `SourceTrace` 抛违例、`generate_report` 只汇编事实、12 个优化方法访问即抛违例；
- **permission（3）**：EXPERT 读监控数据默认拒绝、ADMIN 允许、`AgentPermissionPolicy.check_agent_access` EXPERT→data False / ADMIN→data True；
- **audit（3）**：四类审计各 1 条、`AGENT_METRIC/AGENT_TRACE/AGENT_HEALTH` 枚举存在且 value 正确、健康记录为 AI actor 且无 `record_human_approval`；
- **red line（6）**：`safety_invariants_ok()` 启用态为 True、`engineering_enabled=true` 时三构造器抛违例、15 个 forbidden 方法访问即抛违例、`engineering_approved` 不可访问且不在 `__all__`、层聚合 `agent_observability` 接入、端到端 4 日志派生+报告全程 `safety_invariants_ok()` True。

### 5.2 全量回归（`backend/.venv/bin/python -m pytest tests/agents -q`）
- **结果：1429 passed（零失败，2026-08-06 实测约 40s）**。
- 基线：Phase 3.8.13 = 1400 passed；本层新增 29 用例 → 1429。
- 修复 2 个 prior-phase 过期断言（3.8.13 遗留的 `== 32` 计数，因本层 +3 枚举变 35，已刷新为 35）。
- 未修改 `verified.json` / `config.yaml` / `engineering_enabled`；`engineering_enabled=false`；不输出 `engineering_approved`。

---

## 6. 六大红线验证（fail-closed，全程守约）

| # | 红线 | 验证方式与结果 |
|---|---|---|
| ① | 禁止开启 `engineering_enabled` | `load_engineering_enabled()` 读 `config.yaml:102` = **false**；所有构造/写路径断言 `safety_invariants_ok()`（False 才放行），`monkeypatch` 启用态后三构造器均抛 `EnterpriseRedLineViolationError`（测试已覆盖）。 |
| ② | 禁止输出 `engineering_approved` | `agent_observability.py` 的 `_FORBIDDEN` 含 `engineering_approved`；`getattr(svc, "engineering_approved")` 抛 `EnterpriseRedLineViolationError`；不在 `__all__`；程序化探针确认「blocked → EnterpriseRedLineViolationError (good)」。 |
| ③ | 禁 Agent 自动改/并/发/用/优化自身 | `_FORBIDDEN` 覆盖 `disable_agent`/`auto_optimize`/`evaluate_agent`/`publish`/`apply`/`commit`/`write`/`auto_update`/`auto_modify`/`self_upgrade`；访问即抛错（测试覆盖 15 个 forbidden 方法）。 |
| ④ | 禁止 Agent 自动激活/处置 | `AgentHealthDetector` 16 个处置方法（`disable`/`auto_disable`/`deactivate`/`kill`/`suspend`/`restart`/`auto_fix`/`auto_heal`/`mitigate`/`resolve`/`fix`/`close`/`evaluate`/`rate`/`score`/`judge`）禁用；健康只产出 `requires_human_review=True` 候选，绝不自动处置。 |
| ⑤ | 禁 AI 自动审批 | `AuditService` 无 `record_human_approval`；健康/报告只候选、不审批；`human_review` 必经真实 USER。 |
| ⑥ | 禁 AI 代替专家责任 | 审计只记真实 actor（默认 AI/USER），无「代记人工批准」入口；健康候选 `requires_human_review=True` 强制；监控数据读取默认拒绝（专家无权越界读）。 |

**六红线全部 pass-closed 验证通过。**

---

## 7. 激活状态声明

- **当前激活态**：🟢 **BUILT_NO_GO**。`engineering_enabled=false`（真实读取 `agents/config.yaml:102`）；ESW 窗口维持 OPEN 态，等待主理人 + 专家线下提交真实证据后经人类终端显式置 `enabled=true`。
- **本层不产出**：不开启工程计算、不输出 `engineering_approved`、不自动审批、不 AI 代责、不 Agent 自改/自激活/自优化、不写真实工程参数、不报价。
- **AI 角色边界**：只登记/读取/派生/报告**可溯源事实**；异常只产出「待人工研判候选」；性能报告强 `SourceTrace`、无来源即拒。
- **未完成（人工动作，pending_verification）**：真实 Agent 运行遥测录入、`verified.json` 真实化、`engineering_enabled` 开启、真实工程参数、报价、自动审批均待主理人 + 专家线下执行。
- **下一步**：本报告（#632）与状态/路线图刷新（#633）完成后 **STOP，不进入 Phase 3.8.15**，等待主理人审核授权。
