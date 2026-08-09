# BOIP 研发路线 V4（roadmap_v4.md）

- **生成**：2026-08-02
- **身份**：BOIP AI Chief Architect（Phase 3.2 收口 + Phase 3.3 建立 + Phase 3.4 激活准备架构设计）
- **性质**：Phase 3.4 路线建立；**3.4.0 设计-only（零业务代码改动）**；**3.4.1 实现 Sprint（新增只读激活判定层 4 模块 + 测试 30 用例，零回归，不翻转 `engineering_enabled`）**；**3.4.2 实现 Sprint（UnifiedActivationGate 三域聚合 + 测试 13 用例，零复制规则，fail-closed，不翻转 `engineering_enabled`）**；**3.4.3 实现 Sprint（Engineering AI 消费强制守卫 + 测试 13 用例，零回归，不翻转 `engineering_enabled`）**；**3.4.4 实现 Sprint（Engineering Runtime Integration：EngineeringKnowledgeGuard 接入五工程接口与 RAG 检索链路 + 审计持久化 JSONL + 测试 23 用例，零回归，不翻转 `engineering_enabled`）**；**3.4.5 验证 Sprint（Activation Readiness Verification & Hardening：新增 tests/agents/test_activation_readiness.py 25 用例实证三域 G1-G6 可追踪 / 五接口 RuntimeGuard / RAG 旁路防护 / 三类审计边界，fail-closed 设计确认，零业务代码改动、不翻转 `engineering_enabled`、NO-GO 维持）**。
- **依据**：`.ai/project_status.json`（SSOT，current_roadmap_version=V4）、`.ai/reviews/phase3.4.0_activation_readiness_architecture.md`、`.ai/reviews/phase3.3.8_knowledge_repository_report.md`、`.ai/tasks/phase3.3.9_analysis.md`
- **权威声明**：本文件取代 `roadmap_v3.md`，为 Phase 3.4 起的唯一研发路线；roadmap_v3.md 保留为 Phase 3.3 历史归档。

---

## 1. 当前真实状态（Phase 3.4 激活准备态）

| 维度 | 真实状态 |
|---|---|
| 阶段 | **Phase 3.2 CLOSED（2026-08-01 收口）** → **Phase 3.3 DONE（3.3.1~3.3.8 全 DONE；3.3.8 Knowledge Repository 治理层已交付）** → 🟢 **Phase 3.4 IN_PROGRESS（3.4.0 激活准备架构设计 DONE；3.3.9 Knowledge Intelligence Layer 实现 DONE；3.4.1 激活层实现 DONE；3.4.2 Unified Activation Gate 实现 DONE；3.4.3 Engineering AI Consumption Enforcement 实现 DONE；3.4.4 Engineering Runtime Integration 实现 DONE；**3.4.5 Activation Readiness Verification & Hardening DONE（25 新增测试 + 全 agents 555 passed 零回归，三域 G1-G6 可追踪/五接口 RuntimeGuard/RAG 旁路防护/三类审计边界均实证通过，fail-closed 设计正确，NO-GO 维持，禁止自动激活）**）**；工程审核闭环治理与基础设施全量建成（inert，未激活，三域 G1-G6 全 FAIL 维持关闭） |
| 知识资产层 | `KnowledgeItem` / `KnowledgeRepository` / `KnowledgeEventLog` / Connector→Repository 链路 / Version 管理 / Audit Governance 全建成（3.3.8）；智能层（quality/relationship/conflict）已实现（3.3.9，只读评估/发现/检测，26 测试通过）；**激活层（gate/consumption/read_boundary/rollback）已实现（3.4.1，30 测试通过，全只读/声明性）**；**统一激活闸门（UnifiedActivationGate 三域聚合 + UnifiedConsumptionController 消费接入）已实现（3.4.2，13 测试通过）**；**工程AI消费强制守卫（EngineeringKnowledgeGuard + 独立消费审计日志）已实现（3.4.3，13 测试通过）**；**运行时接入（EngineeringRuntimeGuard 接入五工程接口 + knowledge/rag 检索链路 + PersistentConsumptionAuditLog 落盘 JSONL）已实现（3.4.4，23 测试通过）** |
| 激活准备架构 | 3.4.0 已定义：激活条件链、KnowledgeActivationGate(G1-G6, fail-closed)、消费策略三级分类、AI 读取边界、Rollback 谱系（deprecated→successor→replacement）；**3.4.1 已落地实现为只读判定代码**；**3.4.2 已落地 UnifiedActivationGate，将知识域/阈值域/发布域 G1-G6 聚合成统一决策（零规则复制，fail-closed）** |
| 红线 | `engineering_enabled=false`；无任何 `engineering_approved` 输出；`E-TH-01/02/03` 真实 `value` 仍 `null`（pending_verification） |
| CI | agents 套件 **555 passed**（含 3.3.9 新增 26 + 3.4.1 新增 30 + 3.4.2 新增 13 + 3.4.3 新增 13 + 3.4.4 新增 23 + 3.4.5 新增 25；Ruff/ESLint/Jest 29·93.15%/Alembic/Seed/防编造/硬编码全绿）；`local_ci.sh` 第 2 步 pytest 完整运行受环境级 `[safe-delete]` 守卫 + 24 条预存 `test_threshold_*` 隔离失败阻断（均非 3.4.5 回归，隔离运行 555 passed） |
| 激活态 | **NO-GO 维持**：`engineering_enabled=False`；知识域/阈值域/发布域三域 G1-G6 设计+实现完成但默认全 FAIL（缺真实双签/审核链/G6 授权/CI绿确认/回滚就绪）；**3.4.5 实证验证确认 fail-closed 设计正确、三域失败原因全部可追踪，统一激活决策恒 NO-GO，禁止自动激活** |
| 未完成（人工动作） | 真实知识双签 / 真实审核链 / G6 授权 / CI绿确认 / 回滚就绪确认 / 真实放量 均 pending_verification |

**红线（不可逾越）**：任何无据行业数字必须标 `pending_verification`；工程参数（风压/楼层/评分权重）未经专家签字不得转正；Phase 3.4 不录入真实参数、不开 `engineering_enabled`、不输出 `engineering_approved`、不代建 `ReleaseApproval`、不代专家审核。

---

## 2. Phase 3.4 路线（Engineering Knowledge Activation Readiness — 激活准备）

> **Phase 3.4 定位**：Phase 3.3 已建成"可被安全激活的知识资产仓库容器"。Phase 3.4 目标 = **设计知识激活准备架构**——定义一条 KnowledgeItem 何时、凭何条件才能成为 Engineering AI 可权威引用的依据，并明确 AI 读取边界与失效回滚路径。

### 2.1 已交付（设计与实现）

- **3.4.0** Engineering Knowledge Activation Readiness Architecture（激活准备架构）。**DESIGN_DONE（2026-08-02）**
  - ✅ 产出 `.ai/reviews/phase3.4.0_activation_readiness_architecture.md`（6 章节：架构变化/文件变化/测试结果/红线检查/技术债/下一阶段建议）。
  - ✅ 任务1 激活条件链：KnowledgeItem → Source_Verified → Expert_Verified → Engineering_Verified → Engineering_Approved（每跃迁前提条件与责任主体明确定义，AI 仅校验不代签）。
  - ✅ 任务2 KnowledgeActivationGate：知识域 G1-G6（governance / dual_sign / ci / audit_chain / rollback_ready / authorization），复用 `enable_gate.py` 语义，`can_activate_knowledge` 默认 `(False, reasons)` fail-closed，**不翻转 engineering_enabled**。
  - ✅ 任务3 知识消费策略：citable（仅 Engineering_Approved）/ auxiliary-only（Source/Expert/Engineering_Verified，须标 pending_verification）/ not-citable（Captured/Pending/Deprecated）。
  - ✅ 任务4 Engineering AI 读取边界：可读元数据/质量报告/关系/冲突（辅助信号）；不可读 verified.json value / 不可代建 ReleaseApproval / 不可自助 Engineering_Approved。
  - ✅ 任务5 Rollback 谱系：Deprecated → successor（deprecate(successor=) 已实现并正式化）→ Replacement；不删旧 item，保留审计可溯，满足 G5 rollback_ready。
  - ✅ 红线守约：未开 `engineering_enabled` / 未输出 `engineering_approved` / 未改 `verified.json` / 未建 `ReleaseApproval` / AI 不代专家审核。激活态维持 NO-GO。
  - ✅ 更新 `.ai/project_status.json`（`task_status.phase_3_1.phase_3_4` 设计 DONE 块）+ SSOT `current_roadmap_version=V4`。
- **3.4.1** Engineering Knowledge Activation Layer Implementation（激活层实现）。**DONE（2026-08-02）**
  - ✅ 落地 phase3.4.0 设计文档 §4–§7：新增 `agents/engineering/knowledge/activation/`（`__init__.py` / `gate.py` / `consumption.py` / `read_boundary.py` / `rollback.py`）+ `tests/agents/test_knowledge_activation.py`。
  - ✅ 任务1 `KnowledgeActivationGate.can_activate_knowledge(repository, *, context=None)`：知识域 G1–G6（governance / dual_sign / ci / audit_chain / rollback_ready / authorization）fail-closed 判定，返回 `ActivationDecision(allowed, blocking_reasons, gate_results, detail)`，**绝不翻转 engineering_enabled**；`safety_invariants_ok()` 静态断言 `load_engineering_enabled() is False`。
  - ✅ 任务2 `KnowledgeConsumptionPolicy`：citable（仅 Engineering_Approved）/ auxiliary_only（Source/Expert/Engineering_Verified，须标 pending_verification）/ not_citable（Captured/**Pending_Verification**/Deprecated；纠正初版误映射 auxiliary_only）。
  - ✅ 任务3 `KnowledgeReadBoundary`：可读 metadata/quality_report/relationship/conflict；不可读 verified.json value / 不可代建 ReleaseApproval / 不可写 engineering_enabled / 不可自助 Engineering_Approved；`read_invariants_ok()` 断言。
  - ✅ 任务4 `KnowledgeRollbackPolicy`：复用 `Repository.deprecate(successor=)` 置 Deprecated 并写入 successor 至 parent_knowledge_id；`successor_of`/`build_replacement_chain`/`is_replacement_available`/`history_preserved`；**不删历史**，满足 G5 rollback_ready。
  - ✅ 任务5 `tests/agents/test_knowledge_activation.py`：**30 用例全 PASS**（fail-closed / 六门齐全 / 单门阻断 / 双签显式注入 / 红线守约 / 消费分类 / 读取边界 / 回滚链 / engineering_enabled 不变 / 拒 approved）。
  - ✅ 红线守约：未开 `engineering_enabled` / 未输出 `engineering_approved` / 未改 `verified.json` / 未建 `ReleaseApproval` / AI 不代专家审核。激活态维持 NO-GO。
  - ✅ 全量 agents 无 `--cov` 隔离运行 **481 passed**（原 451 + 新增 30，零回归）；Ruff / ESLint / Jest 29·93.15% / Alembic / Seed / 防编造 / 硬编码全绿；`local_ci.sh` 第 2 步 pytest 完整集受环境级 `[safe-delete]` 守卫 + 24 条预存 `test_threshold_*` `--cov` 隔离失败阻断（非本 Sprint 回归）。报告见 `.ai/reviews/phase3.4.1_activation_layer_report.md`。
- **3.4.2** Unified Activation Gate（统一激活闸门）。**DONE（2026-08-02）**
  - ✅ 新增 `agents/engineering/gate/unified_activation_gate.py`：任务1 `UnifiedActivationGate.evaluate(repository, *, context, thresholds, review_log_path)` 聚合三域为 `UnifiedActivationDecision(allowed, blocking_reasons, domain_results, detail)`；定义 `DomainResult` / `ConsumptionDecision`。
  - ✅ 任务2 聚合现有 Gate（零规则复制）：知识域复用 `KnowledgeActivationGate.can_activate_knowledge`；阈值域复用 `can_enable_engineering`（原因码映射到统一 G1–G6）；发布域复用统一 G1–G6 语义 + `KnowledgeRepository` 审计检查。
  - ✅ 任务3 统一 G1–G6 语义：知识域/阈值域/发布域共享 `G1 governance / G2 dual_sign / G3 ci / G4 audit / G5 rollback / G6 authorization`（常量与 `enable_gate.py` 一致）。
  - ✅ 任务4 Fail-Closed 默认 NO-GO：缺失任何外部条件 → 该域及整体判定拒绝，返回 `blocking_reasons`；顶层 `load_engineering_enabled() is False` 不变量 + `safety_invariants_ok()` 静态断言；**绝不翻转 engineering_enabled** / 不输出 `engineering_approved` / 不创建 `ReleaseApproval` / 不修改 `verified.json`。
  - ✅ 任务5 测试 `tests/agents/test_unified_activation_gate.py`：**13 用例全 PASS**（知识失败/阈值失败/授权失败/CI缺失/全通过模拟/engineering_enabled 保持 False/三域结构/消费接入/红线）；并附 `UnifiedConsumptionController`（ActivationGate→ConsumptionPolicy，禁止未 Approved 知识进入工程计算）。
  - ✅ 红线守约：未开 `engineering_enabled` / 未输出 `engineering_approved` / 未改 `verified.json` / 未建 `ReleaseApproval` / AI 不代专家审核。激活态维持 NO-GO。
  - ✅ 全量 agents 无 `--cov` 隔离运行 **494 passed**（原 481 + 新增 13，零回归）；Ruff / ESLint / Jest 29·93.15% / Alembic / Seed / 防编造 / 硬编码全绿；`local_ci.sh` 第 2 步仍受环境级 `[safe-delete]` 守卫 + 24 条预存 `test_threshold_*` `--cov` 隔离失败阻断（非本 Sprint 回归）。报告见 `.ai/reviews/phase3.4.2_unified_activation_gate_report.md`。

- **3.4.3** Engineering AI Consumption Enforcement（工程AI消费强制治理）。**DONE（2026-08-02）**
  - ✅ 新增 `agents/engineering/knowledge/activation/consumer_guard.py`：任务1 `EngineeringKnowledgeGuard.consume_knowledge(item, unified)` 强制 Engineering AI / RAG 消费链遵守 `UnifiedActivationGate` + `KnowledgeConsumptionPolicy`——顶层断言 `load_engineering_enabled() is False`（fail-closed），统一闸门不允许即禁止任何知识；允许前提下按策略分级（citable=Engineering_Approved 权威；auxiliary_only=Verified 系列仅辅助须 pending_verification；not_citable=Captured/Pending/Deprecated 禁止）。
  - ✅ 任务2 RAG 消费边界：`Engineering_Approved` 可作权威引用；`Source_Verified`/`Expert_Verified`/`Engineering_Verified` 仅辅助（须标 pending_verification）；`Pending_Verification`/`Captured`/`Deprecated` 禁止进入。
  - ✅ 任务3 工程 Agent 接入：`guard_engineering_computation_input(item, unified)` 只读接入点，供 WindPressure/Glass/Profile/Hardware/InstallationRisk 计算入口在计算前调用；**仅判定与审计，不修改任何计算逻辑**。
  - ✅ 任务4 审计记录：独立 `KnowledgeConsumptionAuditLog` 记录 `knowledge_consumed`/`knowledge_blocked`；**显式拒绝 `approved` 事件**（不触碰 repository `EVENT_TYPES` 白名单、不触碰 `verified.json`、不创建 `ReleaseApproval`）。
  - ✅ 任务5 测试 `tests/agents/test_consumption_guard.py`：**13 用例全 PASS**（Approved允许/Pending拒绝/Deprecated拒绝/Gate失败拒绝/auxiliary须 pending_verification/engineering_enabled 保持 False/拒 approved 事件/工程计算入口接入）。
  - ✅ 红线守约：未开 `engineering_enabled`（顶层断言 + `safety_invariants_ok`）/ 未输出 `engineering_approved`（仅 docstring）/ 未改 `verified.json` / 未建 `ReleaseApproval` / AI 不代专家审核（审计硬拒 approved）。激活态维持 NO-GO。
  - ✅ 全量 agents 无 `--cov` 隔离运行 **507 passed**（原 494 + 新增 13，零回归）；Ruff / ESLint / Jest 29·93.15% / Alembic / Seed / 防编造 / 硬编码全绿；`local_ci.sh` 第 2 步仍受环境级 `[safe-delete]` 守卫 + 24 条预存 `test_threshold_*` `--cov` 隔离失败阻断（非本 Sprint 回归）。报告见 `.ai/reviews/phase3.4.3_consumption_enforcement_report.md`。

- **3.4.4** Engineering Runtime Integration（工程AI运行时接入）。**DONE（2026-08-02）**
  - ✅ 任务1 入口识别：五工程接口 `wind_pressure` / `glass_safety` / `profile` / `hardware` / `installation_risk` 经 `EngineeringAgent.analyze_*` 分发器调用各自 `Calculator.calculate`（非独立类）；`UnifiedActivationDecision` 为系统级共享 fail-closed 决策；识别消费入口为各接口计算前的知识候选集。
  - ✅ 任务2 接入 Consumption Guard：`agents/engineering/knowledge/activation/runtime_integration.py` 新增 `EngineeringRuntimeGuard.guard_interface(interface, items, decision)`（独立声明 `ENGINEERING_INTERFACES` 避免 import `agent.py` 成环），每项候选知识过 `guard_engineering_computation_input` 并分区 `authoritative` / `auxiliary` / `blocked`；仅 authoritative 可作权威依据，auxiliary 仅辅助须 `pending_verification`，blocked 一律不得进入。仅判定与审计，不修改任何计算逻辑。`EngineeringAgent.invoke` 新增 `knowledge_consumption` 字段（无 `knowledge_items` 输入时返回空 dict，零副作用）。
  - ✅ 任务3 RAG 入口接入：新建 `agents/engineering/knowledge/rag/`（retriever / context_builder / pipeline / `__init__`），流程 `Retriever → Consumption Guard → Context Builder → Engineering Agent`；`KnowledgeRetriever` 默认词面 Jaccard 检索（领域精确匹配加权），可选注入 `embedder` 做余弦相似度；`RAGPipeline.run` 对每条候选过 `guard_engineering_computation_input` 分区入 `RAGContext`，`to_agent_context()` 输出 authoritative / auxiliary（带 `requires_pending_verification=True`）/ blocked_ids。仓库此前无 RAG 工程组件，本 Sprint 从零新建。
  - ✅ 任务4 消费审计持久化设计：`agents/engineering/knowledge/activation/audit_persistence.py` 新增 `PersistentConsumptionAuditLog`（append-only，默认 `logs/consumption_audit.jsonl`），复用父类 `record` 的 approved 拒绝检查，故文件天然不含 `approved`；独立 JSONL **不经** `repository.event_log`（白名单不含 approved），故天然不产 approved 事件 / 不触 `verified.json` / 不建 `ReleaseApproval`。
  - ✅ 任务5 测试 `tests/agents/test_runtime_integration.py`：**23 用例全 PASS**（Wind 拒绝非 Approved / Glass 拒绝非 Approved / Approved 允许作权威 / Pending 阻断 / Deprecated 阻断 / `engineering_enabled` 保持 False / RAG pipeline 分区 / audit 持久化 JSONL 不产 approved / `EngineeringAgent.invoke` 接入有·无 `knowledge_items` 两种路径）。
  - ✅ 红线守约：未开 `engineering_enabled`（顶层断言 + `safety_invariants_ok`）/ 未输出 `engineering_approved` / 未改 `verified.json` / 未建 `ReleaseApproval` / AI 不代专家审核（审计硬拒 approved）。激活态维持 NO-GO。
  - ✅ 全量 agents 无 `--cov` 隔离运行 **530 passed**（原 507 + 新增 23，零回归）；Ruff / ESLint / Jest 29·93.15% / Alembic / Seed / 防编造 / 硬编码全绿；`local_ci.sh` 第 2 步仍受环境级 `[safe-delete]` 守卫 + 24 条预存 `test_threshold_*` `--cov` 隔离失败阻断（非本 Sprint 回归）。报告见 `.ai/reviews/phase3.4.4_runtime_integration_report.md`。

- **3.4.5** Activation Readiness Verification & Hardening（激活准备最终验证与加固）。**DONE（2026-08-02）**
  - ✅ 任务1 Unified Gate 全链测试：新增 `tests/agents/test_activation_readiness.py` 中 `TestUnifiedGateFullChainTraceability`（9 例）验证 Knowledge / Threshold / Publishing 三域 G1-G6 失败原因**全部可追踪**（`[domain]` 前缀 + `G1_*`..`G6_*` 标签，100% 可解析）；`test_top_level_safety_gate_blocks_when_enabled_simulated` 用 `monkeypatch` 纯测试替身模拟 `engineering_enabled=True`，断言顶层 G1 仍 fail-closed 且不改真实 config。
  - ✅ 任务2 Agent 入口扫描：`TestAgentEntryScan`（7 例）确认 WindPressure / Glass / Profile / Hardware / InstallationRisk 五接口全部经 `EngineeringRuntimeGuard.guard_interface` 分区（Approved→authoritative、Pending/Deprecated/Captured→blocked、Expert_Verified→auxiliary 须 pending）；`ANALYSIS_INTERFACES == ENGINEERING_INTERFACES` 对齐无遗漏；`inspect.getsource(EngineeringAgent.invoke)` 断言含 `_consume_requested_knowledge(` 与 `knowledge_consumption` 接入点。
  - ✅ 任务3 RAG 旁路测试：`TestRAGBypass`（3 例）验证 Pending / Deprecated / Captured 知识经 `RAGPipeline.run` 全部入 `blocked_ids` 不进 agent 上下文；Expert_Verified 仅 auxiliary 且 `requires_pending_verification=True`；闸门拒绝时 authoritative/auxiliary 全空。
  - ✅ 任务4 审计完整性：`TestAuditBoundaries`（6 例）验证 Consumption Audit（`logs/consumption_audit.jsonl`，event_type ∈ {CONSUMED,BLOCKED} 无 approved）/ Repository Audit（`KnowledgeEventLog.record_event("approved")` 抛 `ValueError`）/ Review Log（append-only + 8 必填字段）三类日志边界清晰互不污染。
  - ✅ 任务5 CI 技术债评估：定位 `local_ci.sh` 第 2 步 `pytest --cov` 触发环境级 `[safe-delete]` 守卫（单轮删 175 文件 > 阈值 50 → `SystemExit(1)`，非测试回归）；24 条预存 `test_threshold_*` 仅 `--cov` 并行模式失败（隔离污染），无 `--cov` 31 passed 全绿；提出修复方案（A 清理+单数据文件 / B coverage run+report 拆分 / C 调高守卫阈值；threshold 加 fixture 临时目录隔离）。
  - ✅ 任务6 最终 Activation Readiness 报告：输出 **NO-GO（禁止自动激活）**；fail-closed 设计正确，统一激活决策恒拒绝，激活仍需主理人置 `engineering_enabled=true` + G6 书面授权 + 真实双签/审核链/CI绿/回滚就绪。
  - ✅ 红线守约：未开 `engineering_enabled`（源码 grep `engineering_enabled=True` → 0 命中）/ 未输出 `engineering_approved`（仅 docstring 级禁令提及）/ 未改 `verified.json` / 未建 `ReleaseApproval`（本 Sprint 未实例化）/ AI 不代专家授权（消费审计硬拒 approved）。激活态维持 NO-GO。
  - ✅ 全量 agents 无 `--cov` 隔离运行 **555 passed**（原 530 + 新增 25，零回归）；Ruff / ESLint / Jest 29·93.15% / Alembic / Seed / 防编造 / 硬编码全绿；`local_ci.sh` 第 2 步仍受环境级 `[safe-delete]` 守卫 + 24 条预存 `test_threshold_*` `--cov` 隔离失败阻断（非本 Sprint 回归）。报告见 `.ai/reviews/phase3.4.5_activation_readiness_verification_report.md`。

### 2.2 待实现（设计已就绪，待主理人确认阈值与排期）

- **3.3.9** Knowledge Intelligence Layer（智能层）。**DONE（2026-08-02）**
  - ✅ 新增 `agents/engineering/knowledge/intelligence/{quality,relationship,conflict}.py` + `_core.py`：Task1 `KnowledgeQualityAnalyzer`(completeness/source_strength/freshness/dependency_integrity/overall，全可溯) / Task2 `KnowledgeRelationshipEngine`(parent_child/related/duplicate_candidate/conflict_candidate，纯函数只读) / Task3 `KnowledgeConflictDetector`(parameter/source/status，review_required 恒定 True) / Task4 Repository 只读接口(analyze/quality_report/find_relationships/detect_conflicts，不破现有 API) / Task5 `tests/agents/test_knowledge_intelligence.py`(26 用例)。报告见 `.ai/reviews/phase3.3.9_knowledge_intelligence_implementation_report.md`。
  - 待主理人确认 5 个决策点（freshness 分桶、overall 权重、扫描豁免、接口签名、实现顺序）后进入实现。
- **3.4.1+ / 3.4.2** 激活架构落地（**3.4.1 激活层 DONE；3.4.2 统一闸门 DONE**）。后续待治理确认阈值与排期后，进入**消费层强制落地**（见 §5 TD-3.4.2-3，高优）与真实激活解锁（主理人人工置 `engineering_enabled=true` + G6 书面授权）。

---

## 3. 优先级排序（Phase 3.4）

| 优先级 | 任务 | 理由 |
|---|---|---|
| **P0** | 3.4.0 激活准备架构（设计 DONE） | 为后续激活提供判定框架与边界 |
| **P0** | 3.4.1 激活模块落地（**实现 DONE**） | 只读校验代码已聚合知识域 G1-G6；激活态仍 NO-GO |
| **P0** | 3.4.2 统一闸门落地（**实现 DONE**） | 知识域/阈值域/发布域 G1-G6 聚合为统一决策；零规则复制，fail-closed |
| **P0** | 3.4.4 运行时接入（**实现 DONE**） | `EngineeringKnowledgeGuard` 已挂接五工程接口与 RAG 检索链路 + 审计持久化 JSONL；消费层在真实运行时强制生效，零回归 |
| **P0** | 3.4.5 激活准备最终验证（**DONE**） | 25 新增测试实证三域 G1-G6 可追踪 / 五接口 RuntimeGuard / RAG 旁路防护 / 三类审计边界；fail-closed 设计正确，NO-GO 维持，禁止自动激活；激活解锁仍须主理人人工动作 |
| **P1** | 3.3.9 智能层实现（DONE） | 为 ActivationGate 提供 quality/relationship/conflict 输入信号 |
| **P1** | 还债 TD-3.4.2-1/2（`local_ci` 8/8 可达） | 清除环境级 `[safe-delete]` 守卫与 `--cov` 阈值测试隔离失败 |
| **P2** | 消费层强制（TD-3.4.2-3，高优沿用 TD-3.4.0-3） | **RESOLVED by 3.4.3**：`EngineeringKnowledgeGuard` 已接入 `UnifiedConsumptionController` 并落地 pending_verification 标注与 Deprecated 规避；下一步 3.4.4 接入真实计算入口与 RAG 检索层 |
| **P2** | 激活阈值治理确认（TD-3.4.2-4，沿用 TD-3.4.0-1） | overall/freshness 分桶权重待主理人裁定 |

---

## 4. 红线与治理不变式（Phase 3.4 全程）

1. **不录入真实参数**：`E-TH-01/02/03` 真实 `value` 仍 `null`（pending_verification），Phase 3.4 不填。
2. **不开 `engineering_enabled`**：全局仍 `false`；`can_activate_knowledge` / `can_enable_engineering` 默认拒绝，直至 G1-G6 全绿 + G6 授权。
3. **不输出 `engineering_approved`**：全 `pending_verification`，无 approved 落盘/输出；`Engineering_Approved` 仅由人工经正式流程产生。
4. **不代签/不代授权**：签名与授权由人工线下经正式流程提供，AI 仅编排容器与校验。
5. **不自动创建 `ReleaseApproval`**：G6 授权由主理人书面创建。
6. **防编造/硬编码扫描**：既有代码与文档持续 0 命中；新增设计文档不引入裸数字/行业常数。

---

## 5. 技术债记录（Phase 3.4 起）

- TD-3.4.0-1 激活阈值（overall/freshness 分桶）待治理确认（中，open）。
- TD-3.4.0-2 知识域 G1-G6 与阈值域 G1-G6 需上层聚合（中，open）。
- TD-3.4.0-3 消费策略运行时强制（辅助引用须标 pending_verification）需在消费层落地（高，open）。
- TD-3.4.0-4 沿用 3.2.5-H3-B 冻结记录 bundle_id 不一致（低，待主理人确认）。
- TD-3.4.0-5 `local_ci.sh` 完整运行 `test_smoke_e2e.py` 触发 WorkBuddy `[safe-delete]` 守卫（低，环境级，待基建处理）。
- **TD-3.4.1-1** `local_ci.sh` 第 2 步 pytest 完整集触发 WorkBuddy `[safe-delete]` 守卫（`pytest-cov` 并行 `combine` 删 `.coverage.*` → `SystemExit(1)`），环境级（低，非 3.4.1 回归）。
- **TD-3.4.1-2** 24 条预存 `test_threshold_*` 仅 `--cov` 并行模式失败（隔离污染），无 `--cov` 直接运行 481 passed 全绿（中，预存）。
- **TD-3.4.1-3** 激活阈值（overall/freshness 分桶）仍待治理确认（中，沿用 TD-3.4.0-1）。
- **TD-3.4.1-4** 知识域 G1–G6 与阈值域 G1–G6 待 `UnifiedActivationGate` 聚合（中，沿用 TD-3.4.0-2）→ **RESOLVED by 3.4.2**（零规则复制聚合三域）。
- **TD-3.4.1-5** 消费策略运行时强制（辅助引用须标 pending_verification）待消费层落地（高，沿用 TD-3.4.0-3）→ 部分交付：`UnifiedConsumptionController` 已在 3.4.2 实现，待接入 Engineering Agent/RAG 运行时（TD-3.4.2-3）。
- **TD-3.4.2-1** `local_ci.sh` 第 2 步 pytest 完整集触发 WorkBuddy `[safe-delete]` 守卫（`pytest-cov` 并行 `combine` 删 `.coverage.*` → `SystemExit(1)`），环境级（低，非 3.4.2 回归，同源 TD-3.4.1-1）。
- **TD-3.4.2-2** 24 条预存 `test_threshold_*` 仅 `--cov` 并行模式失败（隔离污染），无 `--cov` 直接运行 494 passed 全绿（中，预存，同源 TD-3.4.1-2）。
- **TD-3.4.2-3** 消费层强制（辅助引用须标 pending_verification、未 Approved 禁止进入工程计算）待接入 Engineering Agent / RAG 运行时（高，沿用 TD-3.4.0-3 / TD-3.4.1-5）→ **RESOLVED by 3.4.3**（`EngineeringKnowledgeGuard.consume_knowledge` 已接入 `UnifiedConsumptionController` 并落地分级与审计；下一步 3.4.4 接入真实计算入口与 RAG 检索层）。
- **TD-3.4.3-1** 消费层运行时集成：当前 `EngineeringKnowledgeGuard` 已就绪但仅在测试中调用，真实 Engineering Agent 计算入口（Glass/WindPressure/Profile/Hardware/InstallationRisk）与 RAG 检索层尚未在运行时挂接 guard（中，open，建议 3.4.4）→ **RESOLVED by 3.4.4**（`EngineeringRuntimeGuard.guard_interface` 已接入 `EngineeringAgent.invoke`；`knowledge/rag` 链路已挂 `guard_engineering_computation_input`）。
- **TD-3.4.3-2** `KnowledgeConsumptionAuditLog` 为内存 append-only，未持久化到独立存储；生产化需落盘/集中审计（低，open，非阻断）→ **RESOLVED by 3.4.4**（`PersistentConsumptionAuditLog` 已落盘 `logs/consumption_audit.jsonl`，不经 repository 白名单，天然不产 approved）。
- **TD-3.4.4-1** 真实 RAG embedding 接入：当前 `KnowledgeRetriever` 默认词面 Jaccard 检索，可选注入 `embedder` 做余弦相似度；真实 embedding 服务接入待主理人排期（低，open，非阻断）。
- **TD-3.4.4-2** 运行时消费审计 JSONL 缺集中回收/轮转策略（仅 append-only，无限增长）；生产化需加轮转/集中采集（低，open，非阻断）。
- **TD-3.4.5-1** `local_ci.sh` 第 2 步 `pytest --cov` 触发环境级 `[safe-delete]` 守卫（单轮删 175 文件 > 阈值 50）→ `SystemExit(1)`（低，环境级，非 3.4.5 回归）。修复：A 清理旧 coverage + 单 `--cov-data-file` 禁用 merge 删除；B `coverage run`+`coverage report` 拆分；C 调高守卫阈值/加豁免。
- **TD-3.4.5-2** 24 条预存 `test_threshold_*` 仅 `--cov` 并行模式失败（隔离污染），无 `--cov` 31 passed 全绿（中，预存，同源 TD-3.4.1-2 / TD-3.4.2-2）。修复：fixture 级 `tmp_path` + `monkeypatch` 隔离全局状态，或 xdist `isolate` 子进程。
- **TD-3.4.5-3** 本 Sprint 新增 25 例验证测试已并入 `tests/agents/test_activation_readiness.py`，建议纳入 CI 门禁常驻（低，open，非阻断；已随 555 passed 验证）。
- **TD-3.4.5-4** 运行时消费审计 JSONL 仍缺集中回收/轮转策略（沿用 TD-3.4.4-2，低，open，非阻断）。
- **TD-3.4.5-5** 真实 RAG embedding 接入待主理人排期（沿用 TD-3.4.4-1，低，open，非阻断）。
- **TD-3.4.2-4** 激活阈值（overall / 权重）治理确认仍待主理人裁定（中，沿用 TD-3.4.0-1）。
- 债 OPEN 现状：Phase 2.2 末 OPEN=13（目标 ≤5 未达标），Phase 3.4 起须排入还债节奏；3.4.2 已闭环 TD-3.4.1-4。

---

**END**
