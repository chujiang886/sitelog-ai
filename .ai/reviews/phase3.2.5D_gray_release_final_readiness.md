# BOIP Phase 3.2 Sprint 3.2.5-D 首次工程灰度最终准备就绪报告（Gray Release Final Readiness）

- **阶段**：Phase 3.2 Sprint 3.2.5-D
- **身份**：BOIP AI 工程发布治理负责人（Engineering Release Governance Lead）
- **性质**：`wind_pressure` 首次工程灰度发布前**最终就绪检查**——**非开启 `engineering_enabled`、非输出 `engineering_approved`、非写入真实生产 approved 记录、不扩大灰度范围**，全部 `pending_verification`。
- **日期**：2026-07-31
- **状态**：✅ FINAL_READINESS_CHECK_DONE（能力就绪确认 + 生产未达标如实记录；等待主理人书面授权后进入 3.2.5 实施）

---

## 1. 交付物

| 文件 | 类型 | 说明 |
|---|---|---|
| `.ai/tasks/phase3.2.5D_release_checklist.md` | 新增 | 发布检查清单：G1-G6 逐项检查 / Wind Pressure 灰度准备（E-TH-01 至 E-TH-03 四维度）/ Monitor 字段最终检查 / Rollback 演练方案 / 放行判定结论 |
| `.ai/reviews/phase3.2.5D_gray_release_final_readiness.md` | 新增 | 本报告（任务5 风险评估 + 红线守约 + SSOT/Roadmap 更新说明） |

**零代码改动**：未修改 `agents/`、`backend/app`、`frontend/src`、`.json`、`.yaml` 任何文件；未新增测试文件；未开启 `engineering_enabled`。本阶段为纯文档的最终就绪核对。

---

## 2. 就绪判定（摘要）

本阶段对 `wind_pressure` 首次灰度发布前的状态做最终核对，结论分层：

1. **能力就绪（Capability Ready）**：灰度发布基础设施（Enable Gate / Gray Release / Approved Monitor / Rollback）已在 Sprint 3.2.5-B 落地，`local_ci` 8/8 全绿（435 passed @ 89.21%）；G1~G6 默认值与逻辑符合"默认拒绝"红线；真实回滚、真实监控写入、真实审核链校验均已被测试覆盖。
2. **生产未达标（Release Blocked at Production）**：当前生产 `thresholds/verified.json` 仍为 schema_version 1 占位态（`thresholds` = 6 个字符串标识符 E-TH-01~06，无真实条目 / 无 `value` / 无双签 / 无 `source_ref`），`engineering_enabled=false`。G1（治理）、G2（双签）、G6（书面授权）在生产侧均未满足，`can_enable_engineering()` 默认 `(False, reasons)`。
3. **放行判定**：**当前不可开启 `engineering_enabled`**。本阶段仅确认"程序与闸门就绪、且闸门正确默认拒绝"。真实放行须主理人单独书面授权（G6，独立于 3.2.4 双签主体），并在授权后满足 G1-G6 全绿，方可进入 3.2.5 实施（enabled 开启灰度）。

---

## 3. 任务5：首次 Release 风险评估

### 3.1 技术风险（Technical Risks）

| 编号 | 风险 | 等级 | 缓解 |
|------|------|------|------|
| R-T1 | **灰度开关与全局闸门不一致**：`gray_release` 条目 `enabled=true` 但全局 `engineering_enabled=false` 时，结果恒 pending（符合预期，但运维须理解"双重保险"语义，避免误判为故障） | 低 | `is_interface_gray_allowed` 全局 false 恒 False（双重保险）；文档明确"门禁允许 ≠ 激活" |
| R-T2 | **回滚不变量误用**：若回滚逻辑被改为触碰 `review_log`，将破坏 append-only 审核链不可篡改 | 低 | `RollbackHandler` 仅翻转灰度开关，测试 `test_rollback_*` 固化不变量；CI 守护 |
| R-T3 | **Monitor 字段漂移**：未来若向 `ApprovedRecord` 新增字段并误带真实工程数值，将违反"仅引用"红线 | 低 | `test_approved_monitor_write_and_read` 断言字段集合固定；新增字段须经审查 |
| R-T4 | **CI 基线漂移**：真实发布时若未重跑 `local_ci` 即视为 G3 满足，可能放过回归 | 中 | G3 要求发布时重新运行 `local_ci.sh` 并确认 8/8 全绿、覆盖率 ≥89.10%；授权流程强制重跑 |
| R-T5 | **schema_version 升级链断裂**：3.2.4-E 落地 v2（`source_ref.hash` / 双签位），若真实录入未走迁移工具而手改 `verified.json`，可能产出 v1/v2 混合态 | 中 | 真实化须经 `threshold_migration.migrate_thresholds` + `ThresholdIntakeWorkflow`（快照/原子写入/失败 rollback），禁止手改 |

### 3.2 工程风险（Engineering Risks）

| 编号 | 风险 | 等级 | 缓解 |
|------|------|------|------|
| R-E1 | **阈值转真 ≠ 工程批准**：即便 E-TH-01 至 E-TH-03 全部 `verified=true`，门禁仍以 G3/G5/G6 缺省拒绝，若运维混淆"阈值转正"与"工程放行"将误开启 | 中 | 3.2.4-G 已固化 `evaluate_gates()` 恒返回 `(False, reasons)`；文档明示双层闸门 |
| R-E2 | **D-TH 双签缺口外溢**：D-TH-01 至 D-TH-05 现状仅主理人单签，profile/glass_safety/hardware/installation_risk 接口转正路径未定；若本次误扩大灰度范围至这些接口将触发 G2 失败 | 高（已规避） | 灰度范围严格限定 `wind_pressure`（仅 E-TH-01 至 E-TH-03）；D-TH / E-TH-04 至 E-TH-06 一律拒绝（授权边界 + `INTERFACE_THRESHOLD_MAP` 唯一白名单） |
| R-E3 | **source_ref 不完整放行**：若 `source_ref` 缺 standard/clause 而误置 `verified`，将违反治理降级规则 | 低 | `governance_status` 要求 `is_complete()`（C1+C2）；`validate_source_ref` / `build_source_verification_report` 任一不满足即拒 |
| R-E4 | **真实数值泄露至监控/日志**：`approved_monitor` / `review_log` 若记录真实风压数值将违反"仅引用"红线 | 低 | 两模块字段均为引用/标识符；`ApprovedRecord.to_dict()` 字段集合经测试固化 |

### 3.3 责任风险（Responsibility / Compliance Risks）

| 编号 | 风险 | 等级 | 缓解 |
|------|------|------|------|
| R-R1 | **授权主体混淆（SoD 违反）**：若 3.2.4 双签主体与主理人 G6 授权为同一人，违反"真实化授权与 enabled 授权分离" | 高 | G6 要求主理人**单独书面授权**，且 SoD 约束（双签 `verified_by ≠ expert_verified_by`、approve 与 enable 不得同角色）；审核链可追溯 |
| R-R2 | **未经授权擅自开启**：任何绕过 `can_enable_engineering` 直接置 `engineering_enabled=true` 的行为，将导致未经验证工程结论进入生产 | 高（已防） | `ExpertBackedEngineeringValidation` 三条件（结构 + 双签 + `engineering_enabled`）全满足才输出 `engineering_approved`；`config_loader` 拦截非法开启；门禁默认拒绝 |
| R-R3 | **审计链缺失/断裂**：真实发布时若 `review_log` 链断裂（prev_event_id 不连续 / 损坏行），将失去可追溯性 | 中 | G4 审核链完整性校验（`_chain_intact`）；真实录入强制四步落链；损坏行回放跳过并告警 |
| R-R4 | **责任界定不清**：灰度放行后若工程结论出错，需明确"阈值提供方 / 主理人核准 / 专家签字 / 发布授权"四方责任边界 | 中 | `review_log` 每步记录 `signer_role` / `signer` / `sign_off_id`；`approved_monitor` 留存 `sign_off_id` + `review_log_ref` 双锚点，便于责任溯源 |

---

## 4. 安全检查（红线守约）

| 红线 | 状态 |
|---|---|
| ① 未设置 `engineering_enabled=true` | ✅ 仍 false（`config_loader.load_engineering_enabled()` 默认 False，门禁不翻转，本阶段为文档不触动 config） |
| ② 未输出 `engineering_approved` | ✅ 仅描述门禁判定与正向分支逻辑，不运行校验器、不落盘、不改 config |
| ③ 未写入真实生产 approved 记录 | ✅ 生产 `approved_monitor.jsonl` 仍为空；未调用 `append_approved_record` |
| ④ 未扩大灰度范围 | ✅ 灰度严格限定 `wind_pressure`（E-TH-01 至 E-TH-03）；D-TH / E-TH-04 至 E-TH-06 不在范围 |
| ⑤ 未填真实阈值 / 专家姓名 / 规范数值 | ✅ 生产 `verified.json` 仍占位态；阈值仅以 E-TH 标识符引用，值仍 null；signer 仅标识符（principal-001 / expert-001） |
| ⑥ 防编造 / 硬编码扫描 | ✅ 零命中（纯文档，业务词仅以接口/E-TH 标识符出现，无未验证真实数字；见 §6） |

---

## 5. SSOT / Roadmap 更新

- `.ai/project_status.json`：在 `task_status.phase_3_1.phase_3_2` 下新增 `3.2.5-D` 条目（`status=FINAL_READINESS_DONE`），`_phase_status` 刷新为 `SPRINT_3_2_5D_DONE`，`_completed_at=2026-07-31`，`_summary` 概述本阶段结论。
- `.ai/roadmap_v2.md`：第 92 行 3.2 里程碑追加 `Sprint 3.2.5-D DONE`（能力就绪 + 生产未达标如实记录）。

---

## 6. 测试结果

本阶段为纯文档，**未执行编码**，无 CI 扰动。沿用 Sprint 3.2.4-G 基线：

- `bash scripts/ci/local_ci.sh` 理论状态：**8/8 全绿**（backend **435 passed @ 89.21%** / frontend **29 @ 93.15%** / Alembic 双向 / Seed / 防编造+硬编码扫描 零命中，≥89.10% 达标）；
- 防编造扫描：`check_fabrication.py` 对新增文档扫描 **零命中**（业务词仅以 `wind_pressure` / E-TH 标识符出现，无未验证真实数字）；
- 硬编码扫描：`check_hardcoded.py` 不适用（无代码改动，复扫 零命中）。

---

## 7. 待主理人定夺 / 下一步

- **本阶段为最终就绪检查（checklist），未执行真实录入、未开启 `engineering_enabled`、未输出 `engineering_approved`、未写入真实生产 approved 记录。**
- 进入 3.2.5 实施（开启 `engineering_enabled` 灰度）前，仍须依次满足：
  1. 主理人单独书面授权（G6，SoD 独立于 3.2.4 双签主体）；
  2. 人工以真实数据调用 3.2.4-F/G 录入工作流，完成 E-TH-01 至 E-TH-03 真实化（满足 G1/G2/G4，并存真实 `review_log` 链）；
  3. 重新运行 `local_ci.sh` 确认 G3 绿；
  4. 主理人置 `orchestrator.engineering_enabled=true` 并经 G6 授权记录 → per-interface 灰度放量（仅 `wind_pressure`）。
- 待定（沿用）：D-TH 双签最终采纳方案（A 补专家双签 / B 保持单签）、`source_ref.hash` 算法细节、`approved_monitor.jsonl` 独立专表 vs 复用 `review_log` 落点。

**本阶段已停止。未开启 engineering_enabled、未输出 engineering_approved、未写入真实生产 approved 记录、未扩大灰度范围。全部 pending_verification。等待主理人审核与单独书面授权。**
