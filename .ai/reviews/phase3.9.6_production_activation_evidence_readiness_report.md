# Phase 3.9.6 收口报告 —— 现有阶段对账与生产激活证据准备层

> 分支：`feat/phase3.9.6-production-activation-evidence-readiness`（自 R2 冻结点 `f7a2aba` 切出）
> 收口 HEAD：`0dfd253`（含 `59807ca` T1–T11 核心 + `0dfd253` 审计账本登记）
> 终端态：**`PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO`**
> 姊妹报告：Phase 3.9.2/3.9.4/3.9.4-R2/3.9.5 各收口报告；`.ai/PHASE_BOUNDARY_LEDGER.md`

---

## 1. 概述与收口结论

Phase 3.9.6 是 Phase 3.9.0–3.9.5 的**收口闭环层**：它把前序各阶段（受控激活准备 / 预生产验证 /
发布闸门 / RC 冻结 / 可观测性 / 遥测）已交付的能力，统一收拢为一份"生产激活就绪 dossier"，并建成
四角色人工签署治理、就绪闸门、工程激活契约、后端 API、前端看板与 CI 门禁。

**收口结论**：本阶段**全部软件证据、人工责任结构、检查清单包、回滚包、签署模板、Go-No-Go 输入均已
就位**，但**无真实生产激活**。终端态固定为 `PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO`。
真实激活是主理人在人类终端显式置 `engineering_enabled=true` 这一唯一动作，须四角色线下签署齐备，
AI 不代执行。本阶段 STOP，不进入 3.9.7、不自动激活、不提交超出范畴的代码。

## 2. 授权与身份（本阶段自主研发负责人）

本阶段以 BOIP AI Chief Architect + Production Activation Readiness Architect + Release Evidence
Authority + Production Governance Auditor + Phase Boundary Owner + 本阶段自主研发负责人身份执行，
被授予：Git 取证 / 修复 / 测试修复 / CI / SSOT / 文档 / 提交 / 收口权限。除以下三类必须停顿外，全程
自主推进、不暂停、不询问：
1. 不可逆真实生产数据变更；
2. 缺失真实生产凭证；
3. 真实生产批准 / 签署 / 激活须由自然人完成。

## 3. 阶段定位与边界

- 3.9.0–3.9.5 已分别交付：受控激活准备、预生产验证 + DR 演练、发布闸门 + 证据包、RC 冻结 + 受控激活
  闸门、可观测性/SRE/事故响应准备、遥测接入 + 合成运维验证。
- 3.9.6 不重造上述任何一层，只做**对账 + 收口 + 证据准备**：把既有能力聚合成"激活前就绪态"，
  并为"真实人工裁决"准备好结构、契约、闸门、签署框架。
- 边界异常（曾误判）：早期 forensics 文档曾因 `git status`/`git diff` 被 SIGKILL（Exit 137）污染，
  误以为"3.9.6 增量是未提交的工作树文件、+4 审计是臆测"。经权威 blob-hash 比对证明：3.9.6 核心增量
  （T1–T11）**已提交**于 `59807ca` + `0dfd253`，工作树干净；+4 审计**真实、可溯源**（见 §6）。

## 4. 真实 Git 事实

| 项 | 值 |
|----|----|
| 当前分支 | `feat/phase3.9.6-production-activation-evidence-readiness` |
| 分支起点（R2 冻结点） | `f7a2aba` |
| 收口 HEAD | `0dfd253` |
| 关键提交 | `59807ca` production activation evidence intake & human signoff governance (T1–T11)<br>`0dfd253` register phase 3.9.6 in the audit category ledger (100→104) |
| 工作树状态 | 干净（本收口新增文件将随逻辑提交一并入仓） |

## 5. 与既有 3.9.6 增量对账（SIGKILL 污染澄清）

- 错误前提：会话早期 `git status`/`git diff` 输出被 SIGKILL（Exit 137）截断，呈现"幽灵修改/未跟踪文件"，
  误导出"6 个未提交文件 / +4 审计臆测"等错误结论。
- 权威核验：`git cat-file -e HEAD:<path>` 证明所有被列路径**已提交**；`git hash-object` 与
  `git rev-parse HEAD:<path>` blob-hash 比对证明关键路径工作树与 HEAD **完全一致**。
- 结论：3.9.6 增量早已在分支上提交，本阶段是在此基础上补齐收口（API/UI/CI/SSOT/文档/测试/报告），
  **非从零重建**。

## 6. 审计增量对账（+4 真实，100→104，证伪"臆测"误判）

- 3.9.6 真实新增 4 类审计事件（基线 100 → 104）：
  `ACTIVATION_EVIDENCE_SUBMITTED` / `ACTIVATION_EVIDENCE_VALIDATED` /
  `HUMAN_SIGNOFF_REGISTERED` / `ACTIVATION_REVIEW_PACKAGE_GENERATED`。
- 真实调用点 **7 处**：`intake_service.py` ×6 + `backend/app/api/governance_activation.py` ×1；
  对应 `AuditService` 记录方法 4 个（`audit.py:3397/3424/3451/3478`）。
- 校验：`.ai/baselines/audit_action_category_ledger.json` `total=104`，与 `audit.py` 枚举 104 成员一致；
  `scripts/audit_category_ledger_validator.py` **PASS**（0 orphan / 0 ghost / 0 duplicate-ownership，
  Git provenance 全 8 phase 验证通过）。
- 早期 forensics 文档 §3 的"+4 臆测"判定**已被 §6.1 修订与 §7 最终结论推翻**，本台账以真实 Git 事实为准。

## 7. 终端态定义

`PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO` —— 模块常量（`activation_readiness.py`
`status_terminal`），不可被运行时改写。语义：就绪证据齐备、可交真人裁决，但**未激活、未部署、未 GO**。

## 8. 核心交付物（Layer A）

`agents/enterprise/production_release/activation_readiness.py`（~1064 行，已提交）核心 API：
- `assemble_activation_readiness_dossier(rc_id, root_dir, signoff_registry)` —— 从仓库事实合成只读
  dossier（终端态、engineering_enabled、证据包、签署要求、SoD、阻断器、pending、闸门、契约）。
- `ProductionActivationReadinessGate`（`_RedLineForbiddenMixin`，`CHECK_KEYS=8`）—— 状态只产
  `BLOCKED`/`PENDING_VERIFICATION`/`READY_FOR_HUMAN_SIGNOFF`，**永不 APPROVED**；
  `set_engineering_enabled` 触发 `EnterpriseRedLineViolationError`。
- `EngineeringActivationContract` —— `activation_allowed_for_human` 仅当闸门 READY 为真（仍只是
  "可交真人裁决"，非"已激活"）。
- `ProductionHumanReviewPacket` —— 机器可读复核包（`schema_version="1.0.0"`、
  `contains_real_secret=False`）。
- `SoDValidator` —— 四角色齐备 / 全真实 USER / 不同自然人 / ok。
- `ACTIVATION_READINESS_FORBIDDEN_COUNT = 340`（结构级禁名，`forbidden.py` 调用即抛）。

## 9. 证据包 v2

`build_default_activation_evidence_bundle_v2(rc_id)` 聚合 3.9.0–3.9.5 关键证据（phase / artifact /
commit / report / hash / verification_status / human_review_status / evidence_scope /
is_real_production_evidence）。当前 `production_evidence_complete=False`：真实生产证据尚未由四角色线下
提交；任何 `evidence_scope != PRODUCTION` 的项不得视作生产就绪证据。

## 10. 生产激活就绪闸门（8 检查，永不 APPROVED）

`CHECK_KEYS=8`：`engineering_enabled_false` / `evidence_bundle_complete` / `governance_integrity_9_9` /
`rollback_reference_present` / `recovery_validation_present` / `no_activation_blockers` /
`human_signoffs_complete` / `no_pending_verification`。硬检查缺失或尚有阻断器 → `BLOCKED`；签署/待核验
未决 → `PENDING_VERIFICATION`；全过 → `READY_FOR_HUMAN_SIGNOFF`。**无 APPROVED 分支**。

## 11. 工程激活契约

`EngineeringActivationContract` 声明前置：`required_gates` / `required_evidence` / `required_signoffs`
/ `blocker_count` / `pending_count` / `activation_allowed_for_human`。当前态：契约 `activation_allowed_for_
human=False`（闸门 blocked、B1–B6 未解、PV1–PV6 未清、四角色未签）。

## 12. 四角色签署与 SoD

`HumanSignoffRegistry` + `build_human_signoff_record` 强制：`actor_kind=="user"`、非空 `actor_id`、
非空 `signature_reference`（`REQUIRED_SIGNOFF_ACTOR_KIND="user"`）。四角色 =
`production-owner` / `release-manager` / `security-owner` / `auditor`（必须不同真实自然人，
`SoDValidator.policy_distinct_natural_persons`）。AI 主体签署一律拒绝。

## 13. 阻断器 B1–B6 与 pending PV1–PV6

`build_default_activation_blockers()` 返回 B1–B6：工程激活开关、真实生产证据、回滚演练真实落库、恢复
验证真实数据、凭据真实治理、四角色签署齐备。`build_default_pending_verification_registry()` 返回
PV1–PV6：待真人提交/核验的真实证据项。二者是当前态闸门 `BLOCKED` 的根因，须由线下真实动作消解。

## 14. 复核包

`ProductionHumanReviewPacket` 汇总 release_candidate / commit_sha / artifact_manifest / test_summary /
security_summary / identity_summary / dr_summary / observability_summary / telemetry_summary /
incident_readiness / rollback / pending_verification / blockers / required_signatures。仅输事实与证据，
不夹带 AI 审批结论。

## 15. 后端 API（8 路由，无 /activate）

`backend/app/api/governance_activation.py`（注册入 `api/__init__.py` + `main.py`）：前缀
`/governance/activation`，tags `["governance-activation"]`，复用 `RELEASE_READ`/`RELEASE_SIGNOFF`
（admin 独享 signoff）。路由：7 个只读（`/readiness` `/evidence` `/blockers` `/pending-verifications`
`/signoff-requirements` `/contract` `/review-packet`）+ `POST /signoff`（真实人工签署，强制 user 主体 +
非空签名，记录 `audit.record_human_signoff_registered`）。**无任何 `/activate` 或 `/deploy-production`
端点。**

## 16. 前端看板

`frontend/src/app/governance-activation/page.tsx`（`"use client"`，`RC_ID="RC-3.9.6"`，
`GATE_CHECK_KEYS=8`）：只读展示 + 真实人工四角色签署表单（需 reason + signature_reference 双填），
BUILT_NO_GO 琥珀色横幅，无自动 GO/激活/部署按钮，尾注明确"无 /activate 或 /deploy-production 端点"。

## 17. 机器可读产物

- `.ai/release-gate/production_activation_review_packet.json`：复核包（`contains_real_secret=False`、
  `terminal_status=PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO`、`automated_approval_prohibited=True`），
  由 `scripts/generate_production_activation_review_packet.py` 生成（只读，CI 可复用）。
- `.ai/runbooks/production_activation/HUMAN_ACTIVATION_CHECKLIST.md`：人工激活执行手册
  （红线 / 前置核对 / 证据提交 / 四角色签署 / 主理人唯一激活动作 / 回滚 / 禁止项）。

## 18. 红线清单（fail-closed）

① 不置 `engineering_enabled=true`（AI）；② 不输出 `engineering_approved`/`GO`/`PRODUCTION_READY`/
自动部署；③ 不 AI 自动评级/确认/禁用/弃用 Agent、不自动生成真实工程参数或报价；④ 不 AI 代替四角色
任一人工责任（`require_human_actor(USER)` 强制）；⑤ 真实凭证/密钥写入由真实运维在受控环境执行，AI 只
生成占位引用；⑥ 真实生产数据变更由真实人工触发并留痕；⑦ 合成演练 PASS 不得伪装为生产已验证
（EvidenceScope 区分）；⑧ 测试不得用 skip/xfail 绕过至绿；⑨ 不提供 `/activate`/`/deploy-production`
端点；⑩ 不自动执行运维动作/关闭事件。

## 19. 测试矩阵（47 用例，fail-closed，无 skip/xfail）

`tests/agents/test_production_activation_readiness.py`（47 用例，全部通过）：
- dossier 终端态/engineering_enabled/闸门/契约/证据包/阻断器/pending/签署要求/SoD（9）；
- 闸门 8 检查、永不 APPROVED 穷举、fail-closed（硬缺失/eng=true 仍 blocked/pending 判定）（7）；
- 结构级禁名 340 项 + 关键禁名（2）；
- 契约字段与 to_dict（2）；
- 签署强制 user/非空签名/非空 actor + 空 registry 未齐（5）；
- SoD 空 registry 不 ok/四角色不在/键齐全（3）；
- EvidenceScope 真实 vs 合成（4）；
- 枚举无 APPROVED + 角色常量（3）；
- build_default 工厂（4）；
- 复核包 JSON 存在且 `contains_real_secret=False`（1）；
- 后端 API 8 路由无禁用端点 + 唯一 POST=signoff（2）；
- 前端看板契约（3）；
- CI yml 引用与 job 数 + 分支覆盖（2）。

## 20. 回归结果

| 套件 | 结果 |
|------|------|
| agents 全量（`tests/agents`） | **2420 passed** |
| backend FastAPI（`backend/tests`） | **374 passed** |
| 前端 jest（`frontend/jest.config.js`） | **117 passed** |
| 前端 tsc `--noEmit` | **0 error** |
| 治理仓库完整性 | **9/9** |
| 生产安全 lint | **7/7** |
| 硬编码扫描 | **0 命中** |
| 审计账本校验 | **PASS**（total=104，0 orphan/ghost/dup，Git provenance 全验证） |

## 21. 治理仓库完整性 9/9

`scripts/check_governance_repository_integrity.py --root .`：红线①（engineering_enabled 不翻转）
至红线⑨（阶段编号唯一）全部通过。

## 22. 生产安全 lint 7/7

`scripts/lint/check_production_security.py`：engineering_enabled 保持 false、static-dev 不得为缺省
身份等 7 类红线静态扫描全过。

## 23. 硬编码扫描 0 命中

`scripts/lint/check_hardcoded.py`：未发现业务阈值、品牌或型号硬编码。

## 24. 审计账本校验 PASS

`scripts/audit_category_ledger_validator.py`：JSON Ledger SSOT（由 Git 真实提交重建）与 `audit.py`
枚举一致，3.9.6（+4）`total_at_commit=104`，全 8 phase Git provenance 验证通过。

## 25. CI 门禁 activation-readiness-gate.yml

`.github/workflows/activation-readiness-gate.yml`（fail-closed，三道 job）：
1. `activation-readiness-integrity`：治理完整性 9/9；
2. `activation-readiness-security`：生产安全 lint 7/7 + 审计账本校验 + 硬编码 0 命中；
3. `activation-readiness-tests`：3.9.6 就绪层契约 + 3.9.2 发布闸门 / RC 冻结回归。
分支覆盖：`main`（占位）+ 显式 3.9.6 分支 + 通配 `feat/phase3.9.*`/`feat/phase*-release-*`/`release/**`
+ 历史 3.9.2 分支。**即便全绿，也只代表 `READY_FOR_HUMAN_REVIEW`，绝不 APPROVED。**

## 26. SSOT 对账

- `project_status.json`：新增 `phase_3_9_6_status = "PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO"`。
- `roadmap_v8.md`：新增 §35.10（3.9.6 交付物与门禁）、§35.11（3.9.6 CI 门禁）。
- `PHASE_BOUNDARY_LEDGER.md`：3.9.6 行收口（start `f7a2aba`，end `0dfd253`，状态 `BUILT_NO_GO`，
  审计真实 +4 已注明，早期"臆测"误判已批注推翻）。
- `.ai/baselines/audit_action_category_ledger.json`：`total=104`，与枚举一致。

## 27. 阶段边界台账更新

`.ai/PHASE_BOUNDARY_LEDGER.md` 3.9.6 行已据真实 Git（起点 `f7a2aba`、收口 `0dfd253`、2 提交）回填，
避免"代码跑到 3.9.6 但报告停 3.9.5"的边界漂移。

## 28. 文档

- `docs/PRODUCTION_ACTIVATION_GOVERNANCE_GUIDE.md`（21 节）：完整激活治理纪律。
- `docs/PRODUCTION_DEPLOYMENT_GUIDE.md` §16：新增"生产激活证据准备层（Phase 3.9.6）"引用章节。

## 29. 与 3.9.2 / 3.9.5 的关系与复用纪律

- 复用（不重造第二套）：`ActivationEvidenceBundle` / `HumanSignoffRegistry` / `ControlledActivationGate`
  / `EnterpriseRedLineViolationError` / `_RedLineForbiddenMixin` / `GovernancePermission`（`RELEASE_READ`
  `RELEASE_SIGNOFF` 复用于激活 API，同一 admin 守门四角色）。
- 3.9.2 关注"发布闸门是否未 BLOCKED"；3.9.5 关注"RC 冻结 + 受控激活闸门"；3.9.6 关注"激活前全量就绪
  证据 + 四角色签署结构"。三者职责正交，本层不触碰 3.9.2/3.9.5 已冻结事实。

## 30. 真实人类待办（主理人 + 四角色线下）

1. 四角色线下提交真实生产证据（RC 冻结基线 / 回滚 runbook / 真实凭证占位）；
2. 四角色逐一线下签署（`POST /governance/activation/signoff`，reason + signature_reference 双填）；
3. 主理人在**人类终端**显式置 `engineering_enabled=true` 并提交合并（唯一 AI 不代执行动作）；
4. 激活后首轮健康检查；回滚预案随时可触发。
详见 `.ai/runbooks/production_activation/HUMAN_ACTIVATION_CHECKLIST.md`。

## 31. 回滚预案

回滚 runbook 沿用 3.9.2 遗留 `.ai/runbooks/production_release/`；本层仅引用不重写。真实回滚演练落库由
release-manager 在 §30 线下确认；触发条件：核心健康检查失败 / 四角色任一方事后撤回 → 立即回滚并
reopen 治理态。

## 32. 不可逾越的 STOP 纪律

收口后 STOP：不进入 3.9.7、不自动激活、不提交超出阶段范畴的代码。AI 在本阶段的一切产出均为"准备"
性质，不构成任何放行授权。任何"全绿 CI / dossier / 复核包"均**不代表可以激活**——激活权只在主理人
手中。

## 33. 剩余风险与未决项

- **R1**：真实生产激活证据（RC 冻结基线哈希、回滚 runbook 真实路径、真实凭证占位）尚未由四角色线下
  提交 → 当前 `production_evidence_complete=False`，属预期内（BUILT_NO_GO）。
- **R2**：四角色签署、主理人置 `engineering_enabled=true` 为真实人工动作，AI 不可代执行。
- **R3**：合成演练结论不得被误读为生产验证（EvidenceScope 已结构级区分，红线⑦）。

## 34. 收口判定

✅ 阶段范畴内全部代码/测试/文档/SSOT/CI 已交付并通过全量回归与 fail-closed 扫描。
✅ 终端态 `PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO` 经 dossier 与测试双重固化。
✅ 审计 +4 真实可溯源，账本一致性 PASS。
⏸ 真实生产激活等待主理人 + 四角色线下证据提交与签署（R1/R2）。

## 35. 附录：文件清单与提交范围

新增/修改（逻辑提交，不含 `git add -A`）：
- `agents/enterprise/production_release/activation_readiness.py`（Layer A 核心，已提交 `59807ca`）
- `backend/app/api/governance_activation.py`（#186，已提交范畴内）
- `backend/app/api/__init__.py`、`backend/app/main.py`（注册，#186）
- `frontend/src/app/governance-activation/page.tsx`（#187）
- `.github/workflows/activation-readiness-gate.yml`（#188）
- `docs/PRODUCTION_ACTIVATION_GOVERNANCE_GUIDE.md`（#190，新增 21 节）
- `docs/PRODUCTION_DEPLOYMENT_GUIDE.md`（#190，§16）
- `tests/agents/test_production_activation_readiness.py`（#190，47 用例）
- `scripts/generate_production_activation_review_packet.py`（#189）
- `.ai/release-gate/production_activation_review_packet.json`（#189）
- `.ai/runbooks/production_activation/HUMAN_ACTIVATION_CHECKLIST.md`（#189）
- `.ai/project_status.json`、`roadmap_v8.md`、`PHASE_BOUNDARY_LEDGER.md`（#189，SSOT 对账）
- `.ai/progress/phase3.9.6_existing_work_forensics.md`（#189，§7 最终结论批注）
- `.ai/reviews/phase3.9.6_production_activation_evidence_readiness_report.md`（本报告）

— 收口报告结束。状态：`PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO`。STOP。
