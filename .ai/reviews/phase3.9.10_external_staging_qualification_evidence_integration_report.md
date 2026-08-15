# Phase 3.9.10 收口报告 —— External Staging Qualification & Evidence Integration Layer

> 终端态：`EXTERNAL_STAGING_QUALIFICATION_BUILT_NO_GO`
> 分支：`feat/phase3.9.10-external-staging-qualification`
> 施工起点 base：`2f4a9838bcfc7105bc561f74fb2658906801e011`
> 审计 canonical baseline：129（本阶段 0 新增类目）
> 收口时间：2026-08-15

---

## 1. 文档元信息
- 文档类型：Phase 收口报告（Governance Closure Report）
- 阶段：3.9.10 External Staging Qualification & Evidence Integration Layer
- 作者角色：AI Chief Architect（执行）/ 主理人（轩哥，待审）
- 关联基线文档：`.ai/progress/phase3.9.10_starting_baseline_validation.md`（T0）、`.ai/progress/phase3.9.10_existing_wip_forensics.md`（T1）

## 2. 执行摘要
Phase 3.9.10 在已 BUILT_NO_GO 的 3.9.9 之上，构建了「外部预生产（External Staging）资格认定与证据集成层」。本阶段**不接入、不部署、不激活**任何真实外部预生产环境，仅交付一套 fail-closed 的资格认定框架、确定性证据包、CI 闸门与人工动作入口。所有 51 项任务已完成，全量回归 0 failed，审计类目 0 新增。终端态为 BUILT_NO_GO，等待主理人 + 四角色线下证据与签署。

## 3. 阶段定位与边界
- 本阶段属于「生产变更管控与人工执行就绪」之后的**外部预生产资格认定**层。
- 显式边界：**不进入 Production Handoff**（旧 WIP 独立登记）、**不进入 Phase 3.9.11**。
- `engineering_enabled=false` 全程保持，AI 不代执行任何生产激活/部署/密钥动作。

## 4. 施工起点锚定（Branch Integrity Guard）
- 当前 HEAD：`2f4a9838bcfc7105bc561f74fb2658906801e011`（= base，未漂移）
- 当前分支：`feat/phase3.9.10-external-staging-qualification`（符合预期）
- `agents/config.yaml:102` → `engineering_enabled: false`（已核验，未改动）
- 每关键写操作前均重新锚定分支/HEAD，未发生自动 drift。

## 5. T0 基线核验详情
见 `.ai/progress/phase3.9.10_starting_baseline_validation.md`。核验项：HEAD=base、分支正确、10 个未跟踪交付物占位、`engineering_enabled=false`、Audit=129、旧 WIP 冲突裁决（§5 记录 e97d5361 不存在的真实来源校正）、3.9.11 残留 0。

## 6. T1 既有 WIP 法证
见 `.ai/progress/phase3.9.10_existing_wip_forensics.md`。记录「确认陈述 vs 实测真实来源」冲突表，并给出裁决：独立 provenance 隔离、不吸收、登记 Pending Human Item。

## 7. 重大法证更正（治理 §4）
上一轮「确认」的旧 WIP tip=`e97d5361` / Audit=155 / +15 commits **在本仓库不存在**：
- `git cat-file -t e97d5361` → NOT_FOUND
- 旧分支 tip = `2f4a9838…` = base
- `git rev-list --count` 相对 base = 0
- 真实载体为 `stash@{4}` / `stash@{5}` 隔离的 `agents/enterprise/production_handoff/` 5 文件 + 修改的 `audit.py`，**未提交、未丢失、未并入**。

以真实来源为准裁决，不吸收、不伪造审计类目。

## 8. 旧 WIP 裁决
- 旧 WIP「Production Handoff & Human Activation Ceremony」判定为**独立历史 WIP**。
- 不得 merge / cherry-pick / 自动吸收到当前 Phase 3.9.10。
- provenance 独立登记、保留历史、不删除、不重写（stash 保留）。
- 磁盘上曾出现的 `agents/enterprise/production_handoff/` 重复副本已按 C 类安全清理移除（stash 已完整保留 provenance，不破坏历史）。

## 9. 冲突处理记录（治理 §4 流程）
- Conflict：编号/文档/Git 冲突（旧 WIP tip 陈述 vs 实测）
- Decision：以真实 git 来源为准，独立隔离旧 WIP，不吸收
- Evidence：`git cat-file` / `git rev-list` / stash 清单
- Pending Human Item：旧 WIP 是否并入由主理人线下裁决（见 §35）

## 10. 分支完整性守卫
脚本 `scripts/check_phase39x_branch_integrity.py`（Task 37）：
- 预期分支 = `feat/phase3.9.10-external-staging-qualification`
- forbidden 段收窄为 `("production_handoff","handoff")`（避免误伤 3.9.7 合法 `production_change` 模块）
- 基于 git 视图（tracked + `git status --porcelain` ?? 行）判定，不做全仓库 2 万文件遍历（规避 SIGKILL）
- 运行结果：**PASS**（分支/无 forbidden 模块/无 3.9.11 残留/Audit total=129 全过）

## 11. 交付物总览
| 类别 | 路径 | 状态 |
|---|---|---|
| T0 文档 | `.ai/progress/phase3.9.10_starting_baseline_validation.md` | 新增 |
| T1 文档 | `.ai/progress/phase3.9.10_existing_wip_forensics.md` | 新增 |
| agents 模块 | `agents/external_staging_qualification/`（16 文件） | 新增 |
| 后端 API | `backend/app/api/external_staging_qualification.py` | 新增 |
| 前端页 | `frontend/src/app/external-staging-qualification/page.tsx` | 新增 |
| 生成器 | `scripts/generate_external_staging_qualification_package.py` | 新增 |
| 校验器 | `scripts/validate_external_staging_qualification_package.py` | 新增 |
| 分支守卫 | `scripts/check_phase39x_branch_integrity.py` | 新增 |
| 测试 | `tests/agents/test_external_staging_qualification.py`（50 tests） | 新增 |
| API 契约 | `.ai/baselines/external_staging_api_contract.json` | 新增 |
| 资格包 | `.ai/staging/external_staging_qualification_package.json` | 新增（确定性） |
| Runbook | `.ai/runbooks/staging/`（2 文件） | 新增 |
| 部署指南 | `docs/EXTERNAL_STAGING_QUALIFICATION_GUIDE.md` | 新增 |
| CI 闸门 | `.github/workflows/external-staging-qualification-gate.yml` | 新增 |
| SSOT ×3 | `PHASE_BOUNDARY_LEDGER.md` / `project_status.json` / `PRODUCTION_DEPLOYMENT_GUIDE.md` | 修改 |

## 12. agents 模块（16 文件）
`models.py` / `package.py` / `pipeline.py` / `gate.py` / `evidence.py` / `isolation.py` / `qualification.py` / `credential_scanner.py` / `denylist.py` / `deployment.py` / `runtime.py` / `scenarios.py` / `security.py` / `config.py` / `probes.py` / `__init__.py`。
核心导出：`ExternalStagingEnvironmentIdentity`、`QualificationPipeline`、`package_hash`。

## 13. 资格包生成器（Task 23）
`scripts/generate_external_staging_qualification_package.py`：确定性生成 `.ai/staging/external_staging_qualification_package.json`，用法 `--source-commit` / `--out`。默认取 `git rev-parse HEAD` 完整 SHA 作为 source_commit。

## 14. 资格包校验器（Task 24）
`scripts/validate_external_staging_qualification_package.py <package.json>`：fail-closed 校验——
- `environment == external_staging`、`production == false`
- `engineering_enabled == false`、`contains_real_secret == false`、`production_activation_prohibited == true`
- resource registry 8 资源计数
- 禁止态未出现（PRODUCTION_READY / APPROVED / GO）
- `package_hash` 与 canonical 重算一致（stale 检测）
- `gate.status` 不在 {approved, production_ready, go}
- 退出码 0=通过，1=失败。

## 15. 分支完整性脚本（Task 37）
见 §10。

## 16. 后端 API
`backend/app/api/external_staging_qualification.py`：FastAPI 路由，暴露资格包读取、Gate 状态、资源注册表摘要等只读/计划接口；不包含任何真实部署/激活端点。

## 17. 前端 UI
`frontend/src/app/external-staging-qualification/page.tsx`：资格认定状态页，展示 Gate 状态、资源清单、证据链、人工动作入口。修复了 `useGet<T>(path: string>)` 泛型语法错误（去多余 `>`），tsc 0 error。

## 18. API 契约
`.ai/baselines/external_staging_api_contract.json`：机器可读 API 契约，定义外部预生产资格认定所需端点与字段约束，供 CI `api-contract-validate` job 校验。

## 19. 测试套件
`tests/agents/test_external_staging_qualification.py`：**50 个 test_**，覆盖环境身份、资格流水线、Gate、证据、隔离、确定性包、校验器、分支完整性等。
**当前（收口时）重跑结果：50 passed**（backend/.venv，0.44s）。

## 20. CI 工作流（Task 38）
`.github/workflows/external-staging-qualification-gate.yml`：8 job——
`branch-integrity-gate` / `staging-qualification-tests` / `package-generate-validate` / `audit-ledger-baseline` / `api-contract-validate` / `credential-safety` / `isolation-check` / `repo-clean`。
已修正 `package-generate-validate` 的 validate 调用缺失位置参数（补 `.ai/staging/external_staging_qualification_package.json`）。

## 21. 确定性包设计
要求「相同事实 → 相同 SHA-256」。包顶层 `package_hash` 由 `_hashable_body()` 计算，逐层剥离非事实字段（`generated_at` / `package_hash`）后做 canonical JSON + SHA-256。

## 22. 确定性缺陷修复（真实缺陷）
根因：`evidence_refs.items[].generated_at` 含微秒时间戳（如 `2026-08-15T03:17:40.507211+00:00`），旧 `_hashable_body` 仅剥离顶层键，破坏确定性（两次 regenerate 哈希不同：`abc891da` vs `3cb31202`）。
修复：新增递归 `_strip_non_fact()`，使 `_hashable_body()` 逐层剥离嵌套 `generated_at`/`package_hash`。
修复后：连续两次 regenerate → `package_hash` 完全相同（见 §23）。

## 23. 确定性验证结果
- 连续两次生成 `/tmp/pkg_a.json` vs `/tmp/pkg_b.json`：`package_hash` 均为 `8d091f8a0ac413e030ea9b6565300aef5bc827ce3b86d8287d38d919cbc0c4ca` → **DETERMINISTIC_OK**
- 整文件 `diff` 仅 `generated_at` 时间戳不同（预期行为）
- 最终提交用完整 SHA 重生成规范包，哈希 = `8d091f8a…`

## 24. Gate 设计（fail-closed）
Gate 状态仅允许：`BLOCKED` / `PENDING_EXTERNAL_STAGING_RESOURCE` / `PENDING_HUMAN_VERIFICATION` / `READY_FOR_EXTERNAL_STAGING_HUMAN_REVIEW`。
**禁止** `APPROVED` / `PRODUCTION_READY` / `GO`。当前包 `gate.status = pending_external_staging_resource`。

## 25. 资格包内容快照（最终提交版）
- `phase=3.9.10`、`terminal_state=EXTERNAL_STAGING_QUALIFICATION_BUILT_NO_GO`
- `source_commit=2f4a9838bcfc7105bc561f74fb2658906801e011`
- `environment_identity.production=false`
- `resource_registry_summary`：total=8，configured=0，verified=0，pending=8
- `isolation_summary`：total=9，verified=0，all_verified=false
- `runtime_health`：13 组件均 `not_configured`（UNKNOWN 不视作 HEALTHY）
- `gate.status=pending_external_staging_resource`，`passed=true`（含 1 个 pending 级 check：all_resources_verified=false）
- `contains_real_secret=false`、`production_activation_prohibited=true`、`engineering_enabled=false`
- `package_hash=8d091f8a0ac413e030ea9b6565300aef5bc827ce3b86d8287d38d919cbc0c4ca`

## 26. 凭据安全
- `credential_reference_safety` check passed：凭据引用无明文泄漏
- `evidence_refs.summary.none_contains_secret=true`，每条证据 `contains_secret=false`
- 全包 `contains_real_secret=false`

## 27. 隔离检查
`cross_environment_isolation` check：隔离 0/9 已证，9 待证（severity=pending）。外部预生产环境尚未真正接入，隔离待人工/真实资源就绪后验证。

## 28. 运行时健康
13 个运行时组件（backend/frontend/database/idp/storage/audit/governance/release/change_control/llm/voice/telemetry/alerting）均为 `not_configured`，`all_healthy=false`，`unknown_treated_as_healthy=false`（fail-closed：未接入即不健康）。

## 29. 全量回归
阶段执行期全量回归（0 failed）：
- agents：**2616 passed**
- backend：**380 passed**
- jest（前端）：**117 passed**
- tsc：**0 error**
收口时额外重跑阶段专属 50 测试：**50 passed**；分支完整性：**PASS**；包校验：**PASS**。

## 30. SSOT 更新 ① —— Phase Boundary Ledger
`.ai/PHASE_BOUNDARY_LEDGER.md` §1 表格追加 3.9.10 行：
branch=`feat/phase3.9.10-external-staging-qualification`、base=`2f4a983`、current_head=`<CLOSURE_COMMIT>`（提交后回填）、status=`PHASE_3_9_10_EXTERNAL_STAGING_QUALIFICATION_EVIDENCE_INTEGRATION_BUILT_NO_GO`、审计 0 新增。

## 31. SSOT 更新 ② —— project_status.json
末尾新增 `phase_3_9_10_status` 键（建模于 `phase_3_9_9_status` 结构）：含 canonical_phase_id、audit_total_canonical=129、tasks_total=51、tasks_completed=51、core_modules 列表、`engineering_enabled=false`、stop 声明「不进入 3.9.11」。current_head 用 `<CLOSURE_COMMIT>` 占位，提交后回填。

## 32. SSOT 更新 ③ —— 部署指南 §18
`docs/PRODUCTION_DEPLOYMENT_GUIDE.md` 附录 A 前插入 §18（External Staging Qualification，含 18.1 做什么/不做什么、18.2 fail-closed 不变量、18.3 人工动作入口、18.4 收口状态）；附录 A 变更记录表追加 `Phase 3.9.10` 行。

## 33. 红线守约（六道 fail-closed）
1. ✅ 未开启 `engineering_enabled`（保持 false）
2. ✅ 未输出 `engineering_approved`
3. ✅ 未 AI 自动评级/确认/生成真实工程参数/报价
4. ✅ 未 AI 自动禁用/弃用/修改 Agent、未自动部署/激活生产
5. ✅ 未代替人工责任（require_human_actor 强制，见 §35）
6. ✅ 未写真实密钥/真实权限/真实生产数据变更/自动关事件/提供 `/activate` `/deploy-production` 端点

## 34. fail-closed 不变量
- 禁止态（APPROVED/PRODUCTION_READY/GO）未出现
- `production=false`、`engineering_enabled=false`、`production_activation_prohibited=true`、`contains_real_secret=false`
- 未接入即 `not_configured`/`BLOCKED`，绝不假阳性 HEALTHY
- 同事实 → 同 `package_hash`（确定性）

## 35. Pending Human Item（人工动作入口，唯一合法出口）
本阶段交付物不含真实外部预生产接入，以下必须主理人 + 四角色线下完成，AI 不代执行：
1. `external_resource_provisioning`：真实外部预生产资源（database/secret_provider/idp/object_storage/telemetry/alert_sandbox/domain_tls/deployment_target）的提供与接入
2. `four_role_signoff`：production-owner / release-manager / security-owner / auditor 真实证据与签署
3. 主理人在人类终端显式置 `engineering_enabled=true`（唯一 AI 不代执行之动作）
4. 旧 WIP（Production Handoff & Human Activation Ceremony）是否并入，由主理人线下裁决

## 36. 不进入项（显式排除）
- ❌ 不进入 Production Handoff（旧 WIP 独立登记，不吸收）
- ❌ 不进入 Phase 3.9.11
- ❌ 不自动激活 / 部署 / 生成真实工程参数 / 提供激活端点

## 37. 提交策略
- 不 `git add -A`、不 `git reset --hard`、不 `git add -A`（治理纪律）
- 显式 `git add` 各交付物路径 + 3 处 SSOT 修改，单提交收口
- 提交后回填 `PHASE_BOUNDARY_LEDGER.md` current_head 与 `project_status.json` current_head/evidence_hash 占位

## 38. git clean 说明
- 收口提交后执行 `git clean -fdq`；保留 stash（旧 WIP provenance）
- 执行前以 `git clean -fdn`（dry-run）核验，仅清理无引用构建产物/明确生成文件，绝不触碰交付物与历史

## 39. STOP 声明
本阶段收口即 **STOP**，等待主理人 + 专家线下审核。不机械推进 3.9.11、不自动激活、不提交超范畴代码。

## 40. 已知限制
- 外部预生产环境未真正接入（8 资源 pending、9 隔离 pending、13 运行时 not_configured）—— 属预期，待人工资源就绪
- 资格包 `gate.status` 为 `pending_external_staging_resource`，非可激活态
- 确定性包哈希因 source_commit 格式（短/全 SHA）差异会变化；同格式下确定

## 41. 后续人类步骤
1. 主理人审核本报告与全部交付物
2. 提供真实外部预生产资源并接入（或由四角色线下验证）
3. 四角色提交真实证据并签署
4. 主理人置 `engineering_enabled=true`（人类终端显式动作）
5. 旧 WIP 并入裁决
6. 进入下一阶段（3.9.11）需主理人另行授权

## 42. 治理 §4 冲突裁决表
| 冲突 | 裁决 | 证据 | Pending |
|---|---|---|---|
| 旧 WIP tip=e97d5361/Audit=155 陈述 vs 实测 | 以真实 git 来源为准，独立隔离不吸收 | `git cat-file` NOT_FOUND、`rev-list`=0、stash 清单 | 主理人裁决是否并入 |

## 43. 证据索引（交付文件清单）
- `.ai/progress/phase3.9.10_starting_baseline_validation.md`
- `.ai/progress/phase3.9.10_existing_wip_forensics.md`
- `scripts/generate_external_staging_qualification_package.py`
- `scripts/validate_external_staging_qualification_package.py`
- `scripts/check_phase39x_branch_integrity.py`
- `agents/external_staging_qualification/`（16 文件）
- `backend/app/api/external_staging_qualification.py`
- `frontend/src/app/external-staging-qualification/page.tsx`
- `tests/agents/test_external_staging_qualification.py`
- `.ai/baselines/external_staging_api_contract.json`
- `.ai/staging/external_staging_qualification_package.json`
- `.ai/runbooks/staging/EXTERNAL_STAGING_OPERATIONS_RUNBOOK.md`
- `.ai/runbooks/staging/HUMAN_EXTERNAL_STAGING_QUALIFICATION_CHECKLIST.md`
- `docs/EXTERNAL_STAGING_QUALIFICATION_GUIDE.md`
- `.github/workflows/external-staging-qualification-gate.yml`
- SSOT：`PHASE_BOUNDARY_LEDGER.md` / `project_status.json` / `PRODUCTION_DEPLOYMENT_GUIDE.md`

## 44. 测试与校验汇总
| 项 | 结果 |
|---|---|
| 阶段专属测试（50 tests） | 50 passed（收口时重跑） |
| 分支完整性守卫 | PASS |
| 包校验（validate） | PASS |
| 全量回归 agents | 2616 passed |
| 全量回归 backend | 380 passed |
| 全量回归 jest | 117 passed |
| tsc | 0 error |
| 确定性包 | DETERMINISTIC_OK（8d091f8a…） |
| Audit 类目总数 | 129（0 新增） |

## 45. 风险与缓解
- **SIGKILL 漂移**：全仓库 grep/diff 触发 exit 137 → 改用 git 安全命令 + 定向 Grep + 基于 git 视图的守卫
- **确定性破坏**：嵌套时间戳 → 递归 `_strip_non_fact` 修复
- **误伤合法模块**：forbidden 段过宽 → 收窄为 `production_handoff/handoff`
- **虚假状态**：summary 高估 → 收口时全部重核验（HEAD/分支/包/测试/守卫）

## 46. 验收标准
- [x] 全部 51 任务完成
- [x] 确定性包生成 + 校验 PASS
- [x] 50 测试 + 全量回归 0 failed
- [x] 分支完整性 PASS、Audit=129
- [x] SSOT 三处更新
- [x] 红线 6/6 守约、fail-closed 不变量成立
- [x] Pending Human Item 明确登记
- [x] STOP 不进 3.9.11 / 不 Production 动作

## 47. 签署与收口
- AI Chief Architect（执行）：✅ 阶段交付完成，STOP 等待审核
- 主理人（轩哥）：⏳ 待审
- 四角色签署：⏳ 待真实证据与线下签署
- 终端态：`EXTERNAL_STAGING_QUALIFICATION_BUILT_NO_GO`
- 收口提交 hash：`<CLOSURE_COMMIT>`（提交后回填本报告 §30/§31/§43 占位）
