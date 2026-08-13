# 生产激活人工签署与执行清单（Phase 3.9.6 交付物）

> 本清单是 **Phase 3.9.6（现有阶段对账与生产激活证据准备层）** 的交付物之一，供真实人工
> （主理人 + 四角色）在 Phase 3.9.6 收口后、线下完成生产激活时使用。
>
> **本阶段（3.9.6）本身不激活、不部署、不宣布 GO。** 终端态固定为
> `PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO`。以下清单描述的是"此态达成之后，
> 人类若要真正激活"必须亲自逐步完成的动作。任何一步未完成，都不得越过 BUILT_NO_GO。

---

## 0. 红线（激活全程不可破，AI 不代执行）

1. `engineering_enabled` 永远不得由 AI 置 `true`；唯一合法改动者是**主理人在人类终端显式提交**。
2. AI 不得输出 `engineering_approved` / `GO` / `PRODUCTION_READY` / 自动部署指令。
3. AI 不得自动评级、自动确认、自动禁用/弃用任何 Agent，不得自动生成真实工程参数或报价。
4. AI 不得代替四角色中任何一人的人工责任（`require_human_actor(USER)` 强制）。
5. 真实生产凭证 / 密钥写入必须由真实运维在受控环境执行，AI 只生成**占位引用**，不写真值。
6. 真实生产数据变更（回滚演练落库、配置下发等）必须由真实人工触发并留痕，AI 不代执行。

---

## 1. 激活前置：本阶段已交付的"就绪证据"（AI 已就位，人类核对）

- [ ] 后端 `GET /governance/activation/readiness` 返回 `status_terminal=PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO`
- [ ] 治理仓库完整性检查器 **9/9**（`scripts/check_governance_repository_integrity.py`）
- [ ] 生产安全 lint **7/7**（`scripts/lint/check_production_security.py`）
- [ ] 审计账本一致性 PASS（`scripts/audit_category_ledger_validator.py`，total=104）
- [ ] 机器可读复核包已生成：`.ai/release-gate/production_activation_review_packet.json`
- [ ] 四角色签署要求已声明（见 `assemble_activation_readiness_dossier` 的 `signoff_requirements`）

---

## 2. 真实人工证据提交（主理人 + 四角色线下）

四角色 = `production-owner` / `release-manager` / `security-owner` / `auditor`。

- [ ] **production-owner**：提交 RC 冻结基线真实证据（commit SHA、清单哈希、冻结时间戳）
- [ ] **release-manager**：提交回滚 runbook 与恢复验证证据（合成演练结论 + 真实回滚路径确认）
- [ ] **security-owner**：提交真实凭证占位 / 凭据治理（HttpOnly Cookie + CSRF）核验结论
- [ ] **auditor**：提交审计完整性结论（四类新增审计事件 ACTIVATION_* 已落账、调用链可溯源）

> 每一类证据须带 `signature_reference`（真实人工签名/工单号，非空）与 `actor_kind="user"`。
> AI 仅登记"签署已发生"这一外部事实（`HUMAN_SIGNOFF_REGISTERED`），不构造签署内容。

---

## 3. 四角色人工签署（真实自然人，逐一线下）

通过 `POST /governance/activation/signoff`（或等价线下记录）完成：

- [ ] production-owner → `GO` / `NO_GO` / `NEED_MORE_EVIDENCE`（reason + signature_reference 双填）
- [ ] release-manager → 同上
- [ ] security-owner → 同上
- [ ] auditor → 同上

签署齐全且全部非 `NO_GO` 后，`HumanSignoffRegistry.snapshot().signoff_complete == True`。

---

## 4. 最终人类裁决（主理人，唯一激活动作）

- [ ] 主理人确认四角色签署齐全、无未决阻断器（B1–B6 全清）、无 pending（PV1–PV6 全清）
- [ ] 主理人在**人类终端**显式将 `agents/config.yaml` 的 `engineering_enabled` 置为 `true`
- [ ] 提交该配置改动并由真实评审合并（**不经过任何自动化脚本代为置位**）
- [ ] 激活后首轮健康检查（`/api/v2/ping`、FastAPI `/docs` 可达、治理 API 只读可达）

---

## 5. 激活后回滚预案（真实人工随时可触发）

- [ ] 回滚 runbook 路径已知：`.ai/runbooks/production_release/`（3.9.2 遗留）+ 本阶段引用
- [ ] 真实回滚演练路径已在 §2 由 release-manager 确认
- [ ] 触发条件：任一核心健康检查失败 / 四角色任一方事后撤回 → 立即回滚并 reopen 治理态

---

## 6. 禁止项（ Checklist 之外的"捷径"一律不合法）

- [ ] 不调用任何 `/activate` 或 `/deploy-production` 端点（**本阶段未提供此类端点**）
- [ ] 不信任任何"全绿 CI = 可以激活"的推断（CI 全绿仅代表 `READY_FOR_HUMAN_REVIEW`）
- [ ] 不绕过四角色任一签署
- [ ] 不在 AI 会话内"视为已签署"——Layer A（客观就绪态）不得顶替 Layer B（人交了/签了什么）

---

*生成依据：Phase 3.9.6 `agents/enterprise/production_release/activation_readiness.py`、
`human_signoff.py`、`governance_activation.py`。本清单为人工执行手册，非自动执行脚本。*
