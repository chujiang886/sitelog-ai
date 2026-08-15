# BOIP External Staging — Secret Management Plan (Phase 3.9.12, T8)

> 文档类型：资源 Provisioning 计划（Track A）
> 责任角色：security-owner
> 关联：T3 Provider ADR、T4 目标架构、T5 BOM、T7 网络、T17 IaC、T20 人工输入表

---

## 0. 状态声明（fail-closed）

- `resource_type = secret_provider`（枚举值，复用 `ResourceType.SECRET_PROVIDER`）
- `status = pending_external_staging_resource`
- `engineering_enabled = false`；`contains_real_secret = false`
- 真实密钥后端/密钥/加密密钥：**全部 PENDING**（Track B）

---

## 1. 目标态（provisioned 后）

- 独立的 staging 密钥后端（腾讯云 SSM / AWS Secrets Manager / Vault），**不**复用 production 密钥库。
- 所有 BOIP 凭据（DB 密码、IdP client secret、API key、TLS 私钥引用）以 `CredentialReference` 表达：仅存引用/provider/id/rotation 元数据，**绝不明文**。
- 自动轮换策略就位；访问经最小权限策略。

---

## 2. IaC 方法（provider-agnostic）

- 模块：`infrastructure/staging/secret_provider.tf`。
- 默认服务：腾讯云 SSM（`tencentcloud_ssm`）。
- 密钥值**从不**出现在 `.tf` / 变量文件 / 包 / 文档 / 审计中；仅声明引用占位。

---

## 3. Provisioning 步骤（AI 就绪 → 真人 apply）

1. **PLAN**：生成 `secret_provider.tf`（密钥后端 + 访问策略 + 轮换规则，**不含值**）。
2. **VALIDATE**：`assert_no_credential_leak` 扫描（复用 `credential_scanner`），确认无 `password=`/`secret=`/`sk-` 等明文模式。
3. **DRY_RUN**：plan 审查。
4. **HUMAN_AUTHORIZED_APPLY**：真人持真实凭据 apply，并在人类终端注入真实密钥值（AI 不碰明文）。

---

## 4. Track B 待输入（PENDING）

- 密钥后端开通权限
- 访问策略（哪些角色可读哪些密钥，最小权限）
- KMS/加密密钥与轮换周期
- 真实密钥值（由真人经安全通道注入，**不**经 AI/ Git / 文档）

---

## 5. 安全与隔离

- **隔离**：staging 密钥库独立于 production；跨库访问默认拒绝。
- **引用化**：代码中一律 `CredentialReference`，复用 `ExternalStagingResource.credential_reference`（仅引用字符串）。
- **扫描即门禁**：任何明文凭据进入扫描目标 → `CredentialLeakError` → 阻断落盘/返回（fail-closed）。
- **轮换**：生产级密钥轮换策略；AI 不自动轮换真实密钥（须真人）。

---

## 6. 验证（ready 判定，非 verified）

- `secret_provider.tf` 通过 VALIDATE（无明文、策略最小权限）。
- 引用占位齐全，期望值注入点明确。
- 不宣称「密钥已配置/已验证」——真实值与连通待 Track B 到位后由真人验证。

---

## 7. 回滚/清理

- 见 T22：销毁 staging 密钥后端（先吊销引用、再 destroy，禁触碰 production 密钥）。

---

## 8. 红线守约

- 不翻转 `engineering_enabled`；**绝不**写/读真实密钥明文；不调用云密钥 API 拉取真实值。
- 任何「已配置/已验证」状态 PENDING，不伪造。
