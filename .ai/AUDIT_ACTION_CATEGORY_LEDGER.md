# AuditActionCategory 权威溯源台账（AUDIT_ACTION_CATEGORY_LEDGER）

> 本文件是由 `scripts/build_audit_category_ledger.py` 从 **Git 真实历史** 渲染的
> **人类可读镜像**。机器可读唯一事实源（SSOT）是
> `.ai/baselines/audit_action_category_ledger.json`。
> 任何数字/成员名单冲突，一律以 JSON Ledger + `git` 为准。

## 0. 权威结论（一句话）

`AuditActionCategory` 当前总数 = **121**，与基线 `.ai/baselines/phase3.8_governance_release_baseline.json` 的 `audit_category_contract.total = 121` **完全一致**。
这 121 个成员**全部可归因于一个已登记阶段**，无孤儿（unassigned）、无幽灵、无重复计数、无重复归属（duplicate ownership）。

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
| 3.9.6 | `59807ca` | 104 | +4 | ACTIVATION_EVIDENCE_SUBMITTED, ACTIVATION_EVIDENCE_VALIDATED, ACTIVATION_REVIEW_PACKAGE_GENERATED, HUMAN_SIGNOFF_REGISTERED |
| 3.9.7 | `42ad9f2` | 108 | +4 | ACTIVATION_HANDOFF_PACKAGE_GENERATED, FINAL_ACTIVATION_READINESS_EVALUATED, FINAL_ACTIVATION_REVIEW_PACKET_GENERATED, HUMAN_FINAL_DECISION_VERIFIED |
| 3.9.7-change | `7ad04ab` | 121 | +13 | CHANGE_ABORT_POLICY_REGISTERED, CHANGE_CHECKPOINT_RECORDED, CHANGE_EVIDENCE_SUBMITTED, CHANGE_FAILURE_SCENARIO_EVALUATED, CHANGE_HUMAN_DECISION_RECORDED, CHANGE_PACKAGE_GENERATED, CHANGE_PLAN_REGISTERED, CHANGE_POST_VERIFICATION_REGISTERED, CHANGE_PREFLIGHT_CHECKED, CHANGE_REQUEST_CREATED, CHANGE_ROLLBACK_REFERENCE_REGISTERED, CHANGE_SIMULATION_PERFORMED, CHANGE_WINDOW_RESERVED |
| HEAD（当前 `7ad04ab`） | — | 121 | 0 | （无新增） |

**增值合计校验**：baseline(69) + 各阶段增量 = 121 = **121** ✓（与基线权威总数一致）

## 3. 对历史 "83→88→95→96→100" 叙事的纠正

此前部分阶段收口文档/报告中出现过 "83 → 88(+5) → 95(+7) → 96(+1) → 100(+4)"
的溯源叙事。经本台账以 Git 为唯一事实源复核，**该叙事全部不成立**，纯属报告散文
推断、未对齐 Git：

- **不存在 +5（83→88）**：`83` 是 3.9.2 阶段**结束**时的累计数（commit `ea57245`），并非起点；3.9.2 自身仅 +4（79→83）。
- **不存在 +7（88→95）**：3.9.3（commit `8c7c9c5`）实际增量为 **+13**（83→96），而非 +7。
- **不存在 +1（95→96）**：3.9.3 从 83 一步到位 96，中间没有 +1 的孤立跳变。
- **+4（96→100）成立**：3.9.4（commit `6ddb9a3`）确实 +4（TELEMETRY_* ×4）。

结论：以 3.8.27 基线 **69** 为起点，真实增量链为 **+3 / +3 / +4 / +4 / +13 / +4 / +4 / +4 / +13**，终点 **121**，与基线一致。

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
SSOT 对齐环节更正为 3.9.3。归属修正只改「这个成员算谁的」，从不改变总数——
当时总数为 100，修正前后一致。

## 7. Phase 3.9.6 增量说明（+4，100 → 104）

3.9.6 新增 4 个类目，每一个都对应本阶段**真实新增的人工行为通道**，而非为阶段编号凑数：

| 类目 | 触发它的真实行为 | 不新增会丢失什么 |
|------|------------------|------------------|
| `ACTIVATION_EVIDENCE_SUBMITTED` | 真实 USER 提交一份激活证据 | 谁在何时交了什么，无留痕 |
| `ACTIVATION_EVIDENCE_VALIDATED` | 对已提交证据做结构/哈希/溯源校验 | 校验是否发生过不可证 |
| `HUMAN_SIGNOFF_REGISTERED` | 真实 USER 以某角色登记签署 | 四角色签署无法追责 |
| `ACTIVATION_REVIEW_PACKAGE_GENERATED` | 生成供人裁决的材料包 | 人「看着哪一版材料」拍板不可回溯 |

四者语义上限均止于**材料/事实留痕**，任何一个都不表示批准、放行或激活。

## 8. Phase 3.9.7-change 增量说明（+13，108 → 121）

3.9.7-change 新增 13 个类目，对应生产变更管控平面（agents/enterprise/production_change/）
真实新增的 USER 行为通道，而非为阶段编号凑数：

| 类目 | 触发它的真实行为 | 不新增会丢失什么 |
|------|------------------|------------------|
| `CHANGE_REQUEST_CREATED` | 真实 USER 创建一份变更请求草稿 | 谁在何时提了什么变更，无留痕 |
| `CHANGE_PLAN_REGISTERED` | 真实 USER 登记变更计划 | 变更步骤不可追责 |
| `CHANGE_WINDOW_RESERVED` | 真实 USER 预约受控变更窗口 | 变更窗口归属混乱 |
| `CHANGE_PREFLIGHT_CHECKED` | 真实 USER 记录变更前预检 | 预检是否发生过不可证 |
| `CHANGE_CHECKPOINT_RECORDED` | 真实 USER 记录变更检查点 | 过程断点无痕 |
| `CHANGE_ABORT_POLICY_REGISTERED` | 真实 USER 登记中止策略 | 中止条件无据 |
| `CHANGE_ROLLBACK_REFERENCE_REGISTERED` | 真实 USER 登记回滚引用 | 回滚基线缺失 |
| `CHANGE_POST_VERIFICATION_REGISTERED` | 真实 USER 登记变更后验证 | 变更结果无人核验 |
| `CHANGE_EVIDENCE_SUBMITTED` | 真实 USER 提交变更证据 | 证据链断裂 |
| `CHANGE_SIMULATION_PERFORMED` | 真实 USER 记录一次**受控仿真**（is_simulation 恒 True，绝不执行真实变更） | 仿真是否跑过不可证 |
| `CHANGE_FAILURE_SCENARIO_EVALUATED` | 真实 USER 记录失败场景评估 | 风险推演无痕 |
| `CHANGE_PACKAGE_GENERATED` | 真实 USER 生成**仿真专用**变更包（simulated_only 恒 True） | 材料包来源不清 |
| `CHANGE_HUMAN_DECISION_RECORDED` | 真实 USER 记录已发生的人工裁决（仅留痕，不翻转 engineering_enabled） | 谁拍板不可回溯 |

全部 13 类语义上限止于「材料就绪 / 仿真 / 留痕」，任何一类都不表示批准、执行、部署、回滚或激活。
变更管控平面不提供 /execute /deploy /rollback /apply /migrate /activate 端点（红线①②④⑤⑥⑧）。

## 9. 红线声明

本台账仅记录事实，不修改 `engineering_enabled`、不触发任何部署、不生成任何真实凭据、
不代替任何人肉责任。审计枚举的 fail-closed 与人工主体（USER）强制约束由既有治理代码保证。
