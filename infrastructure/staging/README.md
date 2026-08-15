# BOIP External Staging — IaC（OpenTofu / Terraform）

> 阶段：Phase 3.9.12 External Staging Provisioning & Operator Readiness
> 策略：见 `docs/adr/ADR-PHASE-3.9.12-IAC-STRATEGY.md`
> 状态：**就绪未 Provision**（8 资源全部 `PENDING_EXTERNAL_STAGING_RESOURCE`）

## 重要声明

- 本目录 IaC 为 **AI 生成的就绪模板**，不是已执行的基础设施。
- **AI 不运行 `apply`**。真实 provisioning 由主理人在人类终端、四角色真实签署后执行 `HUMAN_AUTHORIZED_APPLY`。
- `engineering_enabled = false`；模板中**不含任何真实密钥/Token/私钥**。
- 真实账号/项目/VPC/凭据等 Track B 输入当前为 `PENDING_EXTERNAL_STAGING_RESOURCE`。

## 使用流程（真人）

```bash
# 1. 安装 OpenTofu >= 1.6 (或 Terraform)
# 2. 提供真实凭据（环境变量，勿入 Git）:
#    export TENCENTCLOUD_SECRET_ID=...   # 由真人提供
#    export TENCENTCLOUD_SECRET_KEY=...  # 由真人提供
# 3. 覆写变量 (变量文件或 -var):
#    -var="provider=tencentcloud" -var="project_id=<真实staging项目>" -var="region=<真实区域>"
# 4. 生成计划（AI 已就绪，真人审查）:
tofu init
tofu plan -out=staging.tfplan
# 5. 干跑校验（不实际变更）:
tofu show staging.tfplan
# 6. 真实 apply（仅真人，HUMAN_AUTHORIZED_APPLY）:
tofu apply staging.tfplan
# 7. 清理（仅 staging，禁 production）:
tofu destroy
```

## 资源映射（provider-agnostic）

| 文件 | 资源 | 默认服务 |
|---|---|---|
| `network.tf` | 网络/安全 | VPC/子网/安全组 |
| `secret_provider.tf` | 密钥后端 | 腾讯云 SSM |
| `database.tf` | PostgreSQL | 腾讯云 CDB |
| `identity_provider.tf` | OIDC/SSO | Authing/Keycloak/云 IdP |
| `object_storage.tf` | 对象存储 | 腾讯云 COS |
| `telemetry.tf` | 可观测 | 腾讯云 CLS |
| `alert_sandbox.tf` | 告警沙箱 | 云监控 + 独立通知组 |
| `domain_tls.tf` | 域名/证书 | DNSPod + SSL |
| `deployment_target.tf` | 容器运行时 | 腾讯云 TKE + TCR |

## 校验

- `StagingProvisioningDryRunGuard`（T18）/ `StagingProvisioningValidator`（T19）对模板做静态校验（解析 + 禁明文 + 变量齐备）。
- `StagingCostGuard`（T31）读取 `var.cost_budget` 校验预算上限。
- CI 闸门（T33）在 PR/push 时运行上述校验（fail-closed）。
