# BOIP 研发路线 V5（roadmap_v5.md）

- **生成**：2026-08-02
- **身份**：BOIP AI Chief Architect（Phase 3.5.0 人工激活治理与受控发布准备）
- **性质**：Phase 3.5.0 = **治理流程设计为主 + G4 命名对齐（已落地代码改动）+ CI 债务根因验证**；不翻转 `engineering_enabled`、不输出 `engineering_approved`、不代建 `ReleaseApproval`、不代专家/主理人签署或授权；激活态维持 NO-GO。
- **依据**：`.ai/project_status.json`（SSOT，current_roadmap_version=V5）、`.ai/reviews/phase3.5.0_human_activation_governance_report.md`、`.ai/reviews/phase3.4.5_activation_readiness_verification_report.md`
- **权威声明**：本文件取代 `roadmap_v4.md`，为 Phase 3.5.0 起的唯一研发路线；roadmap_v4.md 保留为 Phase 3.4 历史归档。

---

## 1. 当前真实状态（Phase 3.5.0 人工激活治理态）

| 维度 | 真实状态 |
|---|---|
| 阶段 | **Phase 3.2 CLOSED** → **Phase 3.3 DONE** → **Phase 3.4 DONE（3.4.0~3.4.5 全 ✅）** → 🟢 **Phase 3.5.0 Human Activation Governance DONE（2026-08-02：G2 双签 / G4 审核链 / G6 授权 / Rollback Dry Run 流程设计完成；G4 命名对齐代码已落地；CI 债务根因锁定，人类终端 local_ci 8/8 实证可达；红线 5 条 0 违规）** |
| 治理流程 | **G2 双签**：`ThresholdIntakeWorkflow` 四步（submit→review→expert_recheck→verified），SoD 硬校验（专家≠主理人，须先审核后复核）；**G4 审核链**：`review_log` 含 `submit / review / expert_recheck / verified` 四类且链式无断裂（`REQUIRED_REVIEW_ACTIONS` 已对齐规范名）；**G6 授权**：`EngineeringReleaseApproval` 七字段，人工创建，AI 仅 `validate_release_approval` 校验；**Rollback Dry Run**：`RollbackHandler` snapshot/close/restore + `controller` disable/rollback/restore |
| 红线 | `engineering_enabled=false`；无任何 `engineering_approved` 输出；`E-TH-01/02/03` 真实 `value` 仍 `null`（pending_verification）；`append_approval_record(` 全仓仅定义无 AI 调用方 |
| CI | **人类终端 `local_ci.sh` 8/8 绿**：672 passed / 90.40% coverage / EXIT=0（Ruff/pytest/ESLint/Jest/Alembic/Seed/防编造/硬编码全绿）；agent 运行时仅受 `[safe-delete]` 守卫（单轮>50 删除→SystemExit）阻断，**非回归**；3.4.5 关于 threshold 隔离失败的误判已更正 |
| 激活态 | **NO-GO 维持**：六闸门（G1-G6）默认全 FAIL；`engineering_enabled=False`；人工激活须主理人线下补齐真实双签 + 审核链 + G6 授权 + 显式置 `engineering_enabled=true` |
| 未完成（人工动作） | 真实双签执行 / 真实审核链填充 / G6 授权创建 / 真实 E-TH 数值录入 均 pending_verification |

**红线（不可逾越）**：任何无据行业数字必须标 `pending_verification`；工程参数未经专家签字不得转正；Phase 3.5.0 不代建 `ReleaseApproval`、不开 `engineering_enabled`、不输出 `engineering_approved`、不代专家/主理人签署或授权。

---

## 2. Phase 3.5.0 路线（Human Activation Governance — 人工激活治理）

> **Phase 3.5.0 定位**：Phase 3.4 已完成「激活准备架构与验证」。Phase 3.5.0 目标 = **建立首次人工激活所需治理流程**——把 G2 双签 / G4 审核链 / G6 授权 / Rollback Dry Run 固化为可审计、职责分离、fail-closed 的流程契约，并厘清 CI 债务根因，使人类终端 `local_ci` 8/8 可达。

### 2.1 已交付（治理流程设计 + 代码对齐 + CI 验证）

- **3.5.0** Human Activation Governance & Controlled Release Preparation（人工激活治理与受控发布准备）。**DONE（2026-08-02）**
  - ✅ **任务1 G2 真实双签流程设计**：专家签署（expert_recheck，SoD）+ 管理审核（review，principal）；`ThresholdIntakeWorkflow` 四步落 `review_log`；SoD 硬校验（专家≠主理人、须先审核后复核）；`is_fully_verified` 为 G2 门禁源。AI 仅编排落盘，绝不代签。
  - ✅ **任务2 G4 审核链流程设计 + 代码命名对齐（已落地）**：规范事件名 `submit / review / expert_recheck / verified`；单源 `REQUIRED_REVIEW_ACTIONS` 改值 + `threshold_intake.py` 4 发射点 + `evidence_bundle.REQUIRED_INTAKE_EVENTS` 值 + `threshold_signing_sessions.json` 19 处 + 6 测试文件字面量对齐（共 84 处替换）；保留 `intake_rejected` / `intake_snapshots` / `run_intake_drill`。`required_audit_events_present` / `check_review_log_chain` 按规范名校验。
  - ✅ **任务3 G6 授权流程设计**：`EngineeringReleaseApproval` 七字段（approval_id/interface/scope/authorized_by/effective_time/rollback_owner/approval_document_ref），**人工创建，append-only**；AI 仅 `validate_release_approval` 校验存在性/合法性 + SoD 软校验（authorized_by≠rollback_owner）。`append_approval_record(` 全仓唯一引用为其定义，**无任何 AI 调用方**（红线③ 守约）。
  - ✅ **任务4 CI 债务专项处理**：根因锁定为 **agent 运行时独占的 `[safe-delete]` 守卫**（`CODEBUDDY_SAFE_DELETE_BULK_STATE_DIR` + `CODEBUDDY_TOOL_CALL_ID` 存在时 patch `os.remove`，单轮>50 删除→`SystemExit`）；人类终端无此变量→`local_ci.sh` 第 2 步 **672 passed / 90.40% / EXIT=0 = 8/8 可达**。3.4.5 关于 threshold pytest 隔离失败的误判**已更正**（同为该守卫级联假象）。
  - ✅ **任务5 Rollback Dry Run 设计**：四步验证流程 snapshot → disable → rollback → restore；`RollbackHandler` + `controller` 仅翻转 `GrayReleaseConfig` 开关，不触碰 `review_log`/`verified.json`；全局闸门 `engineering_enabled=False` 时 `is_interface_gray_allowed` 恒 False（不可绕过）。
  - ✅ **红线扫描 0 实际违规**：`engineering_enabled=True` 字面量 0 命中；`engineering_approved=` 赋值 0 命中；`append_approval_record(` AI 调用方 0。
  - ✅ **全量测试零回归**：G4 命名对齐后全仓 **672 passed / coverage 90.40% / EXIT=0**（agents 555 + backend 117）。
  - ✅ 交付 `.ai/reviews/phase3.5.0_human_activation_governance_report.md` + 更新 `.ai/project_status.json`（phase_3_5 块，current_roadmap_version=V5）+ 本 roadmap_v5.md。
  - ✅ **激活态维持 NO-GO**；按指令**完成后停止**，未开启 `engineering_enabled`、未输出 `engineering_approved`、未代建 `ReleaseApproval`、未代专家/主理人签署或授权。

---

## 3. 优先级与技术债

### 3.1 当前 P0

| ID | 描述 | 状态 | 责任 |
|---|---|---|---|
| P0-TD-3.5.0-1 | G4 审核链命名对齐规范名（已落地） | ✅ RESOLVED | AI（本阶段） |
| P0-TD-3.5.0-2 | 更正 3.4.5 threshold 隔离失败误判 | ✅ RESOLVED | AI（本阶段） |
| P0-TD-3.5.0-3 | `local_ci.sh` 加固（去 coverage 并行分片，避免 agent 运行时守卫误伤） | ⏳ 可选 | AI / 主理人 |
| P0-TD-3.5.0-4 | 主理人/专家线下签署模板与授权文档模板落地（G2/G6 线下动作） | ⏳ 人工 | 主理人 |
| P0-TD-3.5.0-5 | 真实 E-TH 数值录入（阻塞于人工提供） | ⏳ 人工 | 主理人 + 专家 |

### 3.2 人工激活前置清单（解锁条件）

1. 经 `ThresholdIntakeWorkflow` 四步录入真实 E-TH-01/02/03（主理人审核 `review` + 专家签署 `expert_recheck`，SoD）；
2. 确认 `review_log` 含完整四类规范事件（`submit/review/expert_recheck/verified`）且链式无断裂；
3. 线下创建 `EngineeringReleaseApproval`（七字段齐全，SoD，`effective_time` 生效）；
4. 人类终端 `local_ci.sh` 8/8 绿（已实证可达）；
5. 完成 Rollback Dry Run（snapshot/disable/rollback/restore 通过）；
6. 显式置 `orchestrator.engineering_enabled=true`（须 G6 授权记录在先）。

---

## 4. 下一阶段建议

- **保持 NO-GO**：在人工未逐项完成 §3.2 前置清单前，禁止任何自动激活路径。
- **可选加固（TD-3.5.0-3）**：若需在 agent 运行时也跑通 `local_ci.sh`，可去除 `backend/pyproject.toml` 的 `[tool.coverage.run] concurrency = ["thread","greenlet"]` 并行分片，或将 `coverage run` 与 `coverage report` 拆分为独立步骤，降低单轮文件删除数量，避开 safe-delete 守卫阈值。
- **进入 Phase 3.6（真实激活执行）的前提**：主理人完成 §3.2 全部线下动作并经 G1-G6 全过。Phase 3.6 仍须维持 fail-closed，且任何 `engineering_enabled` 翻转须由主理人显式操作，AI 不代行。
- **禁止自动激活**：无论 CI 是否全绿、治理流程是否齐备，AI 不得自动置 `engineering_enabled=true`、不得输出 `engineering_approved`、不得代建 `ReleaseApproval`、不得代专家/主理人签署或授权。
