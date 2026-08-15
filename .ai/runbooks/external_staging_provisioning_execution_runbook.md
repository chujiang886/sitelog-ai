# Runbook —— External Staging Provisioning Execution（真实执行手册）

> 本 Runbook 供**主理人 + 四角色**在 Phase 3.9.13 AI 收口（终态 `EXTERNAL_STAGING_PROVISIONING_EXECUTION_BUILT_NO_GO`）之后，线下带外执行真实 External Staging 供给时使用。
> AI 不代执行、不代签、不代置 `engineering_enabled`。本文件只读参考，AI 不自动跑其中任何步骤。

---

## 0. 前置条件

- AI 收口已完成，分支已 STOP，`engineering_enabled=false`。
- 双钥匙 Apply Gate 已升至 `AUTHORIZED_FOR_EXTERNAL_STAGING_APPLY`（Machine Safety Key + Human Authorization Key 双备）。
- 8 资源真实引用已通过 `POST /human-input-record`（USER 专属）登记（引用非明文）。

---

## 1. 真实资源登记（Resource Registration）

对 8 类资源逐一在 `infrastructure/staging/*.tf` 真实填充（移除 count=0 / placeholder）：
`database` / `secret_provider` / `identity_provider` / `object_storage` / `telemetry` / `alert_sandbox` / `domain_tls` / `deployment_target`。

逐项状态机推进：
`PENDING` → `INPUT_RECEIVED` → `REFERENCE_VALIDATED` → `PLAN_READY` → `PLAN_VALIDATED` → `HUMAN_AUTHORIZATION_PENDING` → `AUTHORIZED_FOR_STAGING_APPLY` → `PROVISIONING` → `PROVISIONED` → `REGISTERED`。

> 严禁跳态；任何非法跃迁会被 `ResourceStateMachine` fail-closed 拒绝。

---

## 2. 真实供给（Provisioning）

- 使用供给方无关 IaC（OpenTofu/Tercent Cloud provider），默认 `tencentcloud`。
- 真实 apply 由真人在带外执行（不在 AI/CI 内）。
- 完成后 `PROVISIONED` → `REGISTERED`。

---

## 3. 连通性验证（Connectivity）

- 对每资源做连通探针（DB 连接 / Secret 读取 / IdP 握手 / Storage 读写 / Telemetry push / Alert fire / DNS+TLS / TKE 调度）。
- 通过 → `REGISTERED` → `CONNECTIVITY_VERIFIED`。
- 失败 → `FAILED_CONNECTIVITY`，回滚该资源并复查引用。

---

## 4. 隔离验证（Isolation）

- 校验 staging 令牌 ≠ production 令牌，不复用 production 命名空间。
- 9/9 隔离约束逐项真实验证。
- 通过 → `CONNECTIVITY_VERIFIED` → `ISOLATION_VERIFIED`。

---

## 5. 运行时部署 + E2E（Runtime Deployment / E2E）

- `ISOLATION_VERIFIED` → `QUALIFIED_EXTERNAL_STAGING`。
- 部署目标（TKE+TCR）真实部署，跑 External Staging E2E。

---

## 6. 失败/恢复/回滚（Failure / Recovery / Rollback）

- 任一资源失败进入 `FAILED_*` 态；按 `docs/EXTERNAL_STAGING_CLEANUP_ROLLBACK_RUNBOOK.md` 回滚该资源。
- 禁止跨资源级联破坏。

---

## 7. 人工评审（Human Staging Review）

- 四角色在人类终端评审证据链（`EvidenceChain`，`fabrication_free=true`，`evidence_hash` 可复算）。
- 签署 Provisioning Execution GO。

---

## 8. 红线

- 禁 AI 代执行 / 代签 / 改 `engineering_enabled`。
- 禁伪造证据（任何 `real_resource_provisioned=True` 必须有真实审计形态事件支撑）。
- `engineering_enabled=true` 仅可能发生于最终 Production Human GO 之后，由主理人在人类终端显式置。

---

## 9. 校验命令（人工可跑，非 AI 自动）

```bash
# 分支完整性
python scripts/check_phase3913_branch_integrity.py

# 递归凭据深扫（供给包不得含明文）
python -c "from agents.external_staging_provisioning.credential_deep_scanner import assert_no_deep_credential_leak; from agents.external_staging_provisioning.machine_package import build_machine_package; import json; assert_no_deep_credential_leak(value=build_machine_package()['package'])"

# 确定性执行包哈希（应与 SSOT evidence_hash 一致）
python -c "from agents.external_staging_provisioning.machine_package import build_machine_package; print(build_machine_package()['package_hash'])"

# 无伪造校验
python -c "from agents.external_staging_provisioning.validator_execution import validate_execution_no_fabrication; print(validate_execution_no_fabrication().to_dict())"
```
