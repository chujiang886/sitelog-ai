# Phase 3.9.14 人类动作清单（Human Checklist）

> 本文件是 AI 收口后、**主理人 + 四角色**线下完成的动作清单。
> AI 侧终态：`PHASE_3_9_14_EXTERNAL_STAGING_RUNTIME_E2E_QUALIFICATION_BUILT_NO_GO`（Apply Gate = `pending_human_authorization`）。
> 全部勾选且四角色签署后，方可解除 `pending_human_authorization` 推进至 `AUTHORIZED_AWAITING_APPLY`（仍非 GO/APPROVED/PRODUCTION_READY）。
> 真实 apply / 执行 / 部署属主理人在人类终端带外动作，AI 不代执行、不代签、不代置 `engineering_enabled`。

---

## A. 前置确认（AI 收口已证明）

- [x] 分支 `feat/phase3.9.14-external-staging-runtime-deployment-e2e-qualification` 已 STOP
- [x] `engineering_enabled=false` 全程守约（config.yaml:102 未改）
- [x] 8/8 External Resources `PENDING_EXTERNAL_STAGING_RESOURCE`，0 真实密钥
- [x] 7 层 harness 结论全部 plan-only：九项隔离 / 13 项资格 / Runtime Health / E2E / 故障恢复回滚 / 变更管控 / 证据链
- [x] Branch Integrity PASS；审计 total=129（0 新增企业类目）
- [x] 测试：3.9.14 agents (T16-T33 43 passed + T34-T49 新增) + backend API（T48-T49 新增） + 跨 Phase 聚焦回归 0 失败
- [x] 确定性运行时执行包 hash=`d632d6610e20c48ec72a2a7a04dbd17aee8c76ccdb436541960147fc5d4b9839`（CI 闸门确定性校验比对）
- [x] 双钥匙 Apply Gate：Machine Safety Key 已注册（plan_only + engineering_enabled=false），Human Authorization Key 缺失（待真人 `actor_kind=USER`）
- [x] 变更管控：`is_go_or_approved` 恒 False；终端态 `PHASE_3_9_14_..._BUILT_NO_GO`

---

## B. 真实资源提供（Track B，四角色线下）

- [ ] production-owner：提供真实 `database` 引用（DSN / 账号，引用非明文）
- [ ] security-owner：提供真实 `secret_provider` 引用（Secret Manager ARN/ID，引用非明文）
- [ ] security-owner：提供真实 `identity_provider` 引用（OIDC/SSO tenant，引用非明文）
- [ ] production-owner：提供真实 `object_storage` 引用（COS bucket，引用非明文）
- [ ] release-manager：提供真实 `telemetry` 引用（CLS/Prometheus，引用非明文）
- [ ] release-manager：提供真实 `alert_sandbox` 引用（Monitor/Alert，引用非明文）
- [ ] production-owner：提供真实 `domain_tls` 引用（DNSPod + SSL，引用非明文）
- [ ] production-owner：提供真实 `deployment_target` 引用（TKE + TCR，引用非明文）
- [ ] 全部引用经 3.9.12 `POST /human-input-record`（USER 专属，禁明文密钥）登记

---

## C. 跨环境隔离验证（staging ≠ production）

- [ ] staging 令牌 ≠ production 令牌（不复用 production 命名空间）
- [ ] 9/9 隔离约束逐项真实验证通过
- [ ] IaC 模块 `infrastructure/staging/*.tf` 真实填充（移除 count=0 / placeholder，经真人补全）
- [ ] 13 项 Runtime Qualification 由真人接入真实资源后真实运行并验证通过

---

## D. 双钥匙授权（AUTHORIZED_AWAITING_APPLY）

- [ ] Machine Safety Key：机器生成，要求 `engineering_enabled=false & plan_only=true`（AI 侧已注册）
- [ ] Human Authorization Key：`actor_kind=USER`，四角色在人类终端签署（AI 不得 mint）
- [ ] `DualKeyAuthorization.is_authorized` == True（双钥匙齐备）
- [ ] Apply Gate 升至 `AUTHORIZED_AWAITING_APPLY`（仍非 GO/APPROVED/PRODUCTION_READY）

---

## E. 真实执行（带外，主理人显式）

- [ ] 主理人在人类终端按 `.ai/runbooks/external_staging_runtime_e2e_qualification_runbook.md` 跑真实 Runtime Deploy
- [ ] Resource Registration → Connectivity → Isolation → Runtime Deployment → E2E → Failure/Recovery/Rollback 逐项验证
- [ ] 四角色签署 Runtime E2E GO

---

## F. 最终生产治理（仅最终）

- [ ] 后续 Production Readiness / Production Evidence 阶段完成
- [ ] 最终 Production Human GO
- [ ] **仅当**最终生产治理条件全部满足时，主理人在人类终端显式置 `engineering_enabled=true`
- [ ] 该动作**不属 3.9.14**，排在整个 External Staging 链 + Production Human GO 之后

---

## 禁止项（红线，AI 与人类均须遵守）

- [ ] 禁 AI mint Human Authorization Key（须 `actor_kind=USER`）
- [ ] 禁在 3.9.14 阶段置 `engineering_enabled=true`
- [ ] 禁伪造 7 层结论或真实外部证据（production 泄漏 / 真实执行完成）
- [ ] 禁提供/调用 `/apply` `/deploy` `/migrate` `/execute` `/rollback` `/activate` 端点
- [ ] 禁吸收 Production Handoff WIP（仅存 stash 隔离区）
