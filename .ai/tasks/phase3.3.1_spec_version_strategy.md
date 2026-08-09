# Phase 3.3 Sprint 3.3.1 — 任务4：规范版本管理策略（Spec Version Strategy，pending_verification）

**阶段**：Phase 3.3 Engineering Knowledge Activation
**Sprint**：3.3.1 Real Engineering Knowledge Activation
**身份**：BOIP AI Chief Architect（策略编排，不执行数据变更）
**日期**：2026-08-01
**性质**：纯策略文档，不修改生产 `verified.json`、不触发迁移工具写入，全 pending_verification。

---

## 0. 目标与红线

**目标**：确立真实规范与阈值的**版本管理策略**，使 `schema_version` 与每条 `version` 语义化、历史可回溯、`deprecated` 可回滚。

**红线**：

| # | 禁止 | 说明 |
|---|---|---|
| 1 | 修改生产 `verified.json` | 本策略不触发任何写盘 |
| 2 | 开启 `engineering_enabled` | 全局仍 `false` |
| 3 | 输出 `engineering_approved` | 全 `pending_verification` |

---

## 1. schema_version（全局 schema 版本）

复用 `agents/engineering/thresholds/schema.py` 常量：

- `SCHEMA_VERSION_V1 = 1`：v1 自由文本 `source_ref`、无 `threshold_status` / `version` / `hash`（既有占位库 `verified.json` 现状）。
- `SCHEMA_VERSION_V2 = 2`：v2 结构化 `source_ref`（含 `hash`）+ `threshold_status` + `version` + 双签字段齐备（目标态）。
- `CURRENT_SCHEMA_VERSION = 2`：系统当前目标 schema。
- `entry_schema_version(entry)`：检测单条条目所处版本（v1 / v2），供迁移工具与加载器识别待升级条目。

**策略**：生产 `verified.json` 当前 `schema_version=1`。真实化时由 `threshold_migration.py` 统一升级至 v2（失败自动回滚，禁止静默升级）。

---

## 2. version（每条阈值语义化版本）

- 单条 `version`：语义化标识规范来源版本，如 `GB 50009-2012`（规范号-年号）。真实值由人工经规范 ingestion 登记，本策略不填。
- 多阈值聚合版本：同一 `applies_to` 方案下聚合多条阈值时，取「最小版本」或「联合版本字符串」约定（沿用 Phase 3.2.5-A open_decision，待主理人定）。
- `version` 与 `source_ref.edition` 应一致：edition 提供 C3 校验，version 提供人类可读语义；不一致须告警。

---

## 3. deprecated（失效拒绝加载）

复用 `ThresholdStatus.DEPRECATED` 与 `ThresholdGovernanceView`：

- `ThresholdStatus` 四态：`draft` / `review` / `verified` / `deprecated`。
- `is_loadable`：`deprecated` 拒绝加载（`can_enable_engineering` / 阈值加载器均不纳入）。
- 策略：规范更新或被新版本取代的阈值条目置 `deprecated`，**保留**供降级展示与审计，不物理删除。
- 版本冲突处理：同一 `applies_to` 方案出现版本冲突 → 旧版本置 `deprecated` 拒绝加载，标记 `pending_verification`，不静默采用。

---

## 4. rollback（回滚路径）

回滚依据 `agents/engineering/rollback.py` + `release/controller.py` 既有硬契约：

- **快照优先**：任何阈值版本变更前须 `snapshot`（全局门 `False` 永不旁路）。
- **deprecated 降级**：回滚即把新版本置 `deprecated`，恢复旧 `verified` 条目（旧条目保留不删）。
- **审核链不可篡改**：回滚动作本身落 `review_log` / `release_audit.jsonl`，确保全程可追溯。
- **迁移回滚**：`threshold_migration.py` 任一步失败自动回滚至 v1 占位态，不残留半升级数据。
- 策略：回滚保持 `engineering_enabled` 不变；回滚后仍须经 `release_precheck` 复核 G1-G6 方可重新放量。

---

## 5. 历史保留约定

- 所有历史版本条目保留在 `verified.json`（或后续分库），`deprecated` 态可查不可载。
- 审核链（`review_log` 四类 intake 事件）+ 发布审计（`release_audit.jsonl`）构成不可篡改的版本时间线。
- 版本冲突/回滚事件须在报告中显式记录，标记 `pending_verification` 直至人工确认。

---

## 6. 收口判定（本 Sprint）

本任务仅产出**版本管理策略**，不执行数据变更 → 计为 3.3.1 任务4 DONE（策略态）。真实 schema 升级留待 3.3.2/3.3.4 经 `threshold_migration.py` 执行。

*防编造声明：本文档所有 schema 常量、版本号、状态枚举均为代码既有定义引用或占位，非真实工程参数；真实版本值、规范内容均 pending_verification。*
