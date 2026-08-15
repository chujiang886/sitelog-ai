# BOIP External Staging — Observability Provisioning Plan (Phase 3.9.12, T12)

> 文档类型：资源 Provisioning 计划（Track A）
> 责任角色：release-manager
> 关联：T3 Provider ADR、T4 目标架构、T5 BOM、T7 网络、T17 IaC、T20 人工输入表

---

## 0. 状态声明（fail-closed）

- `resource_type = telemetry`（枚举值，复用 `ResourceType.TELEMETRY`）
- `status = pending_external_staging_resource`
- `engineering_enabled = false`；`contains_real_secret = false`
- 真实日志/指标/追踪后端：**全部 PENDING**（Track B）

---

## 1. 目标态（provisioned 后）

- 独立 staging 可观测性后端（日志 + 指标 + 追踪；腾讯云 CLS / managed Prometheus）。
- staging workspace 与 production 隔离；保留期短于 production（如 7-15 天，见 T6）。
- 采集 agent 部署于 staging 专属资源（deployment_target，T15）。

---

## 2. IaC 方法（provider-agnostic）

- 模块：`infrastructure/staging/telemetry.tf`。
- 默认服务：腾讯云 CLS + 托管 Prometheus。
- 参数：日志集/指标 workspace、采集配置、保留期。

---

## 3. Provisioning 步骤（AI 就绪 → 真人 apply）

1. **PLAN**：生成 `telemetry.tf`（workspace、采集规则、保留期、仪表盘占位）。
2. **VALIDATE**：校验 workspace 标签 `env=staging`；`assert_no_credential_leak`。
3. **DRY_RUN**：plan 审查。
4. **HUMAN_AUTHORIZED_APPLY**：真人持真实账号 apply。

---

## 4. Track B 待输入（PENDING）

- 日志集/指标 workspace 开通
- 采集 agent 部署目标（staging 节点，见 T15）
- 保留期与配额
- 接入凭据（经 secret_provider 引用）

---

## 5. 安全与隔离

- 独立 workspace：staging 遥测数据不与 production 混用。
- 采集端点仅 staging 网络可达（T7）。
- 敏感字段脱敏（不采集真实密钥/PII）。

---

## 6. 验证（ready 判定，非 verified）

- `telemetry.tf` 通过 VALIDATE（标签/保留期/无明文）。
- 采集配置占位齐全。
- 不宣称「遥测已连通/已验证」——真实数据流待 Track B 到位后由真人验证。

---

## 7. 回滚/清理

- 见 T22：删除 staging workspace（非生产数据），禁触碰 production 遥测。

---

## 8. 红线守约

- 不翻转 `engineering_enabled`；不写真实接入密钥；不采集 production 遥测；不自动告警升级。
- 任何「已配置/已验证」状态 PENDING，不伪造。
