# Runbook：灾难恢复演练（Disaster Recovery Drill）

> 阶段：Phase 3.9.2 — Enterprise Production Release Gate & Evidence Package Layer
> 性质：**演练 runbook**。本文件定义灾难恢复演练步骤与判定标准，**不是可执行脚本**。
> AI 阶段仅做「恢复可模拟性 / 校验和声明级」验证（`RecoveryValidation.real_data_overwritten=False`），
> **绝不覆盖或还原任何真实数据**。真实演练由 `production-owner` / `ops` / `auditor` 在隔离环境执行。

---

## 0. 演练目标

验证在「备份丢失 / 数据损坏 / 服务整体不可用」场景下，发布体系能否按声明路径恢复，
且恢复过程不污染真实生产数据。

---

## 1. 演练场景

| 场景 | 触发 | 影响 | 恢复路径 |
|------|------|------|---------|
| D1 | 主库损坏 | 写入失败 | 从 last-known-good 备份还原 + 一致性校验 |
| D2 | 配置漂移 | 服务起不来 | 还原配置快照 + 探活 |
| D3 | 发布引入回归 | 功能异常 | version 回滚（见 `rollback.md`） |
| D4 | 密钥泄露 | 安全风险 | 轮换密钥（人类终端）+ 吊销旧凭证 |

---

## 2. AI 阶段已产出的验证（描述级，不执行）

来自 `ProductionReleaseService.collect_evidence()` + `verify_integrity()`：

- **backup 校验**：只验证「备份是否存在 / 落点是否声明」，不读取、不还原。
- **restore 校验**：只模拟「恢复目标可达、步骤可逆」，不执行真实还原。
- **integrity 校验**：只验证「校验和机制是否声明存在」，不比对生产数据。
- 三项 `real_data_overwritten` 恒 False（`RecoveryValidation` frozen dataclass）。

---

## 3. 真实演练执行（仅隔离环境 + 人类终端）

1. 在**隔离环境**（非生产）拉起 last-known-good 备份。
2. 执行还原脚本，记录耗时与一致性校验结果。
3. 探活：`/api/v2/ping` 返回 `{"ok":true}`。
4. 真实 `RecoveryValidation.real_data_overwritten` 经人工确认后入库（actor=USER）。
5. 演练报告归档，关联 `FailureScenarioCatalog`。

---

## 4. AI 禁区（fail-closed）

- 禁 `restore_real_data` / `overwrite_real_data` / `rotate_real_credential`
  （结构级禁名被 mixin 拦截）。
- AI 不得把 `PENDING_VERIFICATION` 自升为 `VERIFIED`；人工依赖项只能标 `PENDING_VERIFICATION`。
- 真实恢复决策与执行只能源于人类终端。
