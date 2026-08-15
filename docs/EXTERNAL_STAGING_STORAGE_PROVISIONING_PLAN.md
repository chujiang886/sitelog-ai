# BOIP External Staging — Object Storage Provisioning Plan (Phase 3.9.12, T11)

> 文档类型：资源 Provisioning 计划（Track A）
> 责任角色：production-owner
> 关联：T3 Provider ADR、T4 目标架构、T5 BOM、T7 网络、T8 Secret、T17 IaC、T20 人工输入表

---

## 0. 状态声明（fail-closed）

- `resource_type = object_storage`（枚举值，复用 `ResourceType.OBJECT_STORAGE`）
- `status = pending_external_staging_resource`
- `engineering_enabled = false`；`contains_real_secret = false`
- 真实 bucket / 密钥 / CORS：**全部 PENDING**（Track B）

---

## 1. 目标态（provisioned 后）

- 独立 staging 对象存储桶（腾讯云 COS / AWS S3 / 阿里 OSS），**不**与 production 桶共享。
- 生命周期策略（热→冷→归档）；CORS 仅放行 staging 前端域（T14）。
- 访问凭据（如有）经 secret_provider（T8）引用。

---

## 2. IaC 方法（provider-agnostic）

- 模块：`infrastructure/staging/object_storage.tf`。
- 默认服务：腾讯云 COS（`tencentcloud_cos`）。
- 参数：桶名、区域、存储类型、生命周期规则。

---

## 3. Provisioning 步骤（AI 就绪 → 真人 apply）

1. **PLAN**：生成 `object_storage.tf`（桶、区域、CORS、生命周期）。
2. **VALIDATE**：校验 CORS 仅含 staging 域；`assert_no_credential_leak`。
3. **DRY_RUN**：plan 审查。
4. **HUMAN_AUTHORIZED_APPLY**：真人持真实账号 apply。

---

## 4. Track B 待输入（PENDING）

- 存储桶命名与区域
- CORS / 访问策略（仅 staging 前端域）
- 生命周期/保留策略
- 访问凭据（如有，经 secret_provider 引用）

---

## 5. 安全与隔离

- 独立桶：staging 数据不与 production 混用；跨桶访问默认拒绝。
- CORS 白名单严格限定 staging 子域。
- 公共读默认关闭；仅经签名 URL / 私网访问。

---

## 6. 验证（ready 判定，非 verified）

- `object_storage.tf` 通过 VALIDATE（CORS/生命周期/无明文）。
- 桶配置占位齐全。
- 不宣称「桶已可用/已验证」——真实读写待 Track B 到位后由真人验证。

---

## 7. 回滚/清理

- 见 T22：清空 staging 桶（非生产数据，可安全删）→ `terraform/opentofu destroy`。

---

## 8. 红线守约

- 不翻转 `engineering_enabled`；不写真实访问密钥；不挂载 production 桶；不公开 staging 数据。
- 任何「已配置/已验证」状态 PENDING，不伪造。
