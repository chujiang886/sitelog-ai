# BOIP External Staging — Resource BOM (Bill of Materials)

> 文档类型：8 资源清单（T5，Track A）
> 阶段：Phase 3.9.12 External Staging Provisioning & Operator Readiness
> 机器可读：`.ai/staging/external_staging_resource_bom.json`
> 关联：T3 Provider ADR、T4 目标架构、T6 成本模型、T7-T15 八资源计划

---

## 0. 统一状态声明（fail-closed）

| 项 | 值 |
|---|---|
| 资源总数 | **8** |
| 统一状态 | `pending_external_staging_resource`（Track B 真实输入 PENDING） |
| `engineering_enabled` | `false` |
| `contains_real_secret` | `false` |
| 真实账号/密钥/权限/预算/域名/IdP tenant | **全部 PENDING**（须主理人 + 四角色真实签署后提供） |

> 本 BOM 仅描述「provisioning 就绪清单」，**不**代表任何资源已被真实创建或验证。任何「已配置/已验证」状态均回落 PENDING，不伪造。

---

## 1. 八资源清单（复用 `ResourceType` 顺序）

| # | 资源 ID | 类型（枚举值） | 必需 | 责任角色 | 默认供给方服务（T3 ADR） | IaC 模块 |
|---|---|---|---|---|---|---|
| 1 | `ext-staging-database` | `database` | ✓ | production-owner | Tencent Cloud CDB for PostgreSQL | `infrastructure/staging/database.tf` |
| 2 | `ext-staging-secret_provider` | `secret_provider` | ✓ | security-owner | Tencent Cloud SSM | `infrastructure/staging/secret_provider.tf` |
| 3 | `ext-staging-identity_provider` | `identity_provider` | ✓ | security-owner | OIDC/SSO IdP tenant | `infrastructure/staging/identity_provider.tf` |
| 4 | `ext-staging-object_storage` | `object_storage` | ✓ | production-owner | Tencent Cloud COS | `infrastructure/staging/object_storage.tf` |
| 5 | `ext-staging-telemetry` | `telemetry` | ✓ | release-manager | Tencent Cloud CLS / managed Prometheus | `infrastructure/staging/telemetry.tf` |
| 6 | `ext-staging-alert_sandbox` | `alert_sandbox` | ✓ | release-manager | Cloud Monitor alarm + 独立通知通道 | `infrastructure/staging/alert_sandbox.tf` |
| 7 | `ext-staging-domain_tls` | `domain_tls` | ✓ | production-owner | Staging 子域 + TLS（DNSPod + SSL） | `infrastructure/staging/domain_tls.tf` |
| 8 | `ext-staging-deployment_target` | `deployment_target` | ✓ | production-owner | Tencent Cloud TKE + TCR | `infrastructure/staging/deployment_target.tf` |

---

## 2. 各资源 Track B 待输入（真实外部输入，PENDING）

| 资源 | 真人/运维须提供的输入 |
|---|---|
| `database` | 云账号 + 项目/VPC/子网；PG 版本与实例规格；数据库账号与凭据轮换策略（仅引用）；备份/保留策略 |
| `secret_provider` | 密钥后端开通；访问策略（最小权限）；KMS/加密密钥轮换 |
| `identity_provider` | IdP tenant 开通；OIDC client / 回调 URI；用户/角色目录接入策略 |
| `object_storage` | 存储桶命名与区域；CORS / 访问策略；生命周期/保留 |
| `telemetry` | 日志集/指标 workspace；采集 agent 部署（staging 专属）；保留期 |
| `alert_sandbox` | 告警通知端点（非生产）；路由/静默策略；演练通道验证 |
| `domain_tls` | staging 子域名授权；证书颁发机构/自动续期；DNS 托管权 |
| `deployment_target` | 容器镜像仓库命名空间；K8s/ECS 集群与节点池；镜像 digest 登记（待真实 build/push 后） |

---

## 3. 供给方语义（来自 T3 ADR）

- **首选供给方**：腾讯云（RECORDED，非绑定）。
- **IaC 写法**：provider-agnostic 参数化，`variable "provider"` 默认 `tencent_cloud`，允许覆写为阿里云/AWS 等。
- **真实绑定**：主理人持真实凭据 + 四角色签署后，覆写 `provider` 变量并 `HUMAN_AUTHORIZED_APPLY`。

---

## 4. 与既有模型对齐

- 资源类型枚举严格复用 `agents.external_staging_qualification.models.ResourceType`（`__members__` 程序化派生，不手抄）。
- 责任角色映射复用 3.9.10 `_default_owner_role`：DB/Storage/Domain/Deploy→production-owner；Secret/IdP→security-owner；Telemetry/Alert→release-manager。
- 凭据一律 `CredentialReference`（仅引用），复用 `credential_scanner.assert_no_credential_leak`。

---

## 5. 后续

- T6：三档成本模型（minimum viable / recommended / production-like）。
- T7-T15：八资源各自 Provisioning 计划（详细步骤、IaC 资源、回滚、验证）。
- T17：IaC 模板落地（`infrastructure/staging/`）。
- T20：人工输入表（基于本 BOM §2 的待输入）。
