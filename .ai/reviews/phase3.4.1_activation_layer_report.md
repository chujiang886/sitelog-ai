# BOIP Phase 3.4 Sprint 3.4.1 — Engineering Knowledge Activation Layer Implementation

- **生成**：2026-08-02
- **身份**：BOIP AI Chief Architect（Phase 3.4 Sprint 3.4.1）
- **性质**：**实现 Sprint**（对照 `.ai/reviews/phase3.4.0_activation_readiness_architecture.md` 设计文档 §4–§7 落地）。新增 `agents/engineering/knowledge/activation/` 4 模块 + 1 包导出 + `tests/agents/test_knowledge_activation.py`，**全部只读/声明性，fail-closed，不翻转 `engineering_enabled`**。
- **依据**：`.ai/reviews/phase3.4.0_activation_readiness_architecture.md`、`.ai/project_status.json`（SSOT）、`.ai/roadmap_v4.md`、仓库既有 `agents/engineering/gate/enable_gate.py` 与 `agents/engineering/knowledge/repository.py`（3.3.8/3.3.9）。
- **CI 结果**：`local_ci.sh` **7/8 网关绿**（Ruff / ESLint / Jest 29·93.15% / Alembic / Seed / 防编造 / 硬编码 全绿）；第 2 步 pytest 完整集受 **环境级 `[safe-delete]` 守卫 + 24 条预存 `test_threshold_*` `--cov` 隔离失败** 阻断（均非本 Sprint 回归，详见 §5 技术债）。

---

## 0. 最高红线守约总览（5 条）

| # | 红线 | 本 Sprint 结论 |
|---|---|---|
| ① | 禁止开启 `engineering_enabled=true` | ✅ 全程仅读 `load_engineering_enabled()`，未调用任何写接口；门禁断言 `safety_invariants_ok() == (load_engineering_enabled() is False)` |
| ② | 禁止输出 `engineering_approved` | ✅ 无 `Engineering_Approved` 落盘/输出；`APPROVED_STATUS` 仅作条件输入与策略分类常量，`KnowledgeItem` 由测试夹具纯标识符构造（KI-1/SRC-1，无业务数值） |
| ③ | 禁止创建 `ReleaseApproval` | ✅ 代码零引用 `ReleaseApproval`；G6 授权由主理人线下书面创建（仅作 `authorization_present` 布尔注入） |
| ④ | 禁止修改 `verified.json` value | ✅ 全程未读未写 `verified.json`；Repository 不触碰该文件（3.3.8 已定） |
| ⑤ | 禁止 AI 代替专家授权 | ✅ 门禁**只判定**是否允许激活，双签/审核链/G6 授权/CI绿/回滚就绪均为显式或推导输入，AI 不代签、不代授权 |

---

## 1. 架构变化（Architecture Changes）

### 1.1 新增激活判定层（知识域 G1–G6，fail-closed）

在 `agents/engineering/knowledge/activation/` 下落地 Phase 3.4.0 设计文档定义的激活判定框架：

- **门禁语义对齐 `enable_gate.py`**：`KnowledgeActivationGate.can_activate_knowledge(repository, *, context=None) -> ActivationDecision(allowed, blocking_reasons, gate_results, detail)`，对照阈值域 `can_enable_engineering` 的 fail-closed 默认拒绝语义，适配到知识域。
- **六门全默认 FAIL**：
  - **G1 knowledge_governance** — `repo.safety_invariants_ok()`（`engineering_enabled=False`）**且**存在 `Engineering_Approved` 候选；二者缺一即阻。
  - **G2 dual_sign** — 候选 item 审核链（verify 事件 actor）含专家（`expert`）**且**含工程/管理（`engineer`/`mgmt`/`manager`）；显式 `dual_sign_present` 注入优先。
  - **G3 ci_status** — `ctx.ci_green is True`（注入，默认红）。
  - **G4 audit_chain** — 事件日志无 forbidden `approved`，且候选 item 审计链完整（含 `create` + `verify`）。
  - **G5 rollback_ready** — `ctx.rollback_ready is True`（注入，默认不就绪）。
  - **G6 authorization** — `ctx.authorization_present is True`（主理人书面授权，默认缺失）。
- **绝不翻转 `engineering_enabled`**：`can_activate_knowledge` 仅返回判定结论；红线由 `config_loader` 在真实激活时拦截。

### 1.2 消费策略三级分类（对齐设计 §5）

`KnowledgeConsumptionPolicy` 依据 `validation_status` 分类：
- `citable`（可权威引用）— 仅 `Engineering_Approved`。
- `auxiliary_only`（辅助引用，须标 `pending_verification`）— `Engineering_Verified` / `Expert_Verified` / `Source_Verified`。
- `not_citable`（不可引用）— `Captured` / `Pending_Verification` / `Deprecated`。
- **关键纠正**：`Pending_Verification` 归入 `not_citable`（未验证不可引用），**非** `auxiliary_only` —— 初版曾误映射，已按设计文档 §5 修正。

### 1.3 AI 读取边界（`KnowledgeReadBoundary`）

- ✅ **可读**：元数据 `metadata`、质量报告 `quality_report`、关系 `relationship`、冲突 `conflict`（均为辅助信号）。
- ❌ **不可读/不可为**：`verified.json value` / 创建 `ReleaseApproval` 权限 / 写 `engineering_enabled` 权限 / 自助产出 `Engineering_Approved`。
- `read_invariants_ok()` 断言 `engineering_enabled is False`。

### 1.4 Rollback 谱系（`KnowledgeRollbackPolicy`，对齐设计 §7）

- 复用 `KnowledgeRepository.deprecate(knowledge_id, *, successor)`（3.3.8 已实现）：置 `Deprecated`，将 successor 写入被废弃 item 的 `parent_knowledge_id`。
- 提供 `successor_of` / `build_replacement_chain`（一跳）/ `is_replacement_available` / `history_preserved`（item 存在且 `version()>=1`）。
- **不删历史**：废弃 item 保留，审计可溯，满足 G5 rollback_ready。

### 1.5 依赖关系（无回归、无新耦合）

- 仅依赖既有 `KnowledgeRepository`、`config_loader.load_engineering_enabled`、`enable_gate.py` 语义（不 import `KnowledgeItem` / `connector`，降低耦合与编造面）。
- 智能层（3.3.9 quality/relationship/conflict）作为 G1/G4 的潜在上游信号，本 Sprint 不强制依赖（门禁以 repo 接口为准）。

---

## 2. 文件变化（File Changes）

### 2.1 新增文件

| 文件 | 行数 | 职责 |
|---|---|---|
| `agents/engineering/knowledge/activation/__init__.py` | ~45 | 包导出：4 类 + 全部常量 |
| `agents/engineering/knowledge/activation/gate.py` | ~275 | `KnowledgeActivationGate` + `ActivationContext` + `ActivationDecision` + G1–G6 常量 |
| `agents/engineering/knowledge/activation/consumption.py` | ~90 | `KnowledgeConsumptionPolicy`：citable/auxiliary_only/not_citable |
| `agents/engineering/knowledge/activation/read_boundary.py` | ~70 | `KnowledgeReadBoundary`：可读清单 + 四 forbidden + invariants |
| `agents/engineering/knowledge/activation/rollback.py` | ~85 | `KnowledgeRollbackPolicy`：deprecate/successor/chain/history_preserved |
| `tests/agents/test_knowledge_activation.py` | ~360 | 6 测试类 / 30 用例，全 PASS |

### 2.2 修改文件

- 无既有 `.py` 修改（零回归）。
- 元数据/文档：`.ai/project_status.json`（`task_status.phase_3_1.phase_3_4` 插入 `"3.4.1"` DONE 块）、`.ai/roadmap_v4.md`（§1 状态行 + §2 新增 3.4.1 块 + §3 优先级表）、本文件。

---

## 3. 测试结果（Test Results）

### 3.1 新增测试（30 用例全 PASS）

```
tests/agents/test_knowledge_activation.py  30 passed in 0.06s
```

- **TestActivationGateFailClosed**（默认 fail-closed / 六门齐全仍默认阻 G1+G3+G5+G6）
- **TestActivationGateGreen**（全绿 allowed、G3/G5/G6/G1/G2/G4 各单门阻断、双签显式注入）
- **TestActivationGateRedLines**（`engineering_enabled` 前后一致 False、无 `approved` 事件产出、event_log 硬拒 `approved`、非 `KnowledgeRepository` 入参拒）
- **TestConsumptionPolicy**（approved=citable、三 verified=auxiliary_only、Captured/Pending/Deprecated=not_citable、decision_for 形状）
- **TestReadBoundary**（allowed_kinds 四类、四 forbidden 全 False、invariants_ok）
- **TestRollbackPolicy**（deprecate+successor、一跳替换链、历史保留不删、engineering_enabled 不变）

### 3.2 全量 agents 套件（无 `--cov` 隔离运行）

```
pytest tests/agents --no-cov   →  481 passed  (原 451 + 新增 30，零回归)
```

### 3.3 质量扫描

- **防编造扫描**：0 命中（未引入裸行业数字/常数）。
- **硬编码扫描**：0 命中（阈值/路径以常量定义）。
- **Ruff**（activation 范围 + 精确 CI 范围）：全 PASS（已修 2 处 F401 未用 import）。
- **ESLint**：1 warning（预存，与 3.4.1 无关）。
- **Jest**：29 通过 / 93.15%。
- **Alembic**：up + down PASS；**Seed**：PASS。

---

## 4. 红线检查（Red-Line Verification，逐条）

1. **`engineering_enabled` 保持 False** — ✅ `gate.py::_g1_knowledge_governance` 与 `safety_invariants_ok()` 静态断言 `load_engineering_enabled() is False`；测试断言调用前后一致 False；全程无写调用。
2. **无 `engineering_approved` 输出** — ✅ 测试 `TestActivationGateRedLines` 断言 event_log 无 `approved` 事件；`FORBIDDEN_EVENT_TYPE="approved"` 在 G4 中防御性拒绝；Repository `record("x","approved")` 仍硬抛 `ValueError`（3.3.8 白名单维持）。
3. **`verified.json` 未修改** — ✅ 全程未读未写；Repository 不触碰该文件。
4. **未创建 `ReleaseApproval`** — ✅ 代码零引用；G6 由主理人线下创建，仅作布尔注入 `authorization_present`。
5. **AI 不代专家授权** — ✅ 门禁只判定；双签/审核链/CI绿/回滚就绪/G6 授权均为输入，AI 不代签、不代授权。

**结论**：5 条最高红线逐条守约，激活态维持 **NO-GO**（`engineering_enabled=False`）。

---

## 5. 技术债（Technical Debt）

| 债 ID | 描述 | 严重度 | 状态 | 是否 3.4.1 引入 |
|---|---|---|---|---|
| **TD-3.4.1-1** | `local_ci.sh` 完整 pytest 集触发 WorkBuddy 运行环境 `[safe-delete]` 守卫（`pytest-cov` 并行模式 `combine` 删 `.coverage.*` → `SystemExit(1)`）。环境级，非代码问题 | 低 | open | 否（环境级） |
| **TD-3.4.1-2** | 24 条预存 `test_threshold_*` 仅在 `--cov` 并行模式失败（隔离污染），无 `--cov` 直接运行全 PASS（481 passed）。属历史预存问题 | 中 | open | 否（预存） |
| **TD-3.4.1-3** | 激活阈值（overall/freshness 分桶）仍沿用 TD-3.4.0-1，待治理确认 | 中 | open | 沿用 |
| **TD-3.4.1-4** | 知识域 G1–G6 与阈值域 G1–G6 待上层 `UnifiedActivationGate` 聚合（沿用 TD-3.4.0-2） | 中 | open | 沿用 |
| **TD-3.4.1-5** | 消费策略运行时强制（辅助引用须标 `pending_verification`、Deprecated 规避）待消费层落地（沿用 TD-3.4.0-3，高） | 高 | open | 沿用 |

> 说明：TD-3.4.1-1/2 直接关联 `local_ci.sh` 第 2 步 8/8 不可达成；二者均与 3.4.1 代码无关（隔离运行 30 新增 + 451 既有 = 481 全绿）。曾尝试 `.coveragerc`（`parallel=false`）修复，无效已回滚删除。

---

## 6. 下一阶段建议（Next Steps）

1. **还债优先**：处理 TD-3.4.1-1（safe-delete 守卫）/ TD-3.4.1-2（`--cov` 阈值测试隔离），使 `local_ci.sh` 8/8 可达；TD-3.4.1-5（消费层强制）高优。
2. **统一编排**：实现 `UnifiedActivationGate`，聚合阈值域 + 知识域 G1–G6，避免分裂（TD-3.4.1-4）。
3. **激活阈值确认**：治理侧确认 overall/freshness 分桶（TD-3.4.1-3），作为 G1 判定的量化输入。
4. **激活态放开（人工动作，非 AI 责任）**：真实双签 / 真实审核链 / G6 主理人书面授权 / CI绿确认 / 回滚就绪确认 全部到位后，由主理人在 `config` 显式置 `orchestrator.engineering_enabled=true` —— 本 Sprint 不代行。
5. **Stage 收口建议**：3.4.1 为激活层实现 DONE；建议以"激活层实现完成、激活态仍 NO-GO"标记 3.4 Sprint 子类收口，待人工授权动作解锁真实激活。

---

**END — Phase 3.4.1 DONE（实现交付，激活态 NO-GO 维持；5 红线守约；30 测试 PASS；7/8 网关绿）**
