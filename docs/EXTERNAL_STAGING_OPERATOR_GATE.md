# 外部预生产环境 · Operator Gate（算子闸门）

> Phase 3.9.12 · 独立 3 态闸门（与 3.9.10/3.9.11 的 4 态 GateStatus **正交**）
> 代码：`agents/external_staging_provisioning/gate.py`(OperatorGateStatus / ExternalStagingProvisioningOperatorGate)
> 校验：`scripts/validate_external_staging_provisioning.py`(T19)

## 设计原则

Operator Gate 仅描述「**真人供给前**的算子就绪闸门」，不含任何「已通过/可上线」语义。
因此状态**仅 3 态**，明确**禁止** `GO` / `APPROVED` / `PRODUCTION_READY`（这些语义在本平台不存在）。

## 三态定义

| 状态 | 含义 | 后续动作 |
|------|------|---------|
| `BLOCKED` | 存在硬 violation（凭据泄漏 / 隔离失效 / 闸门自检失败 / `engineering_enabled=true`） | 停止，进入 Cleanup/Rollback Runbook(T22) |
| `PENDING_HUMAN_INPUT` | 等待真人提供 8 资源真实输入/密钥/授权（默认态，本阶段即此态） | 真人按人工输入表(T20) + Runbook(T21) 提供 |
| `READY_FOR_HUMAN_PROVISIONING_REVIEW` | 就绪，等待真人供给评审与（离线）授权 | 四角色 + 主理人线下评审/签署后，真人以 `HUMAN_AUTHORIZED_APPLY` 执行 |

> `READY_FOR_HUMAN_PROVISIONING_REVIEW` **不是 GO**——它仅表示「AI 就绪层已构建、可供真人评审」，
> 真实开通仍须主理人在人类终端显式授权（`engineering_enabled=true`）并由真人 apply。

## 决策逻辑（fail-closed）

```
evaluate(checks):
  if 任一 block 级检查失败:  → BLOCKED
  elif 存在 additional_pending_inputs 或 human_input_required: → PENDING_HUMAN_INPUT
  else:                       → READY_FOR_HUMAN_PROVISIONING_REVIEW
```

## 检查项（GateCheck）

| 检查名 | 严重度 | 失败含义 |
|--------|--------|---------|
| `provisioning_bom_complete` | block | 供给 BOM 资源数 ≠ 8 |
| `bom_all_pending` | block | 存在非 PENDING 资源（Track B 必须全 PENDING） |
| `credential_reference_safety` | block | BOM/环境身份含明文凭据泄漏 |
| `iac_dry_run` | block | IaC 干跑校验失败（见 Dry-run Guard T18） |
| `adapter_contract_tests` | block | 8 资源 Adapter 契约测试未全通过 |
| `environment_not_production` | block | 环境身份 `production=true` |
| `engineering_enabled_false` | block | `engineering_enabled=true`（最高红线违例） |
| `security` / `full_regression` / `repository_clean` | block | 安全/回归/仓库清洁未通过 |

## 禁止态（fail-closed）

- **Operator Gate 态**：禁 `go` / `approved` / `production_ready` / `ready`。
- **供给执行模式**（`StagingProvisioningExecutionMode`）：仅 `plan`/`validate`/`dry_run`/`human_authorized_apply`；禁 `auto` / `production`。
- **供给步状态**：禁 `provisioned` / `executed` / `deployed_production` / `go` / `approved`。

## 与本阶段终态的关系

- 终态：`EXTERNAL_STAGING_PROVISIONING_OPERATOR_READY_BUILT_NO_GO`
- 当前 Operator Gate = `PENDING_HUMAN_INPUT`（8 资源真实输入待真人，符合 BUILT_NO_GO）。
- 任何 CI / validate 脚本断言该包 `operator_gate.status` ∈ {blocked, pending_human_input, ready_for_human_provisioning_review}，且不落入 GO/APPROVED。
