# BOIP Phase 3.2 Sprint 3.2.5-D 发布检查清单：首次工程灰度最终准备（Engineering Gray Release Final Readiness）

- **阶段**：Phase 3.2 Sprint 3.2.5-D
- **身份**：BOIP AI 工程发布治理负责人（Engineering Release Governance Lead）
- **性质**：首次工程灰度（`wind_pressure` 风压分析接口）发布前**最终就绪检查**——**非开启 `engineering_enabled`、非输出 `engineering_approved`、非写入真实生产 approved 记录、不扩大灰度范围**，全部 `pending_verification`。
- **日期**：2026-07-31

---

## 0. 摘要与放行判定（结论先行）

本清单对 `wind_pressure` 首次灰度发布前的最终状态做逐项核对。结论分层：

1. **能力就绪（Capability Ready）**：灰度发布基础设施（Enable Gate / Gray Release / Approved Monitor / Rollback）已在 Sprint 3.2.5-B 落地并 CI 8/8 全绿（435 passed @ 89.21%），六项门禁（G1~G6）的逻辑与默认值均符合"默认拒绝"红线；真实回滚、真实监控写入、真实审核链校验均已被测试覆盖。
2. **生产未达标（Release Blocked at Production）**：当前生产 `thresholds/verified.json` 仍为 schema_version 1 的占位态（`thresholds` 为 6 个字符串标识符 E-TH-01~06，无真实条目 / 无 `value` / 无双签 / 无 `source_ref`），`engineering_enabled=false`。因此 G1（阈值治理）、G2（双签）、G6（主理人书面授权）在生产侧**均未满足**，`can_enable_engineering()` 默认返回 `(False, reasons)`。
3. **放行判定**：**当前不可开启 `engineering_enabled`**。本清单仅确认"程序与闸门就绪、且闸门正确默认拒绝"；真实放行须由主理人单独书面授权（G6，独立于 3.2.4 双签主体），并在授权后满足 G1-G6 全绿，方可进入 3.2.5 实施（enabled 开启灰度）。详见 §5。

> 红线重申：本清单不开启 `engineering_enabled`、不输出 `engineering_approved`、不写入真实生产 approved 记录、不扩大灰度范围（`wind_pressure` 之外的硬件 / 玻璃安全 / 型材 / 五金 / 安装风险接口一律不在本次范围）。

---

## 1. 任务1：Release Checklist（G1-G6 逐项检查）

门禁定义源自 `agents/engineering/gate/enable_gate.py`（`can_enable_engineering`）：G1 阈值治理 / G2 双签 / G3 CI / G4 审核链 / G5 回滚就绪 / G6 主理人书面授权。所有外部条件默认值取"不满足"，从而默认 `(False, reasons)`。

| 门禁 | 名称 | 要求 | 验证方法 | 当前生产状态 | 是否放行阻塞 |
|------|------|------|----------|--------------|--------------|
| **G1** | threshold_governance（阈值治理） | 待启用阈值 `threshold_status=verified` + 结构化 `source_ref` 完整 + 双签齐全（`governance_status` ok） | `governance_status(entry)` 全 True | ❌ 生产 `verified.json` 为占位态，E-TH-01 至 E-TH-03 无真实条目、`status` 非 verified | **阻塞** |
| **G2** | dual_sign（双签） | 待启用阈值 `mgmt_signed` AND `expert_signed` 全齐（`is_fully_verified`） | `is_fully_verified(entry)` 全 True | ❌ 生产无 `verified_by/at`、`expert_verified_by/at` | **阻塞** |
| **G3** | ci_status（CI 全绿） | 发布时 CI 8/8 全绿、覆盖率达标 | 运行 `bash scripts/ci/local_ci.sh` | ⚠️ 能力基线 435 passed @ 89.21% 已就绪；**真实发布须重新运行并确认绿** | 发布时须复核（当前能力绿，不代表本次发布已授权） |
| **G4** | audit_chain（审核链完整） | `review_log` 链式无断裂 / 无损坏行 | `read_log` + `_chain_intact` | ⚠️ 生产 `review_log` 未携带 E-TH-01 至 E-TH-03 真实双签链（演练产物落临时文件，生产零改动）；空链视为完整，但无真实签署链则可佐证 G1/G2 未过 | 生产侧随 G1/G2 满足而满足 |
| **G5** | rollback_ready（回滚就绪） | 回滚处理就绪（`RollbackHandler` 可用） | `RollbackHandler(cfg).snapshot()/close_*/restore()` | ✅ 能力就绪（测试覆盖接口级关闭 / 全局熔断 / 自动快照 restore） | 不阻塞（能力已具备） |
| **G6** | authorization（主理人书面授权） | 主理人单独书面授权到位（独立于双签主体） | 注入 `authorization_present=True` + 书面授权记录 | ❌ 无书面授权记录 | **阻塞** |

**判定脚本**（不真实激活，仅逻辑）：无注入时 `can_enable_engineering()` → `(False, [G1, G2, G3, G4?, G5, G6])`；即便 G1/G2 经 3.2.4 实施满足，`engineering_enabled` 仍由 `config.yaml` 全局闸门控制（默认 false），`is_interface_gray_allowed` 全局 false 时恒 False（双重保险，不可绕过，见 `test_cannot_bypass_engineering_enabled`）。

### 1.1 门禁正向分支（逻辑验证，非真实激活）
内存注入 G1~G6 全绿（`thresholds` 全 verified + `ci_green=True` + `rollback_ready=True` + `authorization_present=True`）→ `can_enable_engineering()` 返回 `(True, [])`，**仅证明判定逻辑正确**，不翻转 `config.yaml`、不写 `approved_monitor`、不输出 `approved`。真实激活须主理人显式置 `orchestrator.engineering_enabled=true` 且经 G6 授权记录。

---

## 2. 任务2：Wind Pressure 灰度准备（首个接口）

**首个接口确认**：`wind_pressure`（风压分析）——依灰度准备设计锁定（首个接口选择见设计规范）：无上游工程依赖，所需阈值 E-TH-01 / E-TH-02 / E-TH-03 属 Engineering 侧可独立双签，不依赖 D-TH 双签路径决策。`INTERFACE_THRESHOLD_MAP["wind_pressure"] = ("E-TH-01", "E-TH-02", "E-TH-03")`。

**E-TH-01 / E-TH-02 / E-TH-03 四维度当前状态**（基于生产 `thresholds/verified.json` 实测）：

| 维度 | 期望（发布前须满足） | 当前生产状态（`schema_version=1` 占位） | 就绪 |
|------|----------------------|------------------------------------------|------|
| **治理（Governance）** | `threshold_status=verified` + 结构化 `source_ref` 完整 | ❌ 无真实条目；`thresholds` 仅为字符串 `"E-TH-01"` 等占位，无 `threshold_status` / `version` / 结构化 `source_ref` | 否 |
| **双签（Dual Sign）** | `verified_by`+`verified_at`（主理人）+ `expert_verified_by`+`expert_verified_at`（专家），SoD（`verified_by ≠ expert_verified_by`） | ❌ 无任一签字位 | 否 |
| **source_ref（溯源）** | `ThresholdSourceRef` 结构化且 `is_complete()`（standard + clause 双齐），v2 含 `hash` | ❌ 无 `source_ref`（占位文件仅声明 pending_verification） | 否 |
| **review_log（审核链）** | 四步链路 `intake_submit→review_approve→expert_recheck→intake_verified`，`prev_event_id` 链式无断裂 | ⚠️ 生产 `review_log` 无 E-TH-01 至 E-TH-03 真实签署链（3.2.4-G 演练产物落临时文件，生产零改动） | 否（待 3.2.4 实施真实录入产生） |

> 说明：上述"否/否/否/否"并非缺陷，而是**真实化尚未执行**的如实记录。3.2.4-F（录入工作流）与 3.2.4-G（录入演练）已验证"能力成立"，但真实数据须由人工显式调用 `ThresholdIntakeWorkflow` / `run_intake_drill` 提供真实 `value` / `unit` / `source_ref` / 签字人，并经真实 `review_log` 落地后方可满足 G1/G2/G4。

---

## 3. 任务3：Monitor 最终检查（approved_monitor）

实现：`agents/engineering/approved_monitor.py`（`ApprovedRecord` + `append_approved_record` / `load_approved_records`，append-only）。

**字段最终核对**（每次 `engineering_approved` 出现时写入 `approved_monitor.jsonl`，仅记录引用/标识符，**绝不写入真实工程数值**）：

| 字段 | 含义 | 最终检查结论 |
|------|------|--------------|
| `schema_version` | 监控记录 schema 版本（`ApprovedRecord.schema_version = "1.0"`） | ✅ 常量固定，与 `ApprovedRecord.to_dict()` 对齐 |
| `interface` | 被批准的接口标识（如 `wind_pressure`） | ✅ 仅标识符，无数值 |
| `threshold_version` | 阈值版本（如 `1.0`） | ✅ 仅版本字符串 |
| `sign_off_id` | 审核通过标识（由 `review_log.compute_sign_off_id` 确定性派生，前 16 位 sha256） | ✅ 派生自签名元数据，可复核比对，防篡改 |
| `review_log_ref` | 关联审核链锚点（`event_id` / 末条事件引用） | ✅ 指向 `review_log`，可溯源 |

附加字段：`error`（异常/不一致标记，可选）、`timestamp`（UTC ISO8601）。字段集合经 `test_approved_monitor_write_and_read` 断言 = `{schema_version, interface, threshold_version, sign_off_id, review_log_ref, error, timestamp}`，**确认无真实工程数值字段**。

**当前状态**：生产 `approved_monitor.jsonl` 为空（未发生过真实 approved）；append-only 不可篡改；损坏行由 `load_approved_records` 跳过（`test_approved_monitor_skips_corrupt`）。

---

## 4. 任务4：Rollback 演练方案（恢复 pending_verification）

实现：`agents/engineering/rollback.py`（`RollbackHandler`）。不变量：回滚**仅翻转灰度配置开关**（`GrayReleaseEntry.enabled` / `GrayReleaseConfig.default_enabled`），**不修改任何历史 `review_log`**（append-only 不可篡改）；恢复语义 = 相关接口不再被放行、结果回落 `pending_verification`。

**三种验证场景**（均已被 `tests/agents/test_gray_release.py` 覆盖，逻辑验证不真实激活）：

| 场景 | 操作 | 期望结果 | 对应测试 |
|------|------|----------|----------|
| **接口关闭（Interface Close）** | `handler.snapshot()` → `handler.close_interface("wind_pressure")` | 该接口 `is_interface_gray_allowed(..., engineering_enabled=True)` 由 True 变 False（回落 pending） | `test_rollback_interface_restores_pending` |
| **全局关闭（Global Close / 熔断）** | `handler.close_global()` | 全部接口拒绝工程审核（回落 pending）；`restore()` 后恢复 | `test_rollback_global_close_and_restore` |
| **恢复 pending（Restore）** | `handler.restore()`（优先用显式 `snapshot`，否则自动快照） | 从快照恢复开关；结果重新可被放行（仍受 G1-G6 + 全局闸门约束） | `test_rollback_auto_snapshot` |

**发布前回滚演练步骤（建议真实发布时执行一次 dry-run）**：
1. 载入生产 `gray_release.json`（或内存 `GrayReleaseConfig`），`snapshot()` 保存当前开关态；
2. 触发 `close_interface("wind_pressure")` → 验证风压接口结果回落 `pending_verification`、校验器返回 `verification_status="pending_verification"`、`sign_off_id=None`；
3. 触发 `close_global()` → 验证全局熔断，所有接口回落 pending；
4. 触发 `restore()` → 验证开关恢复至 snapshot 态；
5. 全程确认 `review_log` 无新增/修改行（回滚不变量）。

---

## 5. 放行判定结论与下一步（汇总至 readiness 报告）

- **能力就绪**（G3/G5 + Gate/Gray/Monitor/Rollback 全链路测试覆盖）→ ✅
- **生产未达标**（G1/G2/G6 未满足）→ ❌，**当前禁止开启 `engineering_enabled`**
- **下一步**：主理人单独书面授权（G6，SoD 独立于 3.2.4 双签主体）→ 由人工以真实数据调用 3.2.4-F/G 录入工作流完成 E-TH-01 至 E-TH-03 真实化（满足 G1/G2/G4）→ 重新运行 `local_ci.sh` 确认 G3 绿 → 主理人置 `orchestrator.engineering_enabled=true` 并经 G6 授权记录 → 进入 3.2.5 实施（per-interface 灰度放量）。

**本清单为"最终就绪检查"文档，未执行任何真实录入、未开启 `engineering_enabled`、未输出 `engineering_approved`、未写入真实生产 approved 记录、未扩大灰度范围。全部 `pending_verification`。**
