# 3.2.5-H4-RC Release Candidate Validation（pending_verification）

**阶段**：3.2.5-H4-RC（首次灰度发布候选版本验证 · Release Candidate Validation）（pending_verification）
**角色**：BOIP AI Release Governance 负责人
**日期**：2026-08-01
**目标**：建立首次 `wind_pressure` 灰度 Release Candidate（RC），完成候选版本验证（RC Record / 证据绑定 / Runbook 冻结 / 最终 Pre-Release 模拟 / 风险评估）。

---

## 0. 红线守约声明

| 红线 | 状态 | 说明 |
|---|---|---|
| 1. 未开启 `engineering_enabled=true` | ✅ 守约 | `agents/config.yaml` 全局仍 `false`；RC 仅读 `config_hash` 引用，绝不翻转 |
| 2. 未输出 `engineering_approved` | ✅ 守约 | 全文仅引用概念，无任何 approved 输出 |
| 3. 未生成真实工程参数 | ✅ 守约 | `ReleaseCandidateRecord` 仅承载哈希引用；E-TH-01/02/03 仍 `null`（pending_verification），不猜测、不生成 |
| 4. 未生成专家签名 | ✅ 守约 | 双签/专家复核由人工线下经 `ThresholdIntakeWorkflow` 落 `review_log`，RC 不代签 |
| 5. 未创建 `ReleaseApproval` | ✅ 守约 | G6 授权由主理人书面创建；`release_approvals.jsonl` 仍不存在；RC 不代建 |

> 本阶段新增 `ReleaseCandidateRecord` 数据类与只读采集函数，**零生产写入**：不创建/修改任何生产证据文件，不设置 `ci_green` / `rollback_ready`。真实放量仍须各角色线下补齐证据 + G1-G6 全绿方可 `gray_release_ctl.py enable wind_pressure`。

---

## 1. 概览与当前真实态

- **RC 接口**：`wind_pressure`
- **commit**：`543c3c7a651b158b6c8f76ad99666aef058a1502`（HEAD，与 H3-B 冻结记录同 commit）
- **前置交付物**：H3-B 证据冻结（`release_freeze_record.json`）、H4-A Runbook（`.ai/tasks/phase3.2.5H4A_release_runbook.md`）
- **本次新增**：`agents/engineering/release/candidate.py`（`ReleaseCandidateRecord` + `collect_release_candidate`）、`tests/agents/test_release_candidate.py`（9 passed）、`release_candidate_record.json`
- **真实态（任务4 模拟）**：G1-G6 全 `false`、`verified_integrity=true` → **Final Candidate Decision = NO-GO**
- **RC 决策**：`ReleaseCandidateRecord.decision = NO-GO`（证据包未齐备 + Runbook 已冻结但证据缺位）

---

## 2. 任务1：Release Candidate Record 设计

**代码位置**：`agents/engineering/release/candidate.py`

**数据类 `ReleaseCandidateRecord`**（核心六字段 + 只读绑定字段）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `candidate_id` | str | 由 `interface + commit_hash` 确定性生成（`BOIP-RC-` + sha256[:16]），冻结语义下稳定可复现 |
| `commit_hash` | str | 绑定发布 commit（HEAD） |
| `config_hash` | Optional[str] | `agents/config.yaml` 的 sha256（仅引用，绝不翻转 `engineering_enabled`） |
| `evidence_bundle_id` | str | 绑定 H3-B 证据包 id（确定性重算） |
| `runbook_version` | str | 冻结的 Runbook 版本（`3.2.5-H4-A`） |
| `created_at` | str | UTC 时间戳 |
| `runbook_hash` | Optional[str] | H4-A Runbook 文件 sha256（Runbook 冻结引用） |
| `evidence_binding` | dict | 五类证据哈希 + 存在性标记（只读引用） |
| `notes` | list[str] | 缺失/异常说明 |

**本次生成的 RC 实例**（只读采集）：

| 字段 | 值 |
|---|---|
| candidate_id | `BOIP-RC-8652324bb01db0e5` |
| commit_hash | `543c3c7a651b158b6c8f76ad99666aef058a1502` |
| config_hash | `9aa005aa598dedf75969d12a17f155aa6e27d86dec33cb1c173a7d5b6a0ff2cc` |
| evidence_bundle_id | `BOIP-EB-fb5469bfb0430e2c` |
| runbook_version | `3.2.5-H4-A` |
| runbook_hash | `8a6490384b12d727b4e90df8e88cb6a5c2de246804c5003d0ca926e7eeebe844` |
| decision | **NO-GO** |

---

## 3. 任务2：Evidence Bundle 绑定

RC 经由 `collect_release_evidence_bundle` 绑定 H3-B 五类证据（只读哈希引用，非数值）：

| 证据类别 | 绑定字段 | 真实态 |
|---|---|---|
| Threshold Evidence | `threshold_evidence_hash` | 存在（`verified.json` 存在）；`threshold_evidence_present=true` |
| Review Evidence | `review_log_hash` | 存在但缺四类 intake 事件；`review_evidence_present=false` |
| Authorization Evidence | `authorization_hash` | `null`（授权库不存在）；`authorization_present=false` |
| CI Evidence | `ci_evidence_hash` | 引用 CI 事实字典哈希（基线 481@90%） |
| Rollback Evidence | `rollback_evidence_hash` | 存在（`gray_release_ctl.py` 存在） |

> 绑定语义：RC 通过 `evidence_bundle_id` 锚定 H3-B 证据包，并将五类证据哈希内嵌于 `evidence_binding`。证据缺失处如实记录 `null` / `False`，**不伪造**。

---

## 4. 任务3：Runbook Freeze

冻结 H4-A Runbook 版本，记录 `hash / version / timestamp`：

| 项 | 值 |
|---|---|
| version | `3.2.5-H4-A` |
| hash（sha256） | `8a6490384b12d727b4e90df8e88cb6a5c2de246804c5003d0ca926e7eeebe844` |
| timestamp | RC 创建时刻（UTC，见 `release_candidate_record.json` `created_at`） |
| 文件 | `.ai/tasks/phase3.2.5H4A_release_runbook.md` |

> Runbook 已冻结（hash 写入 RC 记录）。任何后续 Runbook 变更须重新冻结并 bump 版本。

---

## 5. 任务4：Final Pre-Release 模拟

执行 `release_precheck(interface="wind_pressure", return_report=True)`（不注入任何外部条件，默认全 `false`）：

**G1-G6 门禁真实态**：

| 门禁 | 状态 | 阻断原因 |
|---|---|---|
| G1 阈值治理 | ❌ False | `threshold_status` 非 verified（draft/review），不纳入工程判定 |
| G2 双签 | ❌ False | `mgmt_signed` / `expert_signed` 缺位 |
| G3 CI | ❌ False | `ci_green` 未确认（引用基线，未自动置位） |
| G4 审核链 | ❌ False | `review_log` 缺四类 intake 事件 |
| G5 回滚 | ❌ False | `rollback_ready` 未确认 |
| G6 授权 | ❌ False | `release_approvals.jsonl` 不存在 |
| verified_integrity | ✅ True | 无绕过直接改库 |

**Final Candidate Decision：NO-GO**（G1-G6 全阻断，就绪度 0/6 = 0%）。

> 门禁判定链路：`release_precheck` → `ProductionReadinessChecker.run()` → `can_enable_engineering`（G1-G6 唯一事实来源）。默认拒绝，安全。

---

## 6. 任务5：发布风险评估

### 6.1 技术风险
- **工程链路未就绪（高）**：G1-G6 全阻断，RC 不可放行；当前若执行 `enable` 会被 `controller` 五步前置拒绝（REJECTED_GATE_BLOCKED），**无意外放量风险**。
- **RC 仅引用哈希（低）**：`ReleaseCandidateRecord` 不承载真实参数，无代码执行副作用，无引入新故障面。
- **冻结记录 bundle_id 不一致（中，治理卫生）**：见第 8 节。

### 6.2 工程风险
- **真实阈值缺位（高）**：E-TH-01/02/03 仍 `null`（pending_verification），G1/G2 无法过。
- **审核链不完整（高）**：`review_log` 仅含 `schema_established`，缺 `intake_submit / intake_review_approve . intake_expert_recheck . intake_verified` 四类事件，G4 不过。
- **授权缺位（高）**：`release_approvals.jsonl` 不存在，G6 不过；RC **不自动创建**授权（红线 5）。
- **CI / 回滚未确认（中）**：`ci_green` / `rollback_ready` 仅引用基线事实，未自动置位（红线约束），G3/G5 不过。

### 6.3 责任风险
- **SoD 未建立（高）**：`authorized_by` / `rollback_owner` 均未指定，无法校验 `authorized_by ≠ rollback_owner`。
- **角色未就位（高）**：专家（G1/G2 双签）、主理人（G6 授权）、发布执行人、监控值守、回滚负责人职责边界清楚但未实际任命。
- **AI 不代签/不代授权（已守约）**：全部签名/授权由人工线下经正式流程提供，AI 仅作只读核验与记录，责任边界清晰。
- **绕过硬发布风险（中）**：若人工绕过 `gray_release_ctl` 直接改 `gray_release.json`，`manual_modified_thresholds` 与 `verified_integrity` 检测会标记异常，但需运维纪律配合。

---

## 7. RC 记录产物与红线守约

- **产物**：`release_candidate_record.json`（仅承载哈希引用，不写真实参数）。
- **代码**：`agents/engineering/release/candidate.py` + `tests/agents/test_release_candidate.py`（9 passed，连同 H3-B 证据包测试共 17 passed）。
- **红线**：五条全守约（见第 0 节）；`engineering_enabled=false`；无 `engineering_approved` 输出；无真实参数/签名/授权生成。

---

## 8. 治理一致性发现（建议项，非阻断）

H3-B 冻结记录 `release_freeze_record.json` 记录的 `bundle_id = BOIP-EB-0561f7197d25d24b`，但本次按当前确定性算法从同一 commit 重算得 `BOIP-EB-fb5469bfb0430e2c`（且 `config_hash` 完全一致，证实 commit 相同）。差异源于 H3-B 在 `_bundle_id` 确定性修复落地前写入了该 id。

**建议**：以当前确定性算法重新生成 `release_freeze_record.json` 的 `bundle_id`，使 H3-B 冻结记录与 H4-RC 绑定 id 一致，消除治理追踪歧义。本任务不擅自改写 H3-B 产物，留作主理人确认后的收尾动作。

---

## 9. 进入条件与收口

仅当满足以下全部条件，RC 方可由 NO-GO 转为 GO 并进入真实执行：
1. G1：E-TH-01/02/03 真实化且 `governance_status=ok`；
2. G2：`mgmt_signed` AND `expert_signed` 齐备；
3. G3：人工确认 `ci_green`（基线 481@90%）；
4. G4：`review_log` 含完整四类 intake 事件链；
5. G5：`rollback_ready` 人工确认；
6. G6：`release_approvals.jsonl` 存在生效记录且满足 SoD；
7. `verified_integrity=true`（已满足）。

否则 RC 维持 NO-GO，仅作候选快照，不触发任何执行。

*防编造声明：本评审所有标识（BOIP-RC-/BOIP-EB-、E-TH-01/02/03、版本号 3.2.5-H4-RC/H4-A）、配置/证据哈希均为治理引用，非真实工程参数；真实数值、签名、授权均 pending_verification，由人工经正式流程提供。*

---

**结论**：H4-RC 完成首次 `wind_pressure` 灰度 RC 的建立与验证——`ReleaseCandidateRecord` 已落地、五类证据已绑定、H4-A Runbook 已冻结（hash 已记）、最终 Pre-Release 模拟输出 **NO-GO**（G1-G6 全阻断）。五条红线全守约，零生产写入。待人工补齐五类证据后重跑 `release_precheck` 复核全绿，RC 方可转 GO 并按 H4-A Runbook 执行发布。
