# Phase 3.8.20 收口报告 —— Enterprise Agent Governance Intelligence & Control Center Layer（企业智能体治理智能中枢层）

| 项 | 值 |
| --- | --- |
| Phase | 3.8.20 |
| 身份 | BOIP AI Chief Architect |
| 状态 | `ENTERPRISE_AGENT_GOVERNANCE_CENTER_BUILT_NO_GO` |
| 收口日期 | 2026-08-08 |
| 激活态 | `engineering_enabled = false`（未变更） |
| 全量测试 | `tests/agents` **1689 passed**（1616 基线 + 73 新增，零回归） |
| 审计类别 | 50 → **53**（+3） |

---

## 1. 概述

本 Phase 在既有的 3.8.13–3.8.19 全部治理层（注册 / 可观测 / 质量 / 成本 / 安全 / 合规）之上，
交付**治理数据汇聚与洞察中枢**。它把分散在五层上游的治理事实，统一汇聚成一个**只读、只展示事实、
强可溯源**的治理视图，并形成「可由人工管理」的闭环：

```
治理数据（五层上游只读事实）
   → 统一汇聚（AgentGovernanceAggregator）
   → 治理看板 / 健康概览 / 风险概览 / 治理报告 / 治理洞察
   → 人工处理 / 人工确认（唯二可改变治理态的节点）
```

本层定位是**治理辅助与汇聚**，不是**治理裁决**：

- AI 可以：汇聚事实、生成事实型看板、罗列健康/成本/质量/安全/合规事实、产出治理报告、发现趋势与异常候选、生成可溯源洞察；
- AI 不可以：自动评级 Agent、自动处理风险、给出治理建议、自动修改权限或策略、代替治理责任人签字。

与前序治理层最大的结构性差异在于**类型层面就拒绝了「评级 / 处置 / 建议 / 判定」语义**：
`AgentHealthOverview` 刻意**不存在** `rating`/`grade`/`health_level` 字段；`AgentRiskOverview`
`requires_human_handling` **恒为 True**，构造期只能落 `pending_human_review`；`AgentGovernanceInsight`
`requires_human_confirmation` **恒为 True**，文本含治理建议即拒。这些边界在**类型系统**里就让 AI
无从表达（红线③/④/⑤的类型级落地）。

上述边界不是靠约定，而是通过 `_RedLineForbiddenMixin.__getattr__` 结构拦截（**84 个**
forbidden 名）、模型 `__post_init__` 强校验、语义级标记拦截（`_RATING_MARKERS` / `_ADVICE_MARKERS` /
`_CONTROL_MARKERS` + `_reject_markers`），以及 `require_human_actor(USER)` 守卫在**结构上**不可达。

---

## 2. 交付物清单

| # | 交付物 | 路径 / 位置 | 说明 |
| --- | --- | --- | --- |
| 1 | `GovernanceWidgetKind`（6 事实型） | `agents/enterprise/agent_governance_center.py` | `metric_card` / `fact_list` / `trend_chart` / `status_badge` / `raw_table` / `source_link`；**无 action / control 型** |
| 2 | `GovernanceVisibility` + `GovernanceWidget` | 同上 | 看板可见性 + 单挂件（source 空 / 标题含控制语义即抛错；只承载事实，不承载操作） |
| 3 | `AgentGovernanceDashboard` | 同上 | dashboard_id / org_id / widgets / visibility / created_at + name / created_by；**空 widget 拒绝**；只展示事实 |
| 4 | `AgentHealthOverview` | 同上 | overview_id / agent_id / org_id / runtime_facts / quality_facts / cost_facts / security_facts / compliance_facts / source_trace / generated_at；事实键名命中评级语义即抛错；**无 rating / grade / health_level 字段**（禁自动评级） |
| 5 | `RiskOverviewStatus` + `AgentRiskOverview` | 同上 | 状态仅 `pending_human_review` / `under_human_review` / `handled_by_human`（无 AI 终态）；`requires_human_handling` **恒 True**，构造期只能落 `pending_human_review`（禁自动处理） |
| 6 | `AgentGovernanceReport`（5 段 + `SourceTrace`） | 同上 | observability / quality / cost / security / compliance 五段 + source_trace；无 SourceTrace 或空链即拒；段落含建议语义即拒（禁治理建议） |
| 7 | `GovernanceInsightKind` + `GovernanceTrendDirection` + `AgentGovernanceInsight` | 同上 | 洞察类型仅 `fact_trend` / `anomaly_candidate`（无 recommendation 态）；方向中性 `up`/`down`/`flat`/`unknown`；`requires_human_confirmation` **恒 True**，source 必填，文本含建议即拒 |
| 8 | `AgentGovernanceAggregator`（纯只读） | 同上 | `collect_observability_facts` / `collect_quality_facts` / `collect_cost_facts` / `collect_security_facts` / `collect_compliance_facts`；上游缺失返回空（不臆造） |
| 9 | `AgentGovernanceCenterService` | 同上 | 构造断言 `safety_invariants_ok()`；`_ensure_access` 默认拒绝（`EnterpriseIsolationError`）；只读查询 + 唯二人工节点 |
| 10 | 审计增强（+3 类别 / +3 方法） | `agents/enterprise/audit.py` | `AGENT_GOVERNANCE_DASHBOARD` / `AGENT_GOVERNANCE_REPORT` / `AGENT_GOVERNANCE_INSIGHT`；累计 **53**；禁 `record_human_approval` |
| 11 | 权限接入与装配 | `agents/enterprise/service.py`、`agents/enterprise/__init__.py` | `agent_governance_center` 接入 `IdentityService` + `AgentPermissionPolicy` + `AgentRuntimePolicy` + 五层上游只读服务；治理数据读取**默认拒绝**（组织隔离）；`__init__.py` 新增 13 符号导出 |
| 12 | 八类测试（73 用例） | `tests/agents/test_enterprise_agent_governance_center.py` | dashboard / overview / risk / report / insight / permission / audit / red_line |
| 13 | 收口报告 | `.ai/reviews/phase3.8.20_agent_governance_control_center_report.md` | 本文件 |
| 14 | 状态更新 | `.ai/project_status.json`、`.ai/roadmap_v8.md` §23 | `phase_3_8_20 = ENTERPRISE_AGENT_GOVERNANCE_CENTER_BUILT_NO_GO` |

新增代码规模：`agent_governance_center.py` **1570 行**；测试 **1001 行**。

`AgentGovernanceCenterService` 对外方法：`create_dashboard` / `build_health_overview` /
`build_risk_overview` / `generate_governance_report` / `generate_fact_trend_insight` /
`generate_anomaly_candidate_insight` / `human_handle_risk_overview` / `human_confirm_insight` /
`list_dashboards` / `list_health_overviews` / `list_risk_overviews` / `list_governance_reports` /
`list_insights`。其中**只有 2 个人工节点**（`human_handle_risk_overview` / `human_confirm_insight`）
可以改变治理态，且二者都被 `require_human_actor(USER)` 锁死；其余均为**只读事实汇聚 / 展示**。

---

## 3. 红线守约（fail-closed，6 条）

| # | 红线 | 落地机制 | 结果 |
| --- | --- | --- | --- |
| ① | 禁开 `engineering_enabled` | 服务 / 汇聚器构造与全部写路径断言 `safety_invariants_ok()`；磁盘 `agents/config.yaml:102` 恒为 `false`；monkeypatch 启用态后构造即抛 `EnterpriseRedLineViolationError` | ✅ 未开启 |
| ② | 禁输出 `engineering_approved` | `engineering_approved` / `approve` / `sign` / `authorize` / `quote` / `pricing` 列入 `_GOVERNANCE_FORBIDDEN`，`__getattr__` 命中即抛；**本层代码零赋值/零输出**（仅作禁用名与红线注释出现） | ✅ 无任何输出 |
| ③ | 禁 AI 自动评级 / 自动判定 | **类型级**：`AgentHealthOverview` 无 `rating`/`grade`/`health_level` 字段；事实键名命中 `_RATING_MARKERS` 即抛。结构级：拦截 `auto_rate_agent` / `rate_agent` / `auto_grade_agent` / `grade_agent` / `auto_judge_health` / `auto_assess_agent` / `auto_evaluate_agent` / `auto_score_agent` / `score_agent` / `auto_rank_agent` / `auto_classify_agent` / `auto_determine_health` 等 | ✅ 类型 + 结构双不可达 |
| ④ | 禁 AI 自动处理风险 | `AgentRiskOverview.requires_human_handling` **恒 True**，`RiskOverviewStatus` 无 AI 终态；拦截 `auto_handle_risk` / `handle_risk` / `auto_resolve_risk` / `resolve_risk` / `auto_mitigate_risk` / `mitigate_risk` / `auto_close_risk` / `close_risk` / `auto_remediate_risk` / `auto_triage_risk` / `triage_risk` / `auto_dismiss_risk` / `dismiss_risk`；处理强制 `require_human_actor(USER)` | ✅ 结构不可达 |
| ⑤ | 禁 AI 自动处置 / 修改策略 | 拦截 `auto_disable` / `auto_modify` / `auto_upgrade` / `auto_policy_change` / `auto_control_agent` / `control_agent` / `auto_approve_agent` / `auto_sign_governance` / `auto_confirm_risk` / `auto_set_policy` / `auto_recommend_action` / `recommend_action` / `auto_advise` / `advise` / `propose_governance_action` 等；本层对 Agent 状态、权限、策略**只读**（只汇聚五层上游事实），无任何写路径；治理建议语义在 `__post_init__` 被 `_reject_markers` 拒收 | ✅ 结构不可达 |
| ⑥ | 禁 AI 代替治理责任人 | 审计禁 `record_human_approval`（实测 `hasattr` 为 False）；`human_handle_risk_overview` / `human_confirm_insight` 强制 `require_human_actor(USER)` + 非空 `actor_id`；拦截 `act_as_governance_owner` / `take_governance_ownership` / `assume_governance_responsibility` / `auto_govern` / `auto_attest_governance` / `clear_governance` / `auto_sign_off` / `auto_approve_governance`；看板/报告/洞察缺来源即拒落库 | ✅ 强制人工 |

`_GOVERNANCE_FORBIDDEN` 共 **84** 项（含基座 7 项 + 红线③/④/⑤/⑥ 各同族收敛）。

补充事实约束（红线③/④/⑤/⑥ 的可溯源与中性要求）：

- `AgentGovernanceDashboard` 空 widget 列表 → 拒绝构造（无事实不成看板）；
- `AgentHealthOverview` 事实键名命中评级语义 / 含 `rating`/`grade`/`health_level` → 拒绝构造（不评级）；
- `AgentRiskOverview` 构造期只能落 `pending_human_review`，置 `requires_human_handling=False` 即抛（不自动处理）；
- `AgentGovernanceReport.source_trace` 缺失 / 空链 → 拒绝构造；段落文本含建议语义即拒（不提建议）；
- `AgentGovernanceInsight` source 必填，文本含建议即拒，`requires_human_confirmation` 恒 True（不越权确认）；
- 汇聚器上游缺失返回空，**绝不臆造**任何治理事实。

---

## 4. 测试（八类，73 用例）

| 类别 | 用例数 | 覆盖要点 |
| --- | --- | --- |
| 1. dashboard | 10 | 看板构造、空 widget 拒绝、可见性、挂件 source 必填、标题禁控制语义、组织域校验、按 org 过滤、只读查询 |
| 2. overview | 8 | 健康概览构造、无 rating/grade/health_level 字段、事实键名禁评级语义、五层事实汇聚、source_trace 必填、生成器只读汇聚 |
| 3. risk | 12 | `requires_human_handling` 恒 True、`pending_human_review` 唯一构造态、置 False 抛错、状态无 AI 终态、人工处理强制 USER、`under_human_review`/`handled_by_human` 仅人工可达 |
| 4. report | 8 | 五段汇聚、source_trace 必填、空链拒构造、段落禁建议语义、零事实拒绝生成、按 agent 过滤、可溯源渲染 |
| 5. insight | 14 | `requires_human_confirmation` 恒 True、kind 仅 fact_trend/anomaly_candidate（无 recommendation）、方向中性、source 必填、文本禁建议语义、人工确认强制 USER、异常候选只标记不处置 |
| 6. permission | 8 | 默认拒绝（`EnterpriseIsolationError`）、ADMIN 可读且组织隔离、REVIEWER 对 data 类治理数据默认拒绝、只读权限不写、上游服务只读装配校验 |
| 7. audit | 8 | 3 类别齐备且累计 53、看板/报告/洞察记录 actor 如实（默认 AI，人工处置录 USER）、禁 `record_human_approval` |
| 8. red_line | 10 | 6 条红线逐条断言 + 启用态阻断构造 + 启用态阻断写入 + 类型级禁评级字段 + 语义级禁建议/处置标记 + aggregator 纯只读 |

单文件运行：`73 passed in 0.12s`（一次通过，无返工）。

---

## 5. 最终验证

```
$ find tests -name '_tmp_drill_*' -delete
$ rm -rf tests/intake_snapshots
$ backend/.venv/bin/python -m pytest tests/agents -q
1689 passed
```

- 基线 1616（3.8.19 收口）→ 现 **1689**，**+73 全部为本 Phase 新增**，**零回归**。
- `AuditActionCategory` 实测 **53**。
- `_GOVERNANCE_FORBIDDEN` 实测 **84**（无重复）。
- `engineering_enabled` 实测 **False**（红线①）。
- 本层源码 `engineering_approved` 出现仅 3 处且均为**禁用名声明 + 红线注释**（红线②：零输出）。
- 历史累计断言同步刷新（属既定范式，非功能变更）：
  - `test_enterprise_knowledge_governance_audit.py`：`EXPECTED_CATEGORIES` 补 3 个值 + 计数 `== 53`
  - `test_enterprise_knowledge_intelligence_audit.py`：`== 53`
  - `test_enterprise_agent_cost_resource.py`：改名 `..._count_53`
  - `test_enterprise_agent_quality_governance.py`：改名 `..._count_53`
  - `test_enterprise_agent_runtime_policy.py`：改名 `..._count_53_with_3_8_20`
  - `test_enterprise_agent_security_risk.py`：改名 `..._total_53`
  - `test_enterprise_agent_compliance.py`：断言 `== 53`
- 未修改 `verified.json`；未修改 `engineering_enabled`（`agents/config.yaml:102` 仍为 `false`）；测试通过 `monkeypatch` 注入启用态，**不触碰磁盘配置**。
- 注：全量套件存在历史测试技术债（`test_threshold_real_drill.py` 的 `_tmp_drill_*` 临时文件在沙箱批量删除守卫下偶发清理失败），与本 Phase 无关；**隔离运行 `test_threshold_real_drill.py` 为 9 passed**，证明该债非本 Phase 引入；清理临时文件后全量套件即全绿（1689 passed）。

---

## 6. 状态与激活态

| 项 | 值 |
| --- | --- |
| `phase_3_8_20` | `ENTERPRISE_AGENT_GOVERNANCE_CENTER_BUILT_NO_GO` |
| `engineering_enabled` | `false`（`agents/config.yaml:102`，未变更） |
| ESW 窗口 | 维持 `OPEN_EMPTY` |
| 工程放行 | **无**。本层不产出任何治理结论、不评级任何 Agent、不处理任何风险、不给出任何治理建议、不改变任何 Agent 可用状态 |

**BUILT_NO_GO 含义**：能力已建成并通过测试，但**未获工程放行**。治理看板/健康概览/风险概览/
治理报告/治理洞察均只汇总与展示既有事实，仅供真实治理责任人参考；任何 Agent 评级、任何风险处置、
任何治理建议、任何权限或策略调整，均须由人工在本系统之外依据自身职责作出并回填事实。

---

## 7. STOP 声明（等待主理人审核）

Phase 3.8.20 全部 11 项任务（#687–#697）已按主理人授权完成并自检通过。依授权原话
「完成后停止。不要进入 Phase 3.8.21。等待主理人审核」，现**主动 STOP**：

- ❌ 不进入 Phase 3.8.21；
- ❌ 不开启 `engineering_enabled`；
- ❌ 不输出 `engineering_approved`；
- ❌ 不自行评级任何 Agent、不自行处理任何风险、不自行给出任何治理建议、不自行修改任何权限或策略；
- ❌ 不代替治理责任人签字或背书；
- ✅ 等待主理人审核本报告后再行授权。

—— BOIP AI Chief Architect，2026-08-08
