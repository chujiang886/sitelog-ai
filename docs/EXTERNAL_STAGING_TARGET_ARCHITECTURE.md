# BOIP External Staging — Target Architecture (Phase 3.9.12)

> 文档类型：目标架构（Track A 交付物，T4）
> 阶段：Phase 3.9.12 External Staging Provisioning & Operator Readiness
> 关联：T3 Provider ADR、T5 BOM、T6 成本模型、T7-T15 八资源计划、T16 IaC 策略、T17 IaC 模板

---

## 1. 设计目标

把「0/8 真实外部资源」推进到 **可被真人/运维按明确 Runbook 与 IaC/模板实际 Provision 的就绪状态**，而**不实际 Provision**：

- Track A（AI 必须全部完成）：Stack Inventory / ADR / IaC / Validator / Runbook / CI / SSOT / Docs / Tests。
- Track B（真人/真实外部输入）：云账号 / 密钥 / 权限 / 预算 / 域名 / IdP tenant / secret 访问 —— 统一 `PENDING_EXTERNAL_STAGING_RESOURCE`。
- 终态：`EXTERNAL_STAGING_PROVISIONING_OPERATOR_READY_BUILT_NO_GO`。
- Operator Gate 仅 3 态（BLOCKED / PENDING_HUMAN_INPUT / READY_FOR_HUMAN_PROVISIONING_REVIEW），**禁 GO/APPROVED/PRODUCTION_READY**。

---

## 2. 环境定位与隔离模型

```text
                         ┌─────────────────────────────────────────┐
                         │            BOIP Control Plane            │
                         │  (agents/ FastAPI / Next.js 驾驶舱/SSOT) │
                         └───────────────┬─────────────────────────┘
                                         │ (仅编排/生成 IaC + Runbook, 不执行)
                  StagingProvisioningExecutionMode: PLAN/VALIDATE/DRY_RUN
                                         │
        ┌────────────────────────────────┴────────────────────────────────┐
        │                     EXTERNAL STAGING (非生产)                     │
        │  fingerprint ≠ production (命中 ProductionReferenceDenylist → BLOCKED) │
        │                                                                   │
        │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
        │  │ Database │  │ Secret   │  │ IdP      │  │ Object   │  ...8 资源 │
        │  │ (PG/    │  │ Provider │  │ (SSO/    │  │ Storage  │          │
        │  │ 托管)   │  │ (密钥库) │  │ OIDC)    │  │ (COS/S3) │          │
        │  └──────────┘  └──────────┘  └──────────┘  └──────────┘          │
        │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
        │  │ Telemetry│  │ Alert    │  │ Domain-  │  │ Deploy   │          │
        │  │ (监控)  │  │ Sandbox  │  │ TLS      │  │ Target   │          │
        │  │         │  │ (告警)   │  │ (域名证书)│  │ (K8s/ECS)│          │
        │  └──────────┘  └──────────┘  └──────────┘  └──────────┘          │
        └───────────────────────────────────────────────────────────────────┘
                                         ✗ 与 Production 物理/逻辑隔离
```

- **环境标识**：`RuntimeEnvironment.EXTERNAL_STAGING`，`environment_identity.production = False`（复用 `ExternalStagingEnvironmentIdentity`）。
- **隔离证明**：staging fingerprint 与 production fingerprint 不同；命中 `ProductionReferenceDenylist` → `BLOCKED`（复用 3.9.10 denylist）。
- **失败域**：staging 资源故障不得波及 production（独立账号/项目/VPC/子网）。

---

## 3. 八资源供给拓扑（复用 `ResourceType` 顺序）

| # | 资源（枚举值） | 角色 | 供给方式（Track B PENDING） |
|---|---|---|---|
| 1 | `database` | production-owner | 托管 PG（按 Provider ADR：腾讯云 CDB / 阿里 RDS / AWS RDS） |
| 2 | `secret_provider` | security-owner | 密钥库（腾讯云 SSM / AWS Secrets Manager / Vault） |
| 3 | `identity_provider` | security-owner | IdP tenant（OIDC/SSO；腾讯云/Authing/Keycloak） |
| 4 | `object_storage` | production-owner | COS / S3 / OSS |
| 5 | `telemetry` | release-manager | 托管监控（CLS / CloudWatch / Prometheus 托管） |
| 6 | `alert_sandbox` | release-manager | 告警沙箱（独立通知通道，禁发生产 on-call） |
| 7 | `domain_tls` | production-owner | 独立子域 + 证书（staging 专用，禁复用生产证书） |
| 8 | `deployment_target` | production-owner | 容器运行时（TKE / ECS / EKS）+ 镜像仓库（TCR/ACR/ECR） |

> 枚举成员从 `agents.external_staging_qualification.models.ResourceType.__members__` 程序化派生，不手抄。

---

## 4. Provisioning 执行模式（StagingProvisioningExecutionMode）

| 模式 | 允许 | 禁止 |
|---|---|---|
| `PLAN` | 生成 IaC plan 文本 | 任何真实变更 |
| `VALIDATE` | 校验模板/变量/引用完整性（复用 `assert_no_credential_leak`） | 真实连接 |
| `DRY_RUN` | `terraform/opentofu plan` 级别 dry-run | apply |
| `HUMAN_AUTHORIZED_APPLY` | **仅真人**持真实凭据执行 | AI 代执行 |

AI 在 Track A **只产出 PLAN/VALIDATE/DRY_RUN 就绪物**；`HUMAN_AUTHORIZED_APPLY` 由真人触发。

---

## 5. Operator Gate（3 态，独立于 3.9.10/3.9.11 的 4 态 GateStatus）

```text
        ┌─────────────┐
        │   inputs?   │── 缺真实输入/未过校验 → PENDING_HUMAN_INPUT
        └──────┬──────┘
               │ 全齐
        ┌──────┴──────┐
        │  校验通过?  │── 否 → BLOCKED
        └──────┬──────┘
               │ 是
        ┌──────┴───────────────────┐
        │ READY_FOR_HUMAN_         │  → 真人 provisioning 评审（非 GO）
        │ PROVISIONING_REVIEW      │
        └──────────────────────────┘
        （禁 GO / APPROVED / PRODUCTION_READY）
```

评估复用 `GateCheck`/`GateResult`（R8）分级裁决；状态枚举**本阶段新定义 3 态**（见 T2 §2.3），不复用 `GateStatus`。

---

## 6. IaC 与代码层（T16/T17）

- **provider-agnostic 参数化**：`variable "provider"` 默认 `tencent_cloud`（见 T3 ADR），允许覆写。
- **模板位置**：`infrastructure/staging/`（仓库首次引入 IaC 资产）。
- **Dry-run Guard（T18）/ Provisioning Validator（T19）**：复用 adapter 契约测试（R10）+ 凭据扫描（R6）+ 确定性哈希（R13）范式。
- **Operator Package（T24-T26）**：复用 `build_execution_package`/`package_hash`（R13）生成确定性就绪包，含 SHA-256。

---

## 7. 数据流与安全边界

- 任何凭据以 `CredentialReference`（仅引用/provider/id/rotation 元数据）表达；**绝不明文入 Git/Logs/Audit/Docs/Package**。
- `credential_scanner.assert_no_credential_leak` 在闸门口、CI、IaC 生成、包校验四处强制。
- 网络/安全计划（T7）、Secret 管理计划（T8）定义入站/出站、最小权限、密钥轮换。
- `engineering_enabled` 全程 `False`（红线 #1），不翻转。

---

## 8. 阶段收口态（3.9.12）

| 项 | 值 |
|---|---|
| 终态 | `EXTERNAL_STAGING_PROVISIONING_OPERATOR_READY_BUILT_NO_GO` |
| Operator Gate | `READY_FOR_HUMAN_PROVISIONING_REVIEW`（或前置 PENDING/BLOCKED） |
| 8 资源真实配置 | 仍 `PENDING_EXTERNAL_STAGING_RESOURCE`（就绪未 Provision） |
| `engineering_enabled` | `False` |
| 完成动作 | STOP，禁进 3.9.13 |

---

## 9. 与既有层的关系

- 复用 3.9.10 `external_staging_qualification`（基座：8 资源/凭据/身份/denylist）。
- 复用 3.9.11 `external_staging_execution`（执行层：adapter/契约测试/gate/package/evidence 范式）。
- 新增 3.9.12 `external_staging_provisioning`（就绪层：BOM/IaC/Operator Gate/Operator Package）。
- 不吸收 Production Handoff WIP（3.9.10-A 隔离）。
