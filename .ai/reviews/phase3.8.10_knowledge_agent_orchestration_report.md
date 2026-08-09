# Phase 3.8.10 Enterprise Knowledge Agent Orchestration Layer 收口报告

- **阶段**：Phase 3.8.10 — 企业知识智能体编排层
- **身份**：BOIP AI Chief Architect
- **日期**：2026-08-05
- **状态**：🟢 **BUILT_NO_GO**（构建完成，零回归；激活态 `engineering_enabled=false`，不输出 `engineering_approved`）
- **后续**：本报告完成后**停止**，不进入 Phase 3.8.11，等待主理人审核授权

---

## 1. 目标与范围

在 3.8.9「企业知识智能检索与语义理解层」之上，构建**智能体编排层（Agent Orchestration Layer）**，
把四个 AI 智能体串成完整闭环：

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
                                  KnowledgeAnswerReview(真实 USER 复核)
```

约束（来自主理人授权）：
- 六条最高红线 fail-closed（①不开启 `engineering_enabled` ②不输出 `engineering_approved`
  ③不自动应用/执行知识 ④不自动生成工程结论 ⑤不绕过统一护栏 ⑥AI 不替代人工责任）。
- 智能体**只理解 / 召回 / 校验 / 起草**，**绝不批准、绝不落地、绝不生成工程结论**。
- 回答须引用来源（禁无来源），`requires_human_review` 强制 True。
- 复核必须由**真实 USER** 发起，AI 不得代责。

---

## 2. 交付代码（6 智能体 + 审计扩展）

| 模块 | 文件 | 关键契约 |
|---|---|---|
| 查询理解智能体 | `agents/enterprise/knowledge_query_agent.py` | `KnowledgeQueryAgent`（`parse_query`/`identify_intent`/`extract_filters`）；`KnowledgeQuery`（意图+过滤条件）；只理解，不生成工程判断 |
| 检索智能体 | `agents/enterprise/knowledge_retrieval_agent.py` | `KnowledgeRetrievalAgent`（`retrieve` → `KnowledgeContext`）；调用 3.8.9 `KnowledgeRetrievalEngine`，来源/版本/溯源自动派生，绝不落地 |
| 校验智能体 | `agents/enterprise/knowledge_validation_agent.py` | `KnowledgeValidationAgent`（`validate` → `KnowledgeAgentValidationResult`）；四维校验（来源/版本/权限/溯源），**只校验，绝不自动批准** |
| 回答起草智能体 | `agents/enterprise/knowledge_answer_agent.py` | `KnowledgeAnswerAgent`（`draft` → `KnowledgeAnswerDraft`）；references=上下文来源（非空），requires_human_review 强制 True |
| 编排器 | `agents/enterprise/knowledge_agent_orchestrator.py` | `KnowledgeAgentOrchestrator`（`run` 串四步 + `agent_event_log`）；四子智能体共享同一 audit/identity/visibility |
| 人工复核门 | `agents/enterprise/knowledge_answer_review.py` | `KnowledgeAnswerReview`（`submit_review_by_user`：真实 USER，禁 `auto_confirm`/`confirm`/`approve`） |
| 审计扩展 | `agents/enterprise/audit.py` | 新增枚举 `KNOWLEDGE_AGENT_QUERY`/`RETRIEVE`/`VALIDATE`/`DRAFT`（累计 **23**）+ 4 个 `record_*` 方法（actor 默认 AI，如实标注） |
| 聚合挂载 | `agents/enterprise/service.py` + `__init__.py` | `EnterpriseOperationLayer` 新增 6 个智能体成员；`__init__.py` 导出全部符号 |

---

## 3. 红线守约（6 条 fail-closed）

| 红线 | 落地方式 |
|---|---|
| ① 不开 `engineering_enabled` | 所有智能体 / 编排器 / 复核门 `__init__` 断言 `safety_invariants_ok()`；monkeypatch 翻转 `load_engineering_enabled=True` 后构造即抛 `EnterpriseRedLineViolationError`（测试实测拦截） |
| ② 不输出 `engineering_approved` | 所有相关类的 `approve`/`engineering_approved` 列入 `_FORBIDDEN` 元组，访问即抛错；静态测试 `test_no_engineering_approved_output_in_source` 验证源码中无赋值/返回，且 forbidden 元组守卫存在 |
| ③ 不自动应用/执行知识 | `auto_apply_knowledge`/`auto_execute_knowledge`/`auto_update_knowledge`/`publish`/`apply`/`commit` 等列入 `_FORBIDDEN`，访问即抛；代码库无 KnowledgeRepository 自动写入 |
| ④ 不自动生成工程结论 / 不自动审批 | `generate_engineering_conclusion`/`decide`/`approve`/`auto_approve`/`sign`/`authorize` 列入 `_FORBIDDEN`；校验智能体只产出 `ValidationResult`，绝不批准 |
| ⑤ 不绕过统一护栏 | 统一以 `safety_invariants_ok()` 作为构造/写路径前置护栏，等价于 UnifiedActivationGate |
| ⑥ AI 不替代人工责任 | 回答 `requires_human_review` 强制 True；审计禁 `record_human_approval`；复核须真实 USER（`reviewer_user_id` 非空且非 `ai`/`system` + `require_human_actor(USER)`）；actor 如实标注（四智能体动作=AI，人工复核=USER） |

---

## 4. 测试与回归（Task 8）

新增 **8 类测试共 42 用例**，全绿：

| 测试文件 | 覆盖 | 用例数 |
|---|---|---|
| `test_enterprise_knowledge_query_agent.py` | 查询理解智能体：parse/intent/filters/审计/红线 | 5 |
| `test_enterprise_knowledge_retrieval_agent.py` | 检索智能体：可追溯上下文/审计/红线 | 3 |
| `test_enterprise_knowledge_validation.py` | 校验智能体：pass/source_gap/permission_denied/审计/红线 | 5 |
| `test_enterprise_knowledge_answer_agent.py` | 回答起草智能体：references/审计/禁无来源/红线 | 4 |
| `test_enterprise_knowledge_orchestrator.py` | 编排器：run 闭环/agent_event_log/4 审计/启用态拦截 | 3 |
| `test_enterprise_knowledge_review.py` | 人工复核：真实USER/拒ai/非法decision/审计/红线 | 6 |
| `test_enterprise_knowledge_agent_audit.py` | 审计 4 类别存在/全链路审计轨迹/无 record_human_approval | 3 |
| `test_enterprise_knowledge_agent_redline.py` | 6 类全部 fail-closed/无 engineering_approved 输出/复核拒 ai/红线基座导入 | 4 |

另更新既有治理审计测试（`test_enterprise_knowledge_governance_audit.py` 枚举 19→23，新增 4 条 agent 审计方法测试）
与智能检索审计测试（`test_enterprise_knowledge_intelligence_audit.py` 总数 19→23）。

**全 agents 套件回归**：`pytest tests/agents -q` → **1335 passed（1293 基线 + 42 新增），零回归**，实测 32.18s。

---

## 5. 关键设计决策

1. **智能体只做一件事，职责单一**：理解 / 召回 / 校验 / 起草四者分离，任一智能体都不具备「批准 / 落地 / 结论生成」能力（结构上不可达）。
2. **编排器是纯协调者**：`KnowledgeAgentOrchestrator` 不持有任何业务数据，仅串接四智能体并写 `agent_event_log`；
   为统一红线姿态，同样继承 `_RedLineForbiddenMixin`（防御性 fail-closed）。
3. **校验 ≠ 批准**：`KnowledgeValidationAgent.validate` 仅对知识上下文做质量校验，输出 `ValidationResult.passed`，
   但 `requires_human_review` 强制 True，绝不把校验结果当作「答案已被批准」。
4. **来源强制可追溯**：回答草稿 `references` 取自 `KnowledgeContext.sources`；若上下文无来源，`KnowledgeAnswerDraft`
   在结构上拒绝（ValueError：禁止无来源回答）。
5. **真实人工复核门**：`KnowledgeAnswerReview.submit_review_by_user` 是闭环最后一环，必须真实 USER 发起，
   决策（accepted/rejected/needs_revision）仅承载人工意见，不触发任何知识自动落地或 `engineering_enabled` 翻转。

---

## 6. 验证结果

- ✅ `engineering_enabled=false`（`agents/config.yaml:102` 真实读取，未改动）。
- ✅ 全 agents 套件 **1335 passed 零回归**。
- ✅ 启用态（`load_engineering_enabled=True`）下全部智能体 / 编排器 / 复核门构造即抛错（红线①/⑤ fail-closed）。
- ✅ 静态扫描确认无 `engineering_approved` 输出/赋值；无 `record_human_approval` 可用入口（红线②/⑥）。
- ✅ 未修改 `verified.json` / `config.yaml` / `engineering_enabled`；不输出 `engineering_approved`。
- ✅ 回答须引用来源、推荐/草稿 `requires_human_review` 强制 True（红线⑥）。

---

## 7. 状态结论与下一步

- **状态：🟢 BUILT_NO_GO（2026-08-05）**：企业知识智能体编排层已完成查询理解 + 检索召回 + 来源校验 +
  回答起草 + 智能体编排 + 真实人工复核的完整闭环构建，全量测试零回归；`engineering_enabled=false` 守约，
  不输出 `engineering_approved`，不自动应用知识、不生成工程结论、不审批、不 AI 代责。
- **未完成（人工动作，pending_verification）**：真实证据录入与 `verified.json` 真实化 / `engineering_enabled` 开启 /
  真实工程参数 / 报价 / 自动经营建议 / 自动审批 均待主理人 + 专家线下执行。
- **下一步**：**本报告完成后停止，不进入 Phase 3.8.11**，等待主理人审核授权。
