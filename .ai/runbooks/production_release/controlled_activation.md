# Runbook：企业生产发布受控激活（Controlled Activation）

> 阶段：Phase 3.9.2 — Enterprise Production Release Gate & Evidence Package Layer
> 性质：**人工门控 runbook**。本文件是操作手册，**不是可执行脚本**，AI 不自动执行其中任何步骤。
> 激活前提：`Phase 3.9.2` 收口且主理人在人类终端显式授权。

---

## 0. 适用前提（MUST 全部满足，否则禁止激活）

1. `agents/config.yaml` 中 `engineering_enabled` 在 AI 阶段**恒为 false**（红线①）。
2. `Phase 3.9.2` 收口报告 `phase3.9.2_production_release_gate_evidence_package_report.md`
   已生成且结论为 `BUILT_NO_GO`（即「体系建成、未激活」）。
3. 主理人已在**人类终端**完成真实证据收集（密钥、权限、回滚演练、灾难恢复演练）。
4. `ProductionReleaseGate.evaluate()` 返回 `READY_FOR_HUMAN_REVIEW`（非 `BLOCKED` / `PENDING_VERIFICATION`）。
5. 真实 `ReleaseSignoff` 已由 `production-owner` / `auditor` 等真实 USER 主体签署，
   且未被任何 AI 主体代签（红线⑥⑦）。

**任何一条不满足 → STOP，不得激活。**

---

## 1. 激活准备核对（人工）

| # | 核对项 | 证据来源 | 通过标准 |
|---|--------|---------|---------|
| A1 | 真实密钥就位 | 密钥保险库 / 人类终端 | 无明文进入仓库；`verified.json` 不持有真实值 |
| A2 | 真实权限授予 | IdP / 人类终端 | `production-owner` / `ops` / `auditor` 真实角色已授予 |
| A3 | 回滚演练已真实执行 | `rollback.md` 产物 | `RollbackDrillReport.executed_for_real=True`（仅人工可置） |
| A4 | 灾难恢复演练已真实执行 | `disaster_recovery_drill.md` 产物 | `RecoveryValidation.real_data_overwritten` 经人工确认 |
| A5 | 发布清单 SHA-256 完整 | `phase3.9.2_production_release_manifest.json` | 全产物哈希与 manifest 一致、无 `<missing>` |

---

## 2. 激活执行（仅人类终端）

1. 在主理人人类终端将 `agents/config.yaml` 的 `engineering_enabled` 置 `True`（全仓唯一一处）。
2. 运行真实部署流程（**不在本 AI 阶段范围内**，由 ops runbook 独立承载）。
3. 部署后健康检查：`/api/v2/ping` 返回 `{"ok":true}`；各服务探活通过。
4. 激活后观察窗口：保留 `rollback.md` 描述的可逆回滚路径随时可用。

---

## 3. 激活后留痕（人工）

- 真实 `ReleaseSignoff` 写入（actor_kind=USER，AI 主体 403）。
- `ReleasePackageManifest` 落盘（SHA-256 已生成于 Commit B）。
- 在 `.ai/project_status.json` 将 `phase_3_9_2_status` 自 `BUILT_NO_GO` 更新为人工激活态（人工操作）。

---

## 4. AI 禁区（fail-closed，本 runbook 不授权 AI 执行）

- 禁 `set engineering_enabled True`（红线①）
- 禁 `emit engineering_approved`（红线②）
- 禁 `deploy_production_for_real` / `write_real_secret_key` / `grant_real_permission`（③④⑤）
- 禁 `sign_release_for_user` / `auto_conclude_release`（⑥⑦）

任何触发上述禁名的调用均被 `_RedLineForbiddenMixin` 结构拦截并抛
`EnterpriseRedLineViolationError`。
