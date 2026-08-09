# Phase 3.8.19 收口报告 —— Enterprise Agent Compliance & Audit Intelligence Layer（企业智能体合规与审计智能层）

| 项 | 值 |
| --- | --- |
| Phase | 3.8.19 |
| 身份 | BOIP AI Chief Architect |
| 状态 | `ENTERPRISE_AGENT_COMPLIANCE_BUILT_NO_GO` |
| 收口日期 | 2026-08-07 |
| 激活态 | `engineering_enabled = false`（未变更） |
| 全量测试 | `tests/agents` **1616 passed**（1558 基线 + 58 新增，零回归） |
| 审计类别 | 47 → **50**（+3） |

---

## 1. 概述

本 Phase 交付企业智能体**合规与审计智能层**，把既有审计数据变成可被规则检查的合规事实，
形成完整链路：

```
Agent 行为  →  审计数据  →  规则检查  →  合规候选  →  人工审核
   （事实）     （既有沉淀）   （中性标注）   （只发现）    （唯一定性节点）
```

本层的定位是**辅助合规**，不是**合规裁决**：

- AI 可以：登记规则草案、记录检查事实、发现异常模式、产出合规风险候选、生成可溯源报告；
- AI 不可以：判定违法/违规、处罚 Agent、修改权限或策略、让规则自动生效、代替合规责任人签字。

与前序治理层最大的结构性差异在于**枚举层面就拒绝了判罚语义**：
`ComplianceCheckResult` 只有 `pass` / `attention` / `not_applicable` 三个值，
**刻意不存在** `violation` / `illegal` / `fail`。AI 最多只能标注「需要关注」，
「是否违规」这一结论在类型系统里根本无法被 AI 表达（红线③的类型级落地）。

上述边界不是靠约定，而是通过 `_RedLineForbiddenMixin.__getattr__` 结构拦截（**80 个**
forbidden 名）、模型 `__post_init__` 强校验、以及 `require_human_actor(USER)` 守卫
在**结构上**不可达。

---

## 2. 交付物清单

| # | 交付物 | 路径 / 位置 | 说明 |
| --- | --- | --- | --- |
| 1 | `ComplianceRule` + `ComplianceRuleScope` + `ComplianceRuleStatus` | `agents/enterprise/agent_compliance.py` | 合规规则（rule_id / name / scope / keywords / threshold / source）；**来源为空即拒绝构造**；默认 `draft` 且 `is_effective=False`；构造期落 `active` 即抛错 |
| 2 | `ComplianceCheck` + `ComplianceCheckResult` | 同上 | 检查事实（check_id / rule_id / agent_id / result / evidence）；结果枚举**只有** `pass`/`attention`/`not_applicable`，无判罚态；无证据 / 未绑定规则即拒绝 |
| 3 | `AgentComplianceDetector` | 同上 | 三类检测 `check_audit_pattern` / `check_permission_pattern` / `check_runtime_pattern`；**只消费既有事实、只发现候选**，无事实即返回空，绝不臆造 |
| 4 | `ComplianceRiskCandidate` | 同上 | 合规风险候选（risk_id / pattern / evidence / requires_human_review）；`requires_human_review` **恒为 True**，置 False 即抛；无 pattern / 无 evidence 即拒绝构造 |
| 5 | `AgentComplianceReport` + `SourceTrace` | 同上 | 检查事实 + 风险候选 + **来源链**；无来源链即拒绝构造；零事实拒绝生成空报告；摘要不含处罚/批准语义 |
| 6 | `ComplianceReview` + `ComplianceReviewStatus` | 同上 | 合规人工整改；构造期禁止落 `reviewed`；`human_review_compliance_risk` 强制真实 `USER` + 非空 `actor_id` + 非空 `decision` |
| 7 | 审计增强（+3 类别 / +3 方法） | `agents/enterprise/audit.py` | `AGENT_COMPLIANCE_RULE` / `AGENT_COMPLIANCE_CHECK` / `AGENT_COMPLIANCE_RISK`；累计 **50**；禁 `record_human_approval` |
| 8 | 权限接入与装配 | `agents/enterprise/service.py`、`agents/enterprise/__init__.py` | `AgentComplianceService` 接入 `IdentityService` + `AgentPermissionPolicy` + `AgentRuntimePolicy`；合规数据读取**默认拒绝**（`EnterpriseIsolationError`）；`__init__.py` 新增 11 符号导出（`__all__` 222） |
| 9 | 九类测试（58 用例） | `tests/agents/test_enterprise_agent_compliance.py` | rule / check / detector / risk_candidate / report / review / audit / permission / red_line |
| 10 | 收口报告 | `.ai/reviews/phase3.8.19_agent_compliance_audit_report.md` | 本文件 |
| 11 | 状态更新 | `.ai/project_status.json`、`.ai/roadmap_v8.md` §22 | `phase_3_8_19 = ENTERPRISE_AGENT_COMPLIANCE_BUILT_NO_GO` |

新增代码规模：`agent_compliance.py` **1375 行**；测试 **885 行**。

`AgentComplianceService` 对外方法：`register_compliance_rule` / `confirm_rule_active` /
`confirm_rule_deprecated` / `record_compliance_check` / `register_risk_candidate` /
`run_compliance_detection` / `generate_compliance_report` /
`human_review_compliance_risk` / `list_compliance_rules` / `list_compliance_checks` /
`list_risk_candidates` / `list_compliance_reviews`。其中**只有 3 个人工节点**
（`confirm_rule_active` / `confirm_rule_deprecated` / `human_review_compliance_risk`）
可以改变治理态，且三者都被 `require_human_actor(USER)` 锁死。

---

## 3. 红线守约（fail-closed，6 条）

| # | 红线 | 落地机制 | 结果 |
| --- | --- | --- | --- |
| ① | 禁开 `engineering_enabled` | 服务/检测器构造与全部写路径断言 `safety_invariants_ok()`；磁盘 `agents/config.yaml:102` 恒为 `false`；monkeypatch 启用态后构造即抛 `EnterpriseRedLineViolationError` | ✅ 未开启 |
| ② | 禁输出 `engineering_approved` | `engineering_approved` / `approve` / `sign` / `authorize` / `attest_compliance` / `certify_compliance` / `auto_sign_compliance` 列入 `_COMPLIANCE_FORBIDDEN`，`__getattr__` 命中即抛；不在 `__all__` | ✅ 无任何赋值/输出 |
| ③ | 禁 AI 自动判定违法/违规 | **类型级**：`ComplianceCheckResult` 只有 `pass`/`attention`/`not_applicable`，无 `violation`/`illegal`/`fail`。**结构级**：拦截 `auto_violate` / `violate` / `auto_penalty` / `penalty` / `auto_judge_compliance` / `judge_compliance` / `judge_violation` / `judge_illegal` / `declare_violation` / `declare_illegal` / `determine_violation` / `auto_convict` / `convict` / `auto_rule_violation` 等 | ✅ 类型 + 结构双不可达 |
| ④ | 禁 AI 自动处罚 Agent | 拦截 `auto_suspend_agent` / `suspend_agent` / `auto_ban_agent` / `ban_agent` / `auto_disable_agent` / `disable_agent` / `auto_block_agent` / `block_agent` / `auto_kill_agent` / `kill_agent` / `auto_quarantine_agent` / `auto_terminate_agent` / `auto_revoke_agent` / `punish_agent` / `sanction_agent` / `fine_agent` / `auto_fine` / `auto_sanction`；检测器只产出候选，从不触碰任何 Agent 状态 | ✅ 结构不可达 |
| ⑤ | 禁 AI 自动修改权限或策略 | 拦截 `auto_change_permission` / `change_permission` / `auto_grant_permission` / `grant_permission` / `auto_revoke_permission` / `revoke_permission` / `modify_permission` / `escalate_permission` / `auto_modify_policy` / `modify_policy` / `auto_update_policy` / `update_policy` / `apply_policy` / `auto_apply_policy` / `auto_activate_rule` / `activate_rule` / `auto_update_rule` / `update_rule` / `change_rule`；本层对权限与运行策略**只读**（`check_agent_access` / 只读消费 `RuntimeDecisionRecord`），无任何写路径；规则生效/废止强制真实 USER | ✅ 结构不可达 |
| ⑥ | 禁 AI 代替合规责任人 | 审计禁 `record_human_approval`（实测 `hasattr` 为 False）；`human_review_compliance_risk` 强制 `require_human_actor(USER)` + 非空 `actor_id` + 非空 `decision`；拦截 `act_as_compliance_officer` / `take_compliance_ownership` / `assume_compliance_responsibility` / `auto_govern_compliance` / `auto_attest` / `auto_clear_compliance` / `clear_compliance`；规则/检查/候选/报告缺来源即拒落库 | ✅ 强制人工 |

`_COMPLIANCE_FORBIDDEN` 共 **80** 项（含继承自前序层的 `quote` / `pricing` 等报价禁令）。

补充事实约束（红线③/⑥的可溯源要求）：

- `ComplianceRule.source` 为空 → 拒绝构造（无依据不立规）；
- `ComplianceCheck.evidence` 为空或未绑定已注册规则 → 拒绝落库（无证据不检查）；
- `ComplianceRiskCandidate.evidence` 为空 → 拒绝构造（无证据不指控）；
- `AgentComplianceReport.source_trace` 缺失/为空 → 拒绝构造；`generate_compliance_report` 零事实时抛错，不产空报告；
- `attention` 语义在测试中被显式断言为「需人工关注」而**非**「已违规」。

---

## 4. 测试（九类，58 用例）

| 类别 | 用例数 | 覆盖要点 |
| --- | --- | --- |
| 1. rule | 10 | 来源必填、名称必填、默认 draft 且不生效、构造期禁 active、关键字仅显式匹配、摘要无判罚语义、注册拒收 active 输入、生效/废止强制真实 USER 且终态、actor_id 与规则存在性校验 |
| 2. check | 6 | 结果枚举无判罚值、证据必填、必须绑定已注册规则、`attention` ≠ 违规结论、未注册规则拒收、事实按组织域落库 |
| 3. detector | 8 | 无事实返回空（不臆造）、审计频次候选、审计关键字候选、权限模式只读、运行时模式只消费既有事实、阈值以下不产候选、检测须有生效规则、检测产出候选并自动挂 pending 复核 |
| 4. risk_candidate | 5 | `requires_human_review` 恒 True、置 False 抛错、pattern/evidence 必填、注册即生成 pending 复核单、拒绝豁免复核 |
| 5. report | 5 | 来源链必填、零事实拒绝生成、只汇总事实、摘要无处罚/批准语义、按 agent 过滤 |
| 6. review | 5 | 构造期禁 reviewed、AI/system/None 处置被拒、actor_id/decision 必填、真实 USER 处置成功且终态、未知风险拒绝 |
| 7. audit | 5 | 3 类别齐备且累计 50、规则登记记 AI / 生效记 USER、检查记 AI、风险与复核 actor 如实、禁 `record_human_approval` |
| 8. permission | 5 | 默认拒绝（`EnterpriseIsolationError`）、ADMIN 可读且组织隔离、按 agent/result 过滤、服务只读权限不写、聚合层装配校验 |
| 9. red_line | 9 | 6 条红线逐条断言 + 启用态阻断构造 + 启用态阻断写入 + 人工节点强制性 |

单文件运行：`58 passed in 0.09s`（一次通过，无返工）。

---

## 5. 最终验证

```
$ find tests -name '_tmp_drill_*' -delete
$ rm -rf tests/intake_snapshots
$ backend/.venv/bin/python -m pytest tests/agents -q
1616 passed
```

- 基线 1558（3.8.18 收口）→ 现 **1616**，**+58 全部为本 Phase 新增**，**零回归**。
- `AuditActionCategory` 实测 **50**。
- 历史累计断言同步刷新（属既定范式，非功能变更）：
  - `test_enterprise_agent_cost_resource.py`：47 → 50（含函数名 `..._count_50`）
  - `test_enterprise_agent_quality_governance.py`：47 → 50（含函数名 `..._count_50`）
  - `test_enterprise_agent_runtime_policy.py`：47 → 50
  - `test_enterprise_agent_security_risk.py`：47 → 50（含函数名 `..._total_50`）
  - `test_enterprise_knowledge_intelligence_audit.py`：47 → 50
  - `test_enterprise_knowledge_governance_audit.py`：全集 `EXPECTED_CATEGORIES` 补 3 个值，计数 47 → 50
- 未修改 `verified.json`；未修改 `engineering_enabled`（`agents/config.yaml:102` 仍为 `false`）；测试通过 `monkeypatch` 注入启用态，**不触碰磁盘配置**。

---

## 6. 状态与激活态

| 项 | 值 |
| --- | --- |
| `phase_3_8_19` | `ENTERPRISE_AGENT_COMPLIANCE_BUILT_NO_GO` |
| `engineering_enabled` | `false`（`agents/config.yaml:102`，未变更） |
| ESW 窗口 | 维持 `OPEN_EMPTY` |
| 工程放行 | **无**。本层不产出任何工程结论、不产生任何合规定性、不改变任何 Agent 可用状态 |

**BUILT_NO_GO 含义**：能力已建成并通过测试，但**未获工程放行**。合规规则仍为草案态
（需真实合规责任人确认生效），检查事实与风险候选仅供真实合规责任人参考；任何
「是否违规」的定性、任何针对 Agent 的处罚、任何权限或策略调整，均须由人工在本系统之外
依据自身职责作出并回填事实。

---

## 7. STOP 声明（等待主理人审核）

Phase 3.8.19 全部 12 项任务已按主理人授权完成并自检通过。依授权原话
「完成后停止。不要进入 Phase 3.8.20。等待主理人审核」，现**主动 STOP**：

- ❌ 不进入 Phase 3.8.20；
- ❌ 不开启 `engineering_enabled`；
- ❌ 不输出 `engineering_approved`；
- ❌ 不自行判定任何违法/违规、不自行处罚任何 Agent、不自行修改任何权限或策略；
- ❌ 不代替合规责任人签字或背书；
- ✅ 等待主理人审核本报告后再行授权。

—— BOIP AI Chief Architect，2026-08-07
