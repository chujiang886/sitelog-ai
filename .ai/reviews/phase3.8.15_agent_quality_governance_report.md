# Phase 3.8.15 收口报告 —— Enterprise Agent Evaluation & Quality Governance Layer（企业智能体评估与质量治理层）

- **收口时间**：2026-08-06
- **状态**：🟢 BUILT_NO_GO（构建完成、fail-closed 守约、等待主理人审核）
- **授权**：BOIP AI Chief Architect（轩哥授权），11 任务 #634–#644，全程 6 条最高红线 fail-closed
- **激活态**：`engineering_enabled=false`，不输出 `engineering_approved`，不 AI 自动评级/禁用/修改/升级 Agent，不 AI 代责

---

## 1. 阶段目标

在 Phase 3.8.13（Agent 能力注册与治理层）与 Phase 3.8.14（Agent 可观测性与性能智能层）建立的 `AgentPermissionPolicy` + `AgentLifecycleService` + `IdentityService` + `AgentObservabilityService` 基座之上，新增 **Agent 质量治理层**，覆盖「运行数据 → 质量分析 → 人工评价 → 版本改进」的治理主线：

1. Agent 质量指标（`AgentQualityMetric`）——只登记**事实计数**（任务数 / 成功数 / 正向反馈 / 负向反馈 / 评价数 / 平均响应耗时），归一化枚举、负值裁剪为 0，无评价/评级字段；
2. Agent 人工评价（`AgentEvaluation`）——**强制人工责任**（evaluator 为 `ai`/`system`/空即抛 `EnterpriseRedLineViolationError`），AI 不评级；
3. Agent 版本对比（`AgentVersionComparison`）——只算**事实 delta**（指标增减），不替管理/工程做升级决策；强 `SourceTrace` 可溯源；
4. Agent 反馈（`AgentFeedback`）——用户反馈只登记、**恒 `requires_human_review=True`**，绝不自动处置 Agent；
5. Agent 质量报告（`AgentQualityReport`）——强 `SourceTrace`、无来源即抛错、只汇编事实、绝不输出工程结论；
6. 审计增强（+3 枚举 `AGENT_QUALITY`/`AGENT_EVALUATION`/`AGENT_FEEDBACK`，累计 35→38）；
7. 权限接入（`IdentityService` + `AgentPermissionPolicy` + 知识可见性策略做质量数据权限隔离，默认拒绝）；
8. 在 `EnterpriseOperationLayer` 聚合装配（`self.agent_quality_governance`），与 `agent_observability`/`agent_registry`/`agent_permission_policy` 共享同一 `audit`/`identity`/`knowledge_visibility`/`agent_permission_policy` 实例。

**边界（红线）**：本层只登记、汇编、对比**事实**，绝不评价/评级/禁用/修改/升级 Agent，绝不开启工程计算、绝不输出 `engineering_approved`，所有「评价/审核」责任节点必经真实 USER。

---

## 2. 架构设计

```
EnterpriseOperationLayer (agents/enterprise/service.py)
├── identity            : IdentityService(org_id)
├── audit               : AuditService(org_id)            ← 共享同一实例
├── agent_permission_policy : AgentPermissionPolicy(org_id)   ← 3.8.13 基座
├── agent_registry      : AgentLifecycleService(...)      ← 3.8.13 基座
├── knowledge_visibility: KnowledgeVisibilityPolicy(...)  ← 复用
├── agent_observability : AgentObservabilityService(...)  ← 3.8.14 基座
└── agent_quality_governance : AgentQualityGovernanceService(   ← 本层新增聚合入口
        org_id, audit, identity, visibility,
        permission_policy=self.agent_permission_policy)
        ├── record_quality_metric / list_quality_metrics → AgentQualityMetric
        ├── submit_evaluation(require_human_actor USER)   → AgentEvaluation
        │     └── list_evaluations
        ├── compare_versions(agent_id, a, b, ids)         → AgentVersionComparison（只算 delta 事实）
        ├── submit_feedback / review_feedback(require_human_actor USER)
        │     └── list_feedbacks                          → AgentFeedback
        └── generate_quality_report(...)                  → AgentQualityReport（强 SourceTrace）
```

### 可溯源与 fail-closed 基座
- 全部 5 模型 + 1 服务继承 `_RedLineForbiddenMixin`（`agents/enterprise/red_line.py`）：
  - 构造/写路径断言 `safety_invariants_ok()`（读 `load_engineering_enabled()` 须为 `False`，否则抛 `EnterpriseRedLineViolationError`）；
  - `_FORBIDDEN` 方法名经 `__getattr__` 拦截，**访问即抛 `EnterpriseRedLineViolationError`**（非 `AttributeError`），覆盖 `approve`/`engineering_approved`/`quote`/`pricing`/`sign`/`authorize`/`record_human_approval` + **评级类**（`auto_rate_agent`/`auto_grade_agent`/`auto_score_agent`/`rate_agent`/`grade_agent`/`score_agent`/`evaluate_agent`/`judge_agent`）+ **禁用类**（`auto_disable_agent`/`auto_deprecate_agent`/`disable_agent`/`deprecate_agent`/`auto_deactivate`/`deactivate_agent`/`auto_retire`/`retire_agent`）+ **修改类**（`auto_modify_agent`/`modify_agent`/`auto_update_agent`/`update_agent`/`auto_edit_agent`/`edit_agent`/`change_agent`）+ **升级决策类**（`auto_upgrade`/`recommend_upgrade`/`decide_upgrade`/`promote_version`/`auto_promote`/`make_management_decision`/`recommend`/`decide`）；
  - 质量数据读取经 `_ensure_access` → `AgentPermissionPolicy.check_agent_access(..., required_permission=Permission.READ_RESOURCE)`，**默认拒绝**。
- `SourceTrace` 范式（复用 `data_insight.py`）：`raw_refs`/`source_metric`/`source_workflow`/`source_event`；`is_traceable` getter。`AgentVersionComparison.__post_init__` 与 `AgentQualityReport.__post_init__` 强制 `source_trace.is_traceable` 否则抛 `EnterpriseRedLineViolationError`。
- `AgentQualityMetric.__post_init__`：归一化枚举 + 负值裁剪为 0。
- `AgentEvaluation.__post_init__`：拦截 `evaluator in ("ai","system")` 或空（AI/系统不得作为评价主体）。
- `AgentFeedback.__post_init__`：强制 `requires_human_review=True`（即便传入 `False` 也被改回 `True`）。
- `submit_evaluation` / `review_feedback` 调 `require_human_actor(AuditActorKind.USER)` 强制真实人工责任节点（红线⑥）。
- 审计只记真实 actor，无 `record_human_approval`（红线⑥：不提供「代记人工批准」入口）。

---

## 3. 代码文件清单

| 类型 | 路径 |
|---|---|
| 质量治理核心（5 模型 + 1 服务，705 行，7 导出符号） | `agents/enterprise/agent_quality_governance.py`（`AgentQualityMetricType`/`AgentQualityMetric`/`AgentEvaluation`/`AgentVersionComparison`/`AgentFeedback`/`AgentQualityReport`/`AgentQualityGovernanceService`） |
| 审计扩展（任务6 #639） | `agents/enterprise/audit.py`：+3 枚举（`AGENT_QUALITY`/`AGENT_EVALUATION`/`AGENT_FEEDBACK`，累计 35→**38**）；+3 记录方法 `record_agent_quality_action`(L1297)/`record_agent_evaluation_action`(L1325)/`record_agent_feedback_action`(L1352) |
| 权限基座（任务7，复用 3.8.13） | `agents/enterprise/agent_permission_policy.py`（`AgentPermissionPolicy`，默认拒绝）+ `identity.py`（`IdentityService`）+ `agent_lifecycle_service.py`（`AgentLifecycleService`） |
| 服务装配（任务7 #640） | `agents/enterprise/service.py`（`EnterpriseOperationLayer` 新增 `self.agent_quality_governance`，L371–375，注入共享 `agent_permission_policy`）+ `__init__.py`（`EnterpriseOperationLayer` 导出不变） |
| 测试（任务8 #641，八类 29 用例） | `tests/agents/test_enterprise_agent_quality_governance.py` |
| 测试计数修正（2 文件，因 35→38） | `tests/agents/test_enterprise_knowledge_governance_audit.py`（`EXPECTED_CATEGORIES` 35→38 项 + 断言 35→38）、`tests/agents/test_enterprise_knowledge_intelligence_audit.py`（`test_total_audit_categories_35` → `_38`，断言 35→38） |

> 说明：任务1–5（模型与服务）、任务6（审计）、任务7（装配）由 prior session 落地；本会话做只读复核 + 红线核对，并新建测试（任务8 #641）、最终验证（任务9 #642）、收口报告（任务10 #643）、状态刷新（任务11 #644）。

---

## 4. 任务完成情况（#634–#644）

| 任务 | 内容 | 状态 |
|---|---|---|
| #634 | `AgentQualityMetric` 模型（归一化枚举、负值裁剪 0、无评价字段） | ✅ 完成 |
| #635 | `AgentEvaluation` 模型（evaluator 非 ai/system/空 拦截、强制人工责任） | ✅ 完成 |
| #636 | `AgentVersionComparison`（只算 delta 事实、强 `SourceTrace`、不做升级决策） | ✅ 完成 |
| #637 | `AgentFeedback` 模型（`requires_human_review=True` 强制、只登记不处置） | ✅ 完成 |
| #638 | `AgentQualityReport`（强 `SourceTrace`、无来源即拒、只汇编事实） | ✅ 完成 |
| #639 | 审计增强 +3 枚举（AGENT_QUALITY/AGENT_EVALUATION/AGENT_FEEDBACK，累计 35→**38**）+ 3 记录方法 | ✅ 完成 |
| #640 | 权限接入 `IdentityService` + `AgentPermissionPolicy`（经 `EnterpriseOperationLayer` 聚合 `self.agent_quality_governance`，共享 `audit`/`identity`/`knowledge_visibility`/`agent_permission_policy`） | ✅ 完成 |
| #641 | 八类测试（quality_metric/evaluation/version_comparison/feedback/report/permission/audit/red line）共 **29 用例** | ✅ 完成（本会话） |
| #642 | 最终验证 `pytest tests/agents -q` 全过 + 确认红线 | ✅ 完成（本会话：1458 passed；`engineering_enabled=false`；无 `engineering_approved`） |
| #643 | 收口报告（本文件，7 节） | ✅ 完成（本会话） |
| #644 | 更新 `project_status.json` + `roadmap_v8.md`，完成后 STOP | ✅ 完成（本会话：`current_stage.phase_3_8_15_status=BUILT_NO_GO` + `agents_pytest`=1458；`roadmap_v8.md` §18 已追加） |

---

## 5. 测试结果

### 5.1 本层新增测试（`test_enterprise_agent_quality_governance.py`，29 用例全绿）
八类覆盖：
- **quality_metric（4）**：枚举归一化、负值裁剪为 0、无评价/评级字段、`record_quality_metric` 注入 `org_id` 并可列；
- **evaluation（3）**：`evaluator="ai"`/`"system"`/空 抛红线违例、人工 `evaluator="user"` 可登记、`submit_evaluation` 经 `require_human_actor(USER)`；
- **version_comparison（4）**：只算 delta 事实（`compare_versions` 两版本指标增减正确）、强 `SourceTrace`（空/无溯源抛违例）、不做升级决策（无 `recommend_upgrade`/`decide_upgrade` 可达）、跨 org 隔离抛错；
- **feedback（3）**：`requires_human_review=True` 强制（即便传入 `False` 也被改回）、`submit_feedback` 只登记不处置、`review_feedback` 经 `require_human_actor(USER)`；
- **report（3）**：无/空 `SourceTrace` 抛违例、`generate_quality_report` 只汇编事实、12 个评价/优化方法访问即抛违例；
- **permission（3）**：EXPERT 读质量数据默认拒绝、ADMIN 允许、`AgentPermissionPolicy.check_agent_access` EXPERT→data False / ADMIN→data True；
- **audit（3）**：三类审计各 1 条、`AGENT_QUALITY`/`AGENT_EVALUATION`/`AGENT_FEEDBACK` 枚举存在且 value 正确、累计 `len(AuditActionCategory)==38`、评价记录为 USER actor 且无 `record_human_approval`；
- **red line（6）**：`safety_invariants_ok()` 启用态为 True、`engineering_enabled=true` 时构造器抛违例、28 个 forbidden 方法（含评级/禁用/修改/升级类）访问即抛违例、`engineering_approved` 不可访问且不在 `__all__`、层聚合 `agent_quality_governance` 接入、端到端 度量→评价(USER)→对比→反馈→报告 全程 `safety_invariants_ok()` True。

### 5.2 全量回归（`backend/.venv/bin/python -m pytest tests/agents -q`）
- **结果：1458 passed（零失败，2026-08-06 实测）**。
- 基线：Phase 3.8.14 = 1429 passed；本层新增 29 用例 → 1458。
- 修复 2 个 prior-phase 过期断言（3.8.14 遗留的 `== 35` 计数，因本层 +3 枚举变 38，已刷新为 38）。
- 未修改 `verified.json` / `config.yaml` / `engineering_enabled`；`engineering_enabled=false`；不输出 `engineering_approved`。

---

## 6. 六大红线验证（fail-closed，全程守约）

| # | 红线 | 验证方式与结果 |
|---|---|---|
| ① | 禁止开启 `engineering_enabled` | `load_engineering_enabled()` 读 `config.yaml:102` = **false**；构造/写路径断言 `safety_invariants_ok()`（False 才放行），`monkeypatch` 启用态后构造器抛 `EnterpriseRedLineViolationError`（测试已覆盖）。 |
| ② | 禁止输出 `engineering_approved` | `agent_quality_governance.py` 的 `_FORBIDDEN` 含 `engineering_approved`；`getattr(svc, "engineering_approved")` 抛 `EnterpriseRedLineViolationError`；不在 `__all__`；程序化探针确认「blocked → EnterpriseRedLineViolationError (good)」。 |
| ③ | 禁 Agent 自动评级/打分/评价 | `_FORBIDDEN` 覆盖 `auto_rate_agent`/`auto_grade_agent`/`auto_score_agent`/`rate_agent`/`grade_agent`/`score_agent`/`evaluate_agent`/`judge_agent`；访问即抛错（测试覆盖 28 个 forbidden 方法）。 |
| ④ | 禁止 Agent 自动禁用/弃用/修改/升级 | `_FORBIDDEN` 覆盖 `auto_disable_agent`/`auto_deprecate_agent`/`disable_agent`/`deprecate_agent`/`auto_deactivate`/`deactivate_agent`/`auto_retire`/`retire_agent`/`auto_modify_agent`/`modify_agent`/`auto_update_agent`/`update_agent`/`auto_edit_agent`/`edit_agent`/`change_agent`/`auto_upgrade`/`recommend_upgrade`/`decide_upgrade`/`promote_version`/`auto_promote`/`make_management_decision`/`recommend`/`decide`；反馈/评价只候选，绝不自动处置或改动 Agent。 |
| ⑤ | 禁 AI 自动审批 / 自动责任 | `AuditService` 无 `record_human_approval`；评价/反馈复核必经 `require_human_actor(USER)`；无「代记人工批准」入口。 |
| ⑥ | 禁 AI 代替专家责任 | 审计只记真实 actor（USER/AI），评价主体强制非 ai/system；反馈 `requires_human_review=True` 强制；质量数据读取默认拒绝（专家无权越界读）。 |

**六红线全部 fail-closed 验证通过。**

---

## 7. 激活状态声明

- **当前激活态**：🟢 **BUILT_NO_GO**。`engineering_enabled=false`（真实读取 `agents/config.yaml:102`）；ESW 窗口维持 OPEN 态，等待主理人 + 专家线下提交真实证据后经人类终端显式置 `enabled=true`。
- **本层不产出**：不开启工程计算、不输出 `engineering_approved`、不 AI 自动评级/禁用/修改/升级 Agent、不写真实工程参数、不报价、不自动审批。
- **AI 角色边界**：只登记/汇编/对比**可溯源事实**；人工评价须真实 USER；用户反馈只登记、恒 `requires_human_review=True`；质量报告强 `SourceTrace`、无来源即拒。
- **未完成（人工动作，pending_verification）**：真实 Agent 运行质量数据录入、`verified.json` 真实化、`engineering_enabled` 开启、真实工程参数、报价、自动审批均待主理人 + 专家线下执行。
- **下一步**：本报告（#643）与状态/路线图刷新（#644）完成后 **STOP，不进入 Phase 3.8.16**，等待主理人审核授权。
