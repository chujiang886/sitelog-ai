# BOIP 研发路线 V6（roadmap_v6.md）

- **生成**：2026-08-02
- **身份**：BOIP AI Chief Architect（Phase 3.6.0 首次人工受控激活执行 · 演练）
- **性质**：Phase 3.6.0 = **首次人工受控激活端到端演练（DRILL）**：沿 G1–G6 跑通真实工作流机制（Intake → G2 双签 → G4 审核链 → G6 授权 → UnifiedActivationGate → Rollback Dry Run），全部以 DRILL 占位符替代人工专属输入；不翻转 `engineering_enabled`、不输出 `engineering_approved`、不代建 `ReleaseApproval`、不代专家/主理人签署或授权；激活态维持 NO-GO。
- **依据**：`.ai/project_status.json`（SSOT，current_roadmap_version=V6）、`.ai/reviews/phase3.6.0_controlled_activation_execution_report.md`、`.ai/phase3.6.0_drill/result.json`、`.ai/reviews/phase3.5.0_human_activation_governance_report.md`
- **权威声明**：本文件取代 `roadmap_v5.md`，为 Phase 3.6.0 起的唯一研发路线；roadmap_v5.md 保留为 Phase 3.5.0 历史归档。

---

## 1. 当前真实状态（Phase 3.6.0 受控激活演练态）

| 维度 | 真实状态 |
|---|---|
| 阶段 | **Phase 3.2 CLOSED** → **Phase 3.3 DONE** → **Phase 3.4 DONE（3.4.0~3.4.5 全 ✅）** → **Phase 3.5.0 Human Activation Governance DONE** → 🟢 **Phase 3.6.0 Controlled Human Activation Execution DRILL DONE（2026-08-02：G1-G6 全链路机制演练跑通；DRILL 占位符替代人工输入；红线 5 条 0 违规；UnifiedActivationGate verdict=NO-GO）** |
| 演练机制 | **任务1 Intake**：E-TH-01/02/03 四步 submit→review_approve→expert_recheck→threshold_verified（all_verified=True）；**任务2 G2 双签**：SoD（verified_by≠expert_verified_by，DRILL 占位）；**任务3 G4 审核链**：12 events 四类齐全 chain_intact=True；**任务4 G6 授权**：AI 仅 `validate_release_approval`（approval_created_by_ai=False）；**任务5 UnifiedActivationGate**：fail-closed→NO-GO（diagnostic_interface_scoped 显示阈值域 G1-G6 全 PASS）；**任务6 Rollback Dry Run**：snapshot/disable/rollback/restore 全成功，gray_allowed 恒 False |
| 红线 | `engineering_enabled=false`；无任何 `engineering_approved` 输出；`E-TH-01/02/03` 真实 `value` 仍 `null`（pending_verification）；`append_approval_record(` 全仓仅定义无 AI 调用方；所有真实工程参数均为 DRILL 占位（未伪造） |
| CI | **人类终端 `local_ci.sh` 8/8 绿**（沿用 3.5.0 实证）：672 passed / 90.40% coverage / EXIT=0；本阶段无代码改动，未重跑 |
| 激活态 | **NO-GO 维持**：六闸门（G1-G6）默认全 FAIL；`engineering_enabled=False`；人工激活须主理人线下补齐真实双签 + 审核链 + G6 授权 + 显式置 `engineering_enabled=true` |
| 未完成（人工动作） | 真实双签执行 / 真实审核链填充 / G6 授权创建 / 真实 E-TH 数值录入 均 pending_verification（本阶段均为 DRILL 占位） |

**红线（不可逾越）**：任何无据行业数字必须标 `pending_verification`；工程参数未经专家签字不得转正；Phase 3.6.0 不代建 `ReleaseApproval`、不开 `engineering_enabled`、不输出 `engineering_approved`、不代专家/主理人签署或授权、不伪造真实工程参数。

---

## 2. Phase 3.6.0 路线（Controlled Human Activation Execution — DRILL）

> **Phase 3.6.0 定位**：Phase 3.5.0 已完成「激活治理流程设计」。Phase 3.6.0 目标 = **在 fail-closed 前提下，把 G1–G6 全链路真实工作流机制端到端跑通一遍（DRILL）**，验证机制在人工补齐真实资料后**可行**，同时严守红线、绝不进入真实激活态。

### 2.1 已交付（DRILL 演练 + 红线守约）

- **3.6.0** Controlled Human Activation Execution（首次人工受控激活执行 · 演练）。**DONE（2026-08-02）· DRILL**
  - ✅ **任务1 真实 Threshold Intake**：E-TH-01/02/03 经 `ThresholdIntakeWorkflow` 四步（submit→review_approve→expert_recheck→threshold_verified）全部转正（`all_verified=True`）；每步落 `review_log`、终态写 `verified.json`；`gate_allowed=False`/`engineering_enabled=False`（四步转正不解锁工程态）。
  - ✅ **任务2 G2 双签验证（SoD）**：`verified_by=DRILL-PRINCIPAL-001` / `expert_verified_by=DRILL-EXPERT-002`，`sod_ok=True` / `all_signed=True`（专家≠主理人硬校验）。
  - ✅ **任务3 G4 审核链验证**：`review_log` 含 12 事件（3 阈值 × 4 类），四类 `submit/review/expert_recheck/verified` 齐全，`chain_intact=True`，`g4_pass=True`。
  - ✅ **任务4 G6 授权（AI 仅 validate）**：`validate_release_approval` 校验七字段齐全 + `effective_time` ISO8601 + SoD（authorized_by≠rollback_owner），`approval_created_by_ai=False`（红线④守约），`g6_mechanism_ready=True`。
  - ✅ **任务5 UnifiedActivationGate**：fail-closed → `verdict=NO-GO`；`diagnostic_interface_scoped` 证明仅注入 `wind_pressure` 的 E-TH-01/02/03 且 CI/回滚/授权到位时，**阈值域 G1–G6 全 PASS**（数据路径可行），但 knowledge 域受阻→整体 NO-GO。
  - ✅ **任务6 Rollback Dry Run**：snapshot/disable/rollback/restore 全成功；`gray_allowed` 前后恒 False（`engineering_enabled=False` 时 `is_interface_gray_allowed` 恒 False 不可绕过）；`review_log_untouched=True`（回滚仅动 `GrayReleaseConfig`）。
  - ✅ **红线扫描 0 实际违规**：`engineering_enabled=True` 字面量 0 命中；`engineering_approved=` 赋值 0 命中；`append_approval_record(` AI 调用方 0；真实参数/专家签名/主理人授权均未伪造（red_lines 6/6 True）。
  - ✅ 交付 `.ai/reviews/phase3.6.0_controlled_activation_execution_report.md` + 更新 `.ai/project_status.json`（phase_3_6 块，current_roadmap_version=V6）+ 本 roadmap_v6.md。
  - ✅ **激活态维持 NO-GO**；按指令**完成后停止**，未开启 `engineering_enabled`、未输出 `engineering_approved`、未代建 `ReleaseApproval`、未代专家/主理人签署或授权、未伪造真实工程参数。

---

## 3. 优先级与技术债

### 3.1 当前 P0

| ID | 描述 | 状态 | 责任 |
|---|---|---|---|
| P0-TD-3.6.0-1 | G1-G6 激活闸门机制端到端演练（DRILL 完成） | ✅ RESOLVED | AI（本阶段） |
| P0-TD-3.6.0-2 | 接口级 vs 全局级 G1/G2 诊断差异澄清（数据路径可行性证明） | ✅ RESOLVED | AI（本阶段） |
| P0-TD-3.6.0-3 | DRILL 占位符 → 真实资料替换清单（E-TH 数值/双签/授权线下动作） | ⏳ 人工 | 主理人 + 专家 |
| P0-TD-3.5.0-3 | `local_ci.sh` 加固（去 coverage 并行分片，避免 agent 运行时守卫误伤） | ⏳ 可选 | AI / 主理人 |
| P0-TD-3.5.0-4 | 主理人/专家线下签署模板与授权文档模板落地（G2/G6 线下动作） | ⏳ 人工 | 主理人 |
| P0-TD-3.5.0-5 | 真实 E-TH 数值录入（阻塞于人工提供） | ⏳ 人工 | 主理人 + 专家 |

### 3.2 人工激活前置清单（解锁条件，沿用 V5 §3.2）

1. 经 `ThresholdIntakeWorkflow` 四步录入**真实** E-TH-01/02/03（主理人审核 `review` + 专家签署 `expert_recheck`，SoD，替换 DRILL 占位）；
2. 确认 `review_log` 含完整四类规范事件（`submit/review/expert_recheck/verified`）且链式无断裂；
3. 线下创建**真实** `EngineeringReleaseApproval`（七字段齐全，SoD，`effective_time` 生效）；
4. 人类终端 `local_ci.sh` 8/8 绿（已实证可达）；
5. 完成真实 Rollback Dry Run（snapshot/disable/rollback/restore 通过）；
6. 显式置 `orchestrator.engineering_enabled=true`（须 G6 授权记录在先）。

---

## 4. 下一阶段建议

- **保持 NO-GO**：在人工未逐项完成 §3.2 前置清单前，禁止任何自动激活路径。
- **DRILL → 真实**：本阶段 DRILL 占位符不构成任何真实生效记录；主理人须以真实资料替换 DRILL 占位（E-TH 数值、双签身份、G6 授权）后方可进入真实激活评估。
- **可选加固（TD-3.5.0-3）**：若需在 agent 运行时也跑通 `local_ci.sh`，可去除 `backend/pyproject.toml` 的 `[tool.coverage.run] concurrency = ["thread","greenlet"]` 并行分片，或将 `coverage run` 与 `coverage report` 拆分为独立步骤，降低单轮文件删除数量，避开 safe-delete 守卫阈值。
- **进入真实 Phase 3.6.x（真实激活执行）的前提**：主理人完成 §3.2 全部线下动作并经 G1-G6 全过。真实激活仍须维持 fail-closed，且任何 `engineering_enabled` 翻转须由主理人显式操作，AI 不代行。
- **禁止自动激活**：无论 CI 是否全绿、治理流程是否齐备，AI 不得自动置 `engineering_enabled=true`、不得输出 `engineering_approved`、不得代建 `ReleaseApproval`、不得代专家/主理人签署或授权、不得伪造真实工程参数。

---

## 5. Phase 3.6.1 路线（Real Activation Evidence Preparation — 真实激活证据准备）

> **Phase 3.6.1 定位**：Phase 3.6.0 已完成「激活机制 DRILL 演练」。Phase 3.6.1 目标 = **建立真实激活所需证据清单与模板**（DRILL→REAL 映射 + 四类证据模板 + G1-G6 检查表），为人工线下填充真实资料提供契约。本阶段**纯模板设计**，不录入真实值、不签署、不授权、不翻转 `engineering_enabled`。

### 5.1 已交付（证据模板 + 映射 + 检查表）

- **3.6.1** Real Activation Evidence Preparation（真实激活证据准备）。**DONE（2026-08-02）**
  - ✅ **任务1 DRILL→REAL 映射**：`E-TH-01/02/03`（→ `verified.json`）、`verified_by`=DRILL-PRINCIPAL-001（→ 真实主理人）、`expert_verified_by`=DRILL-EXPERT-002（→ 真实专家）、`authorized_by`=DRILL-AUTHORIZER-004（→ 真实授权人）、`rollback_owner`=DRILL-ROLLBACK-003（→ 真实回滚责任人）；替换规则含 SoD 硬约束（专家≠主理人）与 G6 SoD 软约束（授权人≠回滚责任人）。
  - ✅ **任务2 Threshold Evidence Package 模板**：`value/unit/source_ref/version/verification` 全字段留空（`<待人工填写>`），落 `agents/engineering/thresholds/verified.json`（经 `ThresholdIntakeWorkflow.finalize_verified` 写入，禁绕过）。
  - ✅ **任务3 Expert Evidence 模板**：`qualification/domain/sign_scope/signature_record` 留空；`signature_record.is_ai_generated=false`（红线③：AI 不代签），落签署台账/ `threshold_signing_sessions.json`。
  - ✅ **任务4 EngineeringReleaseApproval 模板（G6）**：七字段（approval_id/interface/scope/authorized_by/effective_time/rollback_owner/approval_document_ref）留空；**AI 仅 `validate_release_approval`，不 `append_approval_record`**（红线④），落 `agents/engineering/release/release_approvals.jsonl`（append-only）。
  - ✅ **任务5 G1-G6 最终检查表**：逐闸门列「所需证据 / 通过条件 / 落入文件」；顶层不变量 `load_engineering_enabled() is False` 须保持至主理人显式置 `true`（且须 G6 授权在先）；真实解锁顺序 6 步。
  - ✅ **六条红线 0 违规**：未生成真实参数 / 未编造专家身份 / 未代签 / 未建 ReleaseApproval / 未开 engineering_enabled / 未输出 engineering_approved。
  - ✅ 交付 `.ai/reviews/phase3.6.1_real_activation_evidence_preparation.md` + 更新 `.ai/project_status.json`（phase_3_6 新增 `3.6.1` 块）+ 本 roadmap_v6.md §5。
  - ✅ **激活态维持 NO-GO**；按指令**完成后停止**，未开启 `engineering_enabled`、未输出 `engineering_approved`、未代建 `ReleaseApproval`、未代专家/主理人签署或授权、未伪造真实工程参数。

### 5.2 当前 P0（Phase 3.6.1 衍生）

| ID | 描述 | 状态 | 责任 |
|---|---|---|---|
| P0-TD-3.6.1-1 | DRILL→REAL 占位替换（主理人/专家线下动作） | ⏳ 人工 | 主理人 + 专家 |
| P0-TD-3.6.1-2 | 真实 Threshold 资料录入（value/unit/source_ref 真实规范值） | ⏳ 人工 | 主理人 + 专家 |
| P0-TD-3.6.1-3 | 真实 G6 授权创建（EngineeringReleaseApproval append-only 落盘） | ⏳ 人工 | 主理人 |

### 5.3 真实激活前置清单（解锁条件，沿用 V6 §3.2）

1. 经 `ThresholdIntakeWorkflow` 四步录入**真实** E-TH-01/02/03（主理人审核 `review` + 专家签署 `expert_recheck`，SoD，替换 DRILL 占位）；
2. 确认 `review_log.jsonl` 含完整四类规范事件（`submit/review/expert_recheck/verified`）且链式无断裂；
3. 线下创建**真实** `EngineeringReleaseApproval`（七字段齐全，SoD，`effective_time` 生效）；
4. 人类终端 `local_ci.sh` 8/8 绿（已实证可达）；
5. 完成真实 Rollback Dry Run（snapshot/disable/rollback/restore 通过）；
6. 显式置 `orchestrator.engineering_enabled=true`（须 G6 授权记录在先）。

---

## 6. Phase 3.6.2 路线（Activation Evidence Validation Dry Run — 激活证据验证演练）

> **Phase 3.6.2 定位**：Phase 3.6.1 已建立真实激活证据模板/映射/清单。Phase 3.6.2 目标 = **验证「证据包结构是否满足 G1–G6 输入要求」**（纯结构验证，非真实录入），喂入真实闸门校验代码（UnifiedActivationGate / can_enable_engineering / check_e_th_realization / validate_release_approval / review_log 链式），而**不改变任何真实激活状态**。本阶段**纯内存 bundle + 真实 gate 校验**，不落真实证据文件。

### 6.1 已交付（结构验证演练 + 红线 6/6 守约）

- **3.6.2** Activation Evidence Validation Dry Run（激活证据验证演练）。**DONE（2026-08-03）**
  - ✅ **任务1 Evidence Bundle 完整性**：内存态 `ActivationEvidenceBundle` 四类证据字段齐全 —— Threshold 12 / Expert 5 / Approval 7 / Rollback 4；`all_complete = True`。
  - ✅ **任务2 G1–G6 输入格式**：模拟「CI 绿 / 回滚就绪 / 授权到位 / 审核链完整 / 阈值结构完整」输入，`can_enable_engineering` 返回 `(allowed=True, reasons=[])` → **阈值域 G1–G6 全 `True`**（输入格式被 gate 完全接受）；但 `UnifiedActivationGate().evaluate(repository=None, ...)` 因知识域无仓库候选（G0）+ 发布域 G4 无仓库审计 → **统一 verdict = NO-GO**（fail-closed 正确）。
  - ✅ **任务3 SoD 验证**：四角色 `verified_by=DRILL-PRINCIPAL-001` / `expert_verified_by=DRILL-EXPERT-002` / `authorized_by=DRILL-AUTHORIZER-004` / `rollback_owner=DRILL-ROLLBACK-003` 两两异身份，`sod_ok = True`。
  - ✅ **任务4 可追溯性**：12 事件 / `compute_event_id` 确定性 sha256（64-hex）/ `prev_event_id` 链式无断裂 / `source_ref.hash` 64-hex / 时间均 ISO8601，`traceable = True, issues = []`。
  - ✅ **任务5 G6 仅校验**：`validate_release_approval` 七字段有效，但 **AI 未调 `append_approval_record`**（`approval_created_by_ai = False`）；最终 verdict = **NO-GO**，`engineering_enabled = False`。
  - ✅ **诚实性声明**：bundle `value/unit` 使用代码库自身「待人工填入」标记 `pending_verification`，`check_e_th_realization` 诚实判定 `real_data_present = False` —— 未含任何真实工程参数（红线①守约）。G1/G2 闸门不读 value，故占位值仍能让阈值域 G1–G6 全 PASS，但**不构成真实激活资格**。
  - ✅ **六条红线 0 违规**：未生成真实参数 / 未编造专家身份 / 未代签 / 未建 ReleaseApproval / 未开 engineering_enabled / 未输出 engineering_approved；真实证据文件（`verified.json`/`review_log.jsonl`/`release_approvals.jsonl`）未触碰。
  - ✅ 交付 `.ai/reviews/phase3.6.2_activation_evidence_validation_dry_run.md` + `.ai/phase3.6.2_validation_run.py` + `.ai/phase3.6.2_dryrun/result.json` + 更新 `.ai/project_status.json`（task_status.phase_3_6 新增 `3.6.2` 块）+ 本 roadmap_v6.md §6。
  - ✅ **激活态维持 NO-GO**；按指令**完成后停止**，未开启 `engineering_enabled`、未输出 `engineering_approved`、未代建 `ReleaseApproval`、未代专家/主理人签署或授权、未伪造真实工程参数。

### 6.2 当前 P0（Phase 3.6.2 衍生）

| ID | 描述 | 状态 | 责任 |
|---|---|---|---|
| P0-TD-3.6.2-1 | 真实激活证据填值（依 3.6.2 验证通过的 G1–G6 输入结构，替换 DRILL 占位为真实 E-TH 数值/双签身份/G6 授权） | ⏳ 人工 | 主理人 + 专家 |

### 6.3 真实激活前置清单（解锁条件，沿用 V6 §3.2）

1. 经 `ThresholdIntakeWorkflow` 四步录入**真实** E-TH-01/02/03（主理人审核 `review` + 专家签署 `expert_recheck`，SoD，替换 DRILL 占位）；
2. 确认 `review_log.jsonl` 含完整四类规范事件（`submit/review/expert_recheck/verified`）且链式无断裂；
3. 线下创建**真实** `EngineeringReleaseApproval`（七字段齐全，SoD，`effective_time` 生效）；
4. 人类终端 `local_ci.sh` 8/8 绿（已实证可达）；
5. 完成真实 Rollback Dry Run（snapshot/disable/rollback/restore 通过）；
6. 显式置 `orchestrator.engineering_enabled=true`（须 G6 授权记录在先）。

---

## 7. Phase 3.6.3 路线（Real Activation Evidence Intake — 真实激活证据正式接入）

> **Phase 3.6.3 定位**：Phase 3.6.2 已验证「证据包结构满足 G1–G6 输入要求」。Phase 3.6.3 目标 = **建立真实证据接入（Intake）与校验机制**，对真实仓库证据文件（只读）做接收与校验，生成 Real Evidence Bundle，并运行真实 `UnifiedActivationGate` 输出 GO/NO-GO。**关键事实**：本回合用户指令未附带任何「真实人工提供的激活证据」载荷，故 Intake 机制已就绪但各类证据插槽均 `not_received / pending_verification`，AI 绝不编造。

### 7.1 已交付（接入机制 + 真实状态校验 + 红线 6/6 守约）

- **3.6.3** Real Activation Evidence Intake（真实激活证据正式接入）。**DONE（2026-08-03）· INTAKE-MECHANISM**
  - ✅ **任务1 真实 Threshold Intake**：读取真实 `verified.json`，校验 E-TH-01/02/03 的 `value/unit/source_ref/version/verification` 五要素 —— 全部 `pending_verification`、`verified=False`、双签缺；`all_received=False`（红线①守约：未编造真实数值）。
  - ✅ **任务2 真实专家 Intake**：读取真实 `experts.json`，专家数 = **0**，`received=False`；SoD 不适用（无可分离对象），不违反红线②（未编造专家身份）。
  - ✅ **任务3 真实 G6 Intake（仅验证）**：真实 `release_approvals.jsonl` 不存在，`received=False`；AI `ai_created=False`（红线④守约：仅 validate 占位设计，未调 `append_approval_record`）。
  - ✅ **任务4 生成 Real Evidence Bundle**：`bundle_hash`（sha256 64-hex）/ `bundle_version=1.0.0` / `bundle_timestamp`（ISO8601）为包体溯源元数据（非工程参数）；证据内容全 `pending_verification`；仅落 `.ai/phase3.6.3_intake/result.json`（演练副本）。
  - ✅ **任务5 运行 UnifiedActivationGate（真实状态）**：`evaluate(repository=None, context=全部信号 False, thresholds=None(加载真实 verified.json), review_log_path=真实路径)` → **verdict = NO-GO**，12 项 blocking_reasons，threshold 域 G1–G6 全 False、publishing 域 G2–G6 False、knowledge 域无仓库候选（G0）；顶层 `engineering_enabled=False` → fail-closed 正确。与 3.6.2 区别：3.6.2 模拟资料已填验证「输入格式被接受」，3.6.3 真实状态全缺故全链路失败。
  - ✅ **六条红线 0 违规**：未生成真实参数（E-TH 全 pending）/ 未编造专家身份（专家数 0）/ 未代签（未收签署请求）/ 未建 ReleaseApproval（文件不存在，AI 未创建）/ 未开 engineering_enabled（恒 False）/ 未输出 engineering_approved（仅 NO-GO）；真实证据文件未触碰。
  - ✅ 交付 `.ai/reviews/phase3.6.3_real_activation_evidence_intake_report.md` + `.ai/phase3.6.3_intake_run.py` + `.ai/phase3.6.3_intake/result.json` + 更新 `.ai/project_status.json`（task_status.phase_3_6 新增 `3.6.3` 块）+ 本 roadmap_v6.md §7。
  - ✅ **激活态维持 NO-GO**；按指令**完成后停止**，未开启 `engineering_enabled`、未输出 `engineering_approved`、未代建 `ReleaseApproval`、未代专家/主理人签署或授权、未伪造真实工程参数。

### 7.2 当前 P0（Phase 3.6.3 衍生）

| ID | 描述 | 状态 | 责任 |
|---|---|---|---|
| P0-TD-3.6.3-1 | 真实 Threshold 录入（主理人经 ThresholdIntakeWorkflow 四步填真实 E-TH-01/02/03，专家签署 SoD） | ⏳ 人工 | 主理人 + 专家 |
| P0-TD-3.6.3-2 | 真实专家登记与线下签署（experts.json 填真实 expert_id/qualification/domain/sign_scope/signature_record） | ⏳ 人工 | 专家 |
| P0-TD-3.6.3-3 | 真实 G6 授权创建（EngineeringReleaseApproval append-only 落盘） | ⏳ 人工 | 主理人 |

### 7.3 真实激活前置清单（解锁条件，沿用 V6 §3.2）

1. 经 `ThresholdIntakeWorkflow` 四步录入**真实** E-TH-01/02/03（主理人审核 `review` + 专家签署 `expert_recheck`，SoD）；
2. 专家经资质审核登记（`experts.json` 真实 `expert_id/qualification/domain/sign_scope/signature_record`，`is_ai_generated=false`）；
3. 确认 `review_log.jsonl` 含完整四类规范事件（`submit/review/expert_recheck/verified`）且链式无断裂；
4. 线下创建**真实** `EngineeringReleaseApproval`（七字段齐全，SoD，`effective_time` 生效）；
5. 人类终端 `local_ci.sh` 8/8 绿（已实证可达）；
6. 完成真实 Rollback Dry Run（snapshot/disable/rollback/restore 通过）；
7. 显式置 `orchestrator.engineering_enabled=true`（须 G6 授权记录在先）。

## 8. Phase 3.6.4 路线（Real Evidence Submission & Verification — 真实激活证据提交与验证）

> **Phase 3.6.4 定位**：Phase 3.6.3 已建立「真实证据接入机制」。Phase 3.6.4 目标 = **建立真实证据提交后的验证闭环（Intake → Verify → Bundle → Gate 复核 → 审计链确认）**，且本次**直接驱动仓库真实 gate 代码**（`check_e_th_realization` / `check_review_log_chain` / `validate_release_approval` / `UnifiedActivationGate`），验证逻辑来自代码本身，可信度高于 3.6.3 的自实现校验。**关键事实**：本回合用户指令仍未附带任何「真实人工提供的激活证据」载荷，故闭环实跑后所有证据插槽仍为 `NOT_SUBMITTED_PENDING / not_received`，AI 绝不编造（红线①~⑥全守约）。

### 8.1 已交付（提交后验证闭环 + 真实 gate 代码驱动 + 红线 6/6 守约）

- **3.6.4** Real Evidence Submission & Verification（真实激活证据提交与验证）。**DONE（2026-08-03）· SUBMISSION-VERIFICATION-CLOSED-LOOP**
  - ✅ **任务1 真实 Threshold 提交验证**（真实 `check_e_th_realization` 驱动）：E-TH-01/02/03 全部 `NOT_SUBMITTED_PENDING`，缺失 `value/unit/source_ref/version/dual_sign`；`all_submitted_verified=False`（红线①守约：未编造真实数值）。
  - ✅ **任务2 专家证据验证 + SoD**：真实 `experts.json` 专家数 = **0**，`submission_verified=False`；`sod_applicable=False`（无可分离对象），不违反红线②（未编造专家身份）。
  - ✅ **任务3 G6 授权验证（仅 validate）**：真实 `release_approvals.jsonl` 不存在，`submission_verified=False`；`ai_created=False`（红线④守约：未调 `append_approval_record`，仅 validate 占位设计）。
  - ✅ **任务4 生成 Real Activation Evidence Bundle**：`bundle_hash`（sha256 64-hex）/ `bundle_version=1.0.0` / `bundle_timestamp`（ISO8601）+ 四类证据文件引用（`verified.json` / `experts.json` / `release_approvals.jsonl` / `review_log.jsonl`）；包体溯源元数据非工程参数，证据内容全 `pending_verification`；仅落 `.ai/phase3.6.4_verify/result.json`。
  - ✅ **任务5 UnifiedActivationGate 复核 G1–G6（真实状态）**：`evaluate(repository=None, context=全部信号 False, thresholds=None(加载真实 verified.json), review_log_path=真实路径)` → **verdict = NO-GO**，12 项 blocking_reasons；threshold 域 G1–G6 全 False、publishing 域 G1=True（安全不变量 `engineering_enabled=False`）其余 False、knowledge 域无仓库候选（G0）；顶层 `engineering_enabled=False` 恒 NO-GO。
  - ✅ **任务6 审计链确认**（真实 `check_review_log_chain` 驱动）：`chain_ok=False`，缺失 `submit/review/expert_recheck/verified` 四类人类审核事件（仅 1 条 `SYSTEM` 建链事件）；链式未断裂但事件不全，未达解锁条件。
  - ✅ **六条红线 0 违规**：未生成真实参数（E-TH 全 pending）/ 未编造专家身份（专家数 0）/ 未代签（未收签署请求）/ 未建 ReleaseApproval（文件不存在，AI 未创建）/ 未开 engineering_enabled（恒 False）/ 未输出 engineering_approved（仅 NO-GO）；真实证据文件未触碰。
  - ✅ 交付 `.ai/reviews/phase3.6.4_real_evidence_submission_verification.md` + `.ai/phase3.6.4_verification_run.py` + `.ai/phase3.6.4_verify/result.json` + 更新 `.ai/project_status.json`（task_status.phase_3_6 新增 `3.6.4` 块）+ 本 roadmap_v6.md §8。
  - ✅ **激活态维持 NO-GO**；按指令**完成后停止**，未开启 `engineering_enabled`、未输出 `engineering_approved`。

### 8.2 当前 P0（Phase 3.6.4 衍生，与 3.6.3 同口径，仍待人工）

| ID | 描述 | 状态 | 责任 |
|---|---|---|---|
| P0-TD-3.6.4-1 | 真实 Threshold 录入（主理人经 ThresholdIntakeWorkflow 四步填真实 E-TH-01/02/03，专家签署 SoD） | ⏳ 人工 | 主理人 + 专家 |
| P0-TD-3.6.4-2 | 真实专家登记与线下签署（experts.json 填真实 expert_id/qualification/domain/sign_scope/signature_record） | ⏳ 人工 | 专家 |
| P0-TD-3.6.4-3 | 真实 G6 授权创建（EngineeringReleaseApproval append-only 落盘） | ⏳ 人工 | 主理人 |
| P0-TD-3.6.4-4 | 真实审核链补齐（review_log.jsonl 含 submit/review/expert_recheck/verified 完整四类且链式无断裂） | ⏳ 人工 | 主理人 + 专家 |

### 8.3 重跑本闭环的时机

> 当且仅当上述 P0 人工动作全部完成（真实 E-TH 双签录入 + 真实专家签署 + 真实 ReleaseApproval 落盘 + 完整审核链 + local_ci 8/8 + Rollback Dry Run）后，重跑 `.ai/phase3.6.4_verification_run.py`，各任务方会从 `PENDING` 翻转为 `VERIFIED`，gate 才可能返回 GO。届时仍须由人类终端显式置 `engineering_enabled=true`，**AI 不自动激活**。

## 9. Phase 3.6.5 路线（Final Human Activation Approval Review — 最终人工激活批准复核）

> **Phase 3.6.5 定位**：Phase 3.6.4 已建立「提交后验证闭环」。Phase 3.6.5 目标 = **建立最终人工激活批准复核**，汇总不可变证据包（真实 `collect_release_evidence_bundle`）+ G1–G6 逐 Gate PASS/FAIL + SoD 最终检查 + Rollback 四动作确认，输出 Final Human Decision（GO/NO-GO），并明确 **AI 无权开启**。本次仍直接驱动仓库真实 gate 代码 + 真实证据包模块，验证逻辑来自代码本身。**关键事实**：本回合用户指令仍未附带任何「真实人工提供的激活证据」载荷，故最终复核结论仍为 NO-GO，AI 绝不编造（红线①~⑥全守约）。

### 9.1 已交付（最终复核 + 真实 gate 代码 + 真实证据包 + 红线 6/6 守约）

- **3.6.5** Final Human Activation Approval Review（最终人工激活批准复核）。**DONE（2026-08-03）· FINAL-HUMAN-APPROVAL-REVIEW**
  - ✅ **任务1 Evidence Bundle 汇总 → Final Activation Evidence Summary**（真实 `collect_release_evidence_bundle` 驱动）：不可变证据包 `bundle_id=BOIP-EB-fb5469bfb0430e2c`（commit=`543c3c7`）；threshold/review/rollback 哈希可算（64-hex），`authorization_hash=None`（release_approvals.jsonl 不存在）；`complete=False`（review_evidence_incomplete + authorization_missing）。五类：Threshold NOT REALIZED（E-TH 全 pending）/ Expert NOT RECEIVED（专家数 0）/ Approval NOT RECEIVED / Rollback MECHANISM ONLY（控制器存在但 Dry Run 未执行）/ Audit INCOMPLETE（缺 submit/review/expert_recheck/verified）。
  - ✅ **任务2 G1–G6 逐 Gate PASS/FAIL**（真实 `UnifiedActivationGate`）：knowledge=N/A(G0)、threshold G1–G6 全 FAIL、publishing G1=PASS（安全不变量 `engineering_enabled=False`）其余 FAIL → **verdict=NO-GO**，12 项 blocking_reasons。
  - ✅ **任务3 SoD 最终检查**：`verified_by/expert_verified_by/authorized_by/rollback_owner` 全 null（无可分离对象），`sod_ok=True`；一并校验硬（expert≠principal）+ 软（authorized≠rollback_owner）分离。
  - ✅ **任务4 Rollback 确认**（snapshot/disable/rollback/restore）：控制器脚本存在但四类动作 Dry Run 均未执行 → `ready=False`，与 gate G5 `rollback_ready=False` 一致。
  - ✅ **任务5 Final Human Decision = NO-GO**；**AI authority = NONE**（AI 无权开启 `engineering_enabled`，仅人工终端可显式置 true）。
  - ✅ **六条红线 0 违规**：未生成真实参数（E-TH 全 pending）/ 未编造专家身份（专家数 0）/ 未代签（未收签署请求）/ 未建 ReleaseApproval（文件不存在，AI 未创建）/ 未开 engineering_enabled（恒 False）/ 未输出 engineering_approved（仅 NO-GO）；真实证据文件未触碰。
  - ✅ 交付 `.ai/reviews/phase3.6.5_final_human_activation_review.md` + `.ai/phase3.6.5_final_review_run.py` + `.ai/phase3.6.5_review/result.json` + 更新 `.ai/project_status.json`（task_status.phase_3_6 新增 `3.6.5` 块）+ 本 roadmap_v6.md §9。
  - ✅ **激活态维持 NO-GO**；按指令**完成后停止**，AI 无权开启 `engineering_enabled`、未输出 `engineering_approved`。

### 9.2 当前 P0（Phase 3.6.5 衍生，仍待人工）

| ID | 描述 | 状态 | 责任 |
|---|---|---|---|
| P0-TD-3.6.5-1 | 真实 Threshold 录入（主理人经 ThresholdIntakeWorkflow 四步填真实 E-TH-01/02/03，专家签署 SoD） | ⏳ 人工 | 主理人 + 专家 |
| P0-TD-3.6.5-2 | 真实专家登记与线下签署（experts.json 填真实 expert_id/qualification/domain/sign_scope/signature_record） | ⏳ 人工 | 专家 |
| P0-TD-3.6.5-3 | 真实 G6 授权创建（EngineeringReleaseApproval append-only 落盘，七字段+生效+SoD） | ⏳ 人工 | 主理人 |
| P0-TD-3.6.5-4 | 真实审核链补齐（review_log.jsonl 含 submit/review/expert_recheck/verified 完整四类且链式无断裂） | ⏳ 人工 | 主理人 + 专家 |
| P0-TD-3.6.5-5 | 真实 Rollback Dry Run（snapshot/disable/rollback/restore 执行并留证） | ⏳ 人工 | 主理人 |

### 9.3 最终复核重跑时机

> 当且仅当上述 P0 人工动作全部完成（真实 E-TH 双签录入 + 真实专家签署 + 真实 ReleaseApproval 落盘 + 完整审核链 + local_ci 8/8 + Rollback Dry Run 留证）后，重跑 `.ai/phase3.6.5_final_review_run.py`，各任务方会从 `PENDING` 翻转为 `VERIFIED`，gate 才可能返回 GO。**届时仍须由人类终端显式置 `engineering_enabled=true`，AI 不自动激活、无权开启。**

---

## 10. Phase 3.6.6 — Activation Candidate Freeze（激活候选版本冻结）

> **Phase 3.6.6 定位**：Phase 3.6.5 已给出 FINAL-HUMAN-APPROVAL-REVIEW（NO-GO）。Phase 3.6.6 目标 = **冻结未来人工激活所依据的唯一版本**——把当前仓库真实状态锚定为可复现、可比对、不可篡改的激活候选基线（code / config / evidence / gate 代码 / runbook 五类哈希）。本轮**未收到任何真实人工证据**，冻结是对真实状态的快照，天然 `FROZEN_NO_GO`。AI 不伪造任何证据、不开启 `engineering_enabled`、不输出 `engineering_approved`（红线①~⑥全守约）。

### 10.1 已交付（冻结 + 真实状态只读锚定 + 红线 6/6 守约）

- **3.6.6** Activation Candidate Freeze（激活候选版本冻结）。**DONE（2026-08-03）· ACTIVATION-CANDIDATE-FROZEN**
  - ✅ **任务1 代码版本冻结**：commit `543c3c7a…01502`（master，2026-07-28）；**code_hash** `e00a7df5…60d6cdd`（15 个激活相关源文件拼接 sha256，含未提交工作树）；working tree 存在未提交改动（3.6.x 报告 + 少量源码微调），已记入冻结锚点。
  - ✅ **任务2 配置冻结**：config_hash `9aa005aa…0ff2cc`（agents/config.yaml）；`engineering_enabled` **真实读取 = False** ✅。
  - ✅ **任务3 Evidence Bundle 冻结 → `ActivationCandidateBundle`**：bundle_id `BOIP-ACF-e00a7df54621257a`、bundle_hash `aa397a20…99af6`、`frozen_at=2026-08-03T03:30:37Z`；聚合 **code_hash + config_hash + evidence_hash**（真实证据文件拼接 sha256 `97fb2a47…81ab4`）。证据状态 `ALL_PENDING_NO_REAL_EVIDENCE`（verified.json E-TH 全 null 未双签 / experts=0 / release_approvals 不存在 / review_log 仅 SYSTEM 事件），不可变证据包 `complete=False`。
  - ✅ **任务4 Gate 版本冻结**：UnifiedActivationGate `9b697a8b…57d3456` / ConsumptionPolicy `96c7afd4…6557dc0` / RuntimeGuard `55b635e0…8645ba`（内容哈希锚定，无显式 `__version__`）。
  - ✅ **任务5 Runbook 冻结**：runbook_hash `84b4cf10…3bf8d1`（7 份激活流程文档拼接：roadmap_v6.md + phase3.6.0~3.6.5 报告，全部存在）。
  - ✅ **任务6 Freeze 报告 + 最终裁决 `FROZEN_NO_GO`**；AI 无权开启 `engineering_enabled`，仅锚定状态。
  - ✅ **六条红线 0 违规**：未生成真实参数 / 未编造专家身份 / 未代签 / 未建 ReleaseApproval / 未开 engineering_enabled / 未输出 engineering_approved；本阶段仅对真实文件做只读哈希，未写任何真实证据/配置/代码。
  - ✅ 交付 `.ai/reviews/phase3.6.6_activation_candidate_freeze.md` + `.ai/phase3.6.6_freeze_run.py` + `.ai/phase3.6.6_freeze/freeze_manifest.json` + `.ai/phase3.6.6_freeze/activation_candidate_bundle.json` + 更新 `.ai/project_status.json`（task_status.phase_3_6 新增 `3.6.6` 块）+ 本 roadmap_v6.md §10。

### 10.2 冻结基线（未来人工激活唯一比对基准）

| 锚点 | 值（sha256 / 标识） |
|---|---|
| commit | `543c3c7a651b158b6c8f76ad99666aef058a1502` (master) |
| code_hash | `e00a7df54621257a3786c1d23bbc1e3ea27d2b492675e1054ceaab09260d6cdd` |
| config_hash | `9aa005aa598dedf75969d12a17f155aa6e27d86dec33cb1c173a7d5b6a0ff2cc` |
| evidence_hash | `97fb2a47d367c9dc8cd6db3801f3bc3e1f87f51a359505cac725a0b26f381ab4` |
| bundle_id / bundle_hash | `BOIP-ACF-e00a7df54621257a` / `aa397a20bfb6eec70472c4958353342b8e3746d5224d5438a184eee919499af6` |

### 10.3 激活解锁路径（须在同一冻结基线之上，纯人工）

> 冻结仅锚定状态。真实激活仍须主理人 + 专家线下补齐证据并经 G1–G6 全过，由**人类终端显式置 `engineering_enabled=true`**——**AI 不自动激活、无权开启**。解锁动作同 §9.2（P0-TD-3.6.5-1 ~ 5）+ 人类显式置 enabled。届时以本 §10.2 bundle_hash 为比对基准，重跑 3.6.4/3.6.5 闭环核验证据翻转。

---

## 11. Phase 3.6.7 — Human Activation Evidence Completion（真实人工证据补齐）

### 11.1 已交付（补齐机制 + 冻结完整性验证，只读，无真实证据载荷）

- **3.6.7** Human Activation Evidence Completion（真实人工激活证据补齐）。**DONE（2026-08-03）· NO-GO-EVIDENCE-INCOMPLETE**
  - ✅ **任务1 真实 Threshold 接入**：读取真实 `verified.json`（dict 结构，E-TH-01/02/03 全部 `value=null` / `verified=False` / 无双签 / `source_ref=pending_verification`）→ `NOT_RECEIVED_PENDING`，`all_received=False`，`ai_completed=False`（红线①：绝不补全）。
  - ✅ **任务2 专家接入**：真实 `experts.json` 专家数 = **0** → `NOT_RECEIVED_PENDING`，SoD 无可分离对象不违规，`ai_created_identity=False`（红线②）。
  - ✅ **任务3 真实审核链**：`check_review_log_chain` 驱动 → `chain_ok=False`，缺失 `submit/review/expert_recheck/verified` 四类（仅 1 条 SYSTEM 事件）。
  - ✅ **任务4 真实 G6 授权**：`release_approvals.jsonl` 不存在 → `NOT_RECEIVED_PENDING`，`ai_created=False`（红线④：仅 validate）。
  - ✅ **任务5 冻结完整性验证**：重算采用 3.6.6 完全一致哈希算法，比对基线（frozen_at `2026-08-03T03:30:37Z`）→ **code_hash / config_hash / evidence_hash / UnifiedActivationGate / ConsumptionPolicy / RuntimeGuard 全部 MATCH（`all_critical_match=True`，安全关键冻结面未漂移）**；`runbook_hash` 因每阶段文档增长（3.6.6 自身追加 §10、本阶段追加 §11）而预期变化，非 gate 逻辑漂移；`engineering_enabled` 真实读取 = **False**（红线⑤）。
  - ✅ **任务6 Completion 报告 + 裁决 `NO_GO_EVIDENCE_INCOMPLETE`**；**AI 权限 = NONE**（无权开启 `engineering_enabled`），仅人工终端可显式置 `true`（红线⑥：未输出 `engineering_approved`）。
  - ✅ **六条红线 + 冻结完整 8/8 守约**：未生成真实参数 / 未编造专家身份 / 未代签 / 未建 ReleaseApproval / 未开 engineering_enabled / 未输出 engineering_approved + 冻结未漂移；真实证据文件只读未写。
  - ✅ 交付 `.ai/reviews/phase3.6.7_human_activation_evidence_completion.md` + `.ai/phase3.6.7_completion_run.py` + `.ai/phase3.6.7_complete/completion_result.json` + 更新 `.ai/project_status.json`（task_status.phase_3_6 新增 `3.6.7` 块）+ 本 roadmap_v6.md §11。

### 11.2 真实证据补齐契约（留给主理人 + 专家线下）

1. **E-TH 双签录入**：`ThresholdIntakeWorkflow` 四步 `submit → review → expert_recheck → verified`（主理人审核 + 专家签署，SoD，`expert_id ≠ verified_by`），落真实 value/unit/source_ref(64-hex hash)/version。
2. **专家登记签署**：`experts.json` 填入 `expert_id/qualification/domain/sign_scope/signature_record`，`sign_scope` 覆盖 E-TH-01/02/03 且与 `verified_by` 异身份。
3. **审核链补齐**：`review_log.jsonl` 就 E-TH-01/02/03 各产生 4 条链式事件（确定性 `event_id` + `prev_event_id` 指针），链式无断裂。
4. **G6 授权落盘**：线下真实 `EngineeringReleaseApproval`（七字段齐全，`effective_time` ISO8601，`authorized_by ≠ rollback_owner` 且 `≠ verified_by`）；AI 仅 `validate_release_approval`，绝不 `append_approval_record`。
5. **冻结比对**：补齐后以 §10.2 bundle_hash 为基准，重跑 `.ai/phase3.6.7_completion_run.py` 验证 code/config/gate 仍 MATCH。
6. **人类显式开启**：由**人工终端**置 `engineering_enabled=true`；届时 gate 才可能 GO。**AI 不自动激活、无权开启**。

> 本回合指令未附带任何真实人工证据载荷，故补齐机制就绪但证据插槽全 `pending`；激活态维持 NO-GO。真实解锁严格按 §11.2 线下完成，禁止自动激活。

---

## 12. Phase 3.6.8 — Real Evidence Submission Window（真实证据提交窗口）

### 12.1 已交付（ESW 治理规则建立 + 冻结基线关联 + 真实 gate 预检查，只读，无真实证据载荷）

- **3.6.8** Real Evidence Submission Window（真实证据提交窗口）。**DONE（2026-08-03）· 窗口 OPEN · NO-GO**
  - ✅ **任务1 提交窗口规则**：正式建立「真实证据提交窗口（ESW）」治理规则（`window_id=BOIP-ESW-747f8b2d7847ba7c`，status=OPEN）。四位一体：提交人（principal_maintainer/domain_expert/release_owner，禁 AI/脚本，硬 SoD expert≠principal）/ 提交时间（持续开放+每次须带 UTC 时间戳）/ 文件范围（verified.json·experts.json·release_approvals.jsonl·review_log.jsonl 接受，AI 补全字段拒绝）/ 版本要求（绑定 3.6.6 冻结基线，漂移即暂停）。落 `.ai/phase3.6.8_submission_window/window_rules.json`。
  - ✅ **任务2 Evidence Intake 校验**：驱动真实 `check_e_th_realization` / `check_review_log_chain` 校验真实仓库 → Threshold（E-TH-01/02/03 全 `value=null`、未双签、`all_realized=False`）/ Expert（0 人）/ Approval（`release_approvals.jsonl` 不存在）/ Audit（缺失 submit/review/expert_recheck/verified 四事件，仅 1 SYSTEM）/ Rollback（`release_audit.jsonl` 含 `release-operator` 的 disable/rollback/restore 但 `approval_id` 全空 → 仅 DRILL，非真实授权回滚）。总体完整度 = `false`（0 真实证据载荷）。
  - ✅ **任务3 冻结基线关联**：复用 3.6.6 同一套文件清单+哈希算法重算当前仓库比对 → **code_hash / config_hash / evidence_hash / UnifiedActivationGate / ConsumptionPolicy / RuntimeGuard 全部 MATCH（`all_critical_match=True`，安全关键冻结面未漂移）**；`engineering_enabled` 真实读取 = **False**（红线⑤）。
  - ✅ **任务4 New Evidence Bundle**：生成窗口级证据包（`window_state=OPEN_EMPTY`，`newly_added_evidence=[]`，`newly_added_count=0`），引用冻结基线哈希；证据文件哈希与 3.6.6 一致（未漂移）。落 `.ai/phase3.6.8_submission_window/new_evidence_bundle.json`。
  - ✅ **任务5 Gate 预检查**：驱动真实 `UnifiedActivationGate.evaluate` → **verdict=NO-GO**（12 项 blocking reasons：阈值域+发布域 G1-G6 全 FAIL，知识域 G0_repository_required），`engineering_enabled=False`，`auto_activation_forbidden=True`（红线⑤⑥）。
  - ✅ **六条红线 8/8 守约**：未生成真实参数 / 未编造专家身份 / 未代签 / 未建 ReleaseApproval / 未开 engineering_enabled / 未输出 engineering_approved + 冻结未漂移；真实证据文件只读未写。
  - ✅ 交付 `.ai/reviews/phase3.6.8_real_evidence_submission_window.md` + `.ai/phase3.6.8_submission_window_run.py` + `.ai/phase3.6.8_submission_window/{result.json,window_rules.json,new_evidence_bundle.json}` + 更新 `.ai/project_status.json`（task_status.phase_3_6 新增 `3.6.8` 块）+ 本 roadmap_v6.md §12。

### 12.2 ESW 窗口流入与真实解锁路径（经窗口、纯人工）

1. **经窗口提交**：主理人 + 专家按 ESW 规则（`window_rules.json`）提交真实 E-TH 双签 / 专家登记 / review_log 链 / ReleaseApproval；每次须带 UTC 时间戳 + 真实署名，拒绝无签名/无时间戳。
2. **版本校验**：窗口受理前校验版本匹配 §10.2 冻结基线（任一安全关键哈希漂移 → 暂停并告警，须重新冻结）。
3. **闭环复核**：以 §10.2 `bundle_hash` 为基准重跑 `.ai/phase3.6.5_final_review_run.py` / `.ai/phase3.6.7_completion_run.py` 核验证据翻转且 code/config/gate 仍 MATCH。
4. **人类显式开启**：由**人工终端**置 `engineering_enabled=true`；届时 Gate 才可能 GO。**AI 不自动激活、无权开启**。

> 本回合指令未附带任何真实人工证据载荷，故窗口已 OPEN 但证据插槽全 `pending`；激活态维持 NO-GO。真实证据须严格经 ESW 窗口线下流入，禁止自动激活。

## 13. Phase 3.6.9 — Evidence Governance Operations（证据治理运营）

### 13.1 已交付（长期证据治理能力建立，纯治理模型+真实代码实证，无真实证据载荷）

- **3.6.9** Evidence Governance Operations（证据治理运营）。**DONE（2026-08-02）· 治理能力就绪 · NO-GO**
  - ✅ **任务1 提交审计日志（EvidenceSubmissionLog）**：定义审计行 Schema，强制六字段 `submission_id`/`submitter`/`timestamp`/`files`/`hash`/`status`，附加 `engineering_enabled_touch:false`（常量）+ 六红线自检；提交人须真人签署+UTC 时间戳，AI 不生成身份/不代签（红线②③）。落 `.ai/phase3.6.9_evidence_governance/evidence_submission_log.schema.json`。
  - ✅ **任务2 证据生命周期五态（Evidence Lifecycle）**：`OPEN→SUBMITTED→VALIDATING→VERIFIED→ACCEPTED` + `RETURNED`/`REJECTED`；所有跃迁 `auto=false`、actor 限人类（禁 ai/agent/script）；不变量 I1–I5 含「任一态不翻转 engineering_enabled」（红线⑤）。落 `.ai/phase3.6.9_evidence_governance/evidence_lifecycle.statemachine.json`。
  - ✅ **任务3 证据版本控制（Evidence Version Control）**：`version`/`hash`/`previous_version` 哈希链（`hash=SHA256(prev_hash‖files‖meta)`），不可变+篡改检测；以 3.6.6 冻结基线 `BOIP-ACF-e00a7df54621257a` 为 0 号锚点。落 `.ai/phase3.6.9_evidence_governance/evidence_version_control.schema.json`。
  - ✅ **任务4 人工审核队列（Review Queue）**：三阶段 `pending_reviewer→expert_review→approval_review`，强 SoD（submitter≠reviewer≠expert≠approval_reviewer，AI 禁任审核角色），含拒绝/退回路径；审核队列不修改 engineering_enabled。落 `.ai/phase3.6.9_evidence_governance/review_queue.schema.json`。
  - ✅ **任务5 Gate 关联验证（Gate Association）**：真实代码溯源实证「证据状态变化不自动开启 engineering_enabled」= TRUE fail-closed（`config_loader.py:121` 只读 / `read_boundary.py:45` `can_write_engineering_enabled()=False` / `unified_activation_gate.py:141` `safety_ok = load_engineering_enabled() is False` / `enable_gate.py` 仅判定）。落 `.ai/phase3.6.9_evidence_governance/gate_association.verification.json`。
  - ✅ **六条红线 8/8 守约**：未生成真实参数 / 未编造专家身份 / 未代签 / 未建 ReleaseApproval / 未开 engineering_enabled / 未输出 engineering_approved；真实证据文件只读未写；冻结未漂移。
  - ✅ 交付 `.ai/reviews/phase3.6.9_evidence_governance_operations.md` + `.ai/phase3.6.9_evidence_governance/{evidence_submission_log.schema.json, evidence_lifecycle.statemachine.json, evidence_version_control.schema.json, review_queue.schema.json, gate_association.verification.json}` + 更新 `.ai/project_status.json`（task_status.phase_3_6 新增 `3.6.9` 块）+ 本 roadmap_v6.md §13。

### 13.2 治理能力与解锁路径（纯人工，经 ESW 窗口）

1. **经窗口提交**：主理人 + 专家按 3.6.8 ESW 规则提交真实证据，每次带 UTC 时间戳 + 真实署名；审计行写入 EvidenceSubmissionLog（新版本号）。
2. **版本校验**：窗口受理前校验版本匹配 §10.2 冻结基线（漂移即暂停）。
3. **审核队列**：走完 `pending_reviewer→expert_review→approval_review` 三阶段，任一阶段不翻转 engineering_enabled。
4. **闭环复核**：以 §10.2 `bundle_hash` 为基准重跑 3.6.5/3.6.7 核验证据翻转且 code/config/gate 仍 MATCH。
5. **人类显式开启**：由**人工终端**置 `engineering_enabled=true`；届时 Gate 才可能 GO。**AI 不自动激活、无权开启**。

> 本回合指令未附带任何真实人工证据载荷，故证据治理能力已建立但证据插槽全 `pending`；激活态维持 NO-GO。真实证据须严格经 ESW 窗口线下流入，禁止自动激活。
