# Phase 3.4.2 — Unified Activation Gate（统一激活闸门）实现报告

- **日期**：2026-08-02
- **身份**：BOIP AI Chief Architect
- **性质**：实现（聚合式，只读/声明性，fail-closed，不复制既有规则）
- **红线遵守**：① `engineering_enabled` 保持 `False` ②未输出 `engineering_approved` ③未创建 `ReleaseApproval` ④未修改 `verified.json` ⑤AI 不代专家授权 — 全部 ✅

---

## 1. 架构变化

延续 Phase 3.4.0（激活准备架构）与 3.4.1（激活层实现），本 Sprint 将**知识域 / 阈值域 / 发布域**三类激活判定聚合为单一统一决策入口，避免在工程计算入口出现分散、语义不一致的闸门。

聚合拓扑（不复制规则，直接复用既有实现）：

```
UnifiedActivationGate.evaluate(repository, *, context, thresholds, review_log_path)
        │
        ├── 知识域  → KnowledgeActivationGate.can_activate_knowledge(repository, context)
        │            （复用 agents/engineering/knowledge/activation/gate.py，G1–G6）
        │
        ├── 阈值域  → can_enable_engineering(thresholds, ci_green, rollback_ready,
        │            │                         authorization_present, review_log_path, require_audit_chain)
        │            （复用 agents/engineering/gate/enable_gate.py，G1–G6）
        │            └─ 原因码 → 统一 G1–G6 标签映射
        │
        └── 发布域  → 本地 _evaluate_publishing(repository, context)
                     （复用统一 G1–G6 语义 + KnowledgeRepository 审计检查）

        ↓ 顶层安全不变量：load_engineering_enabled() is False
UnifiedActivationDecision(allowed, blocking_reasons, domain_results, detail)
```

消费接入（任务4，沿用 3.4.1 要求的「禁止未 Approved 知识进入工程计算」）：

```
UnifiedConsumptionController.evaluate(item, unified_decision)
   ├─ unified 不允许 → 任何知识都不得进入工程计算（unified_gate_blocked）
   └─ unified 允许  → KnowledgeConsumptionPolicy.classify(item)
        ├─ citable (Engineering_Approved)      → 权威工程依据（as_authoritative=True）
        ├─ auxiliary_only (三 Verified)          → 仅上下文（requires_pending_verification=True）
        └─ not_citable (Captured/Pending/Deprecated) → 禁止进入工程计算
```

---

## 2. 文件变化

### 2.1 新增

| 文件 | 作用 |
|------|------|
| `agents/engineering/gate/unified_activation_gate.py` | 统一闸门主体。定义 `UnifiedActivationDecision` / `DomainResult` / `ConsumptionDecision`；`UnifiedActivationGate.evaluate()` 聚合三域；`UnifiedConsumptionController` 接入消费策略 |
| `tests/agents/test_unified_activation_gate.py` | 13 用例（知识失败 / 阈值失败 / 授权失败 / CI 缺失 / 全通过模拟 / engineering_enabled 保持 False / 三域结构 / 消费接入 / 红线） |

### 2.2 修改

无（仅新增文件，未改动任何既有业务代码、配置、`verified.json`、仓库事件 schema）。

### 2.3 导出与复用

- 复用 `KnowledgeActivationGate.can_activate_knowledge`（`activation/gate.py`）——知识域规则零复制。
- 复用 `can_enable_engineering` + `GATE_G1..G6` 常量（`gate/enable_gate.py`）——阈值域规则零复制。
- 复用 `KnowledgeConsumptionPolicy`（`activation/consumption.py`）——消费分类零复制。
- 复用 `KnowledgeRepository.event_log` / `query` / `history` ——发布域审计链检查。

---

## 3. 测试与 CI 结果

### 3.1 新增测试（13 passed）

| 类 | 覆盖点 |
|----|--------|
| `TestUnifiedFailClosed` | 默认 fail-closed、`blocking_reasons` 非空、三域均含 G1–G6、`engineering_enabled` 不变 |
| `TestUnifiedKnowledgeFailure` | 空仓库 → 知识域 G1 失败，整体阻；阈值/发布域本应通过 |
| `TestUnifiedThresholdFailure` | draft 阈值 → 阈值域 G1/G2 失败，整体阻；知识/发布域本应通过 |
| `TestUnifiedAuthorizationFailure` | `authorization_present=False` → 三域 G6 全失败 |
| `TestUnifiedAllGreen` | 全条件模拟通过 → `allowed=True`、无原因、六门全绿；`engineering_enabled` 仍 False；无 `approved` 事件 |
| `TestUnifiedConsumption` | 闸门阻→禁止任何知识；Approved→权威；Verified→auxiliary+pending；未 Approved→禁止进入工程计算 |

### 3.2 全量回归

- `pytest tests/agents --no-cov`：**494 passed**（原 481 + 新增 13），**零回归**。
- Ruff（`unified_activation_gate.py` + 两个测试文件）：**All checks passed**（修 2 处 F401 后）。
- ESLint：**0 errors / 1 warning**（与 3.4.1 一致）。
- Jest：**29 passed · 93.15%**。
- Alembic：**up + down PASS**。
- Seed：**PASS**（`:memory:`）。
- 防编造扫描：**0 命中**；硬编码扫描：**0 命中**。

### 3.3 `local_ci.sh` 8/8 现状

**7/8 网关绿**，第 2 步（pytest 完整 `--cov` 运行）仍被环境级 `[safe-delete]` 守卫 + 24 条预存 `test_threshold_*` `--cov` 隔离失败阻断（均非本 Sprint 回归）。隔离运行 `tests/agents` 已 494 passed 全绿。详见技术债 TD-3.4.2-1/2。

---

## 4. 红线检查（逐条）

| # | 红线 | 验证方式 | 结果 |
|---|------|----------|------|
| 1 | 不开 `engineering_enabled=true` | `evaluate()` 只读 `load_engineering_enabled()`；测试断言前后均 `False` | ✅ |
| 2 | 不输出 `engineering_approved` | 全文 grep 仅 docstring 提及；无 `engineering_approved` 输出语句 | ✅ |
| 3 | 不创建 `ReleaseApproval` | 全文 grep 仅 docstring 引用；代码零 `ReleaseApproval` 实例化 | ✅ |
| 4 | 不修改 `verified.json` | 全程未 import / 读写 `verified.json` | ✅ |
| 5 | AI 不代专家授权 | 三域 G6 仅为布尔注入；`event_log` 仍硬拒 `approved` 事件 | ✅ |

---

## 5. 技术债

| ID | 描述 | 优先级 | 处置 |
|----|------|--------|------|
| TD-3.4.2-1 | `local_ci.sh` 第 2 步 pytest `--cov` 触发 WorkBuddy `[safe-delete]` 守卫（`SystemExit(1)`） | 中（环境级） | 待基建/CI 容器处理，与 3.4.1 同源 |
| TD-3.4.2-2 | 24 条预存 `test_threshold_*` 在 `--cov` 并行模式隔离失败（直接运行全 PASS） | 中 | 排查 pytest-cov 并行 cleanup 污染 |
| TD-3.4.2-3 | 统一闸门尚未接入 Engineering Agent / RAG 入口（需消费层强制落地） | 高 | 下一 Sprint 接 UnifiedConsumptionController |
| TD-3.4.2-4 | 激活阈值（overall / 权重）治理确认仍待主理人裁定（沿用 TD-3.4.0-3） | 中 | 治理会议确认 |

---

## 6. 下一阶段建议

1. **还债 TD-3.4.2-1/2**：使 `local_ci.sh` 真正可达 8/8（环境守卫 + cov 隔离）。
2. **消费层强制（TD-3.4.2-3，高优）**：在 Engineering Agent / RAG 检索入口接入 `UnifiedConsumptionController`，强制 `pending_verification` 标注与未 Approved 规避。
3. **真实激活解锁**：由主理人人工置 `engineering_enabled=true` + G6 书面授权（ReleaseApproval）完成；AI 仅提供判定容器。
4. **发布域深化**：当前发布域为统一 G1–G6 复用实现，后续可按发布/放行语义细化（如灰度比例、回滚演练 dry-run 证据）。

---

## 交付清单

- `.ai/reviews/phase3.4.2_unified_activation_gate_report.md`
- `agents/engineering/gate/unified_activation_gate.py`
- `tests/agents/test_unified_activation_gate.py`
- SSOT `task_status.phase_3_1.phase_3_4["3.4.2"]` DONE 块
- `roadmap_v4.md` §1/§2/§3/§5 更新

**激活态维持 NO-GO**（`engineering_enabled=False`；三域 G1–G6 设计与实现完成但默认全 FAIL，缺真实双签/审核链/G6授权/CI绿确认/回滚就绪）。
