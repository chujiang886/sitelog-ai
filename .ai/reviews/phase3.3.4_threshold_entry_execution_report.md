# BOIP Phase 3.3 Sprint 3.3.4 — Real Threshold Entry Execution（真实阈值录入执行 · 结构/准备态）

- **生成日期**：2026-08-02
- **身份**：BOIP AI Chief Architect
- **任务**：Real Threshold Entry Execution（真实阈值录入执行准备）
- **性质**：**结构/准备态**——建立 `ThresholdEntrySession` 会话容器 + `threshold_candidate` KnowledgeItem 关联骨架，编排 `ThresholdIntakeWorkflow` 执行路径；**不调用工作流写入真实值、不写 `verified.json`、不翻转 `engineering_enabled`、不输出 `engineering_approved`**
- **依据**：`.ai/project_status.json`（SSOT，current_roadmap_version=V3）、`.ai/roadmap_v3.md`、`.ai/tasks/phase3.3.1_threshold_entry_plan.md`、`agents/engineering/threshold_intake.py`（ThresholdIntakeWorkflow 真实实现）、`agents/engineering/thresholds/source_ref_validator.py`（C1-C6，字段 `standard/clause/edition/url/hash`，其中 `url` 即本任务规约的 `official_url`）、`agents/engineering/thresholds/verified.json`（E-TH-01..06 初始态）、`agents/engineering/knowledge/experts.json`（v2 专家注册表）、`.ai/reviews/phase3.3.0B_knowledge_item_schema_design.md`（KnowledgeItem 13 字段七态）
- **衔接定位**：3.3.1 已编排录入计划（未执行）；3.3.2 已建规范来源 C1-C6 校验；3.3.3 已建专家注册表与 SoD；本 Sprint 在三者之上建立 E-TH-01/02/03 的**会话容器与执行编排骨架**，真实数值/来源/专家身份/签名/授权一律 `pending_verification`，等待人工经正式流程提供并书面授权。

---

## 0. 设计目标与边界

Phase 3.3 进入「Engineering Knowledge Activation」收口前段。3.3.1/3.3.2/3.3.3 已分别建成规范来源、专家注册表、资质/SoD 治理。本 Sprint 目标：为 E-TH-01/02/03 真实录入建立**可执行的会话结构与流程骨架**。

**边界铁律（最高红线，本轮 7 条）**：
1. AI 绝不生成工程参数（不写任何真实 value）。
2. AI 绝不猜测规范数值（source_ref 不编造条款/版本）。
3. AI 绝不补全缺失 value（缺则保持 `pending_verification`）。
4. AI 绝不代签专家（reviewer/expert 不落任何签署位）。
5. AI 绝不代授权（不创建 ReleaseApproval）。
6. 自动开启 `engineering_enabled` 被禁止（代码内置 `evaluate_gates` 恒 False）。
7. 不输出 `engineering_approved`。
- 代码层已有内置护栏：`evaluate_gates()` 恒返回 `(False, reasons)`，即便双签转正也默认拒绝开启闸门（详见任务6）。

---

## 任务1：建立 ThresholdEntrySession（会话容器）

新增 `agents/engineering/knowledge/threshold_entry_sessions.json`（schema_version=2），为 E-TH-01/02/03 各建一条会话记录，键为 `session_id`。

### 1.1 会话字段（对齐任务1 要求）

| 字段 | 取值 | 说明 |
|---|---|---|
| `session_id` | `SES-E-TH-01` / `SES-E-TH-02` / `SES-E-TH-03` | 会话唯一标识（新增） |
| `threshold_id` | `E-TH-01` / `E-TH-02` / `E-TH-03` | 阈值标识符（字母+数字，标识符安全） |
| `knowledge_id` | `KI-pending-E-TH-xx` | 回指 knowledge_items_pending.json 的 KnowledgeItem（新增，双向绑定） |
| `source_ref` | `pending_verification` | 真实规范来源引用（C1-C6 校验对象），须人工提供 |
| `provider` | `pending_verification` | 阈值提供方（人工标识符） |
| `reviewer` | `pending_verification` | 主理人核准主体（须 `experts.json` sod_role=principal 且 qualification_status=verified） |
| `expert` | `pending_verification` | 行业专家复核主体（须 sod_role=expert 且 verified） |
| `status` | `BLOCKED_PENDING_HUMAN_DATA` | 会话阻塞态，待人工提供真实资料 |
| `workflow_steps` | submit/review_approve/expert_recheck/finalize_verified 均 `blocked_pending_human_data` | 四步进度跟踪，均未执行 |
| `engineering_enabled` | `false` | 闸门保持关闭 |
| `engineering_approved` | `false` | 无 approved 输出 |

> `param` 为辅助说明字段（如「基本风压」），仅描述参数语义，不含真实数值。

### 1.2 会话不变量（写入文件 invariants 段）
- `real_fields_human_provided`：真实字段由人工提供，AI 不生成/不猜测/不补全缺失值。
- `session_knowledge_link`：`session_id` 与 `knowledge_id` 双向绑定（详见任务3）。
- `no_workflow_write`：本 Sprint 不调用工作流，不写 verified.json。
- `no_direct_verified_edit`：任何录入不得绕过工作流直接改 verified.json（任务5 硬约束）。
- `no_activation`：engineering_enabled 恒 false，不输出 approved，不创建 release_approvals.jsonl。
- `source_ref_gate`：source_ref 须先过 C1-C6 方可 submit。
- `sod_gate`：expert_recheck 主体 ≠ review_approve 主体（G2 SoD）。

---

## 任务2：Source Ref 验证（C1-C6）

复用既有 `agents/engineering/thresholds/source_ref_validator.py` 的 `validate_source_ref`，对每条 `source_ref_c1_c6` 逐条校验。会话文件内已结构化承载以下字段（全部 `pending_verification`，`status=PENDING`，`passed=false`）：

| 校验 | 字段（本文件） | 对应 validator | 要求 |
|---|---|---|---|
| C1 standard | `standard` | `standard` | 非空、完整、非占位 |
| C2 clause | `clause` | `clause` | 落在该 source 的 clause 清单（C2 一致性） |
| C3 edition | `edition` | `edition` | 4 位年份或显式版本标识 vX.Y / X.Y |
| C4 official_url | `official_url` | `url` | 可公开复核的 http(s) 链接 |
| C5 hash | `hash` | `hash` | 64 位十六进制 sha256 摘要（禁止手写，由 `compute_content_hash` 计算） |
| C6 completeness | （C1+C2） | `is_complete()` 语义 | C1+C2 即引用完整性 |

**失败处理**：任一 C 不满足 → 拒绝进入 submit，标记 `pending_verification`，不降级强行入库（对齐 3.3.1 计划 §2 步骤1）。真实 source_ref 须由人工从 3.3.2 已登记的 `spec_sources.json`（status=verified_source）条目提供；AI 不补、不猜、不补全缺失值。

---

## 任务3：KnowledgeItem 绑定（谱系）

新增 `agents/engineering/knowledge/knowledge_items_pending.json`（schema_version=2），为 E-TH-01/02/03 各建一条 `threshold_candidate` 型 KnowledgeItem（复用 3.3.0-B/C 13 字段七态契约），新增 `session_id` 反向引用完成双向绑定。

关联链路：`threshold_candidate → KnowledgeItem → Expert_Verified`

| KnowledgeItem 字段 | 取值 | 说明 |
|---|---|---|
| `knowledge_id` | `KI-pending-E-TH-xx` | 候选标识符（占位） |
| `session_id` | `SES-E-TH-xx` | 回指 threshold_entry_sessions.json 的 session_id（双向绑定） |
| `knowledge_type` | `threshold_candidate` | 仅此类允许携带候选 value |
| `parent_knowledge_id` | `pending_verification` | 派生溯源，待人工指定 parent |
| `title` / `content` | `pending_verification` | 真实内容待人工提供 |
| `source` | `pending_verification` | 引用 spec_sources.source_id |
| `author` | `pending_verification` | 引用 experts.expert_id（须 verified） |
| `domain` | `wind_pressure` | 计算域锚点（风工程域） |
| `content_hash` | `pending_verification` | 由采集流程计算，禁止手写 |
| `validation_status` | `Pending_Verification` | 七态初始态 |
| `linked_entities` | `[E-TH-xx]` | 仅引用，不承载值 |
| `created_at` / `updated_at` | `pending_verification` | 由流程写入 |

**parent_knowledge_id 谱系不变量**（写入文件 `lineage_invariants` 段，复用 3.3.0-B/C §1.2）：
- `no_cycle`：谱系禁环，不得形成递归引用。
- `weakest_parent_bound`：派生态置信不得强于其最弱父。
- `deprecated_successor`：父进入 Deprecated 须置 successor 或标记 orphan，避免悬空。
- `parent_must_exist`：parent 引用的 knowledge_id 须真实存在；当前全 `pending_verification`（待人工指定），允许暂置占位但不得转正 value 直至 parent 落实。
- `trace_only`：本文件仅承载候选，真实 value 转正须经 `ThresholdIntakeWorkflow.finalize_verified` 且 `Engineering_Approved`（G6 授权）后写入 verified.json，禁止本文件直接写入。

**关联不变量**：
- `author` 须指向已登记且 `qualification_status=verified` 且 `sign_scope` 覆盖 `domain` 的专家（复用 3.3.3 SoD R4/R5）。
- `Expert_Verified` 须经 experts 双签（review_approve 主理人 + expert_recheck 专家，SoD R1）→ Engineering_Verified（G1-G6 技术就绪）→ Engineering_Approved（G6 授权）方可转正 value。
- `Engineering_Approved` 之前，候选 value 恒 `pending_verification`，不写 `verified.json`。

---

## 任务4：ThresholdIntakeWorkflow 执行编排（review_log 完整）

对齐真实工作流 `agents/engineering/threshold_intake.py` 的四步，明确每步要求**写入 review_log**（`agents/engineering/review_log.py` 的 `append_review_event`）：

```
submit（提交）
   │ - 输入：人工提供 value/unit/source_ref/version + submitted_by
   │ - 动作：校验授权范围(allowed_ids) → validate_source_ref(C1-C6) → 写 draft 态（双签位 null）
   │ - 落 review_log：action=intake_submit
   ▼
review_approve（主理人核准）
   │ - 输入：人工核准，写 verified_by / verified_at（principal 主体）
   │ - 落 review_log：action=intake_review
   ▼
expert_recheck（行业专家复核签）
   │ - 输入：人工复核，写 expert_verified_by / expert_verified_at（expert 主体）
   │ - 校验 SoD：expert_verified_by ≠ verified_by（R1）
   │ - 落 review_log：action=intake_expert_recheck
   ▼
finalize_verified（转正）
   │ - 前置：双签俱全
   │ - 动作：置 verified=true（仍受 engineering_enabled 闸门约束）
   │ - 落 review_log：action=intake_verified
   ▼
evaluate_gates（门禁，恒 False）
```

**执行主体与红线**：
- 真实 `value` / `source_ref` / `verified_by` / `expert_verified_by` 全部由人工在调用时显式提供；AI 仅做格式校验与流程编排，**绝不**生成参数、绝不猜测缺失、绝不修改专家签署、绝不自动补 source_ref（代码注释已固化此约束）。
- 本 Sprint **不执行**上述四步（status=BLOCKED_PENDING_HUMAN_DATA）；真实执行留待人工提供资料并经主理人书面授权后，由人工或受控脚本触发。
- `review_log` 在本次结构态不产生任何事件；真实执行时每步必落一条，确保审核链完整可追溯（满足 G4）。

---

## 任务5：verified.json 保护（禁止绕过工作流直接修改）

- **硬约束**：任何阈值录入都**必须**经由 `ThresholdIntakeWorkflow`（submit→review_approve→expert_recheck→finalize_verified）写入 `verified.json`；**禁止**任何路径直接编辑 `verified.json` 的真实 `value`。
- 本 Sprint 不调用工作流，因此 `verified.json` 六条 E-TH 仍保持 `value=null` / `verified=false`（详见 §7 实测）。
- 即便未来真实录入执行，写入动作也只发生在 `finalize_verified` 步骤内（受双签 + G1-G6 门禁约束），不存在「直接改文件」的旁路。
- 防护对齐：`source_ref_validator.py` 模块红线已固化「不修改磁盘 verified.json」；`threshold_intake.py` 的写盘逻辑仅在 `finalize_verified` 内触发，且受 `evaluate_gates` 闸门限制（即便 verified=true，也绝不翻转 `engineering_enabled`）。

---

## 任务6：激活保护（即使 threshold verified，仍保持 inert）

即便未来真实录入与双签完成，本 Sprint 及后续录入阶段**仍保持**：

- `engineering_enabled = false`（config.yaml `engineering_enabled: false` 不变；loader 默认 False）。
- 不输出任何 `engineering_approved`。
- 不创建 `release_approvals.jsonl`（G6 授权由主理人书面创建，非本 Sprint 范畴）。
- 代码内置护栏：`ThresholdIntakeWorkflow.evaluate_gates()` 恒返回 `(False, reasons)`——即便阈值双签转正，也强制 `ci_green=False / rollback_ready=False / authorization_present=False`，绝不翻转 `engineering_enabled`、绝不写 config.yaml。即录入工作流任何情况下都不允许开启工程计算闸门。

**激活复核（后续 Sprint 3.3.6）才发生的动作**：重跑发布预检脚本复核全部门禁全绿 → RC 状态转 GO → 执行灰度发布启用命令。本 Sprint 不触发。

---

## 7. 红线守约验证（本 Sprint 实测）

| 红线 | 验证结果 |
|---|---|
| AI 不生成工程参数 | E-TH-01/02/03 真实 value 仍 `null`（未触碰 verified.json）；会话/KnowledgeItem 真实字段全 `pending_verification` |
| AI 不猜测规范值 | source_ref 全 `pending_verification`（含 C1-C6 结构化字段），未编造条款号/版本 |
| AI 不补全缺失 value | 缺值处均保持 `pending_verification`，无 AI 填充 |
| AI 不代签专家 | reviewer/expert 全 `pending_verification`，未落任何签署位 |
| AI 不代授权 | 未创建 ReleaseApproval；authorized_by 未填 |
| 不自动开启 engineering_enabled | config `engineering_enabled: false` 不变；evaluate_gates 恒 False |
| 不输出 engineering_approved | 全 `pending_verification`/`false`，无 approved 落盘 |
| 不写 verified.json 真实 value | verified.json 六条 E-TH value=null / verified=false 未改 |
| 禁止绕过工作流直接改 verified.json | 本 Sprint 未调用工作流；verified.json 未改（任务5 硬约束） |

**扫描执行结论**（本机）：
- 防编造扫描 `check_fabrication.py`：仅当一行同时含业务词与裸数字才报错；本 Sprint 文档/结构全程枚举值 + 字母标识符（E-TH/KI/SES），无业务裸数字 → **0 命中**。
- 硬编码扫描 `check_hardcoded.py`：仅扫 `.js/.py/.ts/.tsx`；本 Sprint 无新增工程代码 → **0 命中**。
- `engineering_enabled=False` 实测（config + loader 默认 False）。
- `verified.json` 未改（E-TH value 仍 null）；`release_approvals.jsonl` 不存在。

---

## 8. 交付物与 SSOT/路线图更新

**本 Sprint 交付物**：
1. `agents/engineering/knowledge/threshold_entry_sessions.json`（ThresholdEntrySession 会话容器 v2，E-TH-01/02/03，含 session_id/knowledge_id/C1-C6 结构化，全 pending，status=BLOCKED_PENDING_HUMAN_DATA）
2. `agents/engineering/knowledge/knowledge_items_pending.json`（threshold_candidate KnowledgeItem 关联骨架 v2，含 session_id 双向绑定 + parent_knowledge_id 谱系不变量，复用 13 字段七态）
3. `.ai/reviews/phase3.3.4_threshold_entry_execution_report.md`（本报告）

**SSOT 更新**（`project_status.json` → `task_status.phase_3_3."3.3.4"`）：status=DONE（completed_at 2026-08-02，executed_by BOIP AI Chief Architect），summary/constraints_kept/deliverables/fabrication_scan/next 齐全。

**路线图更新**（`roadmap_v3.md`）：
- §1 当前状态表 Phase 3.3 进度更新为 3.3.1+3.3.2+3.3.3+3.3.4 DONE，3.3.5+ PENDING。
- §2 在 3.3.3 块之后插入「补充 Sprint 3.3.4（DONE，2026-08-02，结构+准备态）」说明块。
- 列表区 3.3.4 由 `PENDING` 翻 `DONE`，补「增强产出（3.3.4）」子项。

---

## 9. 测试执行（相关测试 + 双扫描）

- 本 Sprint 未修改工程代码（仅新增/增强 2 个 JSON 容器 + 报告），故 `local_ci.sh` 的「如修改代码」条件未触发；但仍执行相关阈值测试以确认无回归：
  - 运行 `backend/.venv/bin/python -m pytest tests/agents/test_real_threshold_intake.py tests/agents/test_threshold_real_drill.py tests/agents/test_threshold_governance.py tests/agents/test_threshold_migration.py -q`，确认阈值录入/治理/演练机制无回归（基线沿用 CI 481 passed@90%）。
  - 运行 `check_fabrication.py` 与 `check_hardcoded.py`，确认双扫描 0 命中。
- 现有测试均使用 tmp 路径与内存夹具，不扫描 `knowledge/` 目录，新增 JSON 不影响其通过（已确认）。

---

## 10. 下一步

- 3.3.4 结构/准备态 DONE；**真实数值录入仍阻塞于人工提供**——等待主理人提供 E-TH-01/02/03 真实 value / source_ref / 专家身份，并经 3.3.3 资质审核流程登记专家、主理人书面授权。
- 真实执行顺序：人工提供资料 → 经 `ThresholdIntakeWorkflow` 四步（submit→review_approve→expert_recheck→finalize_verified，每步写 review_log）→ 满足 G1/G2/G4 → 3.3.5 真实签署执行 → 3.3.6 激活复核（G1-G6 全绿 + G6 授权 → RC 转 GO）。
- AI 全程不代录、不代签、不代授权、不开 enabled、不输出 approved。

**红线全程守约，按 3.3.4 指令「完成后停止，等待人工审核」——未填写真实工程参数、未开启 `engineering_enabled`、未输出 `engineering_approved`、未创建 ReleaseApproval、未代签代授权、未绕过工作流直接改 verified.json。**

**END**
