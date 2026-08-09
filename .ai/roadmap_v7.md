# BOIP 研发路线 V7（roadmap_v7.md）

- **生成**：2026-08-03
- **身份**：BOIP AI Chief Architect（Phase 3.7.0 工程智能能力扩展 · 架构设计）
- **性质**：Phase 3.7.0 = **工程智能能力扩展架构设计（非实现、非激活）**：基于真实代码扫描盘点 5 工程 Agent + 知识智能层能力，规划图纸解析/方案生成/成本计算/知识推理/多Agent协作五条路线，设计 KnowledgeItem/Case/Rule/Threshold/Expert 知识图谱，界定 AI 辅助与人工审核边界。
- **依据**：`.ai/project_status.json`（SSOT，current_roadmap_version=V7）、`.ai/reviews/phase3.7.0_engineering_intelligence_expansion_architecture.md`、真实源码 `agents/engineering/calc/*.py` + `agents/engineering/knowledge/intelligence/*.py`
- **权威声明**：本文件取代 `roadmap_v6.md`，为 Phase 3.7.0 起的唯一研发路线；roadmap_v6.md 保留为 Phase 3.6.x 历史归档。

---

## 1. 当前真实状态（Phase 3.7.0 架构设计态）

| 维度 | 真实状态 |
|---|---|
| 阶段 | 3.7.0 架构 ✅ → 3.7.1 基础层 ✅ → 3.7.2 推理层 ✅ → 3.7.3 案例层 ✅ → 3.7.4 方案生成层 ✅ → 3.7.5 方案约束与优化层 ✅ → 3.7.6 成本智能层 ✅ → 3.7.7 图纸智能层 ✅ → 🟢 **3.7.8 工作流编排层 DONE（2026-08-03）** → 🟢 **3.7.9 工程 AI 助手交互层 DONE（2026-08-03）** |
| 工程 Agent 能力 | 5 计算单元（WindPressure/Glass/Profile/Hardware/InstallationRisk）均为**符号结构装配器**，`result=""`、`PENDING_VERIFICATION`、中间量全 `None`；跨模块闸门已就位（wind→glass/profile→hardware→installation_risk） |
| 知识智能层 | Knowledge Graph（**7 实体 / 17 关系** / Repository / 只读推理层 / 案例层 / 方案生成层）+ `KnowledgeRelationshipEngine` / `KnowledgeQualityAnalyzer` / `KnowledgeConflictDetector` 已建，**全部只读、review_required 恒 True**；方案生成层产出候选但仅人工审核批准 |
| 红线 | `engineering_enabled=false`（真实读取 `agents/config.yaml`）；无任何 `engineering_approved` 输出；不自动确认图纸尺寸；不自动生成真实工程参数；不自动报价；零伪造工程参数 |
| 激活态 | **NO-GO 维持**：`engineering_enabled=False`；ESW 窗口 `OPEN_EMPTY`；真实阈值仍为 `value=null/verified=false` |
| 未完成（人工动作） | 真实双签阈值录入 / 显式置 `engineering_enabled=true` / 人类对方案与报价作 `Engineering_Approved` 均 pending_verification |

**红线（不可逾越）**：不自动开启 `engineering_enabled`；不输出 `engineering_approved`；不绕过 `UnifiedActivationGate`；不伪造工程参数；不创建 `ReleaseApproval`；不 AI 代签/代授权。

---

## 2. Phase 3.7.0 路线（Engineering Intelligence Expansion — 架构）

> **Phase 3.7.0 定位**：在 3.3–3.6 知识治理与激活治理地基之上，**规划**工程智能能力扩展方向。本轮仅产出架构设计（能力矩阵 / 路线图 / 知识图谱 / 边界），不进入编码实现、不开启 `engineering_enabled`、不输出 `engineering_approved`。

### 2.1 已交付（架构设计 + 红线守约）

- **3.7.0** Engineering Intelligence Expansion Architecture。**DONE（2026-08-03）· 架构设计**
  - ✅ **任务1 工程 Agent 能力矩阵**：基于真实代码扫描 5 计算单元（`calc/*.py`）+ 知识智能层（`knowledge/intelligence/*.py`）；结论——当前智能 = 符号装配 + 只读分析，无数值推理、无真实参数、无成本/图纸解析实现。
  - ✅ **任务2 Engineering Intelligence Roadmap**：五路线——① 图纸解析（Vision→DesignCandidate 适配器，待建）② 方案生成（SolutionGenerator 编排，待建）③ 成本计算（`calc/cost.py` + `rules/cost_rules.py`，**未实现**）④ 知识推理（KnowledgeGraphEngine 图谱遍历，待建）⑤ 多Agent协作（`orchestration.py` DAG 调度，待建）。
  - ✅ **任务3 Knowledge Graph 需求**：五实体（KnowledgeItem/Case/Rule/Threshold/Expert）+ 12 条边（references/authored_by/parent_child/sourced_from/used_by/applies/cites/basis/witnessed_by/signs）+ 5 条不变量 I1–I5；机器可读 schema 内含于主报告。
  - ✅ **任务4 Phase 3.7 架构边界**：AI 辅助（符号装配/只读分析/解析草稿/变体预筛/BOM草稿/图谱遍历/编排）vs 人工审核（双签阈值/显式 enabled/approved/专家签署/冲突 merge/尺寸核验/方案报价批准）；fail-closed 不变量延续。
  - ✅ 交付 `.ai/reviews/phase3.7.0_engineering_intelligence_expansion_architecture.md` + 更新 `.ai/project_status.json`（phase_3_7 块，current_roadmap_version=V7）+ 本 roadmap_v7.md。

### 2.2 后续候选实现（须人工解锁后启动，非本轮范围）

| 路线 | 建议实现入口 | 解锁前提 |
|---|---|---|
| 图纸解析 | `agents/vision/design_candidate_adapter.py` | Vision 已接入（Phase 2）；人类核验尺寸 + 规范映射 |
| 方案生成 | `agents/engineering/solution_generator.py` | 阈值双签 + `engineering_enabled=true` |
| 成本计算 | `agents/engineering/calc/cost.py` + `rules/cost_rules.py` | `Case`/`cost_rule` 知识就绪 + 单价 source_ref verified |
| 知识推理 | `agents/engineering/knowledge/graph_engine.py` | Knowledge Graph 落库（Case 实体待建） |
| 多Agent协作 | `agents/engineering/orchestration.py` | 复用既有关卡函数；整体受 `UnifiedActivationGate` 约束 |

### 2.3 Phase 3.7.1 Knowledge Graph Foundation（基础层实现 DONE，2026-08-03）

> **定位**：在 3.7.0 架构设计之上，**落地可运行的图谱基础层**（代码实现）。本轮为 Foundation（实体/关系/仓库/接入/冲突/测试），**不开启 `engineering_enabled`、不输出 `engineering_approved`、不伪造工程参数**。

- ✅ **任务1 实体 Schema**：`KnowledgeItem`(复用 connector 13 字段七态) / `Threshold`(复用 schema,value=pending) / `Expert`(复用 experts.json) / `SourceRef`(复用 ThresholdSourceRef) / `Case`&`Rule`(pending_build 骨架，不填真实值)。见 `agents/engineering/knowledge/graph/entities.py`。
- ✅ **任务2 关系 Schema**：`references`/`authored_by`/`parent_child`/`sourced_from`/`used_by`/`applies`/`cites`/`basis`/`witnessed_by`/`signs` 共 **10 关系**，含起止实体约束 + 必需属性 + 不变量；`validate_edge` fail-closed 校验。见 `relationships.py`。
- ✅ **任务3 Graph Repository**：`KnowledgeGraphRepository.add_node`/`add_edge`/`query`/`traverse`/`history` + append-only 审计（`GraphAuditLog`，who/when/hash/version，拒 merge/delete/approve）。见 `repository.py`。
- ✅ **任务4 单向接入**：`KnowledgeRepositoryToGraphSync`（Repository→Graph），图谱不回写，Repository 为唯一事实源；仅建存根节点、不编造值。见 `integration.py`。
- ✅ **任务5 冲突保护**：`KnowledgeGraphConflictDetector`，`review_required` 恒 True，**无 merge/delete/approve 方法**；类型 `duplicate_node`/`dangling_edge`/`type_mismatch`/`pending_build_edge`。见 `conflict.py`。
- ✅ **任务6 测试**：`tests/agents/test_knowledge_graph.py` **33 用例全绿**（schema/entity/relationship/audit/red line）；既有知识测试 70 用例无回归；不碰 `verified.json` 与 `engineering_enabled`。
- ✅ 交付 `.ai/reviews/phase3.7.1_knowledge_graph_foundation_report.md` + 更新 `.ai/project_status.json`（`phase_3_7.3.7.1` 块）+ 本 roadmap_v7.md。

**激活态**：`engineering_enabled=false`；`NO-GO` 维持；ESW 窗口 `OPEN_EMPTY`；图谱仅承载待人工补全骨架，禁止在 enabled 前参与工程判定。

---

### 2.4 Phase 3.7.2 Knowledge Graph Query & Reasoning Layer（推理层实现 DONE，2026-08-03）

> **定位**：在 3.7.1 基础层之上，**新增只读推理层**（`KnowledgeGraphQueryEngine`），支撑查询/寻路/影响分析/关联推理/冲突保持人工审核。**全只读、不审批、不处置、不编造**；不开启 `engineering_enabled`、不输出 `engineering_approved`、不伪造工程参数。

- ✅ **任务1 Graph Query Engine**：`KnowledgeGraphQueryEngine`（构造即断言 `safety_invariants_ok()`→`engineering_enabled=False`，红线①）；`node_query()`(包装 `graph.query`) / `edge_query()`(按 relation_type/source/target 只读过滤) / `path_query()`(start→end 双向 BFS 寻路，支持关系白名单 + 最大跳数) / `impact_analysis()`(threshold impact 仅报告)。见 `agents/engineering/knowledge/graph/query.py`。
- ✅ **任务2 知识路径分析**：`trace_knowledge_path()` 追踪 `KnowledgeItem → Threshold → Rule → CalcAgent` 候选链；输出 candidate analysis，`approval_forbidden` 恒 True；CalcAgent 仅为 pending 候选，**禁止 approve**。
- ✅ **任务3 影响分析**：`impact_analysis(threshold_id)` 收集受影响的 `KnowledgeItem` / `Rule` / `Case` / `CalcAgent 候选`，`requires_human_review=True`，**仅报告、不处置**。
- ✅ **任务4 知识关联推理**：`reason_associations()` 关系遍历支持 `parent_child`/`references`/`cites`/`basis`（双向），复用 `graph.traverse`。
- ✅ **任务5 冲突保持人工审核**：`conflict_scan()` 复用 `KnowledgeGraphConflictDetector`，包装 `ReasoningConflictCandidate`（`review_required` 恒 True / `auto_resolvable` 恒 False）；本引擎**无 merge/delete/approve 方法**。
- ✅ **任务6 测试**：`tests/agents/test_knowledge_graph_reasoning.py` **27 用例全绿**（query/path/impact/audit/red line）；既有 KG 基础测试 33 用例无回归；合计 **60 passed**；不碰 `verified.json` 与 `engineering_enabled`。
- ✅ 交付 `.ai/reviews/phase3.7.2_knowledge_graph_reasoning_report.md` + 更新 `.ai/project_status.json`（`phase_3_7.3.7.2` 块）+ 本 roadmap_v7.md。

**激活态**：`engineering_enabled=false`；`NO-GO` 维持；ESW 窗口 `OPEN_EMPTY`；推理输出均为候选分析，禁止在 enabled 前被当作工程判定依据。

---

### 2.5 Phase 3.7.3 Case Knowledge Layer（案例层实现 DONE，2026-08-03）

> **定位**：在 3.7.1 基础层 + 3.7.2 推理层之上，**新增案例知识层**（`CaseEntity` + `CaseLifecycle` 状态机 + 3 关系扩展）。本轮为案例载体与生命周期，**不开启 `engineering_enabled`、不输出 `engineering_approved`、不伪造真实案例**。

- ✅ **任务1 案例实体**：`CaseEntity`（case_id/project_ref/environment/title/description/domain/design_context/solution/outcome/lessons/linked_thresholds/linked_rules/linked_experts/lifecycle_stage/status）；`to_node` 标 `pending_build=True`（禁止在 enabled 前当就绪实体）；`from_node` 兼容旧键 `related_thresholds`；`from_empty` 壳构造（仅 case_id 占位，不填真实值，红线③）。见 `agents/engineering/knowledge/graph/entities.py`。
- ✅ **任务2 案例生命周期**：`CaseLifecycleStage`(Captured/Verified_Source/Expert_Reviewed/Engineering_Referenced) + `CaseLifecycle`（`advance(by_human_reviewer=False)` 守卫，非法转移抛 `CaseLifecycleError`，`requires_human_review` 恒 True），真实推进仅人工驱动（红线⑤）。见 `agents/engineering/knowledge/graph/case_lifecycle.py`。
- ✅ **任务3 案例链路关系**：新增 `case_item`(Case→KnowledgeItem) / `threshold_rule`(Threshold→Rule) / `rule_expert`(Rule→Expert) 三关系，`validate_edge` fail-closed 校验不变；关系白名单 10→13。见 `relationships.py`。
- ✅ **任务4 测试**：新增 Case 实体/生命周期/关系/red line 用例；基座 KG 测试同步 6 实体/13 关系断言；既有套件无回归（随 3.7.4 合并后 agents 全套 670 passed）；不碰 `verified.json` 与 `engineering_enabled`。
- ✅ 交付 `.ai/reviews/phase3.7.3_case_knowledge_layer_report.md` + 更新 `.ai/project_status.json`（`phase_3_7.3.7.3` 块）+ 本 roadmap_v7.md。

**激活态**：`engineering_enabled=false`；`NO-GO` 维持；案例真实内容须人工经 ESW 窗口导入。

---

### 2.6 Phase 3.7.4 Engineering Solution Generation Layer（方案生成层实现 DONE，2026-08-03）

> **定位**：在 3.7.1–3.7.3 图谱基座之上，**新增工程方案生成层**（`SolutionCandidate` + `DesignCandidate` + `SolutionGenerator` + `SolutionEvaluator` + `SolutionReviewQueue` + 4 关系）。本轮为候选生成/评价/人工审核，**不开启 `engineering_enabled`、不输出 `engineering_approved`、不自动选终、不伪造工程参数**。

- ✅ **任务1 方案候选模型**：`SolutionCandidateEntity`（solution_id/input_context/related_cases/related_rules/related_thresholds/components/confidence/verification_status/status），`to_node` 标 `pending_build=True`，`verification_status` 默认 `PENDING_VERIFICATION`（常量复用 `pending_verification` 同值）；新增 `DesignCandidate` 入参契约（构造即断言 `load_engineering_enabled() is False`，红线①）。见 `entities.py`。
- ✅ **任务2 方案生成器**：`SolutionGenerator`（输入 `DesignCandidate` + `KnowledgeGraphRepository` + 可选 `Case` 列表，产出 `list[SolutionCandidateEntity]` 多候选；`persist=True` 时落 candidate 节点 + 四关系；无 `select`/`finalize`，断言 `UnifiedActivationGate.safety_invariants_ok()`，红线③/⑤）。见 `agents/engineering/knowledge/graph/solution_generation.py`。
- ✅ **任务3 方案关联图谱**：新增 4 关系 `solution_case`/`solution_rule`/`solution_threshold`/`solution_knowledge_item`（`SolutionCandidate`→Case/Rule/Threshold/KnowledgeItem），`validate_edge` fail-closed 校验不变；关系白名单 13→17；实体 6→7。见 `relationships.py`。
- ✅ **任务4 候选评价**：`SolutionEvaluator`（`compatibility_check`/`risk_check`/`knowledge_trace` 输出解释链；`requires_human_review` 恒 True；无终裁，红线③）。见 `solution_generation.py`。
- ✅ **任务5 人工审核**：`SolutionReviewQueue`（`candidate`→`reviewing`→`approved_by_human`/`rejected`；`approve`/`reject` 仅 `by_human=True` 可入，AI 调用抛 `SolutionRedLineViolationError`，红线②/③；非法转移抛 `SolutionReviewError`）。见 `solution_generation.py`。
- ✅ **任务6 测试**：新增 solution entity/generator/trace/review queue/red line 五类（`tests/agents/test_knowledge_graph_solution.py`）；基座 `test_knowledge_graph.py` 同步 7 实体/17 关系断言；不修改 `verified.json` 与 `engineering_enabled`；全 agents 套件 **670 passed** 零回归。
- ✅ 交付 `.ai/reviews/phase3.7.4_solution_generation_layer_report.md` + 更新 `.ai/project_status.json`（`phase_3_7.3.7.4` 块）+ 本 roadmap_v7.md。

**激活态**：`engineering_enabled=false`；`NO-GO` 维持；方案候选仅骨架，禁止在 enabled 前被当作工程依据。

### 2.7 Phase 3.7.5 Solution Constraint & Optimization Layer（方案约束与优化层 DONE，2026-08-03）

> **Phase 3.7.5 定位**：在 3.7.4 方案生成层之上，建立「方案约束与优化层」——定义约束模型、约束引擎（仅过滤明显冲突）、候选对比（无 winner）、可解释层（完整来源链）、审核队列三阶段扩展。**不**自动选终、不自动报价、不伪造工程参数、不开启 `engineering_enabled`、不输出 `engineering_approved`。

- ✅ **任务1 约束模型**：`SolutionConstraint`（constraint_id/type/source/severity/description/status），纯数据占位壳（**非图谱实体**：不进 `KnowledgeGraphEntityType`、不进 `_ENTITY_DISPATCH`、不新增关系白名单）；type/source/severity/description 默认 `PENDING_PLACEHOLDER`、status 默认 `PENDING_VERIFICATION`，AI 不填真实约束数值。见 `agents/engineering/knowledge/graph/entities.py`。
- ✅ **任务2 约束引擎**：`SolutionConstraintEngine`（`check_geometry`/`check_dependency`/`check_compatibility`/`check_conflict`），仅过滤明显冲突（id 重复 / 引用缺失 / 上下文互斥），无 `select`/`finalize`，构造与方法均断言 `UnifiedActivationGate.safety_invariants_ok()`（红线①/③/⑥）。见 `agents/engineering/knowledge/graph/solution_constraint.py`。
- ✅ **任务3 候选对比**：`SolutionComparison`（比较 A/B/C，输出 `difference`/`risk`/`knowledge_trace`，`winner` 恒 None，由 `_RedLineForbiddenMixin` 拦截 `select`/`finalize`/`quote`/`pricing`，红线③/④）。见 `solution_constraint.py`。
- ✅ **任务4 可解释层**：`SolutionExplanation`（沿四关系只读 `traverse` 构建 Case/Rule/Threshold/KnowledgeItem **完整来源链**，只读不写，红线③/⑤/⑥）。见 `solution_constraint.py`。
- ✅ **任务5 审核队列增强**：`SolutionReviewQueue` 扩展 `record_constraint_review`/`record_expert_review`/`human_decision` 三阶段（均仅 `by_human=True` 可驱动，`human_decision` 须两审查完成前置；AI 调用一律抛 `SolutionRedLineViolationError`，红线②/③）；保留既有 `approve`/`reject`。见 `agents/engineering/knowledge/graph/solution_generation.py`。
- ✅ **任务6 测试**：新增 `tests/agents/test_knowledge_graph_constraint.py`（constraint/comparison/explain/review/red line 五类，**+22 用例**）；基座 `test_knowledge_graph.py` 同步 7 实体/17 关系断言不受影响（`len(RELATIONSHIP_SPECS)==17` 仍成立）；不修改 `verified.json` 与 `engineering_enabled`；全 agents 套件 **692 passed** 零回归。
- ✅ 交付 `.ai/reviews/phase3.7.5_solution_constraint_optimization_report.md` + 更新 `.ai/project_status.json`（`phase_3_7.3.7.5` 块）+ 本 roadmap_v7.md。

**激活态**：`engineering_enabled=false`；`NO-GO` 维持；方案约束/对比/解释仅骨架，禁止在 enabled 前被当作工程依据。

---

### 2.8 Phase 3.7.6 Cost Intelligence Layer（成本智能层 DONE，2026-08-02）

> **Phase 3.7.6 定位**：在 3.7.5 方案约束与优化层之上，建立「成本智能层」——定义 BOM 模型、成本规则模型、成本估算器（仅占位估算、禁止报价/成交价/伪造市场价）、成本解释链（关联 Solution/BOM/Rule/SourceRef）、成本人工审核队列（仅人工可批准）。**不**自动报价、不自动成交价格、不伪造市场价格、不开启 `engineering_enabled`、不输出 `engineering_approved`。

- ✅ **任务1 BOM 模型**：`BOMEntity`（bom_id/solution_id/item_type/item_name/quantity/unit/source_ref/status），纯数据占位壳（**非图谱实体**：不进 `KnowledgeGraphEntityType`、不进 `_ENTITY_DISPATCH`、不新增关系白名单）；item_type/item_name/quantity/unit/source_ref 默认 `PENDING_PLACEHOLDER`、status 默认 `PENDING_VERIFICATION`，AI 不填真实工程量。见 `agents/engineering/knowledge/graph/entities.py`。
- ✅ **任务2 成本规则模型**：`CostRule`（rule_id/source_ref/formula/unit_price/status），纯数据占位壳；`unit_price` 默认 `None`（**禁止硬编码价格**，红线⑤）、须有 `source_ref` 指向可信来源；formula 默认 `PENDING_PLACEHOLDER`、status 默认 `PENDING_VERIFICATION`。见 `entities.py`。
- ✅ **任务3 成本估算器**：`CostEstimator`（`material_cost`/`labor_cost`/`auxiliary_cost`/`total_estimate`），输出 `CostEstimateDraft`（仅占位估算壳，真实金额恒 `PENDING_PLACEHOLDER`，`requires_human_review=True`）；由 `_RedLineForbiddenMixin` 拦截 `quote`/`pricing`/`deal_price`/`final_price`/`market_price`/`select`/`finalize`/`approve`/`activate`/`engineering_approved`（红线③/④/⑤）；构造断言 `safety_invariants_ok()`（红线①/⑥）。见 `agents/engineering/knowledge/graph/solution_cost.py`。
- ✅ **任务4 成本解释链**：`CostExplanation`（关联 Solution/BOM/Rule/SourceRef **四类来源载体**，只读聚合；可选 `repository` 时沿图谱 `traverse` 补充 SourceRef/Rule 节点；只读不写，无报价路径）。输出 `CostExplanationReport`。见 `solution_cost.py`。
- ✅ **任务5 成本人工审核队列**：`CostReviewQueue`（draft→reviewing→approved_by_human/rejected）；`approve`/`reject` 仅 `by_human=True` 可驱动（AI 调用抛 `SolutionRedLineViolationError`，红线②/④）；非法状态转移抛 `SolutionReviewError`。见 `solution_cost.py`。
- ✅ **任务6 测试**：新增 `tests/agents/test_knowledge_graph_cost.py`（BOM/CostRule/Estimator/Explanation/Review/RedLine 六类，**+21 用例**）；基座 `test_knowledge_graph.py` 同步 7 实体/17 关系断言不受影响（`len(RELATIONSHIP_SPECS)==17` 仍成立）；不修改 `verified.json` 与 `engineering_enabled`；全 agents 套件 **713 passed** 零回归。
- ✅ 交付 `.ai/reviews/phase3.7.6_cost_intelligence_layer_report.md` + 更新 `.ai/project_status.json`（`phase_3_7.3.7.6` 块）+ 本 roadmap_v7.md。

**激活态**：`engineering_enabled=false`；`NO-GO` 维持；成本估算/解释/审核仅骨架，禁止在 enabled 前被当作报价/成交/取价依据。

---

### 2.9 Phase 3.7.7 Drawing Intelligence Layer（图纸智能层 DONE，2026-08-02）

> **Phase 3.7.7 定位**：在 3.7.6 成本智能层之上，建立「图纸智能解析层」——增强 `DesignCandidate`（7 字段占位）、图纸解析适配器（PDF/CAD/Image→`DesignCandidate`，带 source_ref + confidence 占位）、Vision 接口（仅只读分析壳，禁止工程结论）、尺寸人工审核队列（仅人工可终裁）、知识图谱只读连接（Solution/Case/KnowledgeItem/SourceRef）。**不**自动确认图纸尺寸、不自动生成真实工程参数、不自动报价、不开启 `engineering_enabled`、不输出 `engineering_approved`。

- ✅ **任务1 DesignCandidate 增强**：在 `entities.py` 的 `DesignCandidate` 扩展 7 字段（source_files/geometry/opening_type/glass_config/profile_config/confidence/verification_status），全部默认占位；`DesignCandidate` 是方案生成器契约入参（**非持久化图谱节点**，不进 `KnowledgeGraphEntityType`/`_ENTITY_DISPATCH`/关系白名单），扩展零回归；`__post_init__` 红线①断言保留。见 `agents/engineering/knowledge/graph/entities.py`。
- ✅ **任务2 图纸解析适配器**：`DrawingParser`（parse_pdf/parse_cad/parse_image），私有 `_parse` 恒产出带 source_ref + confidence 占位的 `DesignCandidate`，geometry/opening_type/glass_config/profile_config 恒 `PENDING_PLACEHOLDER`（红线③/④）；构造与每次解析断言 `safety_invariants_ok()`，继承 `_RedLineForbiddenMixin`（`_FORBIDDEN_DRAWING_METHODS` 含 `approve`/`select`/`finalize`/`activate`/`engineering_approved`/`quote`/`pricing`/`confirm_dimension`/`generate_engineering_param`）。见 `agents/engineering/knowledge/graph/solution_drawing.py`。
- ✅ **任务3 Vision 接口**：`VisionAdapter`（image_analysis/drawing_analysis），仅产出 `VisionAnalysisReport`（geometry_hint/opening_hint 恒 `PENDING_PLACEHOLDER`，禁止工程结论，红线③/④/⑤），可无 repository 构造。见 `solution_drawing.py`。
- ✅ **任务4 尺寸审核流程**：`DesignReviewQueue`（parsed→reviewing→verified_by_human/rejected）；`verify`/`reject` 仅 `by_human=True` 可终裁（AI 调用抛 `SolutionRedLineViolationError`，红线②）；非法状态转移抛 `SolutionReviewError`。见 `solution_drawing.py`。
- ✅ **任务5 知识图谱连接**：`DesignGraphConnector.link` 只读聚合 Solution/Case/KnowledgeItem/SourceRef 四类 id + 解析期 source_ref，产出 `DesignKnowledgeLinkReport`，**不写图、不新增关系到 17 白名单**。见 `solution_drawing.py`。
- ✅ **任务6 测试**：新增 `tests/agents/test_knowledge_graph_drawing.py`（DrawingParser/DesignCandidate/Vision/Review/GraphConnector/RedLine 六类，**+27 用例**）；基座 `test_knowledge_graph.py` 同步 7 实体/17 关系断言不受影响（`len(RELATIONSHIP_SPECS)==17` 仍成立）；不修改 `verified.json` 与 `engineering_enabled`；全 agents 套件 **740 passed** 零回归。
- ✅ 交付 `.ai/reviews/phase3.7.7_drawing_intelligence_layer_report.md` + 更新 `.ai/project_status.json`（`phase_3_7.3.7.7` 块）+ 本 roadmap_v7.md。

**激活态**：`engineering_enabled=false`；`NO-GO` 维持；解析/视觉/审核/关联仅骨架，禁止在 enabled 前被当作尺寸确认/参数生成/报价依据。

---

### 2.10 Phase 3.7.8 Engineering Workflow Orchestration Layer（工作流编排层 DONE，2026-08-03）

> **Phase 3.7.8 定位**：在 3.7.7 图纸智能层之上，建立「工程工作流编排层」——定义 `EngineeringWorkflow` 工作流模型，提供 `EngineeringWorkflowEngine` 编排器（串联 DrawingParser / DesignReviewQueue / SolutionGenerator / SolutionConstraintEngine / CostEstimator，**只编排、不改变模块职责**），引入 `HumanReviewCheckpoint` 人工审核节点（AI 不能自动通过）与 `workflow.event_log` 审计追踪。**不**自动确认图纸尺寸、不自动生成真实工程参数、不自动报价、不开启 `engineering_enabled`、不输出 `engineering_approved`、不绕过 `UnifiedActivationGate`。

- ✅ **任务1 EngineeringWorkflow 模型**：`workflow_id` / `input_source` / `stages` / `status` / `created_at` / `requires_human_review` 契约落地；`stage_by_name` / `next_pending_stage` 支撑可追踪推进；**非图谱节点**（与 `DesignCandidate` 同性质），不进 `KnowledgeGraphEntityType` / 17 关系白名单，扩展零回归。见 `agents/engineering/knowledge/graph/solution_workflow.py`。
- ✅ **任务2 EngineeringWorkflowEngine 编排器**：`start_workflow` / `execute_stage` / `pause_for_review` / `resume_workflow` 四个核心 API；每阶段可追踪（`WorkflowStage` 带 actor/时间戳/result_ref）；`human_review` 阶段自动挂起为 `awaiting_human` + `paused_for_review`；`resume_workflow` 仅当 `HumanReviewCheckpoint.all_passed()`（三节点 `by_human=True`）才收尾 `completed`，否则维持 `running` 等待人工。见 `solution_workflow.py`。
- ✅ **任务3 接入既有模块（只编排不改职责）**：`_dispatch` 按 `STAGE_ORDER` 分派 `DrawingParser.parse_*` / `DesignReviewQueue.submit+begin_review` / `SolutionGenerator.generate` / `SolutionConstraintEngine.check_geometry` / `CostEstimator.total_estimate`，并挂接 `HumanReviewCheckpoint`；不修改任何被编排模块的内部逻辑、签名或职责。见 `solution_workflow.py`。
- ✅ **任务4 HumanReviewCheckpoint 人工审核节点**：三门 `drawing_verified` / `solution_reviewed` / `cost_reviewed`；`mark(checkpoint, *, by_human=False)` 非 `by_human` 调用一律抛 `SolutionRedLineViolationError`（红线②）；仅 `by_human=True` 可放行并记录 `human_reviewer`。见 `solution_workflow.py`。
- ✅ **任务5 审计追踪 workflow_event_log**：`WorkflowEvent`（stage / actor / timestamp / status / detail）；引擎在 `start_workflow` / `execute_stage`（running+done/awaiting_human/error）/ `pause_for_review` / `resume_workflow` 全路径追加审计事件至 `wf.event_log`。见 `solution_workflow.py`。
- ✅ **任务6 测试**：新增 `tests/agents/test_knowledge_graph_workflow.py`（Workflow/Stage/ReviewCheckpoint/Audit/RedLine/Integration 六类，**+22 用例**）；全 agents 套件 **762 passed**（基线 740 + 22）零回归；不修改 `verified.json` 与 `engineering_enabled`；`len(RELATIONSHIP_SPECS)==17` 不受影响。
- ✅ 交付 `.ai/reviews/phase3.7.8_workflow_orchestration_layer_report.md` + 更新 `.ai/project_status.json`（`phase_3_7.3.7.8` 块）+ 本 roadmap_v7.md。

**激活态**：`engineering_enabled=false`；`NO-GO` 维持；工作流到 `human_review` 阶段挂起等待真实人工终裁，编排层不产出/不批准任何真实尺寸/工程参数/报价。

### 2.11 Phase 3.7.9 Engineering AI Assistant Interface Layer（工程 AI 助手交互层 DONE，2026-08-03）

> **Phase 3.7.9 定位**：在 3.7.8 工作流编排层之上，建立「工程 AI 助手交互层」——定义 `AssistantSession` 会话模型与 `WorkflowRequest` 用户输入处理产物，提供 `AssistantWorkflowBridge` 桥接 `EngineeringWorkflowEngine`（**只桥接、不改变编排职责**），定义 `AssistantResponse` 响应载体与 `HumanReviewPortal` 人工审核入口（只读查看三审核节点 + 强制 `by_human=True`）。**不**自动确认工程结果、不自动生成真实工程参数、不自动报价、不开启 `engineering_enabled`、不输出 `engineering_approved`、不绕过 `UnifiedActivationGate`。

- ✅ **任务1 AssistantSession 会话模型**：`session_id` / `user_input` / `files` / `workflow_id` / `status` / `created_at` 契约落地；**非图谱节点**（与 `EngineeringWorkflow` 同性质），不进 `KnowledgeGraphEntityType` / 17 关系白名单，扩展零回归。见 `agents/engineering/knowledge/graph/solution_assistant.py`。
- ✅ **任务2 用户输入处理（WorkflowRequest）**：文本/图片/PDF/CAD 路径 → 工作流请求；`_infer_parse_format` 按扩展名推断 `pdf`/`cad`/`image`；`direct_judgment` **恒 False**（红线③：禁止直接工程判断）。见 `solution_assistant.py`。
- ✅ **任务3 AssistantWorkflowBridge 桥接层**：`create_workflow` / `attach_files` / `query_status` 三 API；持 `EngineeringWorkflowEngine` 句柄，**仅桥接不改职责**；`workflow_id="WF-{session_id}"`；建流时 `direct_judgment=False` 不做任何工程判定。见 `solution_assistant.py`。
- ✅ **任务4 AssistantResponse 响应载体**：`workflow_status` / `candidate_results` / `review_required` / `source_trace`；`results_confirmed` **恒 False**、`review_required` **恒 True**（红线③：AI 不自动确认工程结果）。见 `solution_assistant.py`。
- ✅ **任务5 HumanReviewPortal 人工审核入口**：`view_drawing_review` / `view_solution_review` / `view_cost_review` 三节点**只读**查看；`submit_human_decision` **强制 `by_human=True`**（红线⑤：AI 不能自动通过人工审核），桥接到底层 `HumanReviewCheckpoint.mark(by_human=True)`。见 `solution_assistant.py`。
- ✅ **任务6 测试**：新增 `tests/agents/test_knowledge_graph_assistant.py`（assistant/session/workflow bridge/response/red line 五类，**+29 用例**）；全 agents 套件 **791 passed**（基线 762 + 29）零回归；不修改 `verified.json` 与 `engineering_enabled`；`len(RELATIONSHIP_SPECS)==17` 不受影响。
- ✅ 交付 `.ai/reviews/phase3.7.9_engineering_assistant_interface_report.md` + 更新 `.ai/project_status.json`（`phase_3_7.3.7.9` 块）+ 本 roadmap_v7.md。

**激活态**：`engineering_enabled=false`；`NO-GO` 维持；交互层到 `HumanReviewPortal` 仍等待真实人工终裁，不产出/不批准任何真实尺寸/工程参数/报价。

---

## 3. 红线守约（Phase 3.7.0 本轮 6/6；Phase 3.7.1 本轮 5/5；Phase 3.7.2 本轮 5/5；Phase 3.7.3 本轮 5/5；Phase 3.7.4 本轮 5/5；Phase 3.7.5 本轮 6/6；Phase 3.7.6 本轮 6/6；Phase 3.7.7 本轮 6/6；Phase 3.7.8 本轮 6/6；Phase 3.7.9 本轮 6/6）

| # | 红线 | 遵守 |
|---|---|---|
| 1 | 不自动开启 `engineering_enabled` | ✅ 真实 `config.yaml` 仍为 `false` |
| 2 | 不输出 `engineering_approved` | ✅ 全文未输出 approved |
| 3 | 不绕过 `UnifiedActivationGate` | ✅ 复用 fail-closed 闸门，无绕过设计 |
| 4 | 不伪造工程参数 | ✅ 能力矩阵/路线图/KG 全基于真实代码，零虚构数值 |
| 5 | 不创建 `ReleaseApproval` | ✅ 未创建 |
| 6 | 不 AI 代签/代授权 | ✅ ExpertBinder 仅校验，不落签 |

### 3.1 Phase 3.7.1 红线守约（本轮 5/5）

| # | 红线 | 遵守 |
|---|---|---|
| 1 | 不开启 `engineering_enabled` | ✅ 真实 `config.yaml` 仍为 `false`；`KnowledgeGraphRepository.safety_invariants_ok()` 断言 True |
| 2 | 不输出 `engineering_approved` | ✅ 全文未输出 approved；图谱审计白名单拒 `approved` |
| 3 | 不伪造工程参数 | ✅ 基础层零真实数值；`Threshold.value`/Case/Rule 恒 `pending_verification`；集成仅建存根不编造 |
| 4 | AI 不代替专家审核 | ✅ `Expert` 仅资料壳；冲突 `review_required` 恒 True；无 merge/delete/approve |
| 5 | 不绕过 `UnifiedActivationGate` | ✅ 沿用 fail-closed 闸门；边校验 fail-closed；图谱层不产出批准态 |

### 3.2 Phase 3.7.2 红线守约（本轮 5/5）

| # | 红线 | 遵守 |
|---|---|---|
| 1 | 不开启 `engineering_enabled` | ✅ 引擎构造即 `safety_invariants_ok()` 只读断言 True；每次调用前重新断言；真实 `config.yaml` 仍为 `false` |
| 2 | 不输出 `engineering_approved` | ✅ 引擎无 `approve`/`engineering_approved` 方法或属性；`trace`/`impact` 输出 `approval_forbidden` 恒 True；全文未输出 approved |
| 3 | 不自动修改知识状态 | ✅ 推理层全只读（仅 `query`/`traverse`/`get_node`/`get_edge`/`history` + 只读访问 `_edges`/`_nodes`）；审计类测试验证 node/edge count 不变；绝不 `add_node`/`add_edge`/`delete` |
| 4 | 不自动解决冲突 | ✅ `conflict_scan` 复用检测器，`review_required` 恒 True、`auto_resolvable` 恒 False；引擎无 merge/delete/approve 方法 |
| 5 | 不伪造工程参数 | ✅ 受影响集合仅由图谱结构推导；`Threshold.value` 仍为 `pending_verification`；`CalcAgent` 恒 pending 候选（`computation_body=pending_verification`），绝不编造真实计算主体；Case/Rule 仍为 pending_build 骨架 |

### 3.3 Phase 3.7.3 红线守约（本轮 5/5）

| # | 红线 | 遵守 |
|---|---|---|
| 1 | 不开启 `engineering_enabled` | ✅ 复用 `safety_invariants_ok()` 只读断言 True；真实 `config.yaml` 仍为 `false` |
| 2 | 不输出 `engineering_approved` | ✅ 案例层无任何批准态；`CaseLifecycle` 仅人工推进 |
| 3 | 不伪造真实案例 | ✅ Case 字段默认空串/`PENDING_PLACEHOLDER`；`from_empty` 仅壳，零真实值 |
| 4 | AI 不代替专家审核 | ✅ `CaseLifecycle.advance` 默认守卫，AI 不自动转移；`rule_expert` 签署位由真实专家驱动 |
| 5 | 不绕过 `UnifiedActivationGate` | ✅ 沿用 fail-closed 闸门；边校验 fail-closed |

### 3.4 Phase 3.7.4 红线守约（本轮 5/5）

| # | 红线 | 遵守 |
|---|---|---|
| 1 | 不开启 `engineering_enabled` | ✅ Generator/Evaluator/ReviewQueue 构造即 `safety_invariants_ok()` 断言；`DesignCandidate` 构造断言 `load_engineering_enabled() is False` |
| 2 | 不输出 `engineering_approved` | ✅ `ReviewQueue.approve` 仅 `by_human=True` 可入 `approved_by_human`；AI 调用抛 `SolutionRedLineViolationError` |
| 3 | 不自动选择最终工程方案 | ✅ Generator/Evaluator 无 `select`/`finalize`/`approve`，由 `_RedLineForbiddenMixin` 拦截 forbidden 方法名 |
| 4 | 不伪造工程参数 | ✅ `SolutionCandidate.components` 恒 `PENDING_VERIFICATION`、`confidence` 恒 `pending`，不填真实方案数值 |
| 5 | 不绕过 `UnifiedActivationGate` | ✅ 生成/评价/审核所有写/决策路径先断言 `safety_invariants_ok()` |

### 3.5 Phase 3.7.5 红线守约（本轮 6/6）

| # | 红线 | 遵守 |
|---|---|---|
| 1 | 不开启 `engineering_enabled` | ✅ Engine/Comparison/Explanation/ReviewQueue 构造即 `safety_invariants_ok()` 只读断言 |
| 2 | 不输出 `engineering_approved` | ✅ 三阶段审查与终裁均仅 `by_human=True` 可入 `approved_by_human`；AI 调用抛 `SolutionRedLineViolationError` |
| 3 | 不自动选择最终工程方案 | ✅ Engine/Comparison 无 `select`/`finalize`/`winner`，由 `_RedLineForbiddenMixin` 拦截 forbidden 方法名 |
| 4 | 不自动报价 | ✅ 本轮新增：forbidden 方法名补 `quote`/`pricing` 拦截；方案层/约束层/对比层均无报价路径 |
| 5 | 不伪造工程参数 | ✅ `SolutionConstraint` 仅占位壳、Candidate `components`/`confidence` 恒 `PENDING`/`pending`，不填真实数值 |
| 6 | 不绕过 `UnifiedActivationGate` | ✅ 构造/检查/解释/审核所有写/决策路径先断言 `safety_invariants_ok()` |

### 3.6 Phase 3.7.6 红线守约（本轮 6/6）

| # | 红线 | 遵守 |
|---|---|---|
| 1 | 不开启 `engineering_enabled` | ✅ Estimator/Explanation/ReviewQueue 构造即 `safety_invariants_ok()` 只读断言；monkeypatch 翻转即抛 `SolutionRedLineViolationError` |
| 2 | 不输出 `engineering_approved` | ✅ `CostReviewQueue.approve` 仅 `by_human=True` 可入 `approved_by_human`；AI 调用（`by_human=False`）一律抛 `SolutionRedLineViolationError` |
| 3 | 不自动选择最终工程方案 | ✅ Estimator 无 `select`/`finalize`/`winner`，由 `_RedLineForbiddenMixin` 拦截 forbidden 方法名 |
| 4 | 不自动报价 / 不自动成交价格 | ✅ 本轮巩固：forbidden 方法名补 `quote`/`pricing`/`deal_price`/`final_price` 拦截；成本层无任何报价/成交价路径 |
| 5 | 不伪造市场价格 | ✅ 本轮新增：`market_price` 拦截；`CostRule.unit_price` 默认 `None`（禁止硬编码），价格必须有 `source_ref` 来源 |
| 6 | 不绕过 `UnifiedActivationGate` | ✅ 构造/估算/解释/审核所有写/决策路径先断言 `safety_invariants_ok()` |

### 3.7 Phase 3.7.7 红线守约（本轮 6/6）

| # | 红线 | 遵守 |
|---|---|---|
| 1 | 不开启 `engineering_enabled` | ✅ Parser/Vision/ReviewQueue/GraphConnector 构造即 `safety_invariants_ok()` 只读断言；`DesignCandidate.__post_init__` 断言未启用；monkeypatch 翻转即抛 `SolutionRedLineViolationError` |
| 2 | 不输出 `engineering_approved` | ✅ `DesignReviewQueue.verify`/`reject` 仅 `by_human=True` 可入 `verified_by_human`/`rejected`；AI 调用（`by_human=False`）一律抛 `SolutionRedLineViolationError` |
| 3 | 不自动确认图纸尺寸 | ✅ 本轮新增：forbidden 方法名补 `confirm_dimension`；解析结果 geometry/opening_type 恒 `PENDING_PLACEHOLDER`，AI 不确认图纸尺寸 |
| 4 | 不自动生成真实工程参数 | ✅ 本轮新增：forbidden 方法名补 `generate_engineering_param`；glass_config/profile_config 恒 `PENDING_PLACEHOLDER`，AI 不生成真实参数 |
| 5 | 不自动报价 | ✅ forbidden 方法名 `quote`/`pricing` 拦截；本层无报价路径（移除 3.7.6 的 deal_price/final_price/market_price） |
| 6 | 不绕过 `UnifiedActivationGate` | ✅ 构造/解析/分析/审核/连接所有决策路径先断言 `safety_invariants_ok()` |

### 3.8 Phase 3.7.8 红线守约（本轮 6/6）

| # | 红线 | 遵守 |
|---|---|---|
| 1 | 不开启 `engineering_enabled` | ✅ Engine/子模块/HRC 构造 + `start_workflow`/`execute_stage`/`pause_for_review`/`resume_workflow` 全断言 `safety_invariants_ok()`；monkeypatch 翻转即抛 `SolutionRedLineViolationError` |
| 2 | 不输出 `engineering_approved` | ✅ `_FORBIDDEN_WORKFLOW_METHODS` 含 `approve`/`engineering_approved`，mixin 拦截；`HumanReviewCheckpoint.mark` 仅 `by_human=True` 可放行，AI 调用（`by_human=False`）一律抛 `SolutionRedLineViolationError`；全文未输出 approved |
| 3 | 不自动确认图纸尺寸 | ✅ forbidden 方法名含 `confirm_dimension`/`select`/`finalize`/`activate`；编排层不触碰尺寸确认，尺寸仍走 `DesignReviewQueue`（仅人工 `verify`） |
| 4 | 不自动生成真实工程参数 | ✅ forbidden 方法名含 `generate_engineering_param`；被编排的 `DrawingParser`/`SolutionGenerator` 仍恒产出占位壳 |
| 5 | 不自动报价 | ✅ forbidden 方法名含 `quote`/`pricing`；编排层无报价路径，成本估算仍仅占位（需人工审核） |
| 6 | 不绕过 `UnifiedActivationGate` | ✅ 构造/启动/执行/暂停/恢复所有决策路径先断言 `safety_invariants_ok()`；测试 `test_safety_invariants_block_construction` 验证翻转即 fail-closed |

### 3.9 Phase 3.7.9 红线守约（本轮 6/6）

| # | 红线 | 遵守 |
|---|---|---|
| 1 | 不开启 `engineering_enabled` | ✅ `AssistantWorkflowBridge`/`HumanReviewPortal` 构造 + `create_workflow`/`attach_files`/`query_status`/`submit_human_decision` 全断言 `safety_invariants_ok()`；monkeypatch 翻转即抛 `SolutionRedLineViolationError` |
| 2 | 不输出 `engineering_approved` | ✅ `_FORBIDDEN_ASSISTANT_METHODS` 含 `approve`/`engineering_approved`，mixin 拦截；`HumanReviewPortal.submit_human_decision` 仅 `by_human=True` 可放行，AI 调用（`by_human=False`）一律抛 `SolutionRedLineViolationError` |
| 3 | 不自动确认工程结果 | ✅ forbidden 方法名含 `confirm_dimension`/`select`/`finalize`/`activate`；`WorkflowRequest.direct_judgment` 与 `AssistantResponse.results_confirmed` 恒 False |
| 4 | 不自动生成真实工程参数 | ✅ forbidden 方法名含 `generate_engineering_param`；交互层不触碰参数生成 |
| 5 | 不自动报价 | ✅ forbidden 方法名含 `quote`/`pricing`；交互层无报价路径 |
| 6 | 不绕过 `UnifiedActivationGate` | ✅ 构造/建流/查状态/提交审核所有决策路径先断言 `safety_invariants_ok()`；测试 `test_safety_invariants_block_bridge_construction` 验证翻转即 fail-closed |

---

## 4. 激活态与停止声明

- **`engineering_enabled = false`**（真实读取确认）。
- **未输出 `engineering_approved`**。
- **ESW 窗口维持 `OPEN_EMPTY`**；本轮 0 真实证据/参数进入。
- **按指令停止**：工程 AI 助手交互层（3.7.9）实现完成即止，保持 `engineering_enabled=false`、不输出 `engineering_approved`；真实方案数值转正须经 `HumanReviewPortal.submit_human_decision(by_human=True)` 终裁。
- **解锁路径（纯人工）**：主理人+专家经 ESW 窗口提交真实双签阈值（E/D-TH-* `verified=true` + 真实 `value`）→ 人类终端显式置 `engineering_enabled=true` → 人类对方案/报价作 `Engineering_Approved`。
