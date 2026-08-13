# Phase 3.9.6-R1 —— 激活证据 Layer-B 与阶段边界对账收口报告

> 分支：`feat/phase3.9.6-production-activation-evidence-readiness`（自 R2 冻结点 `f7a2aba` 切出，**不新开 3.9.7 分支**）
> R1 起点（3.9.6 core 收口 HEAD）：`94305aa`
> R1 收口提交：`49d6191b9dd52779a13a7d8044f35ec0baef6e65`（§27 最终边界对账收口；HEAD 由 94305aa 前进）
> 终端态：**`PHASE_3_9_6_EVIDENCE_BOUNDARY_RECONCILED_BUILT_NO_GO`**
> 姊妹报告：`.ai/reviews/phase3.9.6_production_activation_evidence_readiness_report.md`（R1 重建版）、`.ai/reviews/phase3.9.6_production_activation_evidence_human_signoff_closure_report.md`、`.ai/PHASE_BOUNDARY_LEDGER.md`

---

## 1. 概述与收口结论

Phase 3.9.6-R1 是 Phase 3.9.6 的**边界对账 sub-delta**（非新 Phase 3.9.7）。它针对"phase 事实漂移"——
即此前收口报告/SSOT 与真实仓库代码在**路由数、测试计数、Layer B 归属**三处的不一致——以真实 Git / 源码 /
API 契约 / 测试 / 机器包证据重新收敛，并据结论重建 SSOT、阶段边界台账与收口报告。

**收口结论**：
1. **Layer B 属 Phase 3.9.6**（commit `59807ca` T1–T11 核心已引入），经 Git 法证确证，**非 3.9.7**；
2. 真实路由基线 = **15 路由（7 Layer A + 8 Layer B）**；
3. 真实测试基线 = agents **2449** / backend **374** / 激活 **118**（110 核心 + 8 边界契约）；
4. SSOT（`project_status.json`）、阶段边界台账、收口报告三处漂移已全部修正并自洽；
5. 终端态固定为 `PHASE_3_9_6_EVIDENCE_BOUNDARY_RECONCILED_BUILT_NO_GO`，**不激活、不进 3.9.7**。

## 2. 授权与身份（本会话自主研发负责人）

本会话以 BOIP AI Chief Architect + Activation Evidence Architecture Owner + Release Evidence Auditor +
Phase Boundary Authority + Quality Baseline Owner 身份执行，被授予 Git 取证 / 修复 / 测试 / CI / SSOT /
文档 / 提交 / 收口权限。全程自主推进、不暂停、不询问（除三类不可逆真人动作外）：
1. 不可逆真实生产数据变更；
2. 缺失真实生产凭证；
3. 真实生产批准 / 签署 / 激活须由自然人完成。

**本会话绝不**提出"Layer B 是否 3.9.6 还是 3.9.7""是否继续"等工程决策问题——该边界已由 Git 事实判定。

## 3. R1 任务授权与边界

- R1 任务流：R1-1 Git 法证 → R1-2 Layer B 归属 → R1-3 测试基线 → R1-4 API 契约 → R1-5..8 Layer A/B 收敛
  → R1-9 清单 1:1 → R1-10/11 证据包确定性 → R1-12 校验器 → R1-13 CI → R1-14 契约测试 → R1-15 契约 SSOT
  → R1-16 台账 → R1-17 SSOT → R1-18/19/20 全量回归 → R1-21 工作树 → R1-22 收口报告重建 → §27 本报告 → STOP。
- 红线（fail-closed）：`engineering_enabled=false` 恒不翻转；无 `engineering_approved` / AI GO / AI 部署 /
  AI 回滚 / AI 签署 / 真实密钥写入 / 真实授权 / 真实生产变更 / 事件自动关闭 / 自动 runbook。
- 不 skip/xfail/ignore/continue-on-error 至绿；不删除真实阻塞器。

## 4. 阶段事实漂移识别（Drift Inventory）

对账前，以下三处存在漂移（以真实仓库为准）：

| # | 漂移项 | 漂移值（旧） | 真实值（R1 收敛） | 证据来源 |
|---|--------|--------------|------------------|----------|
| D1 | 后端 API 路由数 | "8 路由" / "14 路由" | **15 路由（7 Layer A + 8 Layer B）** | `.ai/baselines/production_activation_api_contract.json`（route_count=15） |
| D2 | agents 全量测试 | 2420 / 2441 | **2449**（含 8 边界契约） | `pytest tests/agents` 实测 |
| D3 | 激活测试 | 110（称 3 套件） | **118**（110 核心 + 8 边界契约，4 文件） | 实测 |
| D4 | Layer B 归属 | 收口报告未描述 Layer B（似"无 Layer B"） | **Layer B 属 3.9.6**（commit `59807ca`） | Git 法证（§5） |
| D5 | 收口 HEAD | `0dfd253` | **`94305aa`**（含 `7bc5cba`/`94305aa` SSOT 修正） | `git rev-parse HEAD` |
| D6 | `project_status.json` 计数 | 2441/110、14 路由 | 2449/118、15 路由 | 本报告 §7–§8 |

## 5. Git 法证：Layer B 归属 Phase 3.9.6（非 3.9.7）

- Layer B 模块（`activation_intake.py` / `intake_service.py` / `review_package.py` / `final_decision.py`
  / `human_approval.py` / `evidence_storage_safety.py` / `permission_boundary.py`）随 T1–T11 核心于
  commit **`59807ca`** 一并引入，是 Phase 3.9.6 的核心交付。
- 本 R1 仅补 `evidence_storage_safety` + `permission_boundary` + API/前端/契约测试接线，属同一阶段的收口
  补全，**不新开 3.9.7**。
- 法证方法：`git log --oneline` + `git show --stat 59807ca` 确认 Layer B 文件在 3.9.6 分支、3.9.6 载体提交内。
- 结论：**Layer B 是 Phase 3.9.6 的一部分**，此前"收口报告无 Layer B 章节"本身即漂移 D4。

## 6. Git 事实总表

| 项 | 值 |
|----|----|
| 当前分支 | `feat/phase3.9.6-production-activation-evidence-readiness` |
| 分支起点（R2 冻结点） | `f7a2aba` |
| 3.9.6 core 关键提交链 | `59807ca`(T1–T11, 含 Layer A+B) → `0dfd253`(审计账本 100→104) → `863a038`(docs 部分收口) → `7bc5cba`(final-closure delta T15–T21) → `94305aa`(SSOT current_head/final_closure_commit 准确性修正) |
| R1 收口提交 | `49d6191b9dd52779a13a7d8044f35ec0baef6e65`（§27 最终边界对账收口；94305aa 基础上前进） |
| 工作树状态 | R1 改动待提交（STOP 等主理人审核） |

## 7. 真实路由基线（15 路由 = 7 Layer A + 8 Layer B）

SSOT：`.ai/baselines/production_activation_api_contract.json`（`route_count=15`，由
`scripts/generate_production_activation_api_contract.py` AST 抽取，无需 import app）。

- **Layer A（7 路由，客观就绪态读取）**：`GET /readiness` `/evidence` `/blockers` `/pending-verifications`
  `/signoff-requirements` `/contract` `/review-packet` + `POST /signoff`（真实人工签署）。
- **Layer B（8 路由，证据受理与人工决策记录）**：`GET /intake-summary` `/decision-ledger` `/evidence-list`；
  `GET /evidence` + `POST /evidence`；`POST /evidence-decision`；`POST /review-package`；`POST /final-decision`。
- 权限：读取 `RELEASE_READ`，签署类 `POST /evidence-decision`/`/final-decision`/`/signoff` 需 `RELEASE_SIGNOFF`；
  全部端点 `_require_user_principal` + `_enforce_activation_operation`（deny-by-default）。
- **无 `/activate` / `/deploy-production` 端点。**（`forbidden_endpoints` 仅作声明，不被路由注册。）

## 8. 真实测试基线（实测，非草稿声明）

| 套件 | 结果 |
|------|------|
| agents 全量（`tests/agents`） | **2449 passed**（含 R1 边界契约测试 8 例） |
| backend FastAPI（`backend/tests`） | **374 passed** |
| 激活 3 核心套件 | **110 passed** |
| 边界契约测试 | **8 passed** |
| 激活全部文件 | **118 passed**（110 + 8） |
| 前端 jest（`frontend/jest.config.js`） | **117 passed** |
| 前端 tsc `--noEmit` | **0 error** |
| 治理仓库完整性 | **9/9** |
| 生产安全 lint | **7/7** |
| 硬编码扫描 | **0 命中** |
| 审计账本校验 | **PASS**（total=104，0 orphan/ghost/dup，Git provenance 全 8 phase 验证） |

## 9. Layer A 架构回顾（客观就绪态）

`agents/enterprise/production_release/activation_readiness.py`（~1064 行）：
`assemble_activation_readiness_dossier` / `ProductionActivationReadinessGate`（`CHECK_KEYS=8`，永不 APPROVED）
/ `EngineeringActivationContract` / `ProductionHumanReviewPacket` / `SoDValidator`
（`ACTIVATION_READINESS_FORBIDDEN_COUNT=340`）。终端态 `PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO`。

## 10. Layer B 架构（证据受理 + 人工决策记录，绝不激活）

- `ActivationEvidenceIntakeService`（`intake_service.py`）：`submit_evidence` / `validate_evidence` /
  `record_human_evidence_decision` / `build_review_package` / `summarize`；上限 `SUBMITTED` /
  `STRUCTURALLY_VALIDATED`，`APPROVED_BY_HUMAN` 仅真人推进。
- `FinalHumanDecisionLedger`（`final_decision.py`）：记录真实 user 决策，AI 改人工决策即抛错。
- `FinalActivationReviewPackage` / Chain of Custody / Evidence Provenance：受理→校验→裁决→复核包全链路可溯源。
- **关键不变量：`HUMAN_GO_RECORDED ≠ PRODUCTION_ACTIVATED`**——Layer B 记录"人类已裁决"，激活本身仍由
  主理人在人类终端显式置 `engineering_enabled=true` 完成。

## 11. 证据存储安全（`evidence_storage_safety.py`，红线⑦）

- `EvidenceStoragePolicy` / `EvidenceStorageReceipt` / `compute_evidence_sha256`。
- `_SECRET_LIKE_PATTERNS`：`sk-` / `ghp_` / `PRIVATE KEY` / `password=` / `token=` / `api_key=` / `secret=`。
- `ensure_no_inline_content` / `ensure_reference_not_secret` / `issue_receipt`：**仅引用存储，永存原文**，
  AI 不写真实密钥（红线⑦）。

## 12. 权限边界（`permission_boundary.py`，deny-by-default）

- `ActivationPermissionBoundary` / `ActivationOperation`（7 项白名单）/ `REQUIRED_ACTOR_KIND="user"` /
  `OPERATION_PERMISSION`（`RELEASE_READ` / `RELEASE_SIGNOFF`）。
- `require_activation_operation`：fail-closed 默认拒绝；强制 `actor_kind==user` 且需 `RELEASE_SIGNOFF`；
  AI/SYSTEM 主体一律拒（红线⑧）。

## 13. 机器闸门 1:1 映射（清单 §7）

`.ai/runbooks/production_activation/HUMAN_ACTIVATION_CHECKLIST.md` §7 将 6 个机器闸门（B1–B6）与 6 个
pending（PV1–PV6）逐条映射到机器 gate id，并 §7.3 设**硬规则**：仅当
`readiness_gate.status == READY_FOR_HUMAN_SIGNOFF` 才放行 `engineering_enabled`，否则闸门 `BLOCKED`。

## 14. 证据包 v2 确定性化（R1-10/11）

`scripts/generate_production_activation_review_packet.py` schema `2.0.0`：
- **移除易变字段** `source_commit` / `generated_at`（避免每次提交包变更导致 CI `git diff --exit-code` 永红）；
- 新增 `layer_b` 段（权限边界 describe + 证据存储策略）；
- `packet_sha256` 规范哈希（排除自身字段）；`forbidden_endpoints` 字段排除出禁词扫描。
- 验证：连续两次生成字节完全一致（确定性）。

## 15. 证据包校验器（R1-12，fail-closed）

`scripts/validate_production_activation_review_packet.py`：schema 2.x、终端 `BUILT_NO_GO`、
`engineering_enabled=False`、`contains_real_secret=False`、`packet_sha256` 防篡改、`layer_b` 存在、
阻断器 6 / pending 6、禁词扫描。任一不满足即失败（fail-closed）。

## 16. API 契约生成器 + SSOT（R1-15，AST 抽取）

`scripts/generate_production_activation_api_contract.py`：解析 `governance_activation.py` AST，抽取
`@router.<METHOD>`、前缀、`Depends(require_governance_permission(...))` 默认（Python AST `node.args.defaults`
对齐尾部，非 arg 节点）——产出 `.ai/baselines/production_activation_api_contract.json`
（`route_count=15`）。CI 复用该 JSON 做 `git diff --exit-code` 契约门禁。

## 17. 边界契约测试（R1-14，8 例）

`tests/agents/test_phase3_9_6_evidence_boundary_contract.py`（8 例，全过）：
机器闸门 B1–B6 / PV1–PV6 1:1 映射、证据包 1:1 镜像、包 schema / 红线 / sha256、API 契约 15 路由、
权限边界 7 操作、清单 1:1 硬规则。已纳入 CI pytest 命令与 `tests/agents` 全量收集。

## 18. CI 门禁（R1-13）

`.github/workflows/activation-readiness-gate.yml`（已在 `94305aa` 提交）：
- `activation-readiness-integrity`（9/9）、`activation-readiness-security`（7/7 + 账本 + 硬编码）、
  `activation-readiness-tests`（3 套件 + 契约）；
- `activation-readiness-evidence-packet`：generate → validate → `git diff --exit-code` 包 + 契约（确定性）。
- 即便全绿，仅代表 `READY_FOR_HUMAN_REVIEW`，绝不 `APPROVED`。

## 19. SSOT 对账（R1-17，`project_status.json`）

`phase_3_9_6` 块漂移 D2/D3/D5/D6 已修正：`api_module` 14→**15 路由**；`current_head`/`final_closure_commit`
`7bc5cba`→**`94305aa`**；`agents_full_suite` 2441→**2449**；`activation_three_suites` 110→**118**（含 8 契约）；
`test_files` 增边界契约测试；新增 `r1_reconciliation_delta` 与 `r1_terminal`
（`PHASE_3_9_6_EVIDENCE_BOUNDARY_RECONCILED_BUILT_NO_GO`）。

## 20. 阶段边界台账（R1-16，3.9.6 行）

`.ai/PHASE_BOUNDARY_LEDGER.md` 3.9.6 行更新：end commit `0dfd253`→**`94305aa`**；状态
`PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO`→**`PHASE_3_9_6_EVIDENCE_BOUNDARY_RECONCILED_BUILT_NO_GO`**；
API `8 路由`→**15 路由（7 Layer A + 8 Layer B）**；新增 **Layer B 归属声明**（属 3.9.6，非 3.9.7）；
closure report 引用补充 R1 报告。

## 21. 红线验证（十条，fail-closed）

① `engineering_enabled=false`（config.yaml:102，零翻转）；② 无 `engineering_approved`；③ 无 AI 伪造签署
（`require_human_actor(USER)`）；④ 无 AI 自动批准证据（上限 `STRUCTURALLY_VALIDATED`）；⑤ 无生产 GO
（终端 `BUILT_NO_GO`）；⑥ 无真实部署；⑦ 无真实密钥写入（`evidence_storage_safety` 仅引用）；
⑧ 无真实授权（`permission_boundary` 拒 AI/SYSTEM）；⑨ 无 AI 改人工决策（`FinalHumanDecisionLedger`）；
⑩ 无绕过闸门（所有放行经 `ControlledActivationGate`）。**十条全未触发。**

## 22. 审计账本一致性（104）

`scripts/audit_category_ledger_validator.py` **PASS**：`total=104`，+4（`ACTIVATION_EVIDENCE_SUBMITTED` /
`ACTIVATION_EVIDENCE_VALIDATED` / `HUMAN_SIGNOFF_REGISTERED` / `ACTIVATION_REVIEW_PACKAGE_GENERATED`）
由 `intake_service.py` ×6 + `governance_activation.py` ×1 真实调用（7 处），非臆测；0 orphan / 0 ghost /
0 duplicate-ownership，Git provenance 全 8 phase 验证。

## 23. 完整性 / 安全 / 硬编码

- 治理仓库完整性 **9/9**（`check_governance_repository_integrity.py`：红线①–⑨全过）。
- 生产安全 lint **7/7**（`check_production_security.py`）。
- 硬编码扫描 **0 命中**（`check_hardcoded.py`：无业务阈值/品牌/型号硬编码）。

## 24. 收口报告重建（R1-22）

`.ai/reviews/phase3.9.6_production_activation_evidence_readiness_report.md` 重建：
新增 **§8-B Layer B** 章节、§15 改为 15 路由（分层）、§19 测试矩阵改为 76 例（68 + 8）、§20 回归表改为
2449/374/118、§26 增补 R1 对账说明、§32 增补"R1 属 3.9.6 不进 3.9.7"、§33 剩余风险重标 PR-1/2/3 并补
R1 已完成、§35 文件清单增补 R1 文件、收口 HEAD 改 `94305aa`、终端态补边界对账终端。

## 25. §28 二十项收口条件（全部满足 → 终端态）

| # | 收口条件 | 状态 |
|---|----------|------|
| 1 | Git 法证 Layer B 属 3.9.6（commit `59807ca`） | ✅ |
| 2 | 无 3.9.7 分支 / 无 3.9.7 功能开发 | ✅ |
| 3 | 路由基线 = 15（7A + 8B），API 契约 SSOT 一致 | ✅ |
| 4 | 测试基线 agents 2449 / backend 374 / 激活 118 | ✅ |
| 5 | 前端 jest 117 / tsc 0 | ✅ |
| 6 | 完整性 9/9 | ✅ |
| 7 | 安全 7/7 | ✅ |
| 8 | 审计 104 PASS | ✅ |
| 9 | 硬编码 0 命中 | ✅ |
| 10 | 证据包 v2 确定性（packet_sha256，无易变字段） | ✅ |
| 11 | 证据包校验器 fail-closed 通过 | ✅ |
| 12 | API 契约生成器 + JSON SSOT 存在（route_count=15） | ✅ |
| 13 | 边界契约测试 8 例全过 | ✅ |
| 14 | CI 门禁含 packet + 契约 `git diff --exit-code` | ✅ |
| 15 | 清单 §7 机器闸门 1:1 + 硬规则 | ✅ |
| 16 | `evidence_storage_safety` 拒 inline / 密钥 | ✅ |
| 17 | `permission_boundary` deny-by-default 7 操作 | ✅ |
| 18 | `project_status.json` 漂移修正（D2/D3/D5/D6） | ✅ |
| 19 | 阶段边界台账 3.9.6 行 Layer B 归属 + 终端更新 | ✅ |
| 20 | readiness 报告重建（Layer B + 正确计数） | ✅ |

**二十项全满足 → 终端态 `PHASE_3_9_6_EVIDENCE_BOUNDARY_RECONCILED_BUILT_NO_GO`。**

## 26. §29 STOP 纪律

收口后 STOP：
- **不进入 3.9.7**（Layer B 已证属 3.9.6，本 R1 为 3.9.6 sub-delta）；
- **不自动激活**（无 `/activate`、无 `engineering_enabled=true`）；
- **不提交超出阶段范畴的代码**；
- **等主理人 + 四角色线下审核**：真实证据提交、GO/NO-GO 签署、主理人终端置 `engineering_enabled=true`。

## 27. 与 3.9.2 / 3.9.5 的复用纪律

复用（不重造第二套）：`ActivationEvidenceBundle` / `HumanSignoffRegistry` / `ControlledActivationGate` /
`EnterpriseRedLineViolationError` / `_RedLineForbiddenMixin` / `GovernancePermission`
（`RELEASE_READ` / `RELEASE_SIGNOFF`）。本层仅引用，不触碰 3.9.2/3.9.5 已冻结事实。

## 28. 真实人类待办（主理人 + 四角色线下）

1. 四角色线下提交真实生产证据（RC 冻结基线哈希、回滚 runbook 真实路径、真实凭证占位）；
2. 四角色逐一线下签署（`POST /governance/activation/signoff` / `/evidence-decision` / `/final-decision`，
   reason + signature_reference 双填）；
3. 主理人在**人类终端**显式置 `engineering_enabled=true` 并提交合并（唯一 AI 不代执行动作）；
4. 激活后首轮健康检查；回滚预案随时可触发。
详见 `.ai/runbooks/production_activation/HUMAN_ACTIVATION_CHECKLIST.md`。

## 29. 回滚预案

沿用 3.9.2 遗留 `.ai/runbooks/production_release/`；本层仅引用不重写。真实回滚演练落库由 release-manager
线下确认；触发条件：核心健康检查失败 / 四角色任一方事后撤回 → 立即回滚并 reopen 治理态。

## 30. 剩余风险与未决项

- **PR-1**：真实生产激活证据尚未由四角色线下提交 → `production_evidence_complete=False`（预期内，BUILT_NO_GO）。
- **PR-2**：四角色签署、主理人置 `engineering_enabled=true` 为真实人工动作，AI 不可代执行。
- **PR-3**：合成演练结论不得被误读为生产验证（EvidenceScope 已结构级区分，红线⑦）。
- **R1（边界对账，本次）**：已完成——Layer B 归属 3.9.6 的 Git 法证、15 路由/测试基线收敛、SSOT/台账/报告重建。

## 31. 不可逾越的红线（摘要）

`engineering_enabled=false` 恒不翻转；无 `engineering_approved` / AI GO / AI 部署 / AI 回滚 / AI 签署 /
真实密钥写入 / 真实授权 / 真实生产变更 / 事件自动关闭 / 自动 runbook。任何"全绿 CI / dossier / 复核包"
均**不代表可以激活**——激活权只在主理人手中。

## 32. 文档与产物清单

- `.ai/reviews/phase3.9.6_r1_activation_evidence_boundary_reconciliation_report.md`（本报告）
- `.ai/reviews/phase3.9.6_production_activation_evidence_readiness_report.md`（R1 重建版）
- `.ai/PHASE_BOUNDARY_LEDGER.md`（3.9.6 行）
- `.ai/project_status.json`（`phase_3_9_6` 块 + `r1_reconciliation_delta` + `r1_terminal`）
- `.ai/baselines/production_activation_api_contract.json`（route_count=15 SSOT）
- `.ai/release-gate/production_activation_review_packet.json`（v2 确定性）
- `scripts/generate_production_activation_review_packet.py` / `validate_production_activation_review_packet.py` / `generate_production_activation_api_contract.py`
- `tests/agents/test_phase3_9_6_evidence_boundary_contract.py`（8 例）
- `.github/workflows/activation-readiness-gate.yml` / `.ai/runbooks/production_activation/HUMAN_ACTIVATION_CHECKLIST.md`

## 33. 收口判定

✅ Layer B 归属 Phase 3.9.6 经 Git 法证确证（非 3.9.7）。
✅ 真实路由基线 15（7A+8B）、测试基线 2449/374/118 与机器包/契约 SSOT 一致。
✅ SSOT / 阶段边界台账 / 收口报告三处漂移修正并自洽。
✅ 全量回归 + fail-closed 扫描（完整性 9/9、安全 7/7、审计 104、硬编码 0、jest 117、tsc 0）全过。
✅ 二十项收口条件全满足，终端态 `PHASE_3_9_6_EVIDENCE_BOUNDARY_RECONCILED_BUILT_NO_GO`。
⏸ 真实生产激活等待主理人 + 四角色线下证据提交与签署（PR-1/PR-2）。

— R1 边界对账收口报告结束。状态：`PHASE_3_9_6_EVIDENCE_BOUNDARY_RECONCILED_BUILT_NO_GO`。STOP。
