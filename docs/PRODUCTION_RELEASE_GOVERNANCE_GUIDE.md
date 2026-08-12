# BOIP 生产发布治理指南（Production Release Governance Guide）

> 层级：Phase 3.9.2 — Enterprise Production Release Gate & Evidence Package Layer
> 身份：BOIP AI Chief Architect + Production Release Engineering Lead + Release Governance Auditor
> 状态：**BUILT_NO_GO**（已收口，未开启生产、未进入自动激活，等待主理人线下授权）

本指南说明「生产发布前」的最后一道治理层：它把"是否达到人工签署门槛"用结构化证据与
13 项检查固化下来，交给真实责任人去签 GO / NO-GO / NEED_MORE_EVIDENCE。**它不部署、
不激活、不批准、不代签。**

---

## 1. 概述与定位

- **目标**：把"生产上线前该核验什么 / 该由谁线下签"沉淀为一套**只读 + 人工签署**的
  闸门与证据包体系，外加对应的审计留痕与红线结构拦截。
- **范围**：T1–T15 全部产物为「只读检查 + 证据 / 清单 / 草稿 / 结构」，无副作用写入、
  无密钥、无真实授权、无真实激活。
- **不在范围**：真实生产激活、真实企业数据修改、真实密钥写入、真实权限授予、
  任何 `engineering_approved` 输出、任何真实回滚 / 恢复执行——这些只能源于主理人在
  人类终端的线下决策。
- **与 3.9.0 / 3.9.1 的关系**：3.9.0 准备"上线前该准备什么"；3.9.1 验证"这些准备能否扛住
  验证与灾难"；本层（3.9.2）核验"准备与验证是否齐备到人工签署门槛"。三者构成镜像验证链。

---

## 2. 角色与职责（Separation of Duties）

| 角色 | 职责 | 是否能签 |
|------|------|----------|
| `PRODUCTION_OWNER` | 对生产发布整体负责 | ✅ GO / NO_GO / NEED_MORE_EVIDENCE |
| `RELEASE_MANAGER` | 对发布流程与回滚编排负责 | ✅ GO / NO_GO / NEED_MORE_EVIDENCE |
| `SECURITY_OWNER` | 对安全扫描与凭据态势负责 | ✅ GO / NO_GO / NEED_MORE_EVIDENCE |
| `AUDITOR` | 对证据完整性与审计留痕负责 | ✅ GO / NO_GO / NEED_MORE_EVIDENCE |

- 签署**只能由 `USER` 类型真实主体**提交；`agent` / `system` / `service` 主体一律 403。
- 权限分离：查看 `governance:release:read` 所有治理角色都有；签署 `governance:release:signoff`
  **仅 `governance-admin`** 拥有。AI 不持有任何签署位。
- 任一角色的 NO_GO 即阻断发布；NEED_MORE_EVIDENCE 退回补充证据，不自动放行。

---

## 3. 证据模型（Evidence Model）

`ProductionReleaseEvidence`（`agents/enterprise/production_release/models.py` T1）：

- `evidence_id` / `evidence_type` / `source` / `source_reference` / `created_at`
- `integrity_status`: `INTACT` / `PENDING` / `TAMPERED` / `UNKNOWN`（SHA-256 重算）
- `verification_status`: `VERIFIED` / `PENDING_VERIFICATION` / `FAILED`
- 关联维度：git / test / scanner / staging / rollback / recovery / db / config / doc / secret / signoff

证据服务（`evidence.py`）规则：
- 客观事实（文件存在、测试通过）收集即 `VERIFIED`。
- 人工依赖项（`human_signoff` / `production_secret`）**恒 `PENDING_VERIFICATION`**——
  AI 不代填、不把 PENDING 抬成 VERIFIED（红线⑨/⑩）。
- `verify_integrity` 重算 SHA-256 判定完整性；`build_evidence_chain` 串成链。

---

## 4. 发布候选（Release Candidate）

`ProductionReleaseCandidate`（T2）：

- 状态机：`DRAFT` → `GATHERED` → `AWAITING_HUMAN_REVIEW` → `REJECTED_BY_HUMAN` /
  `APPROVED_FOR_RELEASE_BY_HUMAN`。
- **AI 只造 `DRAFT`**；`release_approved` 字段**恒 `False`**（fail-closed）。
- `mark_awaiting_human_review` 仅推进状态，**不改变** `release_approved=False`。
- 任何"AI 自动批准候选"的方法在禁名集中，调用即抛。

---

## 5. 发布闸门（Release Gate）

`ProductionReleaseGate`（T3），`CHECK_KEYS`（13 项）：

```
git_workspace_integrity          commit_sha_exists
full_test_results_green          production_security_scanner
identity_security_scanner        governance_quality_gate
staging_validation               rollback_drill
recovery_validation             database_migration_status
configuration_baseline           deployment_documentation
evidence_completeness
```

`evaluate` 三态（**永不** `APPROVED`）：
- 有硬缺失 → `BLOCKED`
- 有标 `pending_verification` 项 → `PENDING_VERIFICATION`
- 全部齐备 → `READY_FOR_HUMAN_REVIEW`（等真人签）

---

## 6. 证据完整性链（Evidence Integrity Chain）

- 每条证据自带 SHA-256；`verify_integrity` 重算比对，不一致即 `TAMPERED`。
- 链（chain）按 `evidence_id` 顺序串联，任意一环 `TAMPERED` / `FAILED` 即整链无效。
- 链是**防篡改证据**，不是放行令；能否放行由真人签署决定。

---

## 7. 签署流程（Human Sign-off）

`ReleaseSignoff`（T4）：`actor_kind` 必须 `"user"`；服务层 `forbidden` 名 `create_human_signoff`
由 `_RedLineForbiddenMixin` **结构级**拦截 AI 代签。

API：`POST /governance/releases/{id}/signoff`
- 需 `governance:release:signoff`；`_require_user_principal` 校验 `actor_kind == "user"`。
- 校验 `role ∈ 4 角色`、`decision ∈ {go, no_go, need_more_evidence}`。
- 落 `AuditService.record_release_signoff_recorded`；**不**翻 `engineering_enabled`、**不**部署。

前端：`/governance-release` 页——只读展示候选 / 证据 / 闸门 / 清单 / 回滚 / 签署记录；
**仅真实人工 GO / NO_GO / NEED_MORE_EVIDENCE 按钮；无自动上线按钮、无 AI 批准按钮。**

---

## 8. Go/No-Go 决策草稿（Decision Draft）

`ReleaseDecisionDraft`（T5）：`build_decision_draft` 只产出**草稿态**
（`READY_FOR_HUMAN_GO_NO_GO` / `BLOCKED` / `NEEDS_MORE_EVIDENCE`），随闸门状态走。
- **绝不**产出 `GO_LIVE_APPROVED`；最终 GO_LIVE 只能源于真人签署 + 主理人线下决策。
- 草稿含风险列表（如工作区脏、存在 pending 证据、密钥未线下提供），供签署人研判。

---

## 9. 回滚参考（Rollback Reference）

`ReleaseRollbackReference`（T7）：`build_rollback_reference` 仅**验证引用完整性**
（版本 / 配置 / 数据库 / 恢复四类引用是否齐备），`verified=True` 仅表示"引用齐备"，
**不执行真实回滚**。真实回滚只能源于主理人线下决策。

---

## 10. 审计留痕（Audit Trail）

`agents/enterprise/audit.py` 新增 4 枚举（总数 **79 → 83**）：
- `RELEASE_CANDIDATE_CREATED` · `RELEASE_GATE_EVALUATED` · `RELEASE_SIGNOFF_RECORDED`
  · `RELEASE_MANIFEST_GENERATED`

4 个 `record_*` 方法均 `actor_kind=AuditActorKind.USER`（红线⑥/⑧）。审计表 append-only，
未知主体记法沿用既有治理审计契约。

---

## 11. 红线与 fail-closed 禁名

`agents/enterprise/production_release/forbidden.py`：`PRODUCTION_RELEASE_FORBIDDEN_COUNT = 314`
（含 `governance_traceability` / `production_readiness` / `staging_validation` 历史禁集并集 +
本层增量）。由 `_RedLineForbiddenMixin.__getattr__` 在结构级拦截以下语义：
- 真部署 / 出 `approved` / 自动批准 / AI 代签 / 写真实密钥 / 授真实权限 / 翻转 `engineering_enabled`

十项最高红线（绝对不可修改 / 弱化）：
① `engineering_enabled` 恒 `false` ② 禁 `engineering_approved` ③ 禁 AI 自动批准发布
④ 禁 AI 自动执行部署 ⑤ 禁 AI 修改真实企业数据 ⑥ 禁 AI 写真实生产密钥
⑦ 禁 AI 自动授予生产权限 ⑧ 禁 AI 代 production-owner/release-manager/security-owner/auditor 签署
⑨ 禁把 simulation/drill/staging 描述成 production verified ⑩ 禁通过跳测试 / 改安全断言 / 降权 /
删失败测试 / 伪造证据让 Gate 变绿。

---

## 12. API 与前端

- 后端：`backend/app/api/governance_release.py`（`prefix=/governance/releases`，CSRF 依赖）。
  端点：`GET ""` / `GET /{id}` / `GET /{id}/evidence` / `GET /{id}/gate` / `GET /{id}/manifest`
  （均 `RELEASE_READ`）；`POST /{id}/signoff`（`RELEASE_SIGNOFF` + 真实 USER 校验）。
  `_snapshot()` 基于仓库事实合成只读候选，无副作用。
- 前端：`frontend/src/app/governance-release/page.tsx`，镜像 `governance-dashboard` 的
  `getIdentityProvider().getIdentity()` → `requirePermission` → `fetch` 只读 + 人工点击模式，
  失败不降级。
- 权限词表：`backend/app/identity/permissions.py` 与 `frontend/src/lib/identity/types.ts` /
  `guards.ts` 逐项一致，由 `backend/tests/test_governance_identity_security.py` 钉死。

---

## 13. 收口状态与 STOP 纪律

- **状态：🟢 BUILT_NO_GO（已收口）**：闸门与证据体系已建成并通过验证，但**未开启生产、
  未进入自动激活、未输出 `engineering_approved`**。
- **STOP：不进入 Phase 3.9.3+**，不自动开启 `engineering_enabled`，不真部署，不自动 GO，
  不代替人工责任。本阶段产物待主理人审核授权后提交。
- 最终生产发布（开 `engineering_enabled`、真部署、真签 GO）只能源于主理人在人类终端的
  线下决策，并经 `PRODUCTION_DEPLOYMENT_GUIDE.md` §8 上线自检 + §10 回滚方案验证。
- 关联文档：`.ai/reviews/phase3.9.2_production_release_gate_evidence_package_report.md`、
  `.ai/roadmap_v8.md` §35、`docs/PRODUCTION_DEPLOYMENT_GUIDE.md` §13。
