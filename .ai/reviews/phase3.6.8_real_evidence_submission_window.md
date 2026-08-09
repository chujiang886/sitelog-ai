# Phase 3.6.8 — Real Evidence Submission Window（真实证据提交窗口）

> **身份**：BOIP AI Chief Architect（仅建立窗口机制 + 只读核查真实仓库 + 驱动真实 gate 代码；不生产任何真实证据，无权开启激活）
> **生成时间**：2026-08-03T04:09:12Z
> **裁决**：🔴 **NO-GO**（窗口已 OPEN，但本回合 0 真实证据进入）

---

## 0. 当前状态

| 阶段 | 状态 |
|---|---|
| 3.6.0 Controlled Activation (DRILL) | ✅ DRILL PASS |
| 3.6.1 Evidence Preparation | ✅ Done |
| 3.6.2 Validation (Dry Run) | ✅ Done |
| 3.6.3 Intake | ✅ Done |
| 3.6.4 Verification | ✅ Done |
| 3.6.5 Final Review | ✅ Done |
| 3.6.6 Candidate Freeze | ✅ Done |
| 3.6.7 Evidence Completion | ✅ Done |
| **3.6.8 Submission Window** | ✅ **窗口 OPEN · NO-GO** |

---

## 1. 最高红线（全程 0 违反）

| # | 红线 | 本阶段守约 |
|---|---|---|
| ① | AI 生成真实工程参数 | ✅ 未生成（E-TH value 全 `null`） |
| ② | AI 生成专家身份 | ✅ 未生成（experts = 0） |
| ③ | AI 代签 | ✅ 未代签（无任何签署请求） |
| ④ | AI 创建 ReleaseApproval | ✅ 未创建（`release_approvals.jsonl` 不存在，仅 validate） |
| ⑤ | 自动开启 `engineering_enabled` | ✅ 真实读取 = **False** |
| ⑥ | 输出 `engineering_approved` | ✅ 仅输出 NO-GO |

**真实证据文件（verified.json / experts.json / review_log.jsonl）只读，未写。**

---

## 2. 任务1：提交窗口规则（Evidence Submission Window）

> 治理元数据，非伪造证据。落盘：`.ai/phase3.6.8_submission_window/window_rules.json`

- **window_id**：`BOIP-ESW-747f8b2d7847ba7c`
- **status**：`OPEN`（持续开放，直到主理人显式关闭）
- **定义**：真实人工证据进入激活决策系统的正式窗口

**提交人（submitter）**
- 允许角色：`principal_maintainer` / `domain_expert` / `release_owner`
- 禁止主体：`AI_agent` / `automated_script`
- 身份要求：真实人类、须可核实署名；**禁止 AI 代填/代签**
- 硬 SoD：`domain_expert` 不得兼任 `principal_maintainer`

**提交时间（submission_time）**
- 窗口开启：2026-08-03T04:09:12Z
- 有效期：持续开放直到主理人关闭；**每次提交须带 UTC 时间戳**
- 无签名 / 无时间戳 → 拒绝受理

**文件范围（file_scope）**
- 接受目标：
  - `agents/engineering/thresholds/verified.json`（按 E-TH-id 增补 value/unit/source_ref/version + 双签）
  - `agents/engineering/knowledge/experts.json`（真实专家条目）
  - `agents/engineering/release/release_approvals.jsonl`（G6 授权，七字段 + effective_time）
  - `agents/engineering/review_log.jsonl`（追加 submit/review/expert_recheck/verified 事件）
- 拒绝目标：AI 生成/补全的字段 · `engineering_enabled` 翻转 · `verified.json` 的 `verified` 由 AI 置 true · AI 创建的 ReleaseApproval 记录

**版本要求（version_requirements）**
- 须匹配 3.6.6 冻结基线（见 §4）
- 基线 bundle_id：`BOIP-ACF-e00a7df54621257a` · bundle_hash：`aa397a20bfb6eec70472c4958353342b8e3746d5224d5438a184eee919499af6`
- 漂移策略：若冻结基线任一安全关键哈希漂移 → 窗口自动暂停并告警，须重新冻结后方可继续

**流入校验（intake_checks）**
- Threshold：value/unit/source_ref/version 齐全 + 双签(主理人+专家) + 初态 `verified=false`
- Expert：专家身份真实 + SoD(expert≠principal)
- Approval：`release_approvals.jsonl` 七字段齐全 + `effective_time` + SoD(authorized≠rollback_owner)
- Rollback：`release_audit.jsonl` 须含**真实 approval_id** 的 disable/rollback/restore 实证
- Audit：`review_log` 链式 submit→review→expert_recheck→verified 完整无断裂

---

## 3. 任务2：Evidence Intake 校验（真实 gate 代码驱动）

驱动真实 `check_e_th_realization` / `check_review_log_chain` / 真实文件读取。

### 3.1 Threshold（E-TH-01/02/03）— all_realized = **false**

| 阈值 | value | unit | source_ref | version | 双签 | realized |
|---|---|---|---|---|---|---|
| E-TH-01 | ❌ null | ✅ | ❌ | ❌ | ❌ | ❌ |
| E-TH-02 | ❌ null | ❌ | ❌ | ❌ | ❌ | ❌ |
| E-TH-03 | ❌ null | ❌ | ❌ | ❌ | ❌ | ❌ |

### 3.2 Expert — complete = **false**
- 真实专家数 = **0**（`experts.json` 无条目）

### 3.3 Approval（G6）— complete = **false**
- `release_approvals.jsonl` **不存在**

### 3.4 Rollback — complete = **false**
- `release_audit.jsonl` 含 `release-operator` 的 disable/rollback/restore 实证 → **机制已演练（DRILL）**
- 但全部 `approval_id` 为空 → **非真实 G6 授权回滚实证**

### 3.5 Audit — complete = **false**
- `check_review_log_chain` → `chain_ok = false`
- 缺失事件：`submit` / `review` / `expert_recheck` / `verified`（仅 1 条 SYSTEM 事件）

**总体证据完整度 = `false`（0 真实证据载荷）**

---

## 4. 任务3：冻结基线关联（Freeze Baseline Association）

复用 3.6.6 冻结基线的**同一套文件清单与哈希算法**重算当前仓库，逐项比对。

| 锚点 | 当前 | 3.6.6 基线 | 匹配 |
|---|---|---|---|
| commit | `543c3c7a…01502` (master) | `543c3c7a…01502` | ✅ |
| **code_hash** | `e00a7df5…60d6cdd` | `e00a7df5…60d6cdd` | ✅ |
| **config_hash** | `9aa005aa…0ff2cc` | `9aa005aa…0ff2cc` | ✅ |
| **evidence_hash** | `97fb2a47…81ab4` | `97fb2a47…81ab4` | ✅ |
| UnifiedActivationGate | `9b697a8b…d3456` | `9b697a8b…d3456` | ✅ |
| ConsumptionPolicy | `96c7afd4…57dc0` | `96c7afd4…57dc0` | ✅ |
| RuntimeGuard | `55b635e0…45ba` | `55b635e0…45ba` | ✅ |

> **all_critical_match = True** —— 安全关键冻结面（code/config/gate/evidence）**未漂移**。
> runbook 因逐阶段文档演进预期增长，不列入安全关键漂移判定。

---

## 5. 任务4：Evidence Bundle 更新（New Evidence Bundle）

> 落盘：`.ai/phase3.6.8_submission_window/new_evidence_bundle.json`

- **window_id**：`BOIP-ESW-747f8b2d7847ba7c`
- **window_state**：`OPEN_EMPTY`（窗口已开启，但本回合无真实证据进入）
- 引用基线 bundle_id：`BOIP-ACF-e00a7df54621257a`
- 引用 code/config/evidence/gate 哈希：与 §4 一致
- **newly_added_evidence**：`[]`（本窗口本回合新增真实证据 = **0**）
- **newly_added_count**：`0`
- 当前 evidence_hash：`97fb2a47…81ab4`（与冻结基线一致，文件未变）
- bundle_hash：`0fc4d2aeadec1cd2b5ad3d71a4bb76f77ad25f86d38c1259f27c76551a95236d`

---

## 6. 任务5：Gate 预检查（UnifiedActivationGate，真实代码）

驱动真实 `UnifiedActivationGate.evaluate`（context 全部 False，fail-closed）。

- **verdict**：🔴 **NO-GO**
- **engineering_enabled**：`False`（真实读取）
- **auto_activation_forbidden**：`True`

**Gate 状态**

| 域 | G1 | G2 | G3 | G4 | G5 | G6 |
|---|---|---|---|---|---|---|
| threshold | ❌FAIL | ❌FAIL | ❌FAIL | ❌FAIL | ❌FAIL | ❌FAIL |
| publishing | ✅PASS | ❌FAIL | ❌FAIL | ❌FAIL | ❌FAIL | ❌FAIL |
| knowledge | — | — | — | — | — | — |

**阻塞原因（12 项）**：`G0_repository_required` / `G1_threshold_governance_incomplete` / `G2_dual_sign_incomplete` / `G3_ci_not_green` / `G4_audit_chain_incomplete` / `G5_rollback_not_ready` / `G6_authorization_missing`（阈值域 + 发布域重复计）。

---

## 7. 红线合规汇总

```
no_real_params            = true   # ① 未生成真实工程参数
no_expert_identity        = true   # ② 未生成专家身份
no_proxy_signature        = true   # ③ 未代签
no_release_approval_created = true # ④ 未创建 ReleaseApproval
engineering_enabled_false = true   # ⑤ 未开启
no_engineering_approved   = true   # ⑥ 未输出 engineering_approved
real_evidence_files_untouched = true
```

---

## 8. 裁决与后续

**裁决：NO-GO。窗口已 OPEN，但本回合无真实人工证据载荷进入；Gate 预检查 12 项阻塞，激活态维持。**

**AI 权限 = NONE** —— AI 不自动激活、无权开启 `engineering_enabled`，仅人工终端可显式置 `true`。

**后续（经 ESW 窗口的真实推进路径）**
1. 主理人 + 专家经 ESW 窗口提交真实 E-TH 双签 / 专家登记 / review_log 链 / ReleaseApproval；
2. 每次提交须带 UTC 时间戳 + 真实署名，拒绝无签名/无时间戳；
3. 窗口校验版本匹配 3.6.6 冻结基线（任一哈希漂移则暂停并告警）；
4. 以 §4 bundle_hash 为基准重跑 3.6.5/3.6.7 闭环，核验证据翻转 + 冻结仍 MATCH；
5. **人类终端显式置 `engineering_enabled=true`** → 届时 Gate 才可能 GO。

> 本回合指令未附带任何真实人工证据载荷，故窗口开启但证据插槽全 `pending`；激活态维持 NO-GO。真实解锁严格按上述线下完成，禁止自动激活。

---

## 9. 交付物

- `.ai/reviews/phase3.6.8_real_evidence_submission_window.md`（本报告）
- `.ai/phase3.6.8_submission_window_run.py`（ESW 规则 + 基线比对 + 真实 gate 预检查；只读真实文件，位于 `.ai/` 根）
- `.ai/phase3.6.8_submission_window/result.json`（权威证据：窗口 OPEN + 冻结 MATCH + NO-GO）
- `.ai/phase3.6.8_submission_window/window_rules.json`（ESW 治理规则）
- `.ai/phase3.6.8_submission_window/new_evidence_bundle.json`（窗口开启、0 新增）
- 更新 `.ai/project_status.json`（task_status.phase_3_6 新增 `3.6.8` 块）
- 更新 `.ai/roadmap_v6.md`（§12）
