# BOIP External Staging — Identity Provider Provisioning Plan (Phase 3.9.12, T10)

> 文档类型：资源 Provisioning 计划（Track A）
> 责任角色：security-owner
> 关联：T3 Provider ADR、T4 目标架构、T5 BOM、T7 网络、T8 Secret、T17 IaC、T20 人工输入表

---

## 0. 状态声明（fail-closed）

- `resource_type = identity_provider`（枚举值，复用 `ResourceType.IDENTITY_PROVIDER`）
- `status = pending_external_staging_resource`
- `engineering_enabled = false`；`contains_real_secret = false`
- 真实 IdP tenant / OIDC client / 用户目录：**全部 PENDING**（Track B）

---

## 1. 目标态（provisioned 后）

- 独立 staging IdP tenant（OIDC/SSO），**不**复用 production IdP。
- OIDC client、回调 URI、角色映射就位；client secret 经 secret_provider（T8）引用。
- 与 BOIP 应用 RBAC（默认拒绝）对齐：staging 用户/角色独立于 production。

---

## 2. IaC 方法（provider-agnostic）

- 模块：`infrastructure/staging/identity_provider.tf`。
- 默认：腾讯云/Authing/Keycloak OIDC（SaaS 或自建最小）。
- 仅声明 client/回调/角色映射，**不含** client secret 明文。

---

## 3. Provisioning 步骤（AI 就绪 → 真人 apply）

1. **PLAN**：生成 `identity_provider.tf`（tenant 占位、OIDC client、回调 URI、角色映射）。
2. **VALIDATE**：`assert_no_credential_leak`；校验回调域为 staging 子域（T14）。
3. **DRY_RUN**：plan 审查。
4. **HUMAN_AUTHORIZED_APPLY**：真人持真实 tenant 配置 apply；client secret 经 secret_provider 注入。

---

## 4. Track B 待输入（PENDING）

- IdP tenant 开通权限
- OIDC client ID / 回调 URI（staging 子域）
- 用户/角色目录接入策略（staging 专属）
- client secret（经 secret_provider 引用，AI 不碰明文）

---

## 5. 安全与隔离

- 独立 tenant：staging 身份体系与 production 解耦；跨 tenant 访问默认拒绝。
- 回调绑定 staging 子域（T14），防 token 泄漏至生产域。
- 角色映射默认拒绝（无显式授权不可访问）。

---

## 6. 验证（ready 判定，非 verified）

- `identity_provider.tf` 通过 VALIDATE（无明文 secret、回调域正确）。
- OIDC 配置占位齐全。
- 不宣称「IdP 已连通/已验证」——真实 SSO 登录待 Track B 到位后由真人验证。

---

## 7. 回滚/清理

- 见 T22：吊销 client、删除 tenant 配置（仅 staging），禁触碰 production IdP。

---

## 8. 红线守约

- 不翻转 `engineering_enabled`；不写真实 client secret；不接入 production 用户目录；不自动批准身份。
- 任何「已配置/已验证」状态 PENDING，不伪造。
