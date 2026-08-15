# 外部预生产环境资格验证 —— 人工核查清单（Human Qualification Checklist）

**Phase**：3.9.10 External Staging Qualification & Evidence Integration Layer
**性质**：真实外部预生产环境资格验证与证据接入（**不是** Production 激活）
**终端态**：`EXTERNAL_STAGING_QUALIFICATION_BUILT_NO_GO`

> 本清单与机器 `ExternalStagingQualificationGate` 必须 contract-test 一致。
> 机器 Gate 仅评估软件框架；以下每条真实资源项须由**主理人 + 四角色**线下提供并验证。

---

## 一、8 资源逐项核查

| # | 资源 | 负责人角色 | 配置？ | 验证？ | 凭据引用（非明文） | 备注 |
|---|------|-----------|--------|--------|--------------------|------|
| 1 | Database | production-owner | ☐ | ☐ | `ref:` | 非 Production DB；DSN 不得含密码 |
| 2 | Secret Provider | security-owner | ☐ | ☐ | `ref:` | staging namespace；绝不读原值 |
| 3 | Identity Provider | security-owner | ☐ | ☐ | `ref:` | issuer/audience 非 Production |
| 4 | Object Storage | production-owner | ☐ | ☐ | `ref:` | staging bucket/namespace |
| 5 | Telemetry | release-manager | ☐ | ☐ | `ref:` | metrics/traces/logs 非 Production namespace |
| 6 | Alert Sandbox | release-manager | ☐ | ☐ | `ref:` | 测试事件明确 `STAGING TEST` |
| 7 | Domain + TLS | production-owner | ☐ | ☐ | `ref:` | staging 域名；证书有效 |
| 8 | Deployment Target | production-owner | ☐ | ☐ | `ref:` | 非 Production target |

## 二、隔离核查（Cross-environment Isolation）

- [ ] staging DB != production DB
- [ ] staging secret namespace != production
- [ ] staging IdP != production
- [ ] staging storage != production
- [ ] staging telemetry != production
- [ ] staging alert != production
- [ ] staging domain != production
- [ ] staging deployment target != production
- [ ] staging token != production token

## 三、连接性核查（Connectivity）

- [ ] 每类资源 read-only / non-destructive 探针可达（超时受控）
- [ ] 无 Production fallback
- [ ] 环境先验证（EXTERNAL_STAGING, production=false）

## 四、运行时核查（Runtime Health）

- [ ] backend / frontend / DB / IdP / storage / audit / governance / release /
      change-control / LLM / voice / telemetry / alerting 健康评估
- [ ] `UNKNOWN` 不视作 `HEALTHY`

## 五、证据与闸门（Evidence & Gate）

- [ ] 证据链完整（Resource→Config→Connectivity→Isolation→Deploy→Runtime→Telemetry→Alert→Failure/Recovery→Gate→Human Review）
- [ ] 证据 scope=external_staging，无 secret
- [ ] 机器 Gate 状态 = `PENDING_EXTERNAL_STAGING_RESOURCE` / `PENDING_HUMAN_VERIFICATION` / `READY_FOR_EXTERNAL_STAGING_HUMAN_REVIEW`
- [ ] **禁止** `APPROVED` / `PRODUCTION_READY` / `GO`

## 六、红线确认

- [ ] `engineering_enabled=false`
- [ ] 无真实 Production GO / Deploy / Migration / Rollback / Secret 注入
- [ ] 四角色 Production 签署 **未**进行（属 Production 阶段）
- [ ] 机器包 `contains_real_secret=false` / `production_activation_prohibited=true`

---

**结论**：8 项真实资源全部提供并验证后，方可将 Gate 推进至 `READY_FOR_EXTERNAL_STAGING_HUMAN_REVIEW`；
此后仍须主理人 + 四角色真实签署，**不**自动进入 Production。
