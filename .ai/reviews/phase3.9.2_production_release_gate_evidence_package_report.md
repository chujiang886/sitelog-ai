# Phase 3.9.2 企业生产发布闸门与证据包层 —— 收口报告

> 身份：BOIP AI Chief Architect + Production Release Engineering Lead + Release Governance Auditor
> 阶段定位：**生产发布前的只读闸门 + 人工签署层**——只核验"是否达到人工签署门槛"，
> 范围为证据 / 检查 / 清单 / 草稿 / 结构，**不是生产部署、不是激活阶段、不是 AI 批准**。
> 分支：`feat/phase3.9.2-production-release-gate`（自 `66f9b57` 分出，即 3.9.1 收口点）
> 收口结论：**BUILT_NO_GO**——闸门与证据体系已建成并通过验证，但**未开启生产、未进入自动激活**，
> 等待主理人线下审核与决策。

---

## 1. 目标与范围

- **目标**：把"生产上线前该核验什么 / 该由谁线下签"沉淀为一套**只读 + 人工签署**的
  闸门与证据包体系，外加对应的审计留痕与红线结构拦截。
- **范围**：T1–T15 共 15 个 Task。全部产物为「只读检查 + 证据 / 清单 / 草稿 / 结构」，
  无副作用写入、无密钥、无真实授权、无真实激活。
- **不在范围**：真实生产激活、真实企业数据修改、真实密钥写入、真实权限授予、任何
  `engineering_approved` 输出、任何真实部署 / 回滚 / 恢复执行——这些只能源于主理人在
  人类终端的线下决策。

## 2. 阶段定位与边界

本层是 3.9.0（准备）→ 3.9.1（验证）→ 3.9.2（闸门）镜像验证链的最后一环：
- 准备层解决"上线前该准备什么"；验证层解决"准备能否扛住验证与灾难"；
  本层解决"准备与验证是否齐备到人工签署门槛"。
- **非真部署、非真激活、非自动发布、非 AI 批准**。闸门结论永不 `APPROVED`/`GO`，
  最终 GO 只能源于真人签署 + 主理人线下决策。

## 3. 授权与执行模式

依据阶段授权书（§一~§二十五）以**自主工程负责人**模式执行：分析 → 方案 → 实施 → 测试 →
修复 → 回归 → 文档 → 收口，不主动提问、不把技术判断升级成人工决策。仅三类不可逆情形可暂停
（不可逆生产数据 / 缺外部密钥 / 真实法律责任），本阶段未触发。

## 4. 交付物总览（T1–T15 映射）

| Task | 交付物 | 关键不变量 |
|------|--------|-----------|
| T1 证据模型 | `ProductionReleaseEvidence` | 默认 `PENDING_VERIFICATION`；SHA-256 重算完整性 |
| T2 发布候选 | `ProductionReleaseCandidate` | AI 只造 DRAFT，`release_approved` 恒 False |
| T3 发布闸门 | `ProductionReleaseGate`（13 CHECK_KEYS） | 三态，永不 `APPROVED` |
| T4 人工签署 | `ReleaseSignoff` | `actor_kind` 必须 `user` |
| T5 决策草稿 | `ReleaseDecisionDraft` | 只产草稿态，绝不出 `GO_LIVE_APPROVED` |
| T6 发布清单 | `ReleasePackageManifest`（SHA-256） | 缺文件标 `<missing>`，不伪造 |
| T7 回滚参考 | `ReleaseRollbackReference` | verified 仅表示引用齐备，不执行 |
| T8 证据完整性链 | `ProductionReleaseEvidenceService.verify_integrity` | TAMPERED 即整链无效 |
| T9 发布闸门 API | `backend/app/api/governance_release.py` | 只读 + 签署，强制真实 USER |
| T10 发布驾驶舱 UI | `frontend/src/app/governance-release/page.tsx` | 无自动上线 / 无 AI 批准按钮 |
| T11 发布审计 | audit.py +4 枚举（总数 83） | record 强制 actor=USER |
| T12 发布闸门测试 | 3 个测试文件（81 例） | fail-closed |
| T13 回归测试 | agents/backend/frontend/scanner | 核心 0 failed 0 error |
| T14 3.9.x SSOT | project_status.json + baseline + roadmap §35 | 治理完整性检查 9/9 |
| T15 文档与收口 | 本报告 + 2 份治理指南 | 24 节 / 13 节 |

## 5. T1 证据模型（Evidence Model）

`ProductionReleaseEvidence`（`models.py`）：`evidence_id` / `evidence_type` / `source` /
`source_reference` / `created_at` / `integrity_status`（`INTACT`/`PENDING`/`TAMPERED`/`UNKNOWN`）
/ `verification_status`（`VERIFIED`/`PENDING_VERIFICATION`/`FAILED`）+ 11 个关联维度。
`evidence.py`：客观事实→`VERIFIED`；人工依赖→`PENDING_VERIFICATION`（AI 不代填）。

## 6. T2 发布候选（Release Candidate）

`ProductionReleaseCandidate`：状态机 `DRAFT → GATHERED → AWAITING_HUMAN_REVIEW →
REJECTED_BY_HUMAN / APPROVED_FOR_RELEASE_BY_HUMAN`。AI 只造 DRAFT；`release_approved` 恒 False；
`mark_awaiting_human_review` 不改变该字段。

## 7. T3 发布闸门（Release Gate）

`ProductionReleaseGate.CHECK_KEYS`（13 项）：`git_workspace_integrity` / `commit_sha_exists` /
`full_test_results_green` / `production_security_scanner` / `identity_security_scanner` /
`governance_quality_gate` / `staging_validation` / `rollback_drill` / `recovery_validation` /
`database_migration_status` / `configuration_baseline` / `deployment_documentation` /
`evidence_completeness`。`evaluate`：`BLOCKED`（有缺失）→ `PENDING_VERIFICATION`（有 pending）→
`READY_FOR_HUMAN_REVIEW`（齐备），**永不** `APPROVED`。

## 8. T4 人工签署模型（Release Signoff）

`ReleaseSignoff`：`actor_kind` 必须 `"user"`。服务层禁名 `create_human_signoff` 由
`_RedLineForbiddenMixin` **结构级**拦截 AI 代签。4 角色：`PRODUCTION_OWNER` / `RELEASE_MANAGER` /
`SECURITY_OWNER` / `AUDITOR`；决策 `GO` / `NO_GO` / `NEED_MORE_EVIDENCE` 仅真人可提。

## 9. T5 Go/No-Go 决策草稿（Decision Draft）

`ReleaseDecisionDraft`：`build_decision_draft` 只产 `READY_FOR_HUMAN_GO_NO_GO` / `BLOCKED` /
`NEEDS_MORE_EVIDENCE`，随闸门状态走；**绝不** `GO_LIVE_APPROVED`。含风险列表（工作区脏 /
pending 证据 / 密钥未线下提供）。

## 10. T6 发布清单（Release Package Manifest，SHA-256）

`ReleasePackageManifest`：`artifact_hashes` 用 SHA-256；`build_manifest` 对存在文件算哈希，
缺文件标 `<missing>`（不伪造）。清单是**证据**，不是放行令。

## 11. T7 回滚参考（Rollback Reference）

`ReleaseRollbackReference`：`build_rollback_reference` 仅验证 version/config/database/recovery
四类引用是否齐备，`verified=True` 仅表示"引用齐备"，**不执行真实回滚**。

## 12. T8 证据完整性链（Evidence Integrity Chain）

`verify_integrity` 重算 SHA-256 判定 `INTACT`/`TAMPERED`；`build_evidence_chain` 按顺序串联，
任意一环 `TAMPERED`/`FAILED` 即整链无效。链是防篡改证据，放行由真人决定。

## 13. T9 发布闸门 API（只读 + 人工签署）

`backend/app/api/governance_release.py`（`prefix=/governance/releases`，CSRF 依赖）：
`GET ""` / `GET /{id}` / `GET /{id}/evidence` / `GET /{id}/gate` / `GET /{id}/manifest`
（均 `governance:release:read`）；`POST /{id}/signoff`（`governance:release:signoff` +
`_require_user_principal` 校验 `actor_kind=="user"`，AI 主体 403）。`_snapshot()` 基于仓库事实
合成只读候选，无副作用；签署落 `record_release_signoff_recorded`，不翻 `engineering_enabled`、不部署。

## 14. T10 发布驾驶舱 UI（只读 + 人工签署）

`frontend/src/app/governance-release/page.tsx`：镜像 `governance-dashboard` 的
`getIdentityProvider().getIdentity()` → `requirePermission` → `fetch` 只读 + 人工点击模式。
只读展示候选 / 证据 / 闸门 / 清单 / 回滚 / 签署记录；**仅真实人工 GO/NO-GO/NEED_MORE_EVIDENCE
按钮；无自动上线按钮、无 AI 批准按钮**；失败不降级。`types.ts`/`guards.ts` 同步两权限，
由 `test_governance_identity_security.py` 钉死。

## 15. T11 发布审计（4 个 RELEASE_* 枚举）

`agents/enterprise/audit.py` 在 `RECOVERY_VALIDATION` 后新增 4 枚举：
`RELEASE_CANDIDATE_CREATED` / `RELEASE_GATE_EVALUATED` / `RELEASE_SIGNOFF_RECORDED` /
`RELEASE_MANIFEST_GENERATED`，并新增 4 个 `record_*` 方法（均 `actor_kind=USER`）。
审计总数 **79 → 83**。三处联动：权威测试 `EXPECTED_CATEGORIES` + 计数、基线
`audit_category_contract.total`、本报告 §21。

## 16. T12 发布闸门测试（fail-closed）

3 个测试文件、共 81 例，全部 fail-closed：
- `tests/agents/test_production_release_gate_evidence.py`（23 例，覆盖证据/候选/闸门/签署/清单/回滚/审计/红线）
- `tests/agents/test_enterprise_production_release.py`（27 例，覆盖 service 层 + 禁名结构拦截 + 审计落库 + engineering_enabled 恒 False）
- `backend/tests/test_governance_release.py`（31 例，覆盖 API 只读/签署/RBAC/跨组织拒绝/AI 主体 403）
覆盖：verified/pending/failed 证据、候选 `release_approved=False`、gate 三态、AI 代签拒绝、
USER 签署允许、跨组织拒绝、RBAC 拒绝、manifest 哈希、rollback 引用、审计落库、
`engineering_enabled` 仍 False。

## 17. T13 回归测试（核心 0 failed 0 error）

| 套件 | 结果 |
|------|------|
| agents 全量（`tests/agents`） | 2305 passed / 0 failed |
| backend 全量（`backend/tests`） | 323 passed / 0 failed |
| frontend jest（`frontend/jest.config.js`） | 117 passed / 0 failed（7 suites） |
| frontend tsc `--noEmit` | 0 error |
| 治理仓库完整性检查器 | 9/9 通过 |
| 生产安全红线扫描 | 7/7 通过 |
| 遗留身份头扫描 | OK（无回归） |
| 硬编码扫描 | 通过（无业务阈值/品牌/型号） |
| 防编造扫描 | exit 0（匹配仅历史文档，本阶段无新编造） |

核心测试 **0 failed 0 error**，Gate 测试绿，Scanner 绿。

## 18. T14 3.9.x SSOT 治理

- `.ai/project_status.json`：新增 `phase_3_9_0_status` / `phase_3_9_1_status` / `phase_3_9_2_status`
  （均 `BUILT_NO_GO`）及 `phase_3_9_0` / `phase_3_9_1` / `phase_3_9_2` 三个详细对象；
  治理仓库完整性检查器 9/9 通过（规则 2 阶段登记完整、规则 3 报告路径真实）。
- `.ai/baselines/phase3.8_governance_release_baseline.json`：`audit_category_contract.total` 79→83、
  `authority_assertion` → `assert len(members) == 83`、`history` 追加 `+4 = 83`。
- `.ai/roadmap_v8.md` §35：3.9.0–3.9.2 概览与 3.9.2 交付物 / 门禁 / STOP 纪律。

## 19. T15 文档与收口

- `docs/PRODUCTION_DEPLOYMENT_GUIDE.md`：新增 §13 生产发布闸门与证据包（13.1–13.6）+ 附录 A 变更记录。
- `docs/PRODUCTION_RELEASE_GOVERNANCE_GUIDE.md`（新增，13 节）：角色职责 / 证据 / 候选 / 闸门 /
  完整性链 / 签署 / 决策草稿 / 回滚 / 审计 / 红线 / API 与前端 / 收口 STOP。
- 本报告（24 节）。
- 工作记忆追加本阶段要点。

## 20. 红线与 fail-closed 禁名（314 项）

`agents/enterprise/production_release/forbidden.py`：`PRODUCTION_RELEASE_FORBIDDEN_COUNT = 314`
（`_dedupe` 合并 `governance_traceability` / `production_readiness` / `staging_validation` 禁集 +
本层增量），由 `_RedLineForbiddenMixin.__getattr__` 结构级拦截：真部署 / 出 `approved` /
自动批准 / AI 代签 / 写真实密钥 / 授真实权限 / 翻转 `engineering_enabled`。

十项最高红线（绝对不可修改 / 弱化）：
① `engineering_enabled` 恒 `false` ② 禁 `engineering_approved` ③ 禁 AI 自动批准发布
④ 禁 AI 自动执行部署 ⑤ 禁 AI 修改真实企业数据 ⑥ 禁 AI 写真实生产密钥
⑦ 禁 AI 自动授予生产权限 ⑧ 禁 AI 代 production-owner/release-manager/security-owner/auditor 签署
⑨ 禁把 simulation/drill/staging 描述成 production verified
⑩ 禁通过跳测试 / 改安全断言 / 降权 / 删失败测试 / 伪造证据让 Gate 变绿。

## 21. 验证证据汇总

- 端到端冒烟（实施期）：`ProductionReleaseService(engineering_enabled=False)` 跑通
  候选(DRAFT, release_approved=False)→证据(8 条)→闸门(13 项, 工作区脏返回 BLOCKED 正确)
  →清单(SHA-256 算出)→回滚参考(verified=True)→决策草稿(risks=3)→禁名 `create_human_signoff`
  结构拦截→审计落 `release_candidate_created`。输出 `SMOKE OK`。
- 审计总数：83（权威测试 `test_enterprise_knowledge_governance_audit.py` `assert len(members)==83`）。
- 禁名计数：314。
- 闸门检查：13。

## 22. 未决项与 pending_verification

- 真实生产环境部署与拓扑决策（同源 / 跨子域 / 跨站）——主理人线下。
- 真实密钥线下提供（`production_secret` 证据恒 `PENDING_VERIFICATION`，AI 不代填）。
- 真实权限授予 / 真实回滚执行 / 真实恢复执行——仅演练，未触碰。
- `engineering_enabled` 开启（仅人类终端可执行）。
- 4 角色真人在人类终端签署 GO/NO-GO/NEED_MORE_EVIDENCE。

## 23. 收口结论（BUILT_NO_GO）

本层状态 **🟢 BUILT_NO_GO（已收口）**：闸门与证据体系已建成并通过验证，但**未开启生产、
未进入自动激活、未输出 `engineering_approved`**。T1–T15 全部完成；核心测试 0 failed 0 error；
Gate 测试绿；Scanner 绿；SSOT 支持 3.9.x；文档同步；Release Governance Guide 完成；本报告完整；
`engineering_enabled` 仍 `false`。满足 §二十四收口条件。

## 24. STOP 纪律与下一步

- **STOP：不进入 Phase 3.9.3+**，不自动开启 `engineering_enabled`，不真部署，不自动 GO，
  不代替人工责任。
- 本阶段产物待主理人审核授权后提交（精路径 commit，禁 `git add -A`）。
- 最终生产发布（开 `engineering_enabled`、真部署、真签 GO）只能源于主理人在人类终端的
  线下决策，并经 `PRODUCTION_DEPLOYMENT_GUIDE.md` §8 上线自检 + §10 回滚方案验证。
- 关联文档：`.ai/roadmap_v8.md` §35、`docs/PRODUCTION_DEPLOYMENT_GUIDE.md` §13、
  `docs/PRODUCTION_RELEASE_GOVERNANCE_GUIDE.md`。
