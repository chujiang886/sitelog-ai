# Phase 3.9.4 — Audit Contract Provenance Closure（审计契约溯源收口）

> 任务来源：Phase 3.9.4 §六 / Task 0。
> 执行日期：2026-08-12。
> 调查方法：git 对象级比对（`git show <ref>:agents/enterprise/audit.py`）+ 正则抽取 `AuditActionCategory` 成员 + 全仓 usage grep + 未提交工作树核查。

## 1. 权威基线（实测，非沿用摘要）

| 参照点 | AuditActionCategory 成员数 | 说明 |
|---|---|---|
| `1f223db`（Phase 3.9.2 收口 commit） | **83** | 3.9.2 提交基线（RELEASE_* 4 类，79→83） |
| `8c7c9c5`（Phase 3.9.3 收口 commit） | **96** | 当前真实总数（含 3.9.3 自身 +7 与前序遗留 +6） |
| 增量 `1f223db → 8c7c9c5` | **+13** | 其中 3.9.3 自身 +7，前序遗留 +6 |
| 3.9.3 起点工作树（未计本阶段新增） | **89** | = 83(基线) + 6(前序遗留，当时未提交) |
| 3.9.3 自身新增 | **+7** | OBSERVABILITY_HEALTH_CHECK / ALERT_CANDIDATE_CREATED / INCIDENT_CREATED / INCIDENT_HUMAN_ACKNOWLEDGED / INCIDENT_HUMAN_RESOLVED / INCIDENT_HUMAN_CLOSED / POSTMORTEM_DRAFT_CREATED |
| 前序遗留（未正式归属） | **+6** | 见 §2 |

> ⚠️ 与主理人授权书假设的差异：授权书假定「83 → 88（+5）」「当前 = 95」。
> 实测真实值为「83 → 89（+6，起点工作树已含）」→ 96。差异源于 3.9.3 收口时把前序未提交的 audit 改动一并随 `audit.py` 入库，但当时叙事按「+5 / 95」记录，**少计 1 类（实为 +6 / 96）**。本文件以实测为准，并纠正 3.9.3 文档中的陈旧数字。

## 2. +6 前序遗留审计类别（溯源结论）

| 类别名 | 语义 | 实现状态 |
|---|---|---|
| `ACTIVATION_EVIDENCE_BUNDLE_GENERATED` | 受控激活证据包生成 | enum + `record_*` 已提交（8c7c9c5） |
| `CONTROLLED_ACTIVATION_GATE_EVALUATED` | 受控激活闸门评估 | enum + `record_*` 已提交（8c7c9c5） |
| `HUMAN_ACTIVATION_APPROVAL_RECORDED` | 人类激活批准留痕 | enum + `record_*` 已提交（8c7c9c5） |
| `RC_FREEZE_GENERATED` | 发布候选(RC)冻结清单生成 | enum + `record_*` 已提交（8c7c9c5） |
| `RC_FREEZE_CHECK_PASSED` | RC 冻结一致性检查通过 | enum + `record_*` 已提交（8c7c9c5） |
| `RC_FREEZE_VERIFIED` | RC 冻结核验 | enum + `record_*` 已提交（8c7c9c5） |

### 来源（确证）
- 全仓唯一 consumer：`tests/agents/test_enterprise_rc_freeze_activation_gate.py`（未提交，位于工作树）。
- 该测试 import 自 `agents/enterprise/production_release/` 下一组**未提交**模块：
  - `activation_evidence.py` / `activation_gate.py` / `freeze_checker.py` / `freeze_forbidden.py` / `freeze_manifest.py` / `human_approval.py` / `release_candidate.py`
  - 这 6 个 audit 类别在 `production_release/release_candidate.py`、`human_approval.py`、`freeze_manifest.py`、`activation_evidence.py`、`activation_gate.py` 中被引用。
- 测试文件头部 docstring 明确标注：「Phase 3.9.2 受控激活 / RC 冻结闸门层」。

**结论：+6 类别属于 Phase 3.9.2 的「受控激活 / RC 冻结闸门层」扩展能力**，在前序 3.9.2 开发会话中已实现代码与审计 wiring，但**未随 1f223db 提交**（属中断会话遗留），其 audit 枚举改动随 3.9.3 的 `git add agents/enterprise/audit.py` 一并入库于 `8c7c9c5`，而消费代码仍留在工作树未提交。

## 3. 处置决策（按 §六「根据真实证据自主处理」）

**保留（KEEP）。** 理由：
1. 语义合法：受控激活证据包、激活闸门评估、人类激活批准、RC 冻结生成/检查/核验，均为核心治理 fail-closed 能力，与「engineering_enabled 保持 false、AI 不代责、不自动激活」红线一致。
2. 实现完备：6 类均已在 `audit.py` 落地 `enum 成员 + record_* 方法（actor_kind=USER）`，非孤立残留。
3. 消费方存在：有对应未提交代码与测试，证明是真实设计意图而非误加。

**不机械删除、不机械把 96 改回 90。** 正式归属为「Phase 3.9.2 受控激活 / RC 冻结闸门层扩展」。

## 4. SSOT / 文档同步动作

本 Task 0 收口执行以下同步（随 `fix(audit)` 提交）：
- 纠正 3.9.3 文档中陈旧的「88→95 / == 95 / total=95 / +5」为真实值「89→96 / == 96 / total=96 / +6」，并注明 +6 归属：
  - `.ai/reviews/phase3.9.3_production_observability_incident_readiness_report.md`（§16、§22）
  - `docs/PRODUCTION_OBSERVABILITY_GOVERNANCE_GUIDE.md`（§审计集成）
  - `docs/PRODUCTION_DEPLOYMENT_GUIDE.md`（§14）
  - `.ai/roadmap_v8.md`（§35.2 表行 + 文本）
  - `.ai/project_status.json`（`phase_3_9_3` 嵌套：`audit_delta` / T21）
  - `agents/enterprise/audit.py`（3.9.3 段注释：由「83 → 90」更正为「新增 7 类，并标注前序 +6 归属」）
- **不变（已正确）**：`.ai/baselines/phase3.8_governance_release_baseline.json`（`total=96`）、权威测试 `test_enterprise_knowledge_governance_audit.py`（`assert len(members) == 96`）。
- 治理仓库完整性检查器：9/9 通过（actual == baseline == 权威测试 == 96）。

## 5. 待主理人注意的未提交 3.9.2 遗留

工作树仍含以下**未提交** 3.9.2 产物（本阶段刻意不混入 3.9.4 提交，留给 3.9.2 收口或主理人处理）：
- `agents/enterprise/production_release/`：`M __init__.py` / `M service.py`；未跟踪 `activation_evidence.py` / `activation_gate.py` / `freeze_checker.py` / `freeze_forbidden.py` / `freeze_manifest.py` / `human_approval.py` / `release_candidate.py`
- `tests/agents/test_enterprise_rc_freeze_activation_gate.py`（未跟踪）

这些文件与 §2 的 +6 审计类别一一对应，是「受控激活 / RC 冻结闸门层」的完整实现。它们当前随 `pytest tests/agents` 被收集并**通过**（工作树绿色状态的一部分），但未被任何 commit 纳入版本控制。建议：在 3.9.2 收口或单独的 `fix(production-release-activation)` 提交中正式入库，以闭合该能力的版本化。

## 6. 对 Phase 3.9.4 的约束

- 3.9.4 自身新增审计类别（Task 21）将基于 **96** 这一真实基数，继续三处联动（audit.py 枚举+record / 权威测试 EXPECTED_CATEGORIES 集合 / 基线 total），**绝不**在权威文件外硬编码 `== N`。
- 当前审计总数权威值：**96**（基线 / 权威测试一致）。
