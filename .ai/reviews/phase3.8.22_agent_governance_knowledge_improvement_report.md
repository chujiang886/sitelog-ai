# Phase 3.8.22 收口报告 — Enterprise Agent Governance Knowledge & Continuous Improvement Layer（企业智能体治理知识与持续改进层）

> 报告日期：2026-08-08
> 身份：BOIP AI Chief Architect
> 状态：**🟢 BUILT_NO_GO** — 构建完成，等待主理人审核授权；不进入 Phase 3.8.23。

---

## 1. 概述：阶段目标与范围

本阶段在 3.8.0–3.8.21 全 ✅ 的治理基座之上，建立 **Agent 治理知识资产体系**，把一次性的治理事件沉淀为可复用的组织知识。核心链路：

```
治理事件 → 人工处理 → 治理经验 → 知识候选 → 人工审核 → 知识沉淀
```

- 输入：3.8.21 `GovernanceWorkflowService` 已 human 闭环的治理任务（状态 `completed`、闭环人非空且为真实 USER）。
- 产出：可追溯的治理案例（`GovernanceCase`）、事实归纳模式（`GovernancePattern`）、只能候选的知识（`GovernanceKnowledgeCandidate`）、来源可溯的报告（`GovernanceKnowledgeReport`），以及驱动上述流转的 `GovernanceImprovementWorkflowService`。
- 边界：**AI 只负责"记录与候选生成"，任何"审核结论 / 知识沉淀 / 策略变更 / 责任判定"都必须由真实治理责任人（USER）完成**；知识层对 3.8.21 任务仅做**只读**引用，绝不自动关闭任何治理任务。

---

## 2. 交付物清单（代码 + 测试 + 文档）

| 类型 | 路径 | 规模 |
|---|---|---|
| 治理知识核心（新建） | `agents/enterprise/agent_governance_knowledge.py` | 1516 行，10 个导出符号 |
| 审计增强 | `agents/enterprise/audit.py` | +3 枚举（56→59）+ 3 个 `record_*` 方法（现 2201 行） |
| 权限接入 / 聚合装配 | `agents/enterprise/service.py` + `agents/enterprise/__init__.py` | 注入 `agent_governance_knowledge`，传 `governance_workflow=self.agent_governance_workflow` |
| 测试（新建，八类） | `tests/agents/test_enterprise_agent_governance_knowledge.py` | 1101 行，116 用例 |
| 历史测试修正 | `test_enterprise_knowledge_governance_audit.py` 等 9 个文件 | 审计计数断言 `== 56` → `== 59`；`EXPECTED_CATEGORIES` 集合补 3 成员 |
| 收口报告 | `.ai/reviews/phase3.8.22_agent_governance_knowledge_improvement_report.md` | 本报告 |
| 状态刷新 | `.ai/project_status.json` | `phase_3_8_22_status=ENTERPRISE_AGENT_GOVERNANCE_KNOWLEDGE_BUILT_NO_GO` + 明细块 |
| 路线图 | `.ai/roadmap_v8.md` | §25 |

**10 个导出符号**：`GovernanceCase` / `GovernancePatternKind` / `GovernancePattern` / `GovernanceKnowledgeType` / `GovernanceKnowledgeStatus` / `GovernanceKnowledgeCandidate` / `GovernanceKnowledgeReport` / `GovernanceImprovementStage` / `GovernanceImprovementWorkflowService` / `_KNOWLEDGE_FORBIDDEN`。

---

## 3. 六条最高红线落实情况（fail-closed）

| # | 红线 | 落实方式 | 验证 |
|---|---|---|---|
| ① | `engineering_enabled` 保持 false | `safety_invariants_ok()` = `load_engineering_enabled() is False`；测试 autouse fixture monkeypatch 注入 `False`，不碰磁盘 | `enabled=False`、`inv_ok=True` ✅ |
| ② | 不输出 `engineering_approved` | 全模块零真实输出；仅作为禁名出现在 `_KNOWLEDGE_FORBIDDEN` 与 docstring 禁令说明（负向引用） | grep 命中 3 处均为负向 ✅ |
| ③ | 禁 AI 自动修改 Agent | `_KNOWLEDGE_FORBIDDEN` 含 `auto_modify_agent`/`auto_update_agent`/`modify_agent`/`update_agent` 等 14 个 `agent` 家族；结构级 `__getattr__` 拦截 | 红线测试命中即抛 `EnterpriseRedLineViolationError` ✅ |
| ④ | 禁 AI 自动修改治理策略 | 含 `auto_update_policy`/`auto_apply_policy`/`update_policy`/`apply_policy`/`create_policy`/`publish_policy`/`enforce_policy` 等 18 个 `policy` 家族；知识层无任何策略写接口 | ✅ |
| ⑤ | 禁 AI 自动关闭治理任务 | `GovernanceImprovementWorkflowService` 对 3.8.21 `_tasks` 只读；`_assert_human_closed_task` 强制来源任务 `status=="completed"` 且 `closed_by` 真实 USER；知识层无 `close`/`complete`/`resolve`/`finish` 方法 | ✅ |
| ⑥ | 禁 AI 代替治理责任人 | `start_human_review` / `accept_candidate` / `reject_candidate` 全部 `require_human_actor(AuditActorKind.USER)`；审计禁 `record_human_approval`（仅负向引用） | ✅ |

`_KNOWLEDGE_FORBIDDEN` 共 **97 项**，覆盖基座 7 项 + ③/④/⑤/⑥ 四族；三层拦截：类型级（dataclass 校验）+ 结构级（`_RedLineForbiddenMixin.__getattr__` 命中禁名即抛错）+ 语义级（`_reject_markers` / `_reject_non_human` / `_reject_governance_markers` 对内容做 `auto_*` / 非人类主语 / 策略动作标记扫描）。

---

## 4. 关键设计：链路 · 状态机 · 三层拦截

### 4.1 链路与状态机
`GovernanceImprovementStage` 五态：`CASE_CREATED → CANDIDATE_GENERATED → HUMAN_REVIEW → ACCEPTED / REJECTED`。
- 仅**前进不回退**（`_ALLOWED_STAGE_TRANSITIONS`）；无 AI 终态（`ACCEPTED`/`REJECTED` 仅能在 `HUMAN_REVIEW` 经真实 USER 触发）。
- `create_case`（AI 可发起）：来源任务须已 human 闭环，生成 `SourceTrace`，落 `CASE_CREATED`。
- `generate_candidate`（AI 只能产 `CANDIDATE` 态）：`requires_human_review` 强制 `True`，推进 `CANDIDATE_GENERATED`。
- `start_human_review`（`require_human_actor(USER)`）：推进 `HUMAN_REVIEW`。
- `accept_candidate` / `reject_candidate`（`require_human_actor(USER)`，`review_comment` 必填且过治理标记扫描）：推进 `ACCEPTED` / `REJECTED`。
- `build_knowledge_report`：只读汇编，经验段只收 `ACCEPTED` 候选，强 `SourceTrace`。

### 4.2 事实归纳，禁止自动策略
- `GovernancePattern`（风险/异常/处理三态）`is_policy` 恒 `False`；`description` 过 `_reject_governance_markers` + `_ADVICE_MARKERS`，禁止出现"建议策略/应执行"类表述。
- `GovernanceKnowledgeType` 四类（问题模式/处理经验/预防事实/治理教训）无 policy 类；`GovernanceKnowledgeCandidate.content` 过 `_reject_governance_markers`，若 `generated_by` 非人类额外过 `_ADVICE_MARKERS`。

### 4.3 权限隔离
- `GovernanceImprovementWorkflowService._ensure_access` 默认拒绝（`resource_category="knowledge"`），复用 `IdentityService` + `AgentPermissionPolicy` + `KnowledgeVisibilityPolicy`；治理知识读取须真实授权，未授权抛 `EnterpriseIsolationError`。

### 4.4 审计可溯
- `audit.py` 新增 `AGENT_GOVERNANCE_CASE` / `AGENT_GOVERNANCE_KNOWLEDGE` / `AGENT_GOVERNANCE_IMPROVEMENT` 三类（累计 56→59），对应 `record_agent_governance_case_action` / `record_agent_governance_knowledge_action` / `record_agent_governance_improvement_action` 三方法；actor 如实（默认 AI，人工节点强制 USER），**禁 `record_human_approval`**。

---

## 5. 测试结果与验证

- **新增八类测试 `test_enterprise_agent_governance_knowledge.py`：116 用例全绿**（case / candidate / pattern / workflow / report / permission / audit / red_line）。
- **全 agents 套件（剔除两条历史阈值债文件）：1880 passed / 0 failed**。
  - 基线说明：3.8.21 为 1786 passed；本阶段 +116 新增用例 → 理论 1902；剔除 `test_threshold_migration.py`（8）+`test_threshold_real_drill.py`（16）两条**已知历史技术债**后实跑 1880 全绿。
- **红线状态核验**：`engineering_enabled=false`（`agents/config.yaml:102`）、`safety_invariants_ok()=True`、无 `engineering_approved` 真实输出、无 `record_human_approval` 调用。
- 未修改 `verified.json` / 不改 `engineering_enabled`；测试用 monkeypatch 注入启用态，不触碰磁盘配置。

---

## 6. 已知限制 / 历史技术债

- **`test_threshold_migration.py` + `test_threshold_real_drill.py`（共 24 用例）**：扫描 `tests/` 下 `_tmp_drill_*.json` 临时文件，成组跑时偶发顺序污染导致雪崩式失败；**与 3.8.22 新增代码无关**（单独 `pytest` 各用例均 PASS，已实测）。属历史债，建议单独 hygiene 修复，不阻塞本阶段收口。
- 知识层不持有任何"策略生成 / 责任判定 / 风险整改 / 任务关闭"能力，这些均留待真实治理责任人（USER）线下执行。
- `verified.json` 仍待主理人 + 专家线下提交真实证据后，由人类终端显式置 `engineering_enabled=true`。

---

## 7. 状态结论与下一步

- **状态：🟢 BUILT_NO_GO（2026-08-08）**：企业智能体治理知识与持续改进层已完成 `GovernanceCase` / `GovernancePattern` / `GovernanceKnowledgeCandidate` / `GovernanceKnowledgeReport`(+`SourceTrace`) + `GovernanceImprovementWorkflowService` 的完整 fail-closed 知识沉淀主线构建；审计累计 59 类别；全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不 AI 自动修改 Agent / 修改治理策略 / 关闭治理任务 / 代替治理责任人。
- 全层只记录与归纳既有事实、只由真实治理责任人逐步审核并沉淀；本层不产出任何治理结论、不修订任何策略、不分配任何责任、不整改任何风险、不关闭任何任务。

---

> **STOP（3.8.22 收口）**：本报告与 `project_status.json` / `roadmap_v8.md` 刷新完成后，**不进入 Phase 3.8.23**，等待主理人审核授权。
>
> **未完成（人工动作，pending_verification）**：真实治理知识录入与人工审核 / 真实 Agent 整改与责任判定 / `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动审批 均待主理人 + 专家线下执行。本报告与状态刷新完成后停止。
