# BOIP 生产激活治理指南（Production Activation Governance Guide）

> 适用阶段：Phase 3.9.6 —— 现有阶段对账与生产激活证据准备层。
> 分支：`feat/phase3.9.6-production-activation-evidence-readiness`（自 R2 冻结点 `f7a2aba` 切出）。
> 终端态：`PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO`。
> 姊妹文档：`PRODUCTION_RELEASE_GOVERNANCE_GUIDE.md`（3.9.2）、`PRODUCTION_DEPLOYMENT_GUIDE.md`。

本指南说明"生产激活就绪"这一层的治理纪律：它**只准备证据、结构、契约、闸门与人工签署框架，
绝不激活、不部署、不宣布 GO**。真正的激活是由主理人在人类终端显式置 `engineering_enabled=true`
这一唯一动作触发，且须四角色线下签署齐备。

---

## 1. 概述与定位

Phase 3.9.6 是 Phase 3.9.0–3.9.5 的收口闭环层：它把前序各阶段（受控激活准备 / 预生产验证 /
发布闸门 / RC 冻结 / 可观测性 / 遥测）已交付的能力，统一收拢为一份"生产激活就绪 dossier"。
本层回答的问题是：**在交给真人裁决之前，仓库客观层面是否已把激活所需的一切证据、结构、闸门、
契约、签署框架准备就绪？** 它不回答"是否应该激活"——那是四角色与主理人的人类责任。

本层与 3.9.2（发布闸门）、3.9.5（RC 冻结 + 受控激活闸门）职责正交：
- 3.9.2 关注"发布候选是否冻结、发布闸门是否未 BLOCKED"；
- 3.9.5 关注"RC 冻结事实 + 受控激活闸门 fail-closed"；
- 3.9.6 关注"激活前的全量就绪证据是否齐备、四角色人工签署结构是否就位"。

## 2. 角色与职责（Separation of Duties）

| 角色 | 职责 | 是否可由 AI 代执行 |
|------|------|-------------------|
| 主理人（Principal） | 最终裁决并显式置 `engineering_enabled=true` | **否**（唯一人类终端动作） |
| production-owner | 提交 RC 冻结基线真实证据 | 否 |
| release-manager | 提交回滚 runbook / 恢复验证证据 | 否 |
| security-owner | 提交真实凭证占位 / 凭据治理核验 | 否 |
| auditor | 提交审计完整性结论（含 4 类 ACTIVATION_* 审计） | 否 |
| AI / Agent | 组装 dossier、登记"签署已发生"、生成复核包 | 仅登记事实，不构造决策 |

SoD 校验见 §8。四角色必须由**不同真实自然人**承担（policy_distinct_natural_persons）。

## 3. 证据模型（Activation Evidence Bundle v2）

`build_default_activation_evidence_bundle_v2(rc_id)` 产出 v2 证据包，逐项记录前序各阶段产物：
phase / artifact / commit / report / hash / verification_status / human_review_status /
evidence_scope / is_real_production_evidence。

关键不变量：
- `production_evidence_complete` 在当前（`BUILT_NO_GO`）态为 **False**——因为真实生产证据尚未由
  四角色线下提交。
- 任何 `evidence_scope == "staging"` / `is_real_production_evidence == False` 的项，不得被视作
  生产就绪证据（合成演练 PASS ≠ 生产已验证，见 §11）。

## 4. 生产激活就绪 dossier

`assemble_activation_readiness_dossier(rc_id, root_dir, signoff_registry)` 从仓库事实合成只读
dossier，含：rc_id、engineering_enabled、evidence_bundle、signoff_requirements、sod、blockers、
pending_verification、readiness_gate、contract、status_terminal。

`status_terminal` 恒为 `PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO`（模块常量，不可被运行
时改写）。dossier 不持久化、不激活，仅供 API / 报告消费。

## 5. 生产激活就绪闸门（ProductionActivationReadinessGate）

`ProductionActivationReadinessGate`（`_RedLineForbiddenMixin`）执行 8 项检查（`CHECK_KEYS=8`）：
`engineering_enabled_false` / `evidence_bundle_complete` / `governance_integrity_9_9` /
`rollback_reference_present` / `recovery_validation_present` / `no_activation_blockers` /
`human_signoffs_complete` / `no_pending_verification`。

状态只可能是 `BLOCKED` / `PENDING_VERIFICATION` / `READY_FOR_HUMAN_SIGNOFF`，**永不 `APPROVED`**。
`set_engineering_enabled(...)` 触发 `EnterpriseRedLineViolationError`（红线②：禁开 engineering_enabled）。

## 6. 四角色签署（HumanSignoffRegistry / build_human_signoff_record）

`HumanSignoffRegistry(rc_id)` 维护签署快照（`.signoff_complete` / `.effective_records`）。
`build_human_signoff_record(...)` 强制：`actor_kind == "user"`、非空 `actor_id`、非空
`signature_reference`。`REQUIRED_SIGNOFF_ACTOR_KIND = "user"`——AI 主体（actor_kind != "user"）的
签署请求一律拒绝。

四角色要求由 `build_default_signoff_requirements(registry)` 生成，每个要求含
`required_role` / `current_status` / `signed_by` / `decision` / `is_satisfied`。

## 7. 工程激活契约（EngineeringActivationContract）

`EngineeringActivationContract` 声明激活前置：`required_gates` / `required_evidence` /
`required_signoffs` / `blocker_count` / `pending_count` / `activation_allowed_for_human`。

`activation_allowed_for_human` 仅当就绪闸门为 `READY_FOR_HUMAN_SIGNOFF` 且无阻断器 / 无 pending /
四角色签署齐备时才可能为真——且即便为真，也只是"人类**可以**激活"，不代表"已激活"或"AI 应激活"。

## 8. SoD 校验（SoDValidator）

`SoDValidator.validate(registry)` 校验四角色：四角色是否齐备、是否全为真实 USER、是否由不同自然人
承担（distinct_actor_ids / policy_distinct_natural_persons）、`ok` 标志。任一不满足 → SoD 不通过，
契约 `activation_allowed_for_human` 必为 False。

## 9. 阻断器（B1–B6）与 pending 登记（PV1–PV6）

`build_default_activation_blockers()` 返回 B1–B6（工程激活开关、真实生产证据、回滚演练真实落库、
恢复验证真实数据、凭据真实治理、四角色签署齐备），每项含
`blocker_id` / `category` / `description` / `source` / `evidence` / `owner_role` /
`resolution_status`。

`build_default_pending_verification_registry()` 返回 PV1–PV6（待真人提交/核验的真实证据项），每项含
`id` / `phase` / `item` / `reason` / `required_evidence` / `required_role` / `current_status` /
`source_report`。B1–B6 与 PV1–PV6 在当前态均未消解，是闸门 BLOCKED 的根因。

## 10. 复核包（ProductionHumanReviewPacket）

`ProductionHumanReviewPacket`（`.to_dict()` 含 `schema_version="1.0.0"`、`contains_real_secret=False`）
汇总：release_candidate / commit_sha / artifact_manifest / test_summary / security_summary /
identity_summary / dr_summary / observability_summary / telemetry_summary / incident_readiness /
rollback / pending_verification / blockers / required_signatures。它是**供人裁决的材料包**，不产出
放行结论。

## 11. 审计留痕（4 类 ACTIVATION_* 事件）

3.9.6 真实新增 4 类审计事件（基线 100 → 104），均由本阶段真实新增的接收/签署/复核能力之
`AuditService` 方法记录：
- `ACTIVATION_EVIDENCE_SUBMITTED`（audit.py:278，record 方法:3397）
- `ACTIVATION_EVIDENCE_VALIDATED`（audit.py:279，record 方法:3424）
- `HUMAN_SIGNOFF_REGISTERED`（audit.py:280，record 方法:3451）
- `ACTIVATION_REVIEW_PACKAGE_GENERATED`（audit.py:281，record 方法:3478）

真实调用点 **7 处**：`intake_service.py` ×6 + `backend/app/api/governance_activation.py` ×1。
这些审计只记录"行为已发生"这一外部事实，AI 不构造 `APPROVED_BY_HUMAN` / `REJECTED_BY_HUMAN`。

## 12. 红线与 fail-closed 禁则

1. `engineering_enabled` 永远不得由 AI 置 `true`；
2. 禁输出 `engineering_approved` / `GO` / `PRODUCTION_READY` / 自动部署；
3. 禁 AI 自动评级 / 确认 / 禁用 / 弃用 Agent、自动生成真实工程参数或报价；
4. 禁 AI 代替四角色任一人工责任（`require_human_actor(USER)` 强制）；
5. 真实生产凭证 / 密钥写入由真实运维在受控环境执行，AI 只生成占位引用；
6. 真实生产数据变更由真实人工触发并留痕，AI 不代执行；
7. 合成演练 PASS 不得被伪装为生产已验证（EvidenceScope 区分 SYNTHETIC/STAGING/PRODUCTION/HUMAN）；
8. 测试不得用 skip / xfail 绕过至绿（见 §18）。

## 13. 后端 API（governance_activation.py，8 路由，无 /activate）

前缀 `/governance/activation`，tags `["governance-activation"]`，复用 `RELEASE_READ` /
`RELEASE_SIGNOFF`（admin 独享 signoff，`governance:release:signoff`）。路由：
- `GET /readiness`、`GET /evidence`、`GET /blockers`、`GET /pending-verifications`、
  `GET /signoff-requirements`、`GET /contract`、`GET /review-packet`（均只读）；
- `POST /signoff`（真实人工签署，强制 `actor_kind=user`、非空 `signature_reference`，
  记录 `audit.record_human_signoff_registered`，registry 落 `build_human_signoff_record`）。

**无任何 `/activate` 或 `/deploy-production` 端点。** 前端看板亦无自动 GO / 激活 / 部署按钮。

## 14. 前端看板（governance-activation/page.tsx）

`"use client"`，`RC_ID="RC-3.9.6"`，`GATE_CHECK_KEYS=8`。读取 `GET /governance/activation/readiness`
（权限 `governance:release:read`），展示：BUILT_NO_GO 琥珀色横幅、就绪总览、8 项闸门检查、B1–B6 阻断器、
PV1–PV6 pending、四角色签署要求、工程激活契约、真实人工签署表单（role / decision / reason /
signature_reference，**reason 与 signature_reference 双填**方可提交）。尾注明确"无 /activate 或
/deploy-production 端点"。

## 15. CI 门禁（activation-readiness-gate.yml）

`.github/workflows/activation-readiness-gate.yml`（fail-closed，三道 job）：
1. `activation-readiness-integrity`：治理仓库完整性 9/9；
2. `activation-readiness-security`：生产安全 lint 7/7 + 审计账本校验 + 硬编码扫描 0 命中；
3. `activation-readiness-tests`：3.9.6 就绪层契约 + 3.9.2 发布闸门 / RC 冻结回归。

分支覆盖：`main`（占位）+ 显式 `feat/phase3.9.6-production-activation-evidence-readiness` +
通配 `feat/phase3.9.*` / `feat/phase*-release-*` / `release/**` + 历史 `feat/phase3.9.2-production-release-gate`。
**即便全绿，也只代表 `READY_FOR_HUMAN_REVIEW` / `READY_FOR_HUMAN_SIGNOFF`，绝不 APPROVED。**

## 16. SSOT 与阶段边界

- `project_status.json`：`phase_3_9_6_status = "PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO"`；
- `roadmap_v8.md`：§35.10（3.9.6 交付物与门禁）、§35.11（3.9.6 CI 门禁）；
- `PHASE_BOUNDARY_LEDGER.md`：3.9.6 行（start `f7a2aba`，end `0dfd253`，状态 `BUILT_NO_GO`）；
- 审计 JSON Ledger：`.ai/baselines/audit_action_category_ledger.json` `total=104`，与 `audit.py` 枚举一致；
- 收口报告：`.ai/reviews/phase3.9.6_production_activation_evidence_readiness_report.md`（35§）。

## 17. 真激活流程（线下，主理人唯一动作）

本层不执行以下任何一步；以下为"就绪证据齐备后，人类若要真正激活"的线下步骤（见
`.ai/runbooks/production_activation/HUMAN_ACTIVATION_CHECKLIST.md`）：
1. 四角色线下提交真实生产证据（RC 冻结基线 / 回滚 runbook / 真实凭证占位）；
2. 四角色逐一线下签署（production-owner / release-manager / security-owner / auditor）；
3. 主理人在**人类终端**显式置 `engineering_enabled=true` 并提交合并（唯一 AI 不代执行之动作）；
4. 激活后首轮健康检查；回滚预案随时可触发。

## 18. 测试纪律（fail-closed，no skip/xfail-to-green）

`tests/agents/test_production_activation_readiness.py`（28+ 用例）覆盖：dossier 组装、闸门 8 检查
fail-closed、契约 `activation_allowed_for_human` 在当前态为 False、signoff registry 强制 user 主体
与非空签名、SoD 校验、阻断器 / pending 语义、复核包 `contains_real_secret=False`、API 路由存在且无
`/activate`、前端类型契约、CI 门禁引用文件存在。任何 fail-closed 行为变更不得以 skip / xfail 绕过
至绿（红线⑧）。

## 19. 回滚预案

回滚 runbook 沿用 3.9.2 遗留 `.ai/runbooks/production_release/`，本层仅引用不重写。真实回滚演练
落库由 release-manager 在 §17 线下确认；触发条件：核心健康检查失败 / 四角色任一方事后撤回 → 立即
回滚并 reopen 治理态。

## 20. 机器可读产物

- `.ai/release-gate/production_activation_review_packet.json`：机器可读复核包（schema_version 1.0.0，
  `contains_real_secret=False`，`terminal_status=PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO`）；
- `.ai/runbooks/production_activation/HUMAN_ACTIVATION_CHECKLIST.md`：人工激活执行手册；
- `scripts/generate_production_activation_review_packet.py`：上述 JSON 的生成器（只读，CI 可复用）。

## 21. 收口状态与 STOP 纪律

**本阶段收口态 = `PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO`**：全部软件证据 / 人工责任结构 /
检查清单包 / 回滚包 / 签署模板 / Go-No-Go 输入已就位，但**无真实生产激活**。

收口后 STOP：不进入 3.9.7、不自动激活、不提交超出阶段范畴的代码。剩余真实人类动作：
主理人 + 四角色线下提交真实证据并签署，主理人显式置 `engineering_enabled=true`。
AI 在本阶段的所有产出均为"准备"性质，不构成任何放行授权。
