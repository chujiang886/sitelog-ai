# Phase 3.3 Sprint 3.3.1 — Real Engineering Knowledge Activation 执行报告（pending_verification）

**阶段**：Phase 3.3 Engineering Knowledge Activation
**Sprint**：3.3.1 Real Engineering Knowledge Activation（执行）
**身份**：BOIP AI Chief Architect
**日期**：2026-08-01
**前置**：Phase 3.2 已正式收口（`.ai/reviews/phase3.2_closing_report.md`），工程审核闭环治理与基础设施 inert 就绪；Phase 3.3 已建立（`.ai/roadmap_v3.md`，`PHASE_3_3_READY`）。

---

## 0. 红线守约总览

| # | 红线 | 本 Sprint 守约核验 |
|---|---|---|
| 1 | 不录入真实工程参数 | `verified.json` 未改动，`E-TH-01/02/03` 真实 `value` 仍 `null`（见 §7） |
| 2 | 不开 `engineering_enabled` | `agents/config.yaml` 第102行 `engineering_enabled: false`；loader 实测 `False`（见 §7） |
| 3 | 不输出 `engineering_approved` | 全 `pending_verification`，无 approved 落盘/输出 |
| 4 | 不创建 `ReleaseApproval` | `release_approvals.jsonl` 不存在（见 §7） |
| 5 | 不代签/代授权 | 仅编排容器与流程，未写入任何真实签名/授权 |

**核验结论**：五条红线全程守约；本 Sprint 为纯治理基座建立（数据 + 文档），零代码改动、零生产写入。

---

## 1. 任务1：Spec Source Registry（规范来源登记容器）

**交付**：`agents/engineering/knowledge/spec_sources.json`（新建，仅结构）。

**字段**（与任务书一致）：`source_id` / `standard` / `title` / `publisher` / `edition` / `official_url` / `retrieved_at` / `clause_index`。

**C1-C6 校验支撑**（在文件 `c1_c6_support` 段显式映射，复用 `source_ref_validator.py` 与 `schema.py`）：
- C1 standard ← `standard`
- C2 clause ← `clause_index`（本规范可用条款号清单；阈值 `source_ref.clause` 须落其中）
- C3 edition ← `edition`（须 4 位年份或 `vX.Y`）
- C4 url ← `official_url`（须 http(s) 可复核）
- C5 hash ← 由 `source_ref` 引用内容 sha256 派生（登记时填充，禁止手写）
- C6 完整性 ← C1 + C2（即 `ThresholdSourceRef.is_complete()`）

**结构形态**：含 `schema_version`、`note`、`c1_c6_support` 映射说明、`sources`（空数组，待人工登记）、`_example_entry`（全 `pending_verification` 示范条目）。**未填写任何真实条款参数**。

---

## 2. 任务2：Expert Registry（专家资料登记容器）

**交付**：`agents/engineering/knowledge/experts.json`（新建，仅结构）。

**字段**（与任务书一致）：`expert_id` / `domain` / `qualification_ref` / `sign_scope` / `sod_role`。

**签署角色对齐**（在 `signer_alignment` 段显式映射）：
- `review_log` signer 标识符（`principal-xxx` / `expert-xxx`）↔ 本表 `expert_id`
- `verified_by`（主理人核准）↔ `sod_role=principal`
- `expert_verified_by`（行业专家复核签）↔ `sod_role=expert`
- `authorized_by`（G6 授权）↔ principal，且须 `≠ rollback_owner`
- `rollback_owner`（回滚责任）↔ principal，且须 `≠ authorized_by`

**SoD 规则**：`sod_roles` 段声明 principal / expert 两类角色与互斥约束。**未填写任何真实专家身份**。

---

## 3. 任务3：Threshold Entry Plan（真实阈值录入计划，文档）

**交付**：`.ai/tasks/phase3.3.1_threshold_entry_plan.md`（新建，计划态，不执行）。

编排 `E-TH-01/02/03` 经 `ThresholdIntakeWorkflow` 的录入五步：① `source_ref` 验证（C1-C6）② submit ③ review_approve（写 `verified_by/at`）④ expert_recheck（写 `expert_verified_by/at`，SoD）⑤ finalize_verified（置 `verified=true`）。含执行人/复核人/时间窗占位表、录入前置门禁清单（G1/G2/G4）、失败处理与红线不变量。**不执行录入**。

---

## 4. 任务4：Spec Version Strategy（规范版本管理策略，文档）

**交付**：`.ai/tasks/phase3.3.1_spec_version_strategy.md`（新建，策略态，不执行数据变更）。

定义：`schema_version`（v1/v2，复用 `schema.py` 常量，`CURRENT_SCHEMA_VERSION=2`）、每条 `version` 语义化（规范号-年号）、`deprecated` 拒绝加载（`ThresholdStatus.DEPRECATED` + `is_loadable`）、rollback 路径（快照优先 + deprecated 降级 + 审核链不可篡改 + 迁移自动回滚）。**不修改生产 `verified.json`、不触发迁移写入**。

---

## 5. 任务5：Expert Signing Plan（专家签署计划，文档）

**交付**：`.ai/tasks/phase3.3.1_expert_signing_plan.md`（新建，计划态，不执行签署）。

定义：① 双签流程（主理人 `verified_by/at` → 专家 `expert_verified_by/at`，落 `review_log`）② G6 流程（`EngineeringReleaseApproval` 七字段，落 `release_approvals.jsonl`）③ SoD 规则（`expert_verified_by ≠ verified_by`、`authorized_by ≠ rollback_owner`、G6 主体独立于双签主体）④ 签署落点确认（双签→`review_log`、G6→`release_approvals.jsonl`、监控→`approved_monitor.jsonl`）。**不代签、不创建 `ReleaseApproval`、不输出 approved**。

---

## 6. 测试与扫描

**本 Sprint 性质**：纯数据 + 文档，无新增代码 → 不触发 `local_ci.sh` 重跑；**沿用 CI 基线 `481 passed@90%`（`local_ci.sh` 8/8 全绿）**。

**防编造扫描**：`scripts/lint/check_fabrication.py --root .` → **0 命中**，退出码 0（新增 JSON/文档含 `pending_verification` 占位，无业务词+数字误报）。

**硬编码扫描**：`scripts/lint/check_hardcoded.py --root .` → **0 命中**，退出码 0。

---

## 7. 红线校验（Bash 实测）

| 检查项 | 命令/来源 | 结果 |
|---|---|---|
| `engineering_enabled` | `agents/config.yaml` 第102行 + `load_engineering_enabled()` | `false`（实测 `False`） |
| `release_approvals.jsonl` | 仓库根 + `agents/engineering/` | 均不存在 |
| `verified.json` 真实 value | 读取 `agents/engineering/thresholds/verified.json` | `E-TH-01/02/03` 仍 `value=null`、`verified=false`、双签 `null`（未改动） |
| `engineering_approved` 输出 | 全仓检索 | 无新增 approved 落盘/输出 |
| 新建 JSON 合法性 | `json.load` | 两份 JSON 均解析通过 |

---

## 8. SSOT / roadmap 更新

- `.ai/project_status.json`：`task_status.phase_3_1.phase_3_3."3.3.1".status` 由 `READY` 置为 `DONE`；补 `fabrication_scan="0 命中（退出码 0）"`；`deliverables` 补全五份产物路径。
- `.ai/roadmap_v3.md`：§2 首 Sprint 3.3.1 行由 `READY` 更新为 `DONE`（基座态）；追加里程碑行。

---

## 9. 未完成与下一步

**本 Sprint 收口**：五类管理基座（规范来源容器 / 专家资料容器 / 阈值录入计划 / 规范版本策略 / 专家签署计划）全部就绪 → **3.3.1 DONE（基座态）**。

**仍 pending_verification（人工/后续 Sprint 动作）**：
- 真实规范 ingestion（3.3.2）→ 填 `spec_sources.json` 真实条目
- 真实专家 onboarding（3.3.3）→ 填 `experts.json` 真实名录
- 真实阈值录入执行（3.3.4，须主理人审核 + 单独书面授权）→ 填 `E-TH-01/02/03` 真实 `value`
- 真实签署执行（3.3.5）→ 双签落 `review_log` + G6 落 `release_approvals.jsonl`
- 激活复核（3.3.6）→ 重跑 `release_precheck(wind_pressure)` 复核 G1-G6 全绿 → RC 转 GO → `gray_release_ctl.py enable wind_pressure`（pending_verification）

**遗留（沿用）**：H3-B 冻结记录 `bundle_id` 不一致（建议以当前确定性算法重生成，待主理人确认）；技术债 OPEN=13。

*防编造声明：本报告指出所有 E-TH 标识符、schema 常量、七字段、版本号均为代码既有定义引用或占位，非真实工程参数；真实数值、专家身份、签名、授权均 pending_verification。*
