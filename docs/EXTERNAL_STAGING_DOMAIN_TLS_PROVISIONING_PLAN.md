# BOIP External Staging — Domain & TLS Provisioning Plan (Phase 3.9.12, T14)

> 文档类型：资源 Provisioning 计划（Track A）
> 责任角色：production-owner
> 关联：T3 Provider ADR、T4 目标架构、T5 BOM、T7 网络、T8 Secret、T17 IaC、T20 人工输入表

---

## 0. 状态声明（fail-closed）

- `resource_type = domain_tls`（枚举值，复用 `ResourceType.DOMAIN_TLS`）
- `status = pending_external_staging_resource`
- `engineering_enabled = false`；`contains_real_secret = false`
- 真实子域授权/证书/私钥：**全部 PENDING**（Track B）

---

## 1. 目标态（provisioned 后）

- staging 专用子域（如 `staging.boip.example`），**不复用** production 域名/证书。
- TLS 证书自动颁发与续期（ACME/托管）；私钥经 secret_provider（T8）引用。
- DNS 托管于 staging 专属区域，与 production 区域隔离。

---

## 2. IaC 方法（provider-agnostic）

- 模块：`infrastructure/staging/domain_tls.tf`。
- 默认服务：腾讯云 DNSPod + 托管 SSL（`tencentcloud_dnspod` / `tencentcloud_ssl`）。
- 参数：子域名、证书 SAN、自动续期。

---

## 3. Provisioning 步骤（AI 就绪 → 真人 apply）

1. **PLAN**：生成 `domain_tls.tf`（子域、DNS 记录、证书请求、续期）。
2. **VALIDATE**：校验子域非 production 域；`assert_no_credential_leak`（无私钥明文）。
3. **DRY_RUN**：plan 审查。
4. **HUMAN_AUTHORIZED_APPLY**：真人持真实域名/证书权限 apply；私钥经 secret_provider 注入。

---

## 4. Track B 待输入（PENDING）

- staging 子域名授权（DNS 托管权）
- 证书颁发机构 / 自动续期配置
- TLS 私钥（经 secret_provider 引用，AI 不碰明文）

---

## 5. 安全与隔离

- **独立证书**：staging 证书 SAN 不含 production 域名；禁用生产证书。
- 私钥仅存引用；轮换经 secret_provider。
- DNS 区域隔离：staging 解析故障不影响 production。

---

## 6. 验证（ready 判定，非 verified）

- `domain_tls.tf` 通过 VALIDATE（子域/证书/无明文）。
- DNS/证书配置占位齐全。
- 不宣称「域名已解析/证书已生效」——真实签发待 Track B 到位后由真人验证。

---

## 7. 回滚/清理

- 见 T22：吊销 staging 证书、清理 DNS 记录（不影响 production）。

---

## 8. 红线守约

- 不翻转 `engineering_enabled`；不写真实私钥；不签发 production 证书；不改动 production DNS。
- 任何「已配置/已验证」状态 PENDING，不伪造。
