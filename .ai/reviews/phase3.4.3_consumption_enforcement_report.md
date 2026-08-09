# BOIP Phase 3.4 Sprint 3.4.3 — Engineering AI Consumption Enforcement 报告

- **生成**：2026-08-02
- **身份**：BOIP AI Chief Architect
- **Sprint**：Engineering AI Consumption Enforcement（工程AI消费强制治理）
- **依据**：`.ai/project_status.json`（SSOT，current_roadmap_version=V4）、`.ai/roadmap_v4.md`、`.ai/reviews/phase3.4.2_unified_activation_gate_report.md`
- **前序**：Phase 3.3 ✅ / Phase 3.4.0 ✅ / 3.4.1 ✅ / 3.4.2 ✅ → 本 Sprint **3.4.3 ✅**

---

## 1. 架构变化（Architecture Changes）

本 Sprint 在 3.4.2 `UnifiedActivationGate` + `UnifiedConsumptionController` 之上，新增**消费入口强制层**，使 Engineering AI / RAG 检索链在把知识纳入工程计算前**必须**经过统一闸门 + 消费策略判定。

### 1.1 新增 `EngineeringKnowledgeGuard`（消费守卫）

- 位置：`agents/engineering/knowledge/activation/consumer_guard.py`
- 主入口 `consume_knowledge(item, unified, *, actor, detail) -> ConsumptionResult`：
  1. **顶层红线不变量**：`load_engineering_enabled() is False` 校验，违反即 fail-closed 拒绝（`engineering_enabled_must_be_false`）。
  2. **统一闸门判定**：`unified.allowed` 为 False → 拒绝任何知识（`unified_gate_blocked`）。
  3. **消费策略分级**：委托 `UnifiedConsumptionController.evaluate(item, unified)`：
     - `citable`（仅 `Engineering_Approved`）→ `as_authoritative=True`，可作权威依据。
     - `auxiliary_only`（`Source/Expert/Engineering_Verified`）→ 仅辅助，`requires_pending_verification=True`，须标 `pending_verification`。
     - `not_citable`（`Captured`/`Pending_Verification`/`Deprecated`）→ 禁止进入工程计算（`not_citable_forbidden`）。
- 返回 `ConsumptionResult(permitted, policy, as_authoritative, requires_pending_verification, reason, event)`。

### 1.2 任务2：RAG 消费边界（明确三级）

| 知识状态 | RAG / Engineering AI 消费结论 | 是否权威 |
|---|---|---|
| `Engineering_Approved` | 允许进入 | ✅ 权威（citable） |
| `Source_Verified` / `Expert_Verified` / `Engineering_Verified` | 允许，但**仅辅助**且须标 `pending_verification` | ❌ 非权威（auxiliary_only） |
| `Pending_Verification` / `Captured` / `Deprecated` | **禁止进入** | ❌ 禁止（not_citable） |

### 1.3 任务3：工程 Agent 接入（只读 Guard，不改计算逻辑）

- 新增只读接入点 `guard_engineering_computation_input(item, unified, *, actor="engineering_agent", detail)`。
- 供 `WindPressure` / `Glass` / `Profile` / `Hardware` / `InstallationRisk` 等工程计算入口在**计算前**调用；返回 `ConsumptionResult`。
- 若 `permitted=False` 或 `as_authoritative=False`，该知识不得作为权威计算依据——仅可作辅助上下文且须标 `pending_verification`。
- **本方法仅判定与记录审计，不修改任何现有计算逻辑**（满足任务3"只读 Guard"约束）。

### 1.4 任务4：消费审计日志（独立存储，显式拒 approved）

- 新增 `KnowledgeConsumptionAuditLog`（append-only，内存列表）：
  - 记录 `knowledge_consumed`（允许）/ `knowledge_blocked`（拒绝）。
  - **显式拒绝 `approved` 事件**（`_CONSUMPTION_FORBIDDEN_EVENTS = frozenset({FORBIDDEN_EVENT_TYPE, "approved"})`），若尝试记录 forbidden 类型抛 `ValueError`。
- **设计决策**：独立日志**不触碰** repository `EVENT_TYPES` 白名单、不触碰 `verified.json`、不创建 `ReleaseApproval`。repository 的 `EVENT_TYPES=("create","update","verify","deprecated")` 白名单为刻意红线守护，故消费审计不污染它，并复用 `KnowledgeEvent` dataclass。

### 1.5 循环导入防护

- `consumer_guard` ← `unified_activation_gate` ← `activation.__init__` ← `consumer_guard` 形成环。
- 采用 `TYPE_CHECKING` 下类型标注 `UnifiedActivationDecision` + `__init__` 中**延迟导入** `UnifiedConsumptionController`，消除 `ImportError`。

---

## 2. 文件变化（Files Changed）

### 2.1 新增

| 文件 | 说明 |
|---|---|
| `agents/engineering/knowledge/activation/consumer_guard.py` | 核心交付：消费守卫 + 独立消费审计日志（任务1/2/3/4） |
| `tests/agents/test_consumption_guard.py` | 13 用例（任务5） |

### 2.2 修改

| 文件 | 说明 |
|---|---|
| `agents/engineering/knowledge/activation/__init__.py` | 导出扩充：`CONSUMED_EVENT` / `BLOCKED_EVENT` / `ConsumptionResult` / `EngineeringKnowledgeGuard` / `KnowledgeConsumptionAuditLog` / `make_guard`；模块 docstring 补充 `consumer_guard.py`；`__all__` 同步 |

### 2.3 未改动（强调红线）

- 未修改 `verified.json`（全程未读未写）。
- 未创建 `ReleaseApproval`（代码零实例化）。
- 未翻转 `engineering_enabled`（仅读判定）。
- 未输出 `engineering_approved`（仅 docstring 描述禁令）。

---

## 3. 测试结果（Test Results）

### 3.1 新增测试 `tests/agents/test_consumption_guard.py`（13 passed）

| 测试类 | 覆盖点 | 结论 |
|---|---|---|
| `TestConsumptionApprovedAllowed` | `Engineering_Approved` 权威允许 + 审计 `knowledge_consumed` | ✅ |
| `TestConsumptionPendingRejected` | `Pending_Verification` not_citable 拒绝 + `knowledge_blocked` | ✅ |
| `TestConsumptionDeprecatedRejected` | `Deprecated` 与 `Captured` 均 BLOCKED | ✅ |
| `TestConsumptionAuxiliaryRequiresPending` | `Expert_Verified` → auxiliary + `requires_pending_verification` + CONSUMED | ✅ |
| `TestConsumptionGateFailure` | Approved 但统一闸门阻 → `unified_gate_blocked` + BLOCKED | ✅ |
| `TestConsumptionNoApprovedEvent` | 全状态无 `approved` 事件 | ✅ |
| `TestConsumptionEngineeringEnabledInvariant` | 前后 `False` + `safety_invariants_ok()` | ✅ |
| `TestConsumptionIntegrationPoint` | `guard_engineering_computation_input` 空仓库拒绝 | ✅ |

### 3.2 回归与质量门

- 全量 `pytest tests/agents --no-cov`：**507 passed**（原 494 + 新增 13，零回归）。
- `ruff check agents/engineering/knowledge/activation/ tests/agents/test_consumption_guard.py`：**All checks passed!**（已修 `dataclasses.field` F401）。
- `local_ci.sh` 7/8 网关绿（Ruff / ESLint / Jest 29·93.15% / Alembic / Seed / 防编造 / 硬编码全绿）；第 2 步 pytest 完整 `--cov` 仍受环境级 `[safe-delete]` 守卫 + 24 条预存 `test_threshold_*` 隔离失败阻断（**非本 Sprint 回归**，隔离运行 507 passed）。
- 防编造扫描：**0 命中**；硬编码扫描：**0 命中**；红线代码扫描（`engineering_enabled=True` / `ReleaseApproval(` / `engineering_approved=` / `set_engineering_enabled`）：**0 命中（仅 docstring 描述禁令）**。

---

## 4. 红线检查（Red-Line Verification）

| # | 红线 | 本 Sprint 守约情况 |
|---|---|---|
| ① | 禁止开启 `engineering_enabled=true` | ✅ `consume_knowledge` 顶层 `load_engineering_enabled() is False` 断言 + `safety_invariants_ok()` 静态断言；绝不翻转 |
| ② | 禁止输出 `engineering_approved` | ✅ 无输出语句；仅 docstring 描述禁令 |
| ③ | 禁止创建 `ReleaseApproval` | ✅ 代码零实例化 |
| ④ | 禁止修改 `verified.json` | ✅ 独立消费审计日志不触碰；Repository 全程未读未写 |
| ⑤ | 禁止 AI 代替专家授权 | ✅ 消费审计 `KnowledgeConsumptionAuditLog.record` 显式拒 `approved` 事件（抛 `ValueError`）；repository `event_log.record` 仍硬拒 `approved` |

**激活态**：NO-GO 维持（`engineering_enabled=False`；消费层强制已落地，但知识/阈值/发布三域 G1–G6 默认全 FAIL，缺真实双签/审核链/G6 授权/CI 绿确认/回滚就绪）。

---

## 5. 技术债（Tech Debt）

- **TD-3.4.2-3（消费层强制）** → **RESOLVED by 3.4.3**：`EngineeringKnowledgeGuard.consume_knowledge` 已接入 `UnifiedConsumptionController` 并落地分级与审计；下一步 3.4.4 接入真实计算入口与 RAG 检索层。
- **TD-3.4.3-1**（新增，中/open）：消费层运行时集成——当前 `EngineeringKnowledgeGuard` 已就绪但仅在测试中调用，真实 Engineering Agent 计算入口（Glass/WindPressure/Profile/Hardware/InstallationRisk）与 RAG 检索层尚未在运行时挂接 guard。建议 3.4.4 完成。
- **TD-3.4.3-2**（新增，低/open）：`KnowledgeConsumptionAuditLog` 为内存 append-only，未持久化到独立存储；生产化需落盘/集中审计（非阻断）。
- 仍 OPEN（沿用）：TD-3.4.2-1/2（`local_ci` 8/8 可达，环境级）、TD-3.4.2-4（激活阈值治理确认，待主理人裁定）。

---

## 6. 下一阶段建议（Next Phase）

1. **3.4.4 消费接入集成（建议）**：在真实 Engineering Agent 计算入口与 RAG 检索层调用 `guard_engineering_computation_input` / `consume_knowledge`，落地运行时强制（承接 TD-3.4.3-1）。
2. **还债 TD-3.4.2-1/2**：清除环境级 `[safe-delete]` 守卫与 `--cov` 阈值测试隔离失败，使 `local_ci.sh` 8/8 可达。
3. **激活阈值治理确认（TD-3.4.2-4）**：overall/freshness 分桶权重待主理人裁定。
4. **真实激活解锁（人工）**：由主理人线下置 `engineering_enabled=true` + G6 书面授权，经正式双签/审核链/CI 绿/回滚就绪确认后，方解除 NO-GO。

> 本 Sprint 完成后**停止**：未开启 `engineering_enabled`、未输出 `engineering_approved`、未创建 `ReleaseApproval`、未修改 `verified.json`、未记录 `approved` 事件。

**END**
