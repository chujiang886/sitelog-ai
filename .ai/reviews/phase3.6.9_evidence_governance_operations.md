# Phase 3.6.9 — Evidence Governance Operations（证据治理运营）主报告

- **执行身份**：BOIP AI Chief Architect（Phase 3.6.0~3.6.8 人工受控激活链路延续）
- **执行时间**：2026-08-02（会话续作）
- **前置状态**：3.6.0 DRILL ✅ → 3.6.1 证据准备 ✅ → 3.6.2 验证演练 ✅ → 3.6.3 证据接入 ✅ → 3.6.4 提交验证 ✅ → 3.6.5 终批复核 ✅ → 3.6.6 激活候选冻结 ✅ → 3.6.7 真实证据补齐 ✅ → 3.6.8 真实证据提交窗口 OPEN ✅
- **本阶段目标**：在 3.6.8 已 OPEN 的 ESW 窗口之上，**建立长期证据治理能力**（审计日志 / 生命周期 / 版本控制 / 审核队列 / 闸门关联验证）
- **最高红线 6 项（fail-closed，全程守约）**：
  ① AI 不生成真实工程参数　② AI 不生成专家身份　③ AI 不代签　④ AI 不创建 ReleaseApproval　⑤ 不自动开启 engineering_enabled　⑥ 不输出 engineering_approved
- **停止条件（已达）**：本回合**未收到任何真实人工证据载荷**，AI 仅建立治理机制（schema/状态机/版本链/队列设计）+ 只读核查真实代码 + 诚实报告。**完成后停止，保持 engineering_enabled=false，不输出 engineering_approved。**

---

## 0. 执行事实声明（诚实基线）

> 本回合用户指令**未附带任何真实人工证据载荷**（与 3.6.3/3.6.4/3.6.7/3.6.8 一致）。因此本阶段**只产出治理机制定义（机器可读 schema/状态机/版本链/队列）与真实代码 fail-closed 实证**，**不伪造、不录入任何真实证据记录**。所有 `EvidenceSubmissionLog` 字段仅在 schema 中定义，无实例数据落地。

---

## 1. 任务1 — Submission Audit Log（提交审计日志）

**交付物**：`.ai/phase3.6.9_evidence_governance/evidence_submission_log.schema.json`

定义 `EvidenceSubmissionLog` 审计行 Schema，每条记录代表一次真实证据提交的不可变审计指纹。强制字段（用户指定 6 字段，全部落地且不可缺省）：

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `submission_id` | string | `^BOIP-ESL-[0-9a-f]{16}$` | 提交审计行唯一 ID（每版本递增一次） |
| `submitter` | object | role/identity/signed | 真人提交人（role∈{principal_maintainer,domain_expert,release_owner}；**identity 由人提供，AI 不生成【红线②】**；signed 人类显式签署，**AI 不代签【红线③】**） |
| `timestamp` | string | RFC3339 UTC | 提交时间戳，缺失拒绝受理（ESW 规则） |
| `files` | array[object] | path/kind/file_hash | 真实证据文件清单（kind∈{verified_threshold,expert_register,release_approval,review_log,rollback_audit,other}，每文件带 sha256 哈希） |
| `hash` | string | `^sha256:[0-9a-f]{64}$` | 整条提交包哈希（覆盖 submitter+timestamp+files 内容），审计指纹 |
| `status` | enum | OPEN/SUBMITTED/VALIDATING/VERIFIED/ACCEPTED/REJECTED/RETURNED | 生命周期当前态 |

附加守约字段：
- `engineering_enabled_touch: false`（常量）—— 本审计行对 engineering_enabled 的影响恒为 false（**红线⑤**）。
- `red_lines_checked` —— 六红线逐项自检，全部 `const: true`。
- `version` / `previous_version` —— 版本链指针（见任务3）。

**结论**：审计日志结构就绪，等待人工经 ESW 窗口提交真实证据后由人类写入实例行。

---

## 2. 任务2 — Evidence Lifecycle（证据生命周期五态）

**交付物**：`.ai/phase3.6.9_evidence_governance/evidence_lifecycle.statemachine.json`

定义五态核心生命周期 + 合法跃迁 + 不变量：

```
OPEN ──(human_submit)──▶ SUBMITTED ──(reviewer_pickup)──▶ VALIDATING
   ▲                                                        │
   │                                                  (validation_pass)
   │                                                        ▼
RETURNED ◀──(validation_fail/approval_reject)─── VERIFIED ──(approval_sign)──▶ ACCEPTED
```

| 跃迁 | 触发 | 角色 | auto |
|---|---|---|---|
| OPEN→SUBMITTED | human_submit | human_submitter | false |
| SUBMITTED→VALIDATING | reviewer_pickup | human_reviewer | false |
| VALIDATING→VERIFIED | validation_pass | human_reviewer + domain_expert | false |
| VALIDATING→RETURNED | validation_fail | human_reviewer | false |
| VERIFIED→ACCEPTED | approval_sign | approval_reviewer | false |
| VERIFIED→RETURNED | approval_reject | approval_reviewer | false |
| RETURNED→OPEN | resubmit | human_submitter | false |

**核心不变量（I1–I5）**：
- **I1**：任一态跃迁均不得修改 `engineering_enabled`；该字段仅由人类在 `config.yaml` 显式置位，AI 仅可读断言。
- **I2**：所有合法跃迁 actor ∈ {human_submitter, human_reviewer, domain_expert, approval_reviewer}；**禁止 ai/agent/script 触发任何跃迁**。
- **I3**：`ACCEPTED` 不触发 engineering_enabled 翻转（fail-closed）；到达 ACCEPTED 仅代表人工审核链完成，**不表示工程态开启**。
- **I4**：`REJECTED` 为终态，须由人类显式决策是否重开新 submission。
- **I5**：每次合法跃迁须写入 `EvidenceSubmissionLog` 新审计行（含真人签署+时间戳），保证不可变审计链。

---

## 3. 任务3 — Evidence Version Control（证据版本控制）

**交付物**：`.ai/phase3.6.9_evidence_governance/evidence_version_control.schema.json`

管理 `version` / `hash` / `previous_version`，构建不可篡改哈希链：

- **`version`**：同证据主题下单调递增（首版=1），仅由人类提交触发递增（AI 不自动 bump）。
- **`hash`**：本版本内容 SHA-256 = `SHA256(previous_version_hash ‖ files_content ‖ metadata)`。
- **`previous_version`**：上一版本 `submission_id` 指针；首版为 `null`。
- **不可变性**：`previous_version` 与历史版本哈希不可变；改写历史须以新 `submission_id` 重开，禁止原地 mutate。
- **篡改检测**：若某版本 hash 不能由其 `previous_version_hash` + 当前 files 重算得出 → 判定漂移，审核队列立即暂停并告警。
- **冻结基线锚定**：版本链以 **3.6.6 冻结基线**（`baseline_id=BOIP-ACF-e00a7df54621257a`，`baseline_bundle_hash=aa397a20bfb6eec70472c4958353342b8e3746d5224d5438a184eee919499af6`）为 0 号锚点；任何新证据版本须从基线派生，不回溯改写基线。该基线已由 3.6.8 重算比对 `all_critical_match=True` 证实未漂移。

---

## 4. 任务4 — Review Queue（人工审核队列）

**交付物**：`.ai/phase3.6.9_evidence_governance/review_queue.schema.json`

三阶段人工审核流水线 + 强职责分离（SoD）+ 拒绝/退回路径：

| 阶段 | 顺序 | 角色 | 入口态 | 出口态 | 职责 |
|---|---|---|---|---|---|
| pending_reviewer | 1 | reviewer | SUBMITTED | VALIDATING | 形式审查：完整性/真人签名/UTC 时间戳/版本匹配基线/六红线扫描 |
| expert_review | 2 | domain_expert | VALIDATING | — | 领域专家复核 E-TH 数值/计算/规范引用（**专家身份由人提供，AI 不生成【红线②】**） |
| approval_review | 3 | approval_reviewer | VERIFIED | ACCEPTED | 双签授权复核（主理人+第二独立人）+ 发布域 G6 终验；不翻转 engineering_enabled |

- **SoD 规则**：`submitter ≠ reviewer ≠ expert ≠ approval_reviewer`；`domain_expert` 可与 `human_submitter` 重叠但不得与 `approval_reviewer` 重叠。
- **AI 禁止担任任何审核角色**（reviewer/expert/approval_reviewer/submitter）—— 防 AI 代审/代签/代专家（**红线②③**）。
- **拒绝路径**：VALIDATING → RETURNED（reviewer/expert 驳回），原版本哈希链保留为审计，须新版本号重开 OPEN。
- **退回路径**：VERIFIED → RETURNED（approval_reviewer 驳回）。
- **工程态隔离**：审核队列任一阶段通过/驳回均不修改 `engineering_enabled`（**红线⑤**）；ACCEPTED 仅代表审核链完成。

---

## 5. 任务5 — Gate 关联（Evidence 状态变化不会自动开启 engineering_enabled）

**交付物**：`.ai/phase3.6.9_evidence_governance/gate_association.verification.json`

**结论：TRUE（fail-closed）** —— 基于真实仓库代码溯源，证据状态变化（OPEN→…→ACCEPTED 任一跃迁）**不存在自动置 `engineering_enabled=true` 的代码路径**。

真实代码实证（均经本会话 Read 核实）：

| 文件 | 行 | 符号 | 事实 | 推论 |
|---|---|---|---|---|
| `agents/config_loader.py` | 121 | `load_engineering_enabled()` | 只读读 `orchestrator.engineering_enabled`（config.yaml 缺省 False）；`bool(section.get('engineering_enabled', False))`；**无写入路径** | AI 仅能读，不能写 |
| `agents/engineering/knowledge/activation/read_boundary.py` | 45 | `can_write_engineering_enabled()` | 注释「AI 不得写 engineering_enabled（仅可读断言）」，返回 `False` | 读取边界显式禁止写 |
| `agents/engineering/gate/unified_activation_gate.py` | 141 | `safety_ok = load_engineering_enabled() is False` | 顶层安全不变量：engineering_enabled 必须保持 False 否则 fail-closed | 证据到达 ACCEPTED 不改变 safety_ok 判定 |
| `agents/engineering/gate/enable_gate.py` | — | `EnableGate` | 仅判定是否允许开启，**绝不自翻、绝不输出 engineering_approved** | 状态机与 EnableGate 间无自动置位路径 |

**最终结论**：真实代码无「证据状态→engineering_enabled」写入链路。任务5 成立：**证据状态变化不会自动开启 engineering_enabled；`True` 仅能由人类在 `config.yaml` 显式置位。**

---

## 6. 六条红线守约汇总（8/8）

| # | 红线 | 本阶段守约情况 |
|---|---|---|
| ① | 不生成真实工程参数 | ✅ 仅定义 schema，E-TH value 全 null，未填充任何真实数值 |
| ② | 不生成专家身份 | ✅ experts=0；专家身份字段标注「由人提供，AI 不生成」 |
| ③ | 不代签 | ✅ submitter.signed 须人类显式置 true；AI 不代签 |
| ④ | 不创建 ReleaseApproval | ✅ 未创建；仅引用 3.6.8 既有校验结论 |
| ⑤ | 不自动开启 engineering_enabled | ✅ 真实读取 False；状态机/版本链/审核队列均无写入路径（任务5 实证） |
| ⑥ | 不输出 engineering_approved | ✅ 仅输出 NO-GO / 状态机描述，无 approved 产出 |

附加：真实证据文件只读未写；冻结基线未漂移。

---

## 7. 交付物清单

1. `.ai/reviews/phase3.6.9_evidence_governance_operations.md`（本主报告）
2. `.ai/phase3.6.9_evidence_governance/evidence_submission_log.schema.json`（任务1）
3. `.ai/phase3.6.9_evidence_governance/evidence_lifecycle.statemachine.json`（任务2）
4. `.ai/phase3.6.9_evidence_governance/evidence_version_control.schema.json`（任务3）
5. `.ai/phase3.6.9_evidence_governance/review_queue.schema.json`（任务4）
6. `.ai/phase3.6.9_evidence_governance/gate_association.verification.json`（任务5）
7. `.ai/project_status.json`（新增 `task_status.phase_3_6.9` 块）
8. `.ai/roadmap_v6.md`（新增 §13 Phase 3.6.9 章节）

---

## 8. 激活态与停止声明

- **engineering_enabled = false**（真实读取；任务5 实证架构 fail-closed，证据状态变化不翻转）。
- **未输出 engineering_approved**（仅 NO-GO / 治理模型描述）。
- **ESW 窗口（3.6.8, `BOIP-ESW-747f8b2d7847ba7c`）维持 OPEN_EMPTY**；本回合 0 真实证据进入。
- **停止条件达成**：治理机制已全部建立，无待办动作。
- **未来真实推进路径（纯人工，经 ESW 窗口）**：① 主理人+专家按 ESW 规则提交真实 E-TH 双签 / 专家登记 / review_log 链 / ReleaseApproval（每次带 UTC 时间戳+真实署名）② 窗口校验版本匹配 3.6.6 冻结基线（漂移即暂停）③ 三阶段审核队列走完（pending_reviewer→expert_review→approval_review）④ 以 3.6.6 `bundle_hash` 为基准重跑 3.6.5/3.6.7 闭环核验证据翻转且 code/config/gate 仍 MATCH ⑤ **由人类终端显式置 `engineering_enabled=true`**，届时 Gate 才可能 GO。**AI 不自动激活、无权开启。**

> 本回合指令未附带任何真实人工证据载荷，故证据治理能力已建立但证据插槽全 `pending`；激活态维持 NO-GO。真实证据须严格经 ESW 窗口线下流入，禁止自动激活。
