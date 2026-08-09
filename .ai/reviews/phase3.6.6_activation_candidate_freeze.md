# BOIP Phase 3.6.6 — Activation Candidate Freeze（激活候选版本冻结）

- **身份**：BOIP AI Chief Architect
- **日期**：2026-08-03（冻结执行时间 `2026-08-03T03:30:37Z`）
- **前置**：Phase 3.6.0 ✅ / 3.6.1 ✅ / 3.6.2 ✅ / 3.6.3 ✅ / 3.6.4 ✅ / 3.6.5 ✅
- **目标**：冻结「未来人工激活所依据的唯一版本」——把当前仓库真实状态锚定为可复现、可比对、不可篡改的激活候选基线。

---

## 0. 最高红线（全程禁止，6/6 守约）

| # | 红线 | 本阶段遵守 |
|---|------|-----------|
| ① | AI 生成真实工程参数 | ✅ 未生成任何 E-TH 真实数值 |
| ② | AI 生成专家身份 | ✅ 未编造任何专家 |
| ③ | AI 代签 | ✅ 未代任何角色签署 |
| ④ | AI 创建 ReleaseApproval | ✅ 未调用 `append_approval_record` |
| ⑤ | 自动开启 `engineering_enabled` | ✅ 冻结态 = `False`（真实读取确认） |
| ⑥ | 输出 `engineering_approved` | ✅ 仅 `FROZEN_NO_GO`，未输出 approved |

> **真实证据现状诚实声明**：本回合指令**仍未附带任何「真实人工提供的激活证据」载荷**。冻结是对**当前仓库真实状态**的快照，真实证据仍为 `pending_verification / 未提交`，故冻结基线天然是 `NO-GO`。冻结不伪造任何证据。

---

## 1. 任务1：代码版本冻结（Code Freeze）

| 项 | 值 |
|----|----|
| commit_hash（全） | `543c3c7a651b158b6c8f76ad99666aef058a1502` |
| commit（短） | `543c3c7` |
| branch | `master` |
| commit_timestamp | `2026-07-28T16:09:32+08:00` |
| **code_hash**（15 个激活相关源文件拼接 sha256） | `e00a7df54621257a3786c1d23bbc1e3ea27d2b492675e1054ceaab09260d6cdd` |
| 参与文件数 | 15 |
| working_tree_dirty | **True**（见下） |

**working tree 脏状态说明（诚实）**：当前 `git status` 存在未提交改动，主要为本 Phase 3.6.x 系列报告与若干源码微调（如 `agents/config_loader.py`、`agents/engineering/agent.py`、`scripts/lint/check_fabrication.py`）。`code_hash` 已对**工作树实际内容**求哈希，因此冻结锚点同时覆盖「已提交 commit + 未提交工作树」，比单纯 commit hash 更精确。若要求纯 commit 锚点，`543c3c7` 即对应；若后续提交这些改动，code_hash 将随之变化，须以本冻结清单为权威比对基准。

参与冻结的 15 个激活相关源文件：
`agents/config_loader.py`、`agents/engineering/gate/unified_activation_gate.py`、`agents/engineering/gate/enable_gate.py`、`agents/engineering/knowledge/activation/gate.py`、`agents/engineering/release/gate.py`、`agents/engineering/knowledge/activation/consumption.py`、`agents/engineering/knowledge/activation/consumer_guard.py`、`agents/engineering/knowledge/activation/runtime_integration.py`、`agents/engineering/release/readiness.py`、`agents/engineering/release/evidence_bundle.py`、`agents/engineering/release/approval.py`、`agents/engineering/threshold_loader.py`、`agents/engineering/threshold_intake.py`、`agents/engineering/thresholds/schema.py`、`agents/engineering/review_log.py`。

---

## 2. 任务2：配置冻结（Config Freeze）

| 项 | 值 |
|----|----|
| config 文件 | `agents/config.yaml`（`orchestrator.engineering_enabled` 权威源） |
| **config_hash**（sha256） | `9aa005aa598dedf75969d12a17f155aa6e27d86dec33cb1c173a7d5b6a0ff2cc` |
| `engineering_enabled` | **False** ✅（调用 `load_engineering_enabled()` 真实读取，缺省 False） |
| 预期 `false` | ✅ 一致 |

> 未对 `.env` 取哈希（含密钥，避免泄露）；`config.yaml` 为 `engineering_enabled` 唯一权威配置源，已锚定冻结。

---

## 3. 任务3：Evidence Bundle 冻结（ActivationCandidateBundle）

生成 `ActivationCandidateBundle`，聚合三类哈希 + 证据状态：

| 字段 | 值 |
|------|----|
| **bundle_id** | `BOIP-ACF-e00a7df54621257a` |
| **bundle_hash**（全包 sha256） | `aa397a20bfb6eec70472c4958353342b8e3746d5224d5438a184eee919499af6` |
| frozen_at | `2026-08-03T03:30:37.507076+00:00` |
| code_hash | `e00a7df5…60d6cdd` |
| config_hash | `9aa005aa…0ff2cc` |
| **evidence_hash**（真实证据文件拼接 sha256） | `97fb2a47d367c9dc8cd6db3801f3bc3e1f87f51a359505cac725a0b26f381ab4` |
| engineering_enabled_at_freeze | `False` |

**evidence 文件哈希（真实，只读）**：

| 证据文件 | 存在 | sha256 |
|----------|------|--------|
| `thresholds/verified.json` | ✅ | `c4b44713a37529551fe9c8069b1ce069e1b9fc77cad357a70349349ece223845` |
| `review_log.jsonl` | ✅ | `a4251636bd7726c06de36bb5a736ff909a5881352357d10f2ccf5f6375a6bb44` |
| `knowledge/experts.json` | ✅ | `b84b1b7377ec4d9bfe883394912a195abb8b6ed8b5903aa182407b0a4ef928c5` |
| `release/release_approvals.jsonl` | ❌ 不存在 | `null` |

**证据状态（诚实）**：`verified.json` 中 E-TH-01/02/03 全部 `value=null / verified=false / 无双签`；`experts.json` 专家数 = 0；`release_approvals.jsonl` 不存在；`review_log.jsonl` 仅 1 条 SYSTEM 事件。**结论：`ALL_PENDING_NO_REAL_EVIDENCE`，冻结态不可变证据包 `complete=False`。**

---

## 4. 任务4：Gate 版本冻结（Gate Version Freeze）

| Gate 模块 | 源文件 | version_hash（sha256） |
|-----------|--------|------------------------|
| **UnifiedActivationGate** | `agents/engineering/gate/unified_activation_gate.py` | `9b697a8b288af09143493689a3d504e68aa7b406aad8269dc6e7f26eb57d3456` |
| **ConsumptionPolicy** | `agents/engineering/knowledge/activation/consumption.py` | `96c7afd4a5a191ec5334f338321ef9d20f0909421744cd8704152fa6f6557dc0` |
| **RuntimeGuard** | `agents/engineering/knowledge/activation/runtime_integration.py` | `55b635e08f5d575b5404f8f77e4254003343fc7bb941fcff5bfa2b5aaa8645ba` |

> 各模块无显式 `__version__` 字符串，故「版本」以**内容哈希**锚定（内容不变则版本不变）。三者均实现 fail-closed 不变量：UnifiedActivationGate 顶层 `safety_ok = load_engineering_enabled() is False`；ConsumptionPolicy 非 `Engineering_Approved` 必标 `pending_verification`；RuntimeGuard 只读判定不开启 `engineering_enabled`、不输出 `engineering_approved`。

---

## 5. 任务5：Runbook 冻结（Activation Runbook Freeze）

激活流程文档（runbook）已锚定哈希，作为未来人工激活的**唯一流程依据**：

| runbook 文档 | 存在 | hash |
|--------------|------|------|
| `.ai/roadmap_v6.md`（含 §3.2 解锁清单 / §5–§9 各阶段） | ✅ | 见 `runbook_hash` |
| `.ai/reviews/phase3.6.0_controlled_activation_execution_report.md` | ✅ | — |
| `.ai/reviews/phase3.6.1_real_activation_evidence_preparation.md` | ✅ | — |
| `.ai/reviews/phase3.6.2_activation_evidence_validation_dry_run.md` | ✅ | — |
| `.ai/reviews/phase3.6.3_real_activation_evidence_intake_report.md` | ✅ | — |
| `.ai/reviews/phase3.6.4_real_evidence_submission_verification.md` | ✅ | — |
| `.ai/reviews/phase3.6.5_final_human_activation_review.md` | ✅ | — |

**runbook_hash**（7 文档拼接 sha256）：`84b4cf101e81e8baeaf586d35f1839bfebee6b20e5475fc72f3bbe59cf3bf8d1`
（缺失文档：无；全部 7 份均存在。）

---

## 6. 任务6：Freeze 报告（本文件）& 最终裁决

### ActivationCandidateBundle（冻结权威记录）

```
bundle_id        : BOIP-ACF-e00a7df54621257a
bundle_hash      : aa397a20bfb6eec70472c4958353342b8e3746d5224d5438a184eee919499af6
frozen_at        : 2026-08-03T03:30:37.507076+00:00
code_hash        : e00a7df54621257a3786c1d23bbc1e3ea27d2b492675e1054ceaab09260d6cdd
config_hash      : 9aa005aa598dedf75969d12a17f155aa6e27d86dec33cb1c173a7d5b6a0ff2cc
evidence_hash    : 97fb2a47d367c9dc8cd6db3801f3bc3e1f87f51a359505cac725a0b26f381ab4
gate_versions    : UnifiedActivationGate=9b697a8b… / ConsumptionPolicy=96c7afd4… / RuntimeGuard=55b635e0…
runbook_hash     : 84b4cf101e81e8baeaf586d35f1839bfebee6b20e5475fc72f3bbe59cf3bf8d1
engineering_enabled_at_freeze : False
```

### 最终裁决：`FROZEN_NO_GO`

- 激活候选版本**已冻结**：commit `543c3c7` + 工作树 / config `False` / 证据全 `pending` / gate 代码版本已锚定。
- **AI 无权开启 `engineering_enabled`**：本冻结仅锚定状态，不激活、不输出 `engineering_approved`。
- 未来人工激活须在**同一冻结基线**上补齐真实证据（真实 E-TH 双签录入 → 专家登记签署 → 真实 ReleaseApproval 落盘 → review_log 补齐四类审核事件链 → local_ci 8/8 → Rollback Dry Run），并由人类终端显式置 `engineering_enabled=true`。届时以本 `bundle_hash` 为比对基准，重跑 3.6.4/3.6.5 闭环，各任务方会从 `PENDING` 翻转为 `VERIFIED`，gate 才可能 GO。

---

## 7. 红线复核（6/6 守约）

```
no_real_params            : True
no_expert_identity        : True
no_proxy_signature        : True
no_release_approval_created: True
engineering_enabled_false : True
no_engineering_approved   : True
real_evidence_files_untouched: True
→ 全部 True，红线 0 违规。
```

---

## 8. 交付物

- 本报告：`.ai/reviews/phase3.6.6_activation_candidate_freeze.md`
- 冻结机制脚本：`.ai/phase3.6.6_freeze_run.py`
- 冻结清单（权威证据）：`.ai/phase3.6.6_freeze/freeze_manifest.json`
- 候选包快照：`.ai/phase3.6.6_freeze/activation_candidate_bundle.json`
- SSOT 更新：`.ai/project_status.json` → `task_status.phase_3_6["3.6.6"]`
- Roadmap 更新：`.ai/roadmap_v6.md` → §10

---

## 9. 后续（待主理人 + 专家线下）

1. 真实 E-TH-01/02/03 经 `ThresholdIntakeWorkflow` 四步录入（主理人 `review` + 专家 `expert_recheck`，SoD）；
2. 专家登记并签署（`experts.json` 填充 + 双签）；
3. 线下创建真实 `EngineeringReleaseApproval`（七字段 + `effective_time` + SoD）；
4. `review_log.jsonl` 补齐 `submit/review/expert_recheck/verified` 四类链式事件；
5. 人类终端 `local_ci.sh` 8/8 绿（已实证可达）；
6. 真实 Rollback Dry Run（`scripts/release/gray_release_ctl.py` snapshot/disable/rollback/restore）；
7. **人类终端显式置 `orchestrator.engineering_enabled=true`**（须 G6 授权记录在先）——**AI 不自动激活**。

按指令**完成后停止**：保持 `engineering_enabled = false`，未输出 `engineering_approved`。
