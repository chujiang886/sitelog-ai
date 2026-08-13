# AuditActionCategory 权威溯源台账（AUDIT_ACTION_CATEGORY_LEDGER）

> 本文件是由 `scripts/build_audit_category_ledger.py` 从 **Git 真实历史** 渲染的
> **人类可读镜像**。机器可读唯一事实源（SSOT）是
> `.ai/baselines/audit_action_category_ledger.json`。
> 任何数字/成员名单冲突，一律以 JSON Ledger + `git` 为准。

## 0. 权威结论（一句话）

`AuditActionCategory` 当前总数 = **100**，与基线 `.ai/baselines/phase3.8_governance_release_baseline.json` 的 `audit_category_contract.total = 100` **完全一致**。
这 100 个成员**全部可归因于一个已登记阶段**，无孤儿（unassigned）、无幽灵、无重复计数、无重复归属（duplicate ownership）。

## 1. 计数方法（可复现，Git 为唯一事实源）

由 `scripts/build_audit_category_ledger.py` 对以下阶段边界 commit 执行
`git show <commit>:agents/enterprise/audit.py`，正则提取 `AuditActionCategory`
成员集合，逐阶段做集合差分得到 introduced 集合：

```
python scripts/build_audit_category_ledger.py   # 重建 JSON + 本 Markdown
python scripts/audit_category_ledger_validator.py  # 验证 Git<->JSON<->Enum
```

## 2. 逐阶段溯源时间线（由 JSON Ledger 渲染，Git 实证）

| 阶段 | 边界 commit | 累计总数 | 本阶段增量 | 本阶段新增成员（实名单） |
|------|-------------|----------|------------|--------------------------|
| 3.8.27 | `4aa23fb` | 69 | +69 | （基线全量，见 JSON Ledger `phases.3.8.27.members`） |
| 3.8.30 | `382afd4` | 72 | +3 | GOVERNANCE_REPLAY, GOVERNANCE_TIMELINE, GOVERNANCE_TRACE |
| 3.9.0 | `a538e1e` | 75 | +3 | DEPLOYMENT_MANIFEST, PRODUCTION_READINESS_CHECK, ROLLBACK_PLAN |
| 3.9.1 | `66f9b57` | 79 | +4 | DEPLOYMENT_SIMULATION, RECOVERY_VALIDATION, ROLLBACK_DRILL, STAGING_VALIDATION |
| 3.9.2 | `ea57245` | 83 | +4 | RELEASE_CANDIDATE_CREATED, RELEASE_GATE_EVALUATED, RELEASE_MANIFEST_GENERATED, RELEASE_SIGNOFF_RECORDED |
| 3.9.3 | `8c7c9c5` | 96 | +13 | ACTIVATION_EVIDENCE_BUNDLE_GENERATED, ALERT_CANDIDATE_CREATED, CONTROLLED_ACTIVATION_GATE_EVALUATED, HUMAN_ACTIVATION_APPROVAL_RECORDED, INCIDENT_CREATED, INCIDENT_HUMAN_ACKNOWLEDGED, INCIDENT_HUMAN_CLOSED, INCIDENT_HUMAN_RESOLVED, OBSERVABILITY_HEALTH_CHECK, POSTMORTEM_DRAFT_CREATED, RC_FREEZE_CHECK_PASSED, RC_FREEZE_GENERATED, RC_FREEZE_VERIFIED |
| 3.9.4 | `6ddb9a3` | 100 | +4 | SYNTHETIC_DRILL_COMPLETED, SYNTHETIC_DRILL_STARTED, TELEMETRY_EVIDENCE_RECORDED, TELEMETRY_PROVIDER_CHECKED |
| HEAD（当前 `4983e7b`） | — | 100 | 0 | （无新增） |

**增值合计校验**：baseline(69) + 各阶段增量 = 100 = **100** ✓（与基线权威总数一致）

## 3. 对历史 "83→88→95→96→100" 叙事的纠正

此前部分阶段收口文档/报告中出现过 "83 → 88(+5) → 95(+7) → 96(+1) → 100(+4)"
的溯源叙事。经本台账以 Git 为唯一事实源复核，**该叙事全部不成立**，纯属报告散文
推断、未对齐 Git：

- **不存在 +5（83→88）**：`83` 是 3.9.2 阶段**结束**时的累计数（commit `ea57245`），并非起点；3.9.2 自身仅 +4（79→83）。
- **不存在 +7（88→95）**：3.9.3（commit `8c7c9c5`）实际增量为 **+13**（83→96），而非 +7。
- **不存在 +1（95→96）**：3.9.3 从 83 一步到位 96，中间没有 +1 的孤立跳变。
- **+4（96→100）成立**：3.9.4（commit `6ddb9a3`）确实 +4（TELEMETRY_* ×4）。

结论：真实增量链为 **+3 / +3 / +4 / +4 / +13 / +4**，终点 **100**，与基线一致。

## 4. 归属判定规则（未来新增成员如何登记）

1. 新增 `AuditActionCategory` 成员**必须**落在一个已登记阶段的一个 commit 内。
2. 该 commit 必须在阶段边界列表（§2 / JSON `phases`）中可定位；若为新阶段，须先登记新阶段行。
3. 成员命名须与阶段语义一致（如 3.9.4 的 `TELEMETRY_*` / `SYNTHETIC_DRILL_*`）。
4. 总数断言**只**允许出现在 `tests/agents/test_enterprise_knowledge_governance_audit.py`；
   其余文件硬编码总数将被 `scripts/check_governance_repository_integrity.py` 规则 4 判为违规。
5. 新增后必须重跑 `scripts/build_audit_category_ledger.py` 重建 JSON，并重跑 validator 确认 0 orphan/ghost/dup。

## 5. 校验器

`scripts/audit_category_ledger_validator.py` 读取本 JSON Ledger，校验：
1. `Ledger.total == len(AuditActionCategory)`；
2. `union(Ledger 各阶段 members) == set(AuditActionCategory)`；
3. 无 orphan（枚举存在但 Ledger 未登记）；
4. 无 ghost（Ledger 登记但枚举不存在）；
5. 无 duplicate ownership（同一成员不得属于两个 introduction phase）；
6. 每个阶段 `commit` 必须存在；
7. 从对应 `commit` 实际提取的 introduced members 必须与 Ledger 相等。

## 6. 已知历史文本误归属（已 SSOT 更正）

`project_status.json` 的 `phase_3_9_2` 块曾写
"HUMAN_ACTIVATION_APPROVAL_RECORDED 由 3.9.4 线 commit 9201a7d 引入"。
Git 事实：该成员由 **3.9.3**（commit `8c7c9c5`，+13 之一）引入；`9201a7d` 是 3.9.4 T0 的
**溯源契约归属修正**（+6 归属），不新增枚举成员。该文本误归属已于 3.9.4-R1 在
SSOT 对齐环节更正为 3.9.3，不影响总数（仍为 100）。

## 7. 红线声明

本台账仅记录事实，不修改 `engineering_enabled`、不触发任何部署、不生成任何真实凭据、
不代替任何人肉责任。审计枚举的 fail-closed 与人工主体（USER）强制约束由既有治理代码保证。
