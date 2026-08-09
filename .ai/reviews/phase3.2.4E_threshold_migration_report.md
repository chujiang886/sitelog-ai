# BOIP Phase 3.2 Sprint 3.2.4-E — 阈值治理迁移基础设施实施就绪报告

**身份**：BOIP AI 工程治理架构负责人
**日期**：2026-07-31
**性质**：真实阈值接入（3.2.4 实施）前的「迁移与验证能力」落地——**本阶段不填写真实工程参数、不修改 verified.json 真实 value、不设置 verified=true、不开 engineering_enabled、不输出 engineering_approved**，全部保持 `pending_verification`。本文档仅记录迁移工具、schema v2、source_ref validator 的实现与测试，待主理人书面授权后方可进入 3.2.4 实施（verified.json 真实化）。

---

## 0. 目标达成

把 3.2.4-D 实施方案中的「v1→v2 迁移」「source_ref 校验」「D-TH 双签字段补齐」从设计落地为可执行的代码与测试，使真实阈值接入具备：结构升级能力、引用完整性校验能力、失败自动回滚能力、零破坏向后兼容能力。

---

## 1. 任务交付（对应任务1~5）

### 任务1：Schema v2 实现（扩展 `agents/engineering/thresholds/schema.py`）
- 新增 `SCHEMA_VERSION_V1 / SCHEMA_VERSION_V2 / CURRENT_SCHEMA_VERSION` 常量；
- `ThresholdSourceRef` 新增 `hash` 字段（v2 内容 sha256 摘要，禁止手写），`from_raw` / `as_dict` 同步支持；
- 新增 `entry_schema_version(entry)`：依据 `threshold_status` / `version` / 结构化 `source_ref` 检测 v1 / v2；
- 新增 `ensure_d_th_expert_sign_fields(entry)`：为 D-TH 补 `expert_verified_by/at`（置 `None`，**禁止自动填充**）；
- 既有 `ThresholdStatus` / `ThresholdGovernanceView` / `governance_status` 语义**零破坏**，v1 全兼容。

### 任务2：Migration 工具（新增 `agents/engineering/threshold_migration.py`）
- `migrate_thresholds(input, output, snapshot_dir, *, dth_decision)`：v1→v2 结构升级；
- **M1 快照**：对输入生成内容哈希快照（`verified.<hash>.v1.json`），只读输入；
- **不修改原文件**：读写路径严格分离，输入文件哈希前后一致（测试断言）；
- **M2~M4**：顶层 `schema_version` 1→2、`threshold_status=draft`、`version=1.0.0`（缺省降级）；
- **M5**：`source_ref` 自由文本 → 结构化（补 `hash=""`）；
- **M6**：D-TH 双签决策 A → 补专家签位（null）；决策 B → 不动结构；
- **失败自动回滚**：解析/写入异常 → 删除残存输出、保留快照、`status=rolled_back`；
- **原子写入**：先写临时文件、回解析校验、再 `replace`，避免半截输出；
- 返回 `MigrationReport`（status / snapshot_path / 迁移计数 / per_threshold / errors），含 `as_dict()`。

### 任务3：source_ref validator（新增 `agents/engineering/thresholds/source_ref_validator.py`）
- `validate_source_ref(ref, *, content=None) -> (ok, reason)`：覆盖 C1-C6；
- C1 标准号（非空非占位）/ C2 条款号 / C3 版本（4 位年份或显式版本）/ C4 链接（http(s)）/ C5 内容哈希（64 位十六进制 sha256，可选比对 `content`）/ C6 完整性（C1+C2）；
- 缺失即返回**明确 reason**（`SOURCE_REF_*_MISSING` / `_INVALID` / `_MISMATCH`），供测试与日志追溯。

### 任务4：D-TH 双签字段兼容
- schema 层 `ensure_d_th_expert_sign_fields` 补齐 `expert_verified_by/at = None`；
- `ThresholdGovernanceView.from_entry` 对真实 D-TH（设计侧）解析为 `None`，治理态 DRAFT 不通过；
- 迁移（决策 A）后 D-TH 输出条目带 null 专家签位，无自动填充（测试断言）。

### 任务5：测试（新增 `tests/agents/test_threshold_migration.py`）
覆盖八要点：v1 读取 / v2 读取 / migration 成功 / migration 失败 rollback / source_ref 缺失 / hash 失败 / D-TH 双签兼容 / engineering_enabled=false 保护；另补充 noop（已 v2）/ source_ref 字典分支 / 非 Mapping 条目跳过 / 决策 B / 报告序列化 / 默认快照目录回滚。

---

## 2. 质量门禁（local_ci 8/8）

| 阶段 | 结果 |
|---|---|
| [1/8] Ruff lint | 通过 |
| [2/8] Pytest 覆盖率 | 415 passed，**Total coverage 88.92%**（≥88.75%） |
| [3/8] 前端 ESLint | 通过 |
| [4/8] 前端 Jest | 29 passed |
| [5/8] Alembic 升降级 | 通过 |
| [6/8] Seed | 通过 |
| [7/8] 防编造扫描 | 0 命中 |
| [8/8] 硬编码扫描 | 0 命中 |

> 覆盖率由 3.2.5-B 的 88.75% 提升至 88.92%（新增代码全被测试覆盖，仅异常守卫分支未覆盖，属合理）。

---

## 3. 红线守约

- 未填真实工程阈值（所有 `value=null`，source_ref 占位）；
- 未改 `verified.json` 真实 value（迁移只写独立输出，原文件哈希不变）；
- 未置 `verified=true`（迁移条目 `threshold_status=draft`、`verified=false`）；
- 未开 `engineering_enabled`（门禁默认拒绝 + 校验 enabled=False 恒 pending）；
- 未输出 `engineering_approved`（迁移不构成任何转正）；
- 全 `pending_verification`；防编造 / 硬编码扫描 0 命中。

---

## 4. 待主理人定夺的开放项

- **D-TH 双签最终采纳**：本实现按方案 A 方向（补专家签位）落地能力，但最终是否采纳 A 仍须书面授权；
- **source_ref.hash 算法**：采用 sha256 内容摘要，实施时由脚本计算比对，禁止手写；
- **真实化授权与 enabled 授权分离（SoD）**：迁移 ≠ 启用，真实化后仍需 3.2.5-B 门禁 G1~G6 全绿 + 主理人单独书面授权方可 `engineering_enabled=true`；
- **首个真实化范围**：建议先 E-TH-01/02/03（首个灰度接口所需，Engineering 侧可独立双签），不阻塞 D-TH 决策。

---

## 5. 下一步

等待主理人审核 + 单独书面授权后，方可按 3.2.4-D 迁移步骤 M1-M8 与 M7/M8（写 `review_log` + 跑门禁）落地 3.2.4 实施（verified.json 真实化），以及 3.2.5 实施（engineering_enabled 开启灰度）。**本阶段已停止，未进入真实阈值录入。**

---

**本阶段交付边界**：新增 `agents/engineering/thresholds/schema.py` 扩展、`agents/engineering/thresholds/source_ref_validator.py`、`agents/engineering/threshold_migration.py`、`tests/agents/test_threshold_migration.py`；零既有逻辑破坏、红线全程守约、防编造/硬编码扫描 0 命中、local_ci 8/8 全绿 415 passed@88.92%。
