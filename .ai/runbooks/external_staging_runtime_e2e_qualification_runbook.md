# Runbook —— External Staging Runtime Deployment & End-to-End Qualification（真实执行手册）

> 本 Runbook 供**主理人 + 四角色**在 Phase 3.9.14 AI 收口（终态 `PHASE_3_9_14_EXTERNAL_STAGING_RUNTIME_E2E_QUALIFICATION_BUILT_NO_GO`）之后，线下带外执行真实 External Staging 运行时部署与端到端资格认定时使用。
> AI 不代执行、不代签、不代置 `engineering_enabled`。本文件只读参考，AI 不自动跑其中任何步骤。

---

## 0. 前置条件

- AI 收口已完成，分支已 STOP，`engineering_enabled=false`。
- 双钥匙 Apply Gate 已升至 `AUTHORIZED_AWAITING_APPLY`（Machine Safety Key + Human Authorization Key 双备，Human Key 须 `actor_kind=USER`）。
- 8 资源真实引用已通过 Phase 3.9.13 登记流程（引用非明文），且 Phase 3.9.13 供给执行已真实完成（PROVISIONED/REGISTERED）。
- 本阶段 7 层（隔离 / 资格 / Health / E2E / 恢复 / 变更 / 证据）已 plan-only 就绪，fail-closed 全部通过。

---

## 1. 运行时部署前置（Runtime Deployment Prerequisites）

- 确认 9/9 跨环境隔离约束已在真实资源上验证（staging 令牌 ≠ production 令牌 / 不复用 production 命名空间）。
- 确认 13/13 运行时资格检查项在真实 External Staging 上可运行（qualify_all 不再 plan-only）。
- `infrastructure/staging/*.tf` 仍为 count=0 / plan-only，真实 apply 由带外执行。

---

## 2. 真实运行时部署（Runtime Deployment）

- 对 8 类资源（database / secret_provider / identity_provider / object_storage / telemetry / alert_sandbox / domain_tls / deployment_target）在 External Staging 真实部署。
- 完成后 `0/8 runtime_deployed` → 真实部署计数推进。
- 严禁跳态；任何非法跃迁会被 fail-closed 拒绝。

---

## 3. 端到端资格认定（E2E Qualification）

- 部署目标（TKE+TCR）真实部署后，跑 External Staging 端到端资格链路（6 步 E2E plan 转为真实执行）。
- `0/13 runtime_e2e_qualified` → 真实资格计数推进。
- 通过 → `QUALIFIED_EXTERNAL_STAGING`。

---

## 4. 失败/恢复/回滚（Failure / Recovery / Rollback）

- 任一资源失败进入失败态；按 `docs/EXTERNAL_STAGING_CLEANUP_ROLLBACK_RUNBOOK.md` 回滚该资源。
- `production_rollback_forbidden=True` 恒守约：禁止把 External Staging 失败回滚动作波及 Production。
- 禁止跨资源级联破坏。

---

## 5. 人工评审（Human E2E Review）

- 四角色在人类终端评审证据链（`Phase3914EvidenceModel`，`has_production_leakage()=False`，`integrity_hash` 可复算）。
- 签署 Runtime E2E GO。

---

## 6. 红线

- 禁 AI 代执行 / 代签 / 改 `engineering_enabled`。
- 禁伪造证据（任何 `real_resource_provisioned=True` / `runtime_executed_count>0` 必须有真实审计形态事件支撑）。
- `engineering_enabled=true` 仅可能发生于最终 Production Human GO 之后，由主理人在人类终端显式置。
- 禁 AI mint Human Authorization Key（须 `actor_kind=USER`）。

---

## 7. 校验命令（人工可跑，非 AI 自动）

```bash
# 分支完整性
python scripts/check_phase3914_branch_integrity.py

# 递归凭据深扫（运行时包不得含明文）
python -c "from agents.external_staging_runtime.credential_deep_scanner import assert_no_deep_credential_leak; from agents.external_staging_runtime.machine_package import build_machine_package; import json; assert_no_deep_credential_leak(value=build_machine_package()['package'])"

# 确定性运行时包哈希（应与 SSOT evidence_hash 一致 = d632d661…）
python -c "from agents.external_staging_runtime.machine_package import build_machine_package; print(build_machine_package()['package_hash'])"

# 只读 API 自审（7 项不变量）
python -c "from agents.external_staging_runtime.self_audit import run_self_audit; r=run_self_audit(); print(r.passed, r.package_hash, r.terminal_state)"

# 只读 Dashboard
python -c "from agents.external_staging_runtime.dashboard import build_readonly_dashboard; import json; print(json.dumps(build_readonly_dashboard(), ensure_ascii=False, indent=2))"
```
