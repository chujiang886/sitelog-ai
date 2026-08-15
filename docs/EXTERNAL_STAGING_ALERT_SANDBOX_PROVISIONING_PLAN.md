# BOIP External Staging — Alert Sandbox Provisioning Plan (Phase 3.9.12, T13)

> 文档类型：资源 Provisioning 计划（Track A）
> 责任角色：release-manager
> 关联：T3 Provider ADR、T4 目标架构、T5 BOM、T7 网络、T12 遥测、T17 IaC、T20 人工输入表

---

## 0. 状态声明（fail-closed）

- `resource_type = alert_sandbox`（枚举值，复用 `ResourceType.ALERT_SANDBOX`）
- `status = pending_external_staging_resource`
- `engineering_enabled = false`；`contains_real_secret = false`
- 真实告警通道/路由：**全部 PENDING**（Track B）

---

## 1. 目标态（provisioned 后）

- 独立 staging 告警沙箱：独立通知通道（邮件/Webhook/IM），**禁发 production on-call**。
- 告警路由/静默策略就位；与遥测（T12）联动触发 staging 专属告警。
- 演练通道可验证告警链路而不打扰生产值班。

---

## 2. IaC 方法（provider-agnostic）

- 模块：`infrastructure/staging/alert_sandbox.tf`。
- 默认服务：云监控告警 + 独立通知组（不与 production 通知组共享）。
- 参数：通知端点、路由规则、静默窗口。

---

## 3. Provisioning 步骤（AI 就绪 → 真人 apply）

1. **PLAN**：生成 `alert_sandbox.tf`（通知组、路由、静默策略、演练通道）。
2. **VALIDATE**：校验通知组不含 production on-call 成员；`assert_no_credential_leak`。
3. **DRY_RUN**：plan 审查。
4. **HUMAN_AUTHORIZED_APPLY**：真人持真实账号 apply。

---

## 4. Track B 待输入（PENDING）

- 告警通知端点（非生产，如 staging IM 群/邮箱）
- 路由/静默策略
- 演练通道验证方式

---

## 5. 安全与隔离

- **禁发生产**：通知组与 production 完全隔离；任何误配 production on-call → 校验失败（BLOCKED）。
- 告警内容脱敏（不泄露真实密钥/PII）。
- 静默策略防告警风暴。

---

## 6. 验证（ready 判定，非 verified）

- `alert_sandbox.tf` 通过 VALIDATE（无 production 成员/无明文）。
- 路由配置占位齐全。
- 不宣称「告警已联动/已验证」——真实演练待 Track B 到位后由真人执行。

---

## 7. 回滚/清理

- 见 T22：删除 staging 通知组/路由（不影响 production）。

---

## 8. 红线守约

- 不翻转 `engineering_enabled`；不写真实通知凭据；不接入 production 告警；不自动升级告警。
- 任何「已配置/已验证」状态 PENDING，不伪造。
