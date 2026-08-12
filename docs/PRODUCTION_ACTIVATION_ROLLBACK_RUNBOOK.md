# 生产激活 / 回滚运行手册（Production Activation & Rollback Runbook）

> 适用阶段：Phase 3.9.2 —— Release Candidate Freeze & Controlled Activation Gate
> 状态：**仅文档，不含任何自动执行能力**。所有真实动作必须由主理人在人类终端执行；
> 本手册不构成任何放行依据。

---

## 0. 总原则（fail-closed）

1. **engineering_enabled 保持 false**：任何真实部署 / 激活之前，必须由主理人在人类终端
   显式开启 `agents/config.yaml` 的 `engineering_enabled`。AI 与 CI 只能断言它必须为 false，
   绝不能开启。
2. **不输出 engineering_approved**：放行决策只能源于真实 `HumanActivationApproval` 组合，
   永不来自 AI 的 GO / APPROVED。
3. **不伪造人工签署**：`production-owner` / `release-manager` / `security-owner` / `auditor`
   四类角色的真实签署必须由对应真实人工在外部（API / 线下）完成；AI 不构造、不代签、
   不翻转 `engineering_enabled`、不宣布 Production GO。
4. **回滚优先**：真实激活前必须确认 `ReleaseRollbackReference`（上一已知良好版本 + Commit +
   数据库 revision + 配置基线 + 回滚步骤引用 + 恢复校验引用）齐备且经真人核对。

---

## 1. 放行前置（Gate 全绿，且等待真实人工）

受控激活闸门（`ControlledActivationGate`）在 RC 冻结检查（`FROZEN`）+ 激活证据包
（`is_complete`）之上判定：

| 闸门状态 | 含义 | 人类动作 |
| --- | --- | --- |
| `BLOCKED` | 硬检查失败（冻结漂移 / 治理不完整 / engineering_enabled 为真 / 缺客观证据 / 缺回滚恢复引用） | **禁止**推进；先修复硬缺口 |
| `PENDING_VERIFICATION` | 客观检查全过，但真实人工签署仍 PENDING | 由四类角色完成真实签署 |
| `READY_FOR_HUMAN_REVIEW` | 全过且四角色签署齐备 | 主理人线下最终裁决是否激活 |

闸门**永不**返回 `ACTIVATED_BY_HUMAN`；该状态只能源于真实人工 `GO` 签署后由
`HumanActivationApprovalService` 留痕，且**不**翻转 `engineering_enabled`。

---

## 2. 标准放行流程（真实人工线下执行）

1. **确认冻结态**：`python scripts/ci_release_gate.py --rc-spec .ai/release-gate/rc-spec.3.9.2.json`
   应输出 `freeze_status = frozen` 且 `activation_gate_status ∈ {READY_FOR_HUMAN_REVIEW,
   PENDING_VERIFICATION}`。CI 流水线（`release-gate.yml`）须全绿。
2. **四类角色真实签署**：`production-owner` / `release-manager` / `security-owner` /
   `auditor` 各自在 API / 线下完成 `HumanActivationApproval`（decision=GO）。
3. **主理人开启 engineering_enabled**：在人类终端将 `agents/config.yaml` 的
   `engineering_enabled` 改为 `true`（仅此一处，且须记录在案）。
4. **执行真实部署 / 激活**：使用既有部署流程（非本仓库 AI 能力）。
5. **冒烟 + 恢复校验**：按 `ReleaseRollbackReference.recovery_validation_reference`
   执行恢复校验；确认可观测性与告警正常。

---

## 3. 回滚流程（一旦异常立即执行）

1. **判定触发**：错误率 / 延迟 / 数据异常超过阈值，或恢复校验失败。
2. **拉起回滚引用**：取 `ReleaseRollbackReference` 的 `last_known_good_version` /
   `last_known_good_commit` / `database_revision` / `config_baseline`。
3. **执行回滚步骤**：按 `rollback_steps_reference` 回退至上一已知良好态。
4. **恢复校验**：按 `recovery_validation_reference` 验证数据与服务健康。
5. **关闭 engineering_enabled**（如不再继续）：回退 `engineering_enabled=false`，
   并补一条审计留痕（actor=真实 USER）。
6. **事后复盘**：生成 `POSTMORTEM_DRAFT_CREATED` 类证据，归档至下一阶段治理。

---

## 4. 红线速查（违反即中止）

- ① `engineering_enabled` 不得由 AI/CI 开启；
- ② 不得输出 `engineering_approved`；
- ③ 不得真实部署 / 自动激活（AI 路径恒 `activation_approved=False`）；
- ④ 不得修改真实企业数据 / 配置（除主理人在人类终端显式开启 engineering_enabled）；
- ⑤ 不得写入真实密钥 / 自动授予真实生产权限；
- ⑥ 不得 AI 代替人工责任（签署 actor_kind 恒 USER）；
- ⑦ 不得 AI 代生产负责人 / 各签署角色签署；
- ⑧ 不得绕过闸门 / 伪造人工签署 / 宣布激活 GO；
- ⑨ 不得把 simulation / staging / drill 描述成 production verified；
- ⑩ 不得强制冻结 / 自动核验 / 自动激活（冻结须真实人工发起）。

---

## 5. 证据与审计

- 所有真实人工动作通过 `AuditService` 留痕（`actor_kind=USER`），类别含
  `RC_FREEZE_GENERATED` / `RC_FREEZE_VERIFIED` / `RC_FREEZE_CHECK_PASSED` /
  `CONTROLLED_ACTIVATION_GATE_EVALUATED` / `ACTIVATION_EVIDENCE_BUNDLE_GENERATED` /
  `HUMAN_ACTIVATION_APPROVAL_RECORDED`。
- 审计总数基线：`.ai/baselines/phase3.8_governance_release_baseline.json`（`total=96`，
  权威断言位于 `tests/agents/test_enterprise_knowledge_governance_audit.py`）。
- 治理完整性：`./scripts/check_governance_repository_integrity.py` 须 9/9 通过。
