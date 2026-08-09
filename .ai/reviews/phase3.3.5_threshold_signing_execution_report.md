# BOIP Phase 3.3 Sprint 3.3.5 — Real Threshold Signing Execution（真实阈值签署执行 · 结构/签署准备态）

- **生成日期**：2026-08-02
- **身份**：BOIP AI Chief Architect
- **任务**：Real Threshold Signing Execution（真实阈值签署执行）
- **性质**：**结构/签署准备态**——建立 E-TH-01/02/03 真实审核签署链的框架与槽位容器，对齐 `ThresholdIntakeWorkflow` 双签步骤（`review`→`expert_recheck`）与 `review_log.py` 审核链；**不调用工作流写真实签名、不 append 真实 review_log.jsonl、不写 verified.json、不翻转 engineering_enabled、不输出 engineering_approved、不创建 ReleaseApproval**
- **依据**：`.ai/project_status.json`（SSOT）、`.ai/roadmap_v3.md`、`.ai/reviews/phase3.3.4_threshold_entry_execution_report.md`、`agents/engineering/threshold_intake.py`（ThresholdIntakeWorkflow 真实实现：`review(verified_by, verified_at)`→`intake_review_approve`；`expert_recheck(expert_verified_by, expert_verified_at)`→`intake_expert_recheck`，内置 SoD `expert_verified_by != verified_by`）、`agents/engineering/review_log.py`（append-only 审核链 `append_review_event`）、`agents/engineering/knowledge/experts.json`（v2 专家注册表与 SoD）、`agents/engineering/knowledge/threshold_entry_sessions.json`（3.3.4 录入会话）、`.ai/reviews/phase3.3.0B_knowledge_item_schema_design.md`（KnowledgeItem 13 字段七态）
- **衔接定位**：3.3.4 已建 E-TH-01/02/03 录入会话与 `threshold_candidate` KnowledgeItem 关联骨架；本 Sprint 在其之上建立**双签执行框架**——主理人审核槽位（任务1）、专家复核槽位+SoD（任务2）、KnowledgeItem 状态推进机（任务3）、verified.json 保护（任务4）、审计链三事件要求（任务5）；所有签署位一律 `pending_verification`，等待人工经正式流程提供身份与签名并书面授权。

---

## 0. 设计目标与边界

Phase 3.3 收口前段。3.3.1/3.3.2/3.3.3/3.3.4 已建成规范来源、专家注册表、资质/SoD 治理、阈值录入会话。本 Sprint 目标：为 E-TH-01/02/03 真实审核签署建立**可执行的双签框架与校验规则**。

**边界铁律（最高红线，本轮 7 条）**：
1. AI 绝不生成专家身份（专家主体由人工从 experts.json 提供，AI 不编造）。
2. AI 绝不生成签名（`verified_by`/`expert_verified_by` 等签署位由人工落，AI 不代签）。
3. AI 绝不代替主理人确认（`review` 步骤由人工执行，AI 不填 `verified_by/verified_at`）。
4. AI 绝不代替专家复核（`expert_recheck` 步骤由人工执行，AI 不填 `expert_verified_by/expert_verified_at`）。
5. AI 绝不创建 ReleaseApproval（G6 授权由主理人书面创建，非本 Sprint 范畴）。
6. 不开启 `engineering_enabled`（`evaluate_gates` 恒 False 内置护栏）。
7. 不输出 `engineering_approved`。

> 代码层已有内置护栏：`evaluate_gates()` 恒返回 `(False, reasons)`，即便双签转正也默认拒绝开启闸门（详见激活保护节）。

---

## 任务1：主理人审核（Principal Review）框架

新增于 `threshold_signing_sessions.json` 每个会话的 `principal_review` 段，对齐 `threshold_intake.py` 的 `review(threshold_id, verified_by, verified_at)` 步骤。

| 字段 | 取值 | 说明 |
|---|---|---|
| `verified_by` | `pending_verification` | 主理人核准主体标识符（人工提供，须 experts.json `sod_role=principal` 且 `qualification_status=verified`） |
| `verified_at` | `pending_verification` | 核准时间戳（人工提供，UTC ISO8601） |
| `signer_role` | `principal` | 角色固定为 principal（主理人） |
| `required_role` | `principal` | 校验：主体须映射 `sod_role=principal` |
| `role_check` | 须 experts.json sod_role=principal 且 qualification_status=verified | 资格闸门（复用 3.3.3 SoD R5 状态闸门） |
| `review_log_action` | `intake_review_approve` | 真实执行时落 review_log 的事件名（用户简称 `intake_review`） |
| `status` | `BLOCKED_PENDING_HUMAN_SIGN` | 阻塞待人工签署 |

**红线守约**：AI 不生成签名、不代主理人确认——`verified_by/verified_at` 全 `pending_verification`，本 Sprint 不调用 `review()`，不 append 真实 review_log。

---

## 任务2：专家复核（Expert Recheck）框架 + SoD

每个会话的 `expert_recheck` 段，对齐 `threshold_intake.py` 的 `expert_recheck(threshold_id, expert_verified_by, expert_verified_at)` 步骤。

| 字段 | 取值 | 说明 |
|---|---|---|
| `expert_verified_by` | `pending_verification` | 专家复核主体标识符（人工提供，须 `qualification_status=verified` 且 `sign_scope` 覆盖 `domain`） |
| `expert_verified_at` | `pending_verification` | 复核时间戳（人工提供） |
| `signer_role` | `expert` | 角色固定为 expert |
| `required_qualification_status` | `verified` | 校验：专家须 `qualification_status=verified`（3.3.3 资质流程产出） |
| `required_sign_scope_cover` | `domain` | 校验：专家 `sign_scope` 须覆盖本阈值 `domain`（wind_pressure） |
| `review_log_action` | `intake_expert_recheck` | 真实执行时落 review_log 的事件名 |
| `status` | `BLOCKED_PENDING_HUMAN_SIGN` | 阻塞待人工签署 |

**SoD 硬规则（R1，不变式）**：
- `expert_verified_by != verified_by`——专家复核人不得与主理人核准人同一身份（G2 职责分离）。
- 由 `threshold_intake.expert_recheck` 内置 `REASON_SOD_CONFLICT` 强制拒绝（代码已固化）；框架段 `sod_check.rule = "expert_verified_by != verified_by"`、`enforced_by` 指向该代码路径，`status=PENDING`。
- 红线：AI 不代专家复核——`expert_verified_by/expert_verified_at` 全 `pending_verification`。

---

## 任务3：KnowledgeItem 状态推进（七态机）

在 `knowledge_items_pending.json` 新增顶层 `state_progression` 段，复用 3.3.0-B/C 七态契约，定义 E-TH-01/02/03 对应 `threshold_candidate` KnowledgeItem 的合法推进路径：

- **当前态**：`Pending_Verification`（三项 `KI-pending-E-TH-xx` `validation_status` 仍 `Pending_Verification`，无真实签署）。
- **合法推进**：`Pending_Verification → Source_Verified`（source_ref 过 C1-C6 且人工提供）→ `Expert_Verified`（经双签：主理人 `review_approve` + 专家 `expert_recheck`，满足 SoD R1）→ `Engineering_Verified`（G1-G6 技术维度 `release_precheck` 通过，未授权）。
- **禁止跃迁**：`Engineering_Approved`——须经 G6 主理人书面授权落 `release_approvals.jsonl` 后方可；本 Sprint 及签署阶段**禁止直接进入**。
- **护栏**：`no_skip`（禁止跳级直达 `Engineering_Approved`）、`sign_driven`（Expert_Verified 须由真实专家签名驱动，AI 不代签）、`no_value_write`（Engineering_Approved 之前候选 value 恒 pending_verification，不写 verified.json）、`current_items_stay_pending`（当前三项保持 Pending_Verification）。

---

## 任务4：verified.json 保护（禁止绕过工作流）

- **硬约束**：任何阈值 `value` 写入**必须**经由 `ThresholdIntakeWorkflow`（`submit → review_approve → expert_recheck → finalize_verified`），**禁止**任何路径绕过工作流直接编辑 `verified.json`。
- 本 Sprint 不调用工作流，因此 `verified.json` 六条 E-TH 仍 `value=null` / `verified=false`（详见 §7 实测）。
- 即便未来真实签署执行，真实 `value` 落盘只发生在 `finalize_verified` 步骤内（受双签 + G1-G6 门禁约束），不存在「直接改文件」的旁路。
- 框架 `invariants.no_direct_verified_edit` 固化此约束。

---

## 任务5：审计链检查（Audit Chain）

- **要求**：真实签署执行时，`review_log.jsonl`（append-only）必须包含完整三事件，构成不可篡改审核链：
  1. `intake_submit`（提交，由 `submit()` 落）
  2. `intake_review_approve`（主理人核准，由 `review()` 落；用户简称 `intake_review`）
  3. `intake_expert_recheck`（专家复核签，由 `expert_recheck()` 落）
- 每事件由 `append_review_event` 写入，含确定性 `event_id` + `prev_event_id` 链指针（链式溯源，满足 G4 审核链完整）。
- **本设计态不产生任何事件**：框架段 `review_log_events.required` 列出三事件、`status=PENDING`；`review_log.jsonl`（现存仅 2026-07-28 `schema_established` 系统事件）本 Sprint **不 append**，保持零伪造签署记录。

---

## 激活保护（红线 6/7）

即便未来真实双签完成，本 Sprint 及后续签署阶段**仍保持**：

- `engineering_enabled = false`（config.yaml `engineering_enabled: false` 不变；loader 默认 False）。
- 不输出任何 `engineering_approved`。
- 不创建 `release_approvals.jsonl`（G6 授权由主理人书面创建，非本 Sprint 范畴）。
- 代码内置护栏：`ThresholdIntakeWorkflow.evaluate_gates()` 恒返回 `(False, reasons)`——即便阈值双签转正，也强制 `ci_green=False / rollback_ready=False / authorization_present=False`，绝不翻转 `engineering_enabled`、绝不写 config.yaml。即签署工作流任何情况下都不允许开启工程计算闸门。

**激活复核（后续 Sprint 3.3.6）才发生的动作**：重跑发布预检脚本复核全部门禁全绿 → RC 状态转 GO → 执行灰度发布启用命令。本 Sprint 不触发。

---

## 7. 红线守约验证（本 Sprint 实测）

| 红线 | 验证结果 |
|---|---|
| AI 不生成专家身份 | experts.json 仍 `experts:[]` 空；签署框架 `verified_by/expert_verified_by` 全 `pending_verification`，未编造任何专家 |
| AI 不生成签名 | 所有签署位（`verified_by/verified_at/expert_verified_by/expert_verified_at`）全 `pending_verification`，未落任何真实签名 |
| AI 不代主理人确认 | 未调用 `review()`，`verified_by/verified_at` 未填 |
| AI 不代专家复核 | 未调用 `expert_recheck()`，`expert_verified_by/expert_verified_at` 未填 |
| AI 不创建 ReleaseApproval | `release_approvals.jsonl` 不存在；`authorized_by` 未填 |
| 不开启 engineering_enabled | config `engineering_enabled: false` 不变；evaluate_gates 恒 False |
| 不输出 engineering_approved | 全 `pending_verification`/`false`，无 approved 落盘 |
| 不写 verified.json 真实 value | verified.json 六条 E-TH value=null / verified=false 未改 |
| 禁止绕过工作流直接改 verified.json | 本 Sprint 未调用工作流；verified.json 未改（任务4 硬约束） |
| 不 append 真实 review_log | review_log.jsonl 仍仅含 2026-07-28 schema_established 系统事件，无 E-TH 伪造签署 |

**扫描执行结论**（本机）：
- 防编造扫描 `check_fabrication.py`：仅当一行同时含业务词与裸数字才报错；本 Sprint 文档/结构全程枚举值 + 字母标识符（E-TH/KI/SES/G1-G6 区间），无业务裸数字 → **0 命中**。
- 硬编码扫描 `check_hardcoded.py`：仅扫 `.js/.py/.ts/.tsx`；本 Sprint 无新增工程代码 → **0 命中**。
- `engineering_enabled=False` 实测（config + loader 默认 False）。
- `verified.json` 未改（E-TH value 仍 null）；`release_approvals.jsonl` 不存在；`review_log.jsonl` 未 append。

---

## 8. 交付物与 SSOT/路线图更新

**本 Sprint 交付物**：
1. `agents/engineering/knowledge/threshold_signing_sessions.json`（真实阈值签署链框架 v1，E-TH-01/02/03，含 principal_review/expert_recheck 双签槽位全 pending + SoD 规则 + 审计链三事件要求 + KnowledgeItem 状态推进 + 激活保护，status=BLOCKED_PENDING_HUMAN_SIGN）
2. `agents/engineering/knowledge/knowledge_items_pending.json`（在 3.3.4 v2 基础上增补 `state_progression` 七态推进机段，任务3）
3. `.ai/reviews/phase3.3.5_threshold_signing_execution_report.md`（本报告）

**SSOT 更新**（`project_status.json` → `task_status.phase_3_3."3.3.5"`）：status=DONE（completed_at 2026-08-02，executed_by BOIP AI Chief Architect），summary/constraints_kept/deliverables/fabrication_scan/next 齐全。

**路线图更新**（`roadmap_v3.md`）：
- §1 当前状态表 Phase 3.3 进度更新为 3.3.1+3.3.2+3.3.3+3.3.4+3.3.5 DONE，3.3.6 PENDING。
- §2 在 3.3.4 块之后插入「补充 Sprint 3.3.5（DONE，2026-08-02，结构+签署准备态）」说明块。
- 列表区 3.3.5 由 `PENDING` 翻 `DONE`，补「增强产出（3.3.5）」子项。

---

## 9. 测试执行（相关测试 + 双扫描）

- 本 Sprint 未修改工程代码（仅新增 1 个 JSON 框架 + 增强 1 个 JSON + 报告），故 `local_ci.sh` 的「如修改代码」条件未触发；但仍执行相关阈值测试以确认无回归：
  - 运行 `backend/.venv/bin/python -m pytest tests/agents/test_real_threshold_intake.py tests/agents/test_threshold_real_drill.py tests/agents/test_threshold_governance.py tests/agents/test_threshold_migration.py -q`，确认阈值录入/治理/演练机制无回归（基线沿用 CI 481 passed@90%）。
  - 运行 `check_fabrication.py` 与 `check_hardcoded.py`，确认双扫描 0 命中。
- 现有测试均使用 tmp 路径与内存夹具，不扫描 `knowledge/` 目录，新增 JSON 不影响其通过（已确认）。

---

## 10. 下一步

- 3.3.5 结构/签署准备态 DONE；**真实签署仍阻塞于人工提供**——等待主理人提供 `verified_by/verified_at`、专家提供 `expert_verified_by/expert_verified_at`（专家须经 3.3.3 资质审核登记且 `qualification_status=verified`、`sign_scope` 覆盖 domain），并经主理人书面授权。
- 真实执行顺序：人工提供签署身份与签名 → 经 `ThresholdIntakeWorkflow` 双签（`review`→`expert_recheck`，每步落 review_log，满足 SoD R1）→ 满足 G1/G2/G4 → 3.3.6 激活复核（G1-G6 全绿 + G6 授权 → RC 转 GO）。
- AI 全程不代录、不代签、不代授权、不开 enabled、不输出 approved。

**红线全程守约，按 3.3.5 指令「完成后停止，等待人工审核」——未生成专家身份、未生成签名、未代主理人确认、未代专家复核、未创建 ReleaseApproval、未开启 engineering_enabled、未输出 engineering_approved、未绕过工作流直接改 verified.json、未 append 真实 review_log。**

**END**
