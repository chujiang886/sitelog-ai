# BOIP Phase 3.4.4 报告：Engineering Runtime Integration（工程AI运行时接入）

- **日期**：2026-08-02
- **身份**：BOIP AI Chief Architect
- **性质**：实现 Sprint（additive read-only integration，不修改任何计算逻辑，fail-closed，不翻转 `engineering_enabled`）
- **依据**：`.ai/project_status.json`（SSOT）、`.ai/roadmap_v4.md`、本 Sprint 实现代码与测试
- **前置**：3.4.0 激活准备架构（DESIGN_DONE）→ 3.4.1 激活层（DONE）→ 3.4.2 统一闸门（DONE）→ 3.4.3 消费强制（DONE）→ **3.4.4 运行时接入（DONE）**

---

## 1. 架构变化（Architecture Changes）

### 1.1 入口识别（任务1）
- 五工程知识消费入口 = `EngineeringAgent` 的五个 `analyze_*` 分发器：`wind_pressure` / `glass_safety` / `profile` / `hardware` / `installation_risk`，各自调用对应 `Calculator.calculate`（非独立类）。
- 系统级决策 `UnifiedActivationDecision` 为共享 fail-closed 决策；知识候选集来自各接口计算前的 `input_data["knowledge_items"]`。
- 仓库此前**无** RAG 工程组件，3.4.4 从零新建 `agents/engineering/knowledge/rag/` 包。

### 1.2 运行时接入点（任务2）
- 新增 `EngineeringRuntimeGuard`（独立声明 `ENGINEERING_INTERFACES`，**不 import `agent.py`** 以避免循环依赖）。
- `guard_interface(interface, items, decision)`：逐项候选过 `guard_engineering_computation_input` 并分区：
  - `authoritative`：Engineering_Approved，可作权威依据；
  - `auxiliary`：Verified 系列，仅辅助，须标 `pending_verification`；
  - `blocked`：Captured / Pending / Deprecated，一律不得进入。
- `EngineeringAgent` 向后兼容接入：`invoke` 成功路径新增 `knowledge_consumption` 字段；**无 `knowledge_items` 输入时返回空 dict，零副作用**（既有测试 `test_engineering.py` 不受影响）。

### 1.3 RAG 入口接入（任务3）
流程：`Retriever → Consumption Guard → Context Builder → Engineering Agent`。
- `KnowledgeRetriever`：默认词面 Jaccard 检索（领域精确匹配 +0.5 加权），可选注入 `embedder: callable[str, list[float]]` 做余弦相似度，便于后续接真实 embedding 服务而不改流程结构。
- `RAGPipeline.run(query, corpus, decision)`：每条候选过 `guard_engineering_computation_input` 分区入 `RAGContext`。
- `RAGContext.to_agent_context()`：输出 `{authoritative_knowledge, auxiliary_knowledge(带 requires_pending_verification=True), blocked_knowledge_ids, decision_allowed}`。

### 1.4 消费审计持久化（任务4）
- 新增 `PersistentConsumptionAuditLog`（append-only，默认 `logs/consumption_audit.jsonl`）。
- 复用父类 `record` 的 approved 拒绝检查，故文件天然不含 `approved`。
- 独立于 `repository.event_log`（白名单刻意不含 approved），故**不产 approved 事件 / 不触 `verified.json` / 不建 `ReleaseApproval`**。
- `load_existing()` 支持重启后审计连续（幂等，不再写文件）。

---

## 2. 文件变化（File Changes）

| 文件 | 类型 | 说明 |
|---|---|---|
| `agents/engineering/knowledge/activation/runtime_integration.py` | 新建 | `ENGINEERING_INTERFACES` / `InterfaceGuardResult` / `EngineeringRuntimeGuard`（任务1+2 核心接入点） |
| `agents/engineering/knowledge/rag/__init__.py` | 新建 | 导出 `KnowledgeRetriever` / `RetrievalResult` / `RAGContext` / `RAGPipeline` |
| `agents/engineering/knowledge/rag/retriever.py` | 新建 | 词面 Jaccard + 可选 embedding 余弦检索 |
| `agents/engineering/knowledge/rag/context_builder.py` | 新建 | `RAGContext` + `to_agent_context()` |
| `agents/engineering/knowledge/rag/pipeline.py` | 新建 | `RAGPipeline.run` 编排 Retriever→Guard→Context |
| `agents/engineering/knowledge/activation/audit_persistence.py` | 新建 | `PersistentConsumptionAuditLog` + `make_persistent_audit_log`（任务4） |
| `agents/engineering/agent.py` | 修改（additive） | 4 处 edit：import / `__init__` 增加 `knowledge_guard`+`knowledge_repository` / `consume_knowledge_for`+`_consume_requested_knowledge` / `invoke` 接入 `knowledge_consumption` |
| `tests/agents/test_runtime_integration.py` | 新建 | 23 用例（任务5） |

---

## 3. 测试结果（Test Results）

### 3.1 新增测试（23 passed）
`tests/agents/test_runtime_integration.py` 覆盖：
- **Wind 拒绝非 Approved**：`wind_pressure` 接口对 Pending/Expert_Verified/Deprecated 候选正确分区（authoritative 空，blocked 命中）。
- **Glass 拒绝非 Approved**：`glass_safety` 接口对 Deprecated 阻断、Source_Verified 仅 auxiliary。
- **Approved 允许**：任意工程接口上 Engineering_Approved 进入 authoritative；未知接口名抛 `ValueError`。
- **Pending 阻断**：所有接口 Pending_Verification 一律 blocked。
- **Deprecated 阻断**：所有接口 Deprecated / Captured 一律 blocked。
- **`engineering_enabled` 保持 False**：跑完接口 + RAG 流程前后 `load_engineering_enabled()` 恒 `False`；`safety_invariants_ok()` True；`UnifiedActivationGate` 真实空仓库 fail-closed。
- **RAG pipeline 分区**：authoritative={KI-A} / auxiliary={KI-E} / blocked={KI-P,KI-D}；`to_agent_context` 结构正确（auxiliary 带 `requires_pending_verification`）。
- **audit 持久化 JSONL**：落盘 `consumption_audit.jsonl`，事件类型仅 `knowledge_consumed`/`knowledge_blocked`，无 `approved`；`load_existing` 幂等不重复落盘。
- **`EngineeringAgent.invoke` 接入**：无 `knowledge_items` 时 `knowledge_consumption=={}`（向后兼容）；有 `knowledge_items` 时正确分区；未提供 `unified_decision` 且无仓库时 fail-closed 全阻断。

### 3.2 全量回归
- 隔离运行 `tests/agents --no-cov`：**530 passed**（基线 507 + 新增 23），**零回归**。
- Ruff（7 文件）：**All checks passed!**（修复初版 F401 未用 `Any` 导入）。
- ESLint / Jest 29·93.15% / Alembic / Seed / 防编造 / 硬编码：全绿。
- `local_ci.sh` 第 2 步 pytest 完整 `--cov` 运行仍受环境级 `[safe-delete]` 守卫 + 24 条预存 `test_threshold_*` `--cov` 隔离失败阻断（非本 Sprint 回归，已知长期 7/8）。

---

## 4. 红线检查（Red-Line Compliance）

| 红线 | 状态 | 证据 |
|---|---|---|
| ① 不开 `engineering_enabled=true` | ✅ 守约 | `consume_knowledge` 顶层断言 `load_engineering_enabled() is False`；`EngineeringRuntimeGuard.safety_invariants_ok()` 静态断言；全程未调用任何 setter；配套代码扫描 0 命中 |
| ② 不输出 `engineering_approved` | ✅ 守约 | 实现代码中无输出语句；仅 docstring 描述禁令 |
| ③ 不创建 `ReleaseApproval` | ✅ 守约 | 代码零实例化；G6 由主理人线下创建 |
| ④ 不修改 `verified.json` | ✅ 守约 | 持久化审计走独立 JSONL，不经 `repository.event_log`；Repository 全程未读未写 |
| ⑤ AI 不代专家授权 | ✅ 守约 | 消费审计 `record` 显式拒 `approved` 事件；`repository.event_log` 仍硬拒 `approved` |

**代码扫描结果**：`engineering_enabled=True` / `ReleaseApproval(` / `engineering_approved=` / `set_engineering_enabled` / `.approve(` / `verified.json` 写 —— **0 命中**（仅在 docstring 描述禁令，无任何实例化/翻转/写入）。

---

## 5. 技术债（Tech Debt）

- **TD-3.4.3-1**（消费层运行时集成） → **RESOLVED by 3.4.4**：`EngineeringRuntimeGuard` 已接入 `EngineeringAgent.invoke`，`knowledge/rag` 链路已挂 `guard_engineering_computation_input`。
- **TD-3.4.3-2**（审计持久化） → **RESOLVED by 3.4.4**：`PersistentConsumptionAuditLog` 落盘 `logs/consumption_audit.jsonl`，不经 repository 白名单，天然不产 `approved`。
- **TD-3.4.4-1**（真实 RAG embedding 接入）：`KnowledgeRetriever` 默认词面 Jaccard，真实 embedding 服务接入待主理人排期（低，open，非阻断）。
- **TD-3.4.4-2**（审计 JSONL 轮转）：当前仅 append-only 无限增长，生产化需加轮转/集中采集（低，open，非阻断）。
- 沿用债 TD-3.4.2-1 / TD-3.4.2-2（`local_ci` 8/8 环境级 `[safe-delete]` + `test_threshold_*` `--cov` 隔离）仍 OPEN，非本 Sprint 回归。
- 激活阈值治理确认（TD-3.4.2-4 / TD-3.4.0-1）仍待主理人裁定。

---

## 6. 下一阶段建议（Next Steps）

1. **还债**：清除 `local_ci.sh` 环境级 `[safe-delete]` 守卫与 `test_threshold_*` `--cov` 隔离失败，使 8/8 可达（TD-3.4.2-1/2，中）。
2. **治理确认**：激活阈值（overall / freshness 分桶权重）由主理人裁定（TD-3.4.2-4）。
3. **真实激活解锁（人工动作）**：由主理人线下置 `engineering_enabled=true` + G6 书面授权 + 真实双签/审核链/CI绿确认/回滚就绪；AI 不代行。
4. **RAG embedding 接入**（TD-3.4.4-1）与**审计轮转**（TD-3.4.4-2）按排期推进，均非阻断。
5. **本 Sprint 完成后按指令停止**：等待主理人验收，未进入 Phase 3.5。

---

**END**
