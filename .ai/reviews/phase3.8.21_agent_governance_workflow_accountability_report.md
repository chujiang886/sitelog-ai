# Phase 3.8.21 收口报告 —— Enterprise Agent Governance Workflow & Accountability Layer（企业智能体治理流程与责任闭环层）

| 项 | 值 |
| --- | --- |
| Phase | 3.8.21 |
| 身份 | BOIP AI Chief Architect |
| 状态 | `ENTERPRISE_AGENT_GOVERNANCE_WORKFLOW_BUILT_NO_GO` |
| 收口日期 | 2026-08-07 |
| 激活态 | `engineering_enabled = false`（未变更） |
| 全量测试 | `tests/agents` **1786 passed**（3.8.20 基线 1689 + 本 Phase 97 新增，零回归） |
| 审计类别 | 53 → **56**（+3） |

---

## 1. 概述

本 Phase 在既有的 3.8.13–3.8.20 全部治理层（注册 / 可观测 / 质量 / 成本 / 安全 / 合规 / 治理中枢）
之上，交付**治理流程与责任闭环层**。它把「治理发现 → 治理任务 → 责任人 → 人工处理 → 结果记录 →
治理闭环」这条链路，在**类型系统、结构层级、语义层级**三重维度上锁死为**纯人工责任闭环**，
让 AI 只能在事实层辅助、永远无法替代治理责任人：

```
治理发现（五层上游只读事实 / 人工上报）
   → create_task（AI 只建候选，无责任人、无完成态）
   → assign_owner（强制 require_human_actor(USER) + 责任人必为真实 USER）
   → start_processing（强制 USER）
   → submit_result（强制 USER + 结果必人工填写）
   → human_close（唯一闭环入口，强制 USER，生成 GovernanceClosureReport + 来源链）
```

本层定位是**治理工作流编排 + 责任闭环**，不是**治理裁决**：

- AI 可以：从治理发现创建候选任务、如实记录被观察到的处理动作、生成可溯源闭环报告草稿；
- AI 不可以：自动分配责任、自动整改风险、自动关闭任务、自动修改权限或策略、代替治理责任人签字。

与前序治理层最大的结构性差异在于**流程级就拒绝了「AI 代责」语义**：`GovernanceTask`
构造期 `requires_human_completion` **恒为 True**、`owner_id` 必空、`status` 只能落 `created`，
状态机**只前进不回退**，且**不存在任何 AI 终态**（无 `auto_completed` / `closed_by_ai`）；
`GovernanceClosureReport` 必须有可溯源 `source_trace` 与人工 `human_result`，且 `closed_by`
必为真实 USER。这些边界在**类型系统 + 结构拦截 + 语义拦截**三处同时生效。

上述边界通过 `_RedLineForbiddenMixin.__getattr__` 结构拦截（**98 个** forbidden 名）、
模型 `__post_init__` 强校验、语义级标记拦截（`_REMEDIATION_MARKERS` / `_ASSIGNMENT_MARKERS` /
`_PERMISSION_MARKERS` + `_reject_markers` / `_reject_non_human`），以及 `require_human_actor(USER)`
守卫在**结构上**不可达。

---

## 2. 交付物清单

| # | 交付物 | 路径 / 位置 | 说明 |
| --- | --- | --- | --- |
| 1 | `GovernanceTaskSourceType`（8 类事实来源） | `agents/enterprise/agent_governance_workflow.py` | `SECURITY_RISK` / `COMPLIANCE_RISK` / `RISK_OVERVIEW` / `GOVERNANCE_INSIGHT` / `QUALITY_ISSUE` / `COST_ANOMALY` / `OBSERVABILITY_ANOMALY` / `HUMAN_REPORTED`；**只描述事实发现，不含任何 AI 处置意图** |
| 2 | `GovernanceTaskStatus`（5 态） | 同上 | `CREATED` / `ASSIGNED` / `PROCESSING` / `WAITING_REVIEW` / `COMPLETED`；**无 AI 终态** |
| 3 | `GovernanceTask` | 同上 | task_id / source_type / source_id / owner_id / status / created_at / completed_at / org_id / agent_id / title / detail / created_by / closed_by / requires_human_completion；构造期强制 `requires_human_completion=True`、owner_id 空、无完成/关闭态、标题/说明禁整改/分配/改权限语义 |
| 4 | `GovernanceAssignment` | 同上 | assignment_id / task_id / assignee / role / timestamp / org_id / assigned_by / note；assignee 与 assigned_by 必为真实 USER（非人类标识即拒），note 禁自动分配/整改语义 |
| 5 | `GovernanceActionRecord` | 同上 | record_id / task_id / action / actor / timestamp / result / source / org_id / actor_kind；action/result 禁自动整改/改权限语义；`is_human_action` 如实标注 |
| 6 | `GovernanceClosureReport` | 同上 | report_id / task_id / org_id / agent_id / source_type / source_id / action_records / human_result / closed_by / closed_at / source_trace；无来源链 / 无人工结论 / 非人类 closed_by / 结论含整改语义即拒 |
| 7 | `GovernanceWorkflowService` | 同上 | `_FORBIDDEN = _GOVERNANCE_FORBIDDEN`；构造断言 `safety_invariants_ok()`；`create_task` / `assign_owner` / `start_processing` / `submit_result` / `human_close` / `record_observed_action` / 只读查询；AI 只建候选与登记事实，所有状态推进与闭环强制 USER |
| 8 | 审计增强（+3 类别 / +3 方法） | `agents/enterprise/audit.py` | `AGENT_GOVERNANCE_TASK` / `AGENT_GOVERNANCE_ACTION` / `AGENT_GOVERNANCE_CLOSURE`；累计 **56**；actor 如实（默认 AI、人工节点强制 USER）；禁 `record_human_approval` |
| 9 | 权限接入与装配 | `agents/enterprise/service.py`、`agents/enterprise/__init__.py` | `agent_governance_workflow` 接入 `IdentityService` + `AgentPermissionPolicy` + `AgentRuntimePolicy` + 3.8.20 治理中枢（只读消费）；治理数据读取**默认拒绝**（组织隔离）；`__init__.py` 新增 7 符号导出 |
| 10 | 八类测试（97 用例） | `tests/agents/test_enterprise_agent_governance_workflow.py` | task / assignment / action / workflow / closure / permission / audit / red_line（70 个测试函数，参数化展开后 97 用例） |
| 11 | 收口报告 | `.ai/reviews/phase3.8.21_agent_governance_workflow_accountability_report.md` | 本文件 |
| 12 | 状态更新 | `.ai/project_status.json`、`.ai/roadmap_v8.md` §24 | `phase_3_8_21 = ENTERPRISE_AGENT_GOVERNANCE_WORKFLOW_BUILT_NO_GO` |

新增代码规模：`agent_governance_workflow.py` **1322 行**；测试 **865 行**。

`GovernanceWorkflowService` 对外方法：`create_task` / `assign_owner` / `start_processing` /
`submit_result` / `human_close` / `record_observed_action` / `list_tasks` / `list_assignments` /
`list_action_records` / `list_action_records_of` / `list_closure_reports` / `get_closure_report`。
其中**只有 1 个闭环入口**（`human_close`，且被 `require_human_actor(USER)` 锁死）可以改变治理态；
`record_observed_action` 只登记被观察事实、**不改变任何状态**；其余均为**只读查询**。

---

## 3. 红线守约（fail-closed，6 条）

| # | 红线 | 落地机制 | 结果 |
| --- | --- | --- | --- |
| ① | 禁开 `engineering_enabled` | 服务构造与全部写路径断言 `safety_invariants_ok()`；磁盘 `agents/config.yaml:102` 恒为 `false`；monkeypatch 启用态后构造即抛 `EnterpriseRedLineViolationError` | ✅ 未开启 |
| ② | 禁输出 `engineering_approved` | `engineering_approved` / `approve` / `sign` / `authorize` / `quote` / `pricing` 列入 `_GOVERNANCE_FORBIDDEN`，`__getattr__` 命中即抛；**本层代码零赋值/零输出**（仅作禁用名与红线注释出现） | ✅ 无任何输出 |
| ③ | 禁 AI 自动整改风险 | 类型级：`GovernanceTask` 无 `remediate`/`fix`/`resolve`/`close` 方法，`GovernanceTaskStatus` 无 AI 终态；语义级：标题/说明/结果命中 `_REMEDIATION_MARKERS` 即拒；结构级：拦截 `auto_remediate` / `auto_fix` / `auto_resolve` / `auto_close` / `close_task` / `complete_task` / `auto_repair` / `auto_mitigate` 等 | ✅ 类型 + 结构 + 语义三不可达 |
| ④ | 禁 AI 自动分配责任 | 类型级：`GovernanceTask` 构造期 `owner_id` 必空、赋值即抛，责任人必真实 USER；语义级：标题/说明命中 `_ASSIGNMENT_MARKERS` 即拒，assignee/assigned_by 命中 `_NON_HUMAN_ASSIGNEES` 即抛；结构级：拦截 `auto_assign` / `auto_delegate` / `auto_designate_owner` / `assign_responsibility_automatically` 等；`assign_owner` 强制 `require_human_actor(USER)` | ✅ 类型 + 结构 + 语义三不可达 |
| ⑤ | 禁 AI 自动修改权限策略 | 结构级：拦截 `auto_change_permission` / `grant_permission` / `revoke_permission` / `change_policy` / `auto_modify_policy` 等；本层对 `AgentPermissionPolicy` **只读引用**，无任何 set 器、无写路径；动作记录结果命中 `_PERMISSION_MARKERS` 即拒 | ✅ 结构不可达 + 纯只读 |
| ⑥ | 禁 AI 代替治理责任人 | 审计禁 `record_human_approval`（实测访问即抛 `EnterpriseRedLineViolationError`）；`human_close` 强制 `require_human_actor(USER)` + 非空 `actor_id` + 非空 `human_result`；`GovernanceClosureReport.closed_by` 必为真实 USER；拦截 `act_as_governance_owner` / `auto_confirm_closure` / `auto_recommend` / `auto_signoff` 等；任务/报告缺来源即拒落库 | ✅ 强制人工 |

`_GOVERNANCE_FORBIDDEN` 共 **98** 项（含基座 7 项 + 红线②/③/④/⑤/⑥ 各同族收敛）。

补充事实约束（红线③/④/⑤/⑥ 的可溯源与中性要求）：

- `GovernanceTask` 构造期 `requires_human_completion=False` / 预填 `owner_id` / 预填 `completed_at` / 预填 `closed_by` / 非 `created` 态 → 全部拒绝构造（AI 不得伪造完成或分配）；
- `GovernanceAssignment` assignee / assigned_by 命中非人类标识（ai / system / bot / agent / auto / llm / 机器人 等）即拒；真实人名（eng-li / zhang.san）正常放行；
- `GovernanceActionRecord` action / result 命中自动整改或改权限语义即拒；`actor_kind=ai` 如实标注，绝不冒充人工；
- `GovernanceClosureReport` 缺 `source_trace` / 空来源链 / 缺 `human_result` / `closed_by` 非人类 / 结论含整改语义 → 全部拒绝构造；
- `record_observed_action` 只登记事实，**绝不改变任务状态、绝不整改、绝不关闭**。

---

## 4. 测试（八类，97 用例）

| 类别 | 测试函数数 | 覆盖要点 |
| --- | --- | --- |
| 1. task | 15 | 5 态枚举（无 AI 终态）、来源类型只事实、created 态字段、source_id 必填、禁预填 owner/completed/closed、禁非 created 构造、requires_human_completion 恒 True、禁整改/分配/改权限语义、只前进不回退、模型无 close/assign 方法 |
| 2. assignment | 9 | 字段构造、四非空校验、责任人/分配者必真实 USER（9 类非人类标识拒）、note 禁自动语义、真实人名放行 |
| 3. action | 10 | 字段构造、四非空校验、结果禁自动整改（4 类）、action 禁自动整改（3 类）、结果禁改权限（3 类）、AI 记录非人工动作、模型无整改方法 |
| 4. workflow | 14 | create_task 只产候选、source_id 必填、禁重复、assign_owner 强制 USER + 拒非人类、start_processing/submit_result 强制 USER、submit_result 禁空结果、全链路到 waiting_review、human_close 唯一闭环入口、human_close 强制 USER、record_observed_action 不改状态、禁非法回退迁移 |
| 5. closure | 7 | 字段构造、source_id 必填、human_result 必填、closed_by 必真实 USER、无来源链拒、结论禁整改语义、render_source 含来源链 |
| 6. permission | 4 | REVIEWER 对 data 类治理数据默认拒绝（`EnterpriseIsolationError`）、ADMIN 放行、闭环报告同样隔离、本层对权限策略纯只读（无改权限方法） |
| 7. audit | 5 | 3 新类别齐备且累计 56、create_task 触发审计、human_close 触发审计、禁 `record_human_approval`、forbidden 元组覆盖整改/分配/改权限 |
| 8. red_line | 6 | 6 条红线逐条断言 + 启用态阻断构造 + safety_invariants_ok 为 True（被禁态）+ 无 engineering_approved 输出 + 结构拦截 auto_remediate/auto_fix/auto_resolve/auto_assign/grant_permission + 全链路无 engineering_approved 字段 |

单文件运行：`97 passed in 0.15s`（一次通过，无返工）。

---

## 5. 最终验证

```
$ find tests -name '_tmp_drill_*' -delete
$ rm -rf tests/intake_snapshots
$ backend/.venv/bin/python -m pytest tests/agents -q
1786 passed
```

- 3.8.20 基线 1689 → 现 **1786**，**+97 全部为本 Phase 新增**，**零回归**。
- `AuditActionCategory` 实测 **56**（3.8.20 基线 53 + 本 Phase 3）。
- `_GOVERNANCE_FORBIDDEN` 实测 **98**（无重复）。
- `engineering_enabled` 实测 **False**（红线①）。
- 本层源码 `engineering_approved` 出现仅 1 处且为**禁用名声明 + 红线注释**（红线②：零输出）。
- 历史累计断言同步刷新（属既定范式，非功能变更）：
  - `test_enterprise_knowledge_governance_audit.py`：`EXPECTED_CATEGORIES` 补 3 个值 + 计数 `== 56`（3.8.20 已完成）
  - `test_enterprise_knowledge_intelligence_audit.py`：`== 56`
  - `test_enterprise_agent_cost_resource.py`：断言 `== 56`
  - `test_enterprise_agent_quality_governance.py`：断言 `== 56`
  - `test_enterprise_agent_runtime_policy.py`：断言 `== 56`
  - `test_enterprise_agent_security_risk.py`：断言 `== 56`
  - `test_enterprise_agent_governance_center.py`：断言 `== 56`
  - `test_enterprise_agent_compliance.py`：断言 `== 56`
- 未修改 `verified.json`；未修改 `engineering_enabled`（`agents/config.yaml:102` 仍为 `false`）；测试通过 `monkeypatch` 注入启用态，**不触碰磁盘配置**。
- 注：全量套件存在历史测试技术债（`test_threshold_real_drill.py` 的 `_tmp_drill_*` 临时文件在沙箱批量删除守卫下偶发清理失败），与本 Phase 无关；清理临时文件后全量套件即全绿（1786 passed）。

---

## 6. 状态与激活态

| 项 | 值 |
| --- | --- |
| `phase_3_8_21` | `ENTERPRISE_AGENT_GOVERNANCE_WORKFLOW_BUILT_NO_GO` |
| `engineering_enabled` | `false`（`agents/config.yaml:102`，未变更） |
| ESW 窗口 | 维持 `OPEN_EMPTY` |
| 工程放行 | **无**。本层不产出任何治理结论、不分配任何责任、不整改任何风险、不关闭任何任务、不修改任何权限或策略、不代替治理责任人签字 |

**BUILT_NO_GO 含义**：能力已建成并通过测试，但**未获工程放行**。治理任务 / 责任分配 / 处理记录 /
闭环报告均只陈述与汇聚既有事实、只由真实治理责任人逐步推进并闭环；任何风险整改、任何责任裁定、
任何权限或策略调整，均须由人工在本系统之外依据自身职责作出并回填事实。

---

## 7. STOP 声明（等待主理人审核）

Phase 3.8.21 全部 11 项任务（#701–#711）已按主理人授权完成并自检通过。依授权原话
「完成后停止。不要进入 Phase 3.8.22。等待主理人审核」，现**主动 STOP**：

- ❌ 不进入 Phase 3.8.22；
- ❌ 不开启 `engineering_enabled`；
- ❌ 不输出 `engineering_approved`；
- ❌ 不自动整改任何风险（auto_remediate / auto_fix / auto_resolve）；
- ❌ 不自动分配任何责任（auto_assign / auto_delegate）；
- ❌ 不自动修改任何权限或策略（grant_permission / change_policy）；
- ❌ 不代替治理责任人签字或背书；
- ✅ 等待主理人审核本报告后再行授权。

—— BOIP AI Chief Architect，2026-08-07
