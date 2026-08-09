# BOIP Phase 3.8.9 收口报告 —— Enterprise Knowledge Intelligence & Semantic Retrieval Layer（企业知识智能检索与语义理解层）

- **阶段**：Phase 3.8.9（Enterprise 层，知识智能检索与语义理解）
- **身份**：BOIP AI Chief Architect
- **日期**：2026-08-05
- **状态**：🟢 `ENTERPRISE_KNOWLEDGE_INTELLIGENCE_BUILT_NO_GO`（已构建，未授权启用）
- **激活态**：`engineering_enabled=false`（真实读取 `agents/config.yaml` line 102）；不输出 `engineering_approved`
- **测试基线**：全 agents 套件 **1293 passed**（1240 基线 + 53 新增，零回归，30.46s）

---

## 1. 目标与范围

进入企业知识智能检索与语义理解层，把「知识资产 → 语义理解 → 检索 → 引用 → 人工使用」的链路在企业侧结构化为可审计、可追溯、fail-closed 的六模块能力。本层**只检索、只候选、只起草**，绝不自动应用知识、绝不生成工程结论、绝不 AI 代责。

**6 条 fail-closed 红线（全程守约）**：
- ① 禁止开启 `engineering_enabled`（所有构造/写路径断言 `safety_invariants_ok()`）。
- ② 禁止输出 `engineering_approved`（forbidden 方法名拦截）。
- ③ 禁止自动改/应用知识（`auto_update_knowledge`/`auto_publish_knowledge`/`auto_merge_knowledge`/`auto_apply_knowledge` 拦截）；代码库无 KnowledgeRepository，引擎 `index()` 仅目录化已存在的人工知识元数据。
- ④ 禁止 AI 自动生成工程结论（`generate_engineering_conclusion` 拦截）；`approve`/`sign`/`authorize` 结构性拦截。
- ⑤ 禁止绕过 `UnifiedActivationGate`（以 `safety_invariants_ok()` 作为统一前置护栏）。
- ⑥ 禁止 AI 代替专家责任（`require_human_actor(USER)` 强制人工复核节点；`requires_human_review` 强制 True；审计禁 `record_human_approval`；actor 如实标注）。

---

## 2. 任务对照（9 任务全交付）

| # | 任务 | 交付物 | 状态 |
|---|---|---|---|
| 1 | `KnowledgeSearchQuery` | `knowledge_search.py`：`KnowledgeSearchQuery`（query_id/org_id/user_id/query_text/filters/created_at，强制 org_id 隔离）+ `KnowledgeSearchService` | ✅ |
| 2 | `KnowledgeRetrievalEngine` | `knowledge_retrieval.py`：`KnowledgeItem` + `KnowledgeRetrievalEngine`（`search`/`semantic_match`/`filter_by_permission`/`retrieve_context`，只返回候选知识） | ✅ |
| 3 | `KnowledgeContext` | `knowledge_context.py`：`KnowledgeTrace` + `KnowledgeContext`（context_id/knowledge_items/sources/versions/trace，所有知识可溯源） | ✅ |
| 4 | `KnowledgeAnswerDraft` | `knowledge_answer.py`：`KnowledgeAnswerDraft`（answer_id/query_id/references/confidence/requires_human_review，须引用来源，禁无来源回答） | ✅ |
| 5 | `KnowledgeRecommendationCandidate` | `knowledge_recommendation.py`：`KnowledgeRecommendationCandidate`（仅为候选，禁 `auto_apply_knowledge`） | ✅ |
| 6 | 权限接入 | `knowledge_visibility.py`：`KnowledgeVisibilityPolicy`（基于 `IdentityService` 角色默认拒绝检索）；引擎 `filter_by_permission` 接入 | ✅ |
| 7 | 审计增强 | `audit.py`：新增 `KNOWLEDGE_SEARCH`/`KNOWLEDGE_RETRIEVAL`/`KNOWLEDGE_QUERY` 三枚举 + `record_knowledge_search_action`/`record_knowledge_retrieval_action`/`record_knowledge_query_action`；actor 真实；禁 `record_human_approval` | ✅ |
| 8 | 测试 | 8 类共 53 用例（search/retrieval/permission/context/answer_trace/recommendation/audit/redline） | ✅ |
| 9 | 最终验证 | `pytest tests/agents -q` 全过；`engineering_enabled=false`；无 `engineering_approved`；刷新 `project_status.json` + `roadmap_v8.md` | ✅ |

---

## 3. 源码要点（6 模块 + 审计扩展）

| 模块 | 路径 | 关键契约 |
|---|---|---|
| 检索查询 | `agents/enterprise/knowledge_search.py` | `KnowledgeSearchQuery`（强制 org_id）+ `KnowledgeSearchService`（`create_query`/`run`/`run_with_context`）；编排检索引擎；查询在组织作用域隔离 |
| 检索引擎 | `agents/enterprise/knowledge_retrieval.py` | `KnowledgeItem` + `KnowledgeRetrievalEngine`（`search`/`semantic_match`/`filter_by_permission`/`retrieve_context`）；启发式词元重叠打分（无外部嵌入依赖）；只返回候选知识；`index()` 仅目录化已存在知识元数据 |
| 知识上下文 | `agents/enterprise/knowledge_context.py` | `KnowledgeTrace` + `KnowledgeContext`；`__post_init__` 自动派生 `sources`/`versions`/`trace`，`has_source_gaps()` 识别缺来源项；所有知识可溯源 |
| 回答草稿 | `agents/enterprise/knowledge_answer.py` | `KnowledgeAnswerDraft`（references 非空强制，禁无来源；`requires_human_review` 强制 True）+ `KnowledgeAnswerService.draft_answer` |
| 推荐候选 | `agents/enterprise/knowledge_recommendation.py` | `KnowledgeRecommendationCandidate`（仅为候选，`requires_human_review` 强制 True）+ `KnowledgeRecommendationService.recommend`（`recommend` 为合法入口，不在 `_FORBIDDEN`） |
| 可见性策略 | `agents/enterprise/knowledge_visibility.py` | `KnowledgeVisibilityPolicy`（`_ROLE_VISIBLE_KNOWLEDGE` 角色→知识类型，默认拒绝）；引擎 `filter_by_permission` 接入 |
| 审计扩展 | `agents/enterprise/audit.py` | 新增 `KNOWLEDGE_SEARCH`/`KNOWLEDGE_RETRIEVAL`/`KNOWLEDGE_QUERY`（枚举累计 19）；三 `record_*` 方法（search/retrieval 默认 USER，query 默认 AI）；无 `record_human_approval` |
| 聚合/导出 | `agents/enterprise/service.py` + `__init__.py` | 挂载 `knowledge_visibility`/`knowledge_retrieval`/`knowledge_search`/`knowledge_answers`/`knowledge_recommendations`；导出 12 新符号 |

**红线守约机制（复用 `_RedLineForbiddenMixin`）**：各服务 `_FORBIDDEN` 元组精确命中 forbidden 方法名（`__getattr__` 精确匹配拦截），不含任何合法方法名（如 `recommend`/`search`/`draft_answer` 等均可达）。人工门禁方法（`require_human_actor`）与断言（`safety_invariants_ok()`）从基座继承。

---

## 4. 数据流与可追溯闭环

```
用户查询 KnowledgeSearchQuery(org_id,user_id,query_text)
   │  create_query → 审计 KNOWLEDGE_SEARCH(USER)
   ▼
KnowledgeRetrievalEngine.search
   │  ① semantic_match 打分 → ② filter_by_permission(角色,默认拒绝) → ③ 业务过滤 → ④ top_k
   │  返回候选 KnowledgeItem[]（绝不生成工程结论）
   │  审计 KNOWLEDGE_RETRIEVAL(USER)
   ▼
KnowledgeContext（由候选项拼装，自动派生 sources/versions/trace，全部可溯源）
   │
   ├─ KnowledgeAnswerDraft（须引用来源 references 非空，requires_human_review=True）
   │     审计 KNOWLEDGE_QUERY(AI 起草)
   └─ KnowledgeRecommendationCandidate（仅为候选，requires_human_review=True，禁 auto_apply）
         审计 KNOWLEDGE_RETRIEVAL(AI 提议)
```

所有路径**只产出候选/草稿**，最终采用、知识落地、版本激活、工程结论生成均须经真实人工（主理人 + 专家）线下执行。

---

## 5. 测试与回归（8 类 53 用例全绿）

| 测试文件 | 用例数 | 覆盖 |
|---|---|---|
| `test_enterprise_knowledge_search.py` | 9 | 查询强制 org_id、create_query 审计、run 返回候选、run_with_context 可追溯、跨域隔离、forbidden 拦截 |
| `test_enterprise_knowledge_retrieval.py` | 9 | index 目录化、search 相关度排序、empty query 空、semantic_match 打分、filter_by_permission 默认拒绝、retrieve_context 溯源、禁生成工程结论、审计 |
| `test_enterprise_knowledge_retrieval_permission.py` | 6 | ADMIN 全可见、DESIGNER/ENGINEER 不可见 feedback、REVIEWER 不可见 design_spec、未分类默认拒绝、引擎按角色过滤、默认拒绝 |
| `test_enterprise_knowledge_context.py` | 6 | 自动派生 sources/versions/trace、逐条溯源、source gaps 识别、item_ids、空项集合 |
| `test_enterprise_knowledge_answer_trace.py` | 6 | 须引用来源（空 references 抛错）、requires_human_review 强制、confidence 边界、审计、禁 auto_apply/conclusion |
| `test_enterprise_knowledge_recommendation.py` | 6 | 推荐候选、requires_human_review 强制、score 边界、审计、禁 auto_apply、跨域隔离 |
| `test_enterprise_knowledge_intelligence_audit.py` | 6 | 三新枚举、三 record 方法、枚举累计 19、actor 真实、禁 record_human_approval |
| `test_enterprise_knowledge_intelligence_redline.py` | 6 | 构造 fail-closed（enabled 翻转抛错）、无 engineering_approved、禁 auto_apply、禁 conclusion/decide、require_human_actor 拒绝 AI |

- 全 agents 套件 **1293 passed（1240 基线 + 53 新增）零回归**（2026-08-05 实测，30.46s）。
- 未修改 `verified.json` / `config.yaml` / `engineering_enabled`；`engineering_enabled=false`；不输出 `engineering_approved`。

---

## 6. 交付物清单（3.8.9）

| 类型 | 路径 |
|---|---|
| 检索查询 | `agents/enterprise/knowledge_search.py` |
| 检索引擎 | `agents/enterprise/knowledge_retrieval.py` |
| 知识上下文 | `agents/enterprise/knowledge_context.py` |
| 回答草稿 | `agents/enterprise/knowledge_answer.py` |
| 推荐候选 | `agents/enterprise/knowledge_recommendation.py` |
| 可见性策略 | `agents/enterprise/knowledge_visibility.py` |
| 审计扩展 | `agents/enterprise/audit.py` |
| 聚合/导出 | `agents/enterprise/service.py`、`agents/enterprise/__init__.py` |
| 测试×8 | `tests/agents/test_enterprise_knowledge_{search,retrieval,retrieval_permission,context,answer_trace,recommendation,intelligence_audit,intelligence_redline}.py` |
| 收口报告 | `.ai/reviews/phase3.8.9_knowledge_intelligence_retrieval_report.md` |
| 状态刷新 | `.ai/project_status.json`（顶层 `phase_3_8_9_status=ENTERPRISE_KNOWLEDGE_INTELLIGENCE_BUILT_NO_GO` + `current_stage.phase_3_8_9_status`） |
| 路线刷新 | `.ai/roadmap_v8.md` §12 |

---

## 7. 状态结论与终止点

- **状态：🟢 BUILT_NO_GO（2026-08-05）**：企业知识智能检索与语义理解层已完成检索查询 + 语义检索引擎 + 可追溯上下文 + 带来源回答草稿 + 推荐候选 + 角色可见性策略 + 审计 3 类别的完整构建，全量测试零回归；`engineering_enabled=false` 守约，不输出 `engineering_approved`，不自动应用知识、不生成工程结论、不审批、不 AI 代责。
- **未完成（人工动作，pending_verification）**：真实证据录入与 `verified.json` 真实化 / `engineering_enabled` 开启 / 真实工程参数 / 报价 / 自动经营建议 / 自动审批 均待主理人 + 专家线下执行。
- **本报告完成后停止，不进入 Phase 3.8.10**，等待主理人审核授权。
