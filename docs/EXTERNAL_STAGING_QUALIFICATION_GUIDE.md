# 外部预生产环境资格验证与证据接入 —— 治理指南
## External Staging Qualification & Evidence Integration Layer

**Phase**：3.9.10
**性质**：真实外部预生产环境资格验证与证据接入层（**不是** Production 激活）。
**终端态**：`EXTERNAL_STAGING_QUALIFICATION_BUILT_NO_GO`
**最高红线**：`engineering_enabled=false` 全程保持；禁止真实 Production GO / 部署 /
回滚 / 密钥写入 / 权限授予 / 数据变更。

---

## 1. Architecture

```
agents/external_staging_qualification/
├── models.py            # 8 资源 / 状态枚举 / 环境身份 / 凭据引用（禁止明文）
├── denylist.py          # Production Reference Denylist v2
├── credential_scanner.py# 凭据引用安全扫描（fail-closed）
├── probes.py            # ExternalStagingConnectivityProbe（read-only / non-destructive）
├── qualification.py     # 8 资源资格验证编排
├── runtime.py           # RuntimeQualification（HEALTHY/DEGRADED/UNHEALTHY/UNKNOWN/NOT_CONFIGURED）
├── isolation.py         # CrossEnvironmentIsolationProof（9 项）
├── evidence.py          # QualificationEvidence + EvidenceChain（SHA-256）
├── gate.py              # ExternalStagingQualificationGate（BLOCKED/PENDING_*/READY_*）
├── package.py           # 机器可读包 + SHA-256
├── deployment.py        # ExternalStagingDeploymentProvider（仅 Staging）
├── config.py            # 外部预生产身份 + 指纹
├── pipeline.py          # 全链路编排 / resource-less dry-run
├── scenarios.py         # 故障 / 恢复场景（fail-closed）
├── security.py          # 安全 / RBAC / 跨组织
└── __init__.py          # 公共 API
```

复用 `agents/staging_runtime/` 原语：`RuntimeEnvironment.EXTERNAL_STAGING`、
`EnvironmentIdentity`、`EnvironmentFingerprint`、`EnvironmentIsolationGuard`、
`StagingSecretProvider`。

## 2. 8 Resource Model

| 资源 | 类型 | 负责人角色 |
|------|------|-----------|
| Database | `database` | production-owner |
| Secret Provider | `secret_provider` | security-owner |
| Identity Provider | `identity_provider` | security-owner |
| Object Storage | `object_storage` | production-owner |
| Telemetry | `telemetry` | release-manager |
| Alert Sandbox | `alert_sandbox` | release-manager |
| Domain + TLS | `domain_tls` | production-owner |
| Deployment Target | `deployment_target` | production-owner |

每项字段：`resource_id / resource_type / environment / required / configured /
verified / owner_role / source_reference / credential_reference / isolation_status /
connectivity_status / qualification_status / evidence_refs / last_checked_at`。
**禁止**存 Secret 明文值。

## 3. Credentials

仅保存：`secret reference / provider reference / credential id / rotation metadata /
verification metadata`。
**禁止**：Secret raw value / Password / Token / Private key / 含密码的 DSN。
`CredentialReference.contains_raw_secret()` + `credential_scanner.assert_no_credential_leak()`
提供扫描与 fail-closed 拦截。

## 4. Connectivity

`ExternalStagingConnectivityProbe`：`probe_database / probe_idp / probe_storage /
probe_telemetry / probe_alert / probe_domain_tls / probe_deployment_target /
probe_secret_provider`。
- read-only / non-destructive / 超时受控；
- 无 Production fallback；环境先验证；
- 真实资源缺失 → `PENDING_EXTERNAL_STAGING_RESOURCE`。

## 5. Isolation

`CrossEnvironmentIsolationProof`：9 项（DB / secret / IdP / storage / telemetry /
alert / domain / deployment target / token）—— staging != production。
无法证明 → `PENDING` / `BLOCKED`（绝不声明隔离成立）。

## 6–19. DB / IdP / Storage / Telemetry / Alert / TLS / Deployment / Runtime / Evidence / Gate / API / Dashboard / CI / Security / Human workflow / Troubleshooting

详见 `agents/external_staging_qualification/` 各模块 docstring 与
`ExternalStagingQualificationGuide` 机器契约（CI 生成）。
关键点：所有真实资源缺失时系统仍正确识别 pending、不 fallback production、不伪造
connectivity / validation，Gate 保持 `PENDING_EXTERNAL_STAGING_RESOURCE`。

## 20. 红线速查

- `engineering_enabled=false`；不输出 `engineering_approved`；
- 不真实部署 / 迁移 / 回滚 / 写 Secret / 改权限 / 改数据；
- 不把 Staging 说成 Production；不自动关 Incident / 不 skip 掩盖失败 / 不删断言换绿 / 不伪造结果；
- 不推导 Production Approved / 不输出 GO；
- 终端态恒为 `EXTERNAL_STAGING_QUALIFICATION_BUILT_NO_GO`。
