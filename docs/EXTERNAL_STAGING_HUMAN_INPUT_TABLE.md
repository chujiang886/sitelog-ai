# 外部预生产环境 · 人工输入表（Human Input Table）

> Phase 3.9.12 · External Staging Provisioning & Operator Readiness
> 配套：`docs/EXTERNAL_STAGING_RESOURCE_BOM.md`(T5) / `docs/EXTERNAL_STAGING_TARGET_ARCHITECTURE.md`(T4)
> 机器可读：`.ai/staging/external_staging_human_input_table.json`

## 总览

本表列出 8 类外部预生产资源在「AI 仅完成就绪层（Track A）」后，**必须由真人/运维在线下提供的真实输入（Track B）**。

**fail-closed 红线（贯穿本表）：**
- 所有 `状态` 列当前**统一为 `PENDING`**；AI 不代填、不伪造、不预估真实账号/密钥/配额。
- 凭据一律以 `CredentialReference`（引用/provider/id/rotation 元数据）登记，**绝不明文**写入本表 / Git / Logs / Audit / Package。
- 任何一项真实输入落地后，须由对应 `责任角色` 在**人类终端**登记并签署；AI 不代执行 `human_authorized_apply`。
- `engineering_enabled` 保持 `false`；本表不触发任何自动开通。

| # | 资源 ID | 资源类型 | 责任角色 | 必须提供的真实输入（Track B） | 对应 IaC 模块 | 状态 |
|---|---------|---------|---------|------------------------------|--------------|------|
| 1 | `ext-staging-database` | database | production-owner | 1) 云账号 + 项目/VPC/子网；2) PostgreSQL 版本与实例规格；3) 数据库账号与凭据（仅引用，不存明文）+ 轮换策略；4) 备份/保留策略 | `infrastructure/staging/database.tf` | PENDING |
| 2 | `ext-staging-secret_provider` | secret_provider | security-owner | 1) 密钥后端开通（如腾讯云 SSM）；2) 访问策略（最小权限）；3) KMS/加密密钥与轮换配置 | `infrastructure/staging/secret_provider.tf` | PENDING |
| 3 | `ext-staging-identity_provider` | identity_provider | security-owner | 1) 独立 IdP tenant 开通（OIDC/SSO，禁与生产共享）；2) OIDC client / 回调 URI（仅 staging 子域）；3) client_secret 引用（不存明文） | `infrastructure/staging/identity_provider.tf` | PENDING |
| 4 | `ext-staging-object_storage` | object_storage | production-owner | 1) 独立存储桶（COS）开通；2) 桶策略与 CORS（仅 staging 子域）；3) 访问密钥引用（不存明文） | `infrastructure/staging/object_storage.tf` | PENDING |
| 5 | `ext-staging-telemetry` | telemetry | release-manager | 1) 独立日志/指标 workspace（CLS/Prometheus）；2)  retention 策略（建议 15 天）；3) 采集端与 staging 环境绑定 | `infrastructure/staging/telemetry.tf` | PENDING |
| 6 | `ext-staging-alert_sandbox` | alert_sandbox | release-manager | 1) 独立告警通知组（禁发 production on-call）；2) `forbid_prod_notify=true` 校验；3) 告警路由与静默策略 | `infrastructure/staging/alert_sandbox.tf` | PENDING |
| 7 | `ext-staging-domain_tls` | domain_tls | production-owner | 1) 独立 staging 子域（如 `staging.example.com`）；2) 证书（SAN **不含** production 域名）；3) DNS 托管与证书轮换 | `infrastructure/staging/domain_tls.tf` | PENDING |
| 8 | `ext-staging-deployment_target` | deployment_target | production-owner | 1) 独立集群（TKE）开通；2) 独立镜像仓库（TCR）；3) 集群访问凭证引用（不存明文）+ 镜像同步策略 | `infrastructure/staging/deployment_target.tf` | PENDING |

## 跨资源通用输入（额外 Track B）

| 类别 | 说明 | 责任角色 | 状态 |
|------|------|---------|------|
| 云账号与权限 | 真实云账号、项目、RAM/子账号、最小权限策略；**不写入任何密钥明文** | production-owner / security-owner | PENDING |
| 成本预算护栏 | 设定 `cost_budget`（默认 ¥6000 示意上限，见 `docs/EXTERNAL_STAGING_COST_MODEL.md` T6）；超预算阻断 apply | production-owner | PENDING |
| 四角色真实签署 | production-owner / release-manager / security-owner / auditor 线下提交证据并签署 | 四角色 | PENDING |
| 主理人显式授权 | 主理人在人类终端将 `engineering_enabled` 置 `true`（**唯一 AI 不代执行之动作**） | 主理人 | PENDING |
| Provider 绑定确认 | ADR-PHASE-3.9.12-EXTERNAL-STAGING-PROVIDER 当前为 RECORDED（腾讯云首选，非真实绑定）；真人确认最终 provider 并覆写 `var.provider` | production-owner | PENDING |

## 输入登记与校验流程（fail-closed）

1. 真人按上表逐项准备真实输入，**密钥仅以引用登记**。
2. 运行 `python scripts/validate_external_staging_provisioning.py` 确认算子包未被篡改、8 资源仍 PENDING、`engineering_enabled=false`、Operator Gate 未落入 GO/APPROVED。
3. 运行 `python scripts/generate_external_staging_provisioning_package.py` 重新生成算子包（确定性哈希），与已签署版本比对。
4. 四角色线下签署 + 主理人置 `engineering_enabled=true` 后，由真人执行 `tofu apply`（模式 `HUMAN_AUTHORIZED_APPLY`），**非 AI**。
5. 任何一步发现明文密钥/越权/预算超限 → 立即 `BLOCKED`，停止并回滚（见 Cleanup/Rollback Runbook）。

> 本表所有 `状态=PENDING` 为真实事实；AI 不预判、不代填。待真人提供后于人类终端更新，不在本仓库自动改写。
