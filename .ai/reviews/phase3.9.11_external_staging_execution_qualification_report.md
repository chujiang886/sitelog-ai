# Phase 3.9.11 收口报告 —— External Staging Execution & Qualification Layer

> 真实外部预生产环境「执行与资格验证」层（fail-closed，不激活、不部署、不 GO）
> 收口终态：`EXTERNAL_STAGING_EXECUTION_QUALIFICATION_BUILT_NO_GO`

---

## 1. 文档元信息

| 项 | 值 |
|---|---|
| 阶段 | Phase 3.9.11 |
| Canonical ID | `3.9.11-external-staging-execution-qualification` |
| 官方名 | External Staging Execution & Qualification Layer（真实外部预生产环境执行与资格验证层） |
| 分支 | `feat/phase3.9.11-external-staging-execution-qualification` |
| Phase base | `2f4a9838bcfc7105bc561f74fb2658906801e011` |
| Pre-closure HEAD | `2b0f306b898dcd04226720eb83a744ec8fc9df6b` |
| 收口提交 | 见 `.ai/project_status.json#phase_3_9_11_status.current_head`（SSOT 回填） |
| 终端态 | `EXTERNAL_STAGING_EXECUTION_QUALIFICATION_BUILT_NO_GO` |
| Gate 态 | `pending_external_staging_resource` |
| 审计账本总数（canonical） | 129（Phase 3.9.11 引入 0 新类目） |
| engineering_enabled | `false`（全程守约，config.yaml:102 未改） |
| 日期 | 2026-08-15 |
| 身份 | BOIP AI Chief Architect + External Staging Execution Engineer + Staging Isolation Safety Verifier（非 Production 激活/部署/签署主体） |

---

## 2. 执行摘要

Phase 3.9.11 在 Phase 3.9.10（External Staging Qualification & Evidence Integration）已冻结的资格框架之上，继续完成 **Track A（AI 必须完成的全部软件工程）**：真实外部预生产环境的「执行层」——执行计划（10 步）、执行 Gate（4 态 fail-closed）、执行包生成器/校验器、后端执行 API（7 路由，含修复长期 orphaned 的资格路由注册）、前端执行看板、CI 执行闸门、两个 Runbook、治理指南、人类可读 packet，以及 65 个 fail-closed 执行测试。

**Track B（真人/真实外部资源）依旧缺失**：8 项 External Staging 资源（DB/Secret/IdP/Storage/Alert 等）统一 `PENDING_EXTERNAL_STAGING_RESOURCE`，13 项证据链 none 含真实密钥；**绝不伪造** 8/8·9/9·13/13，绝不将 sandbox/fake 证据冒充 real external。

终态 `EXTERNAL_STAGING_EXECUTION_QUALIFICATION_BUILT_NO_GO`：结构性证明在「resource-less」条件下 External Staging 执行层不可达 Production。STOP 后仅报告 7 项要点，等主理人 + 四角色线下提供真实资源并签署。

---

## 3. 阶段定位与边界

- **是 External Staging（外部预生产），不是 Production。** 全程 `engineering_enabled=false`。
- **不是 Phase 3.9.10 的吸收或覆盖**：3.9.11 是 3.9.10 资格框架的「执行层」延续，复用其契约，不重造第二套。
- **永久隔离旧 WIP「Production Handoff & Human Activation Ceremony」**（stash@{0}/{stash@{7}}/{stash@{8}}）：禁 pop / merge / cherry-pick / 吸收 / 删除 / 重写。
- 六锚点 `2f4a9838`（phase_base）→ `34b0491` → `cb64105` → `056860ac` → `0be2f62` → `9b0970a4`（current_repository_head）互为祖先，本阶段在其直系演进线上。

---

## 4. 施工起点锚定（Branch Integrity Guard）

| 锚点 | 含义 | 核验 |
|---|---|---|
| `2f4a9838bcfc7105bc561f74fb2658906801e011` | Phase 3.9.9 Real Staging 收口线之后合法演进起点（phase_base，严格锁定） | ANCESTOR-OK |
| `34b0491` | 3.9.10 implementation_closure_commit | ANCESTOR-OK |
| `cb64105` | 3.9.10 pre_r1_anchor | ANCESTOR-OK |
| `056860ac` | 3.9.10 r1_code_package_commit | ANCESTOR-OK |
| `0be2f62` | 3.9.10 R1 final_head | ANCESTOR-OK |
| `9b0970a47106ee58ef9bac269a24c84d078d8540` | current_repository_head | ANCESTOR-OK |

`scripts/check_phase3911_branch_integrity.py` → 4×[PASS]（分支名 / forbidden 模块 / 3.9.12 残留 / 审计 129）。

---

## 5. T0 基线核验详情

- 分支正确：`feat/phase3.9.11-external-staging-execution-qualification`。
- `git status --porcelain` 仅含本阶段交付物（15 项新增/修改，无外国文件）。
- 6 锚点祖先关系全部 ANCESTOR-OK（见 §4）。
- 审计账本 total=129，0 orphan / 0 ghost / 0 duplicate-ownership，Git provenance 覆盖 11 phases。

---

## 6. T1 既有 WIP 法证（重申）

旧 WIP「Production Handoff & Human Activation Ceremony」真实载体经法证为：
- `stash@{0}`（3.9.10 资格分支上的 R2-preserve WIP）
- `stash@{7}` / `stash@{8}`（3.9.10 handoff 分支上的 carryover WIP）

仓库内无 `e97d5361` 这类 handoff 提交；handoff 内容仅存于 stash 隔离区，未并入任何 active 分支。

---

## 7. 旧 WIP 裁决

依据治理 §4：旧 WIP 与当前 active 3.9.11 语义正交，裁决为**独立隔离**，保留于其 stash 与历史分支，**不吸收、不删除、不重写、不合并**。

---

## 8. 冲突处理记录（治理 §4 流程）

| Conflict | Decision | Evidence | Pending Human Item |
|---|---|---|---|
| 3.9.10 资格测试 `test_current_branch_is_phase_branch` 硬编码 `feat/phase3.9.10-external-staging-qualification`，在 3.9.11 分支上误红（1 failed） | 改为**阶段无关**断言：当前分支匹配 `^feat/phase3\.9\.\d+-external-staging-` 即通过；`test_old_wip_is_separate_branch_not_merged` 改为派生当前分支并校验其与旧 WIP 分支互相独立。意图（Branch Integrity）保留，不绑定具体 Phase 编号，3.9.10 / 3.9.11 分支均能正确校验 | 修改 `tests/agents/test_external_staging_qualification.py`：加 `import re`，两测试改为模式/派生校验；重跑 `tests/agents` 由 `1 failed, 2680 passed` → `2681 passed` | 无（纯测试环境正确性修复，不改变业务含义/安全等级/历史事实/激活状态） |

---

## 9. 交付物总览

| 类别 | 交付物 | 状态 |
|---|---|---|
| agents 执行模块 | `agents/external_staging_execution/`（gate.py 等，复用 qualification 契约） | ✅ |
| 执行包 | `scripts/generate_external_staging_execution_package.py` + `validate_*.py` | ✅ |
| 执行包产物 | `.ai/staging/external_staging_execution_qualification_package.json`（hash=`7ac2f200…`） | ✅ |
| API 契约基线 | `.ai/baselines/external_staging_execution_api_contract.json` | ✅ |
| 分支完整性 | `scripts/check_phase3911_branch_integrity.py` | ✅ |
| 后端执行 API | `backend/app/api/external_staging_execution.py`（7 路由，fail-closed） | ✅ |
| 后端资格 API 注册修复 | `backend/app/api/__init__.py` + `backend/app/main.py`（接回长期 orphaned 资格路由） | ✅ |
| 前端执行看板 | `frontend/src/app/external-staging-execution/page.tsx`（只读，无 GO/Deploy） | ✅ |
| CI 执行闸门 | `.github/workflows/external-staging-execution-qualification-gate.yml`（9 job，fail-closed） | ✅ |
| Runbook | `.ai/runbooks/staging/HUMAN_EXTERNAL_STAGING_EXECUTION_CHECKLIST.md` + `EXTERNAL_STAGING_EXECUTION_RUNBOOK.md` | ✅ |
| 治理指南 | `docs/EXTERNAL_STAGING_EXECUTION_QUALIFICATION_GUIDE.md` | ✅ |
| 人类可读 packet | `.ai/packets/external_staging_execution_human_packet.json` | ✅ |
| 测试 | `tests/agents/test_external_staging_execution.py`（65 passed）+ 资格测试阶段无关修复 | ✅ |

---

## 10. agents 模块

`agents/external_staging_execution/` 复用 3.9.10 资格层与 3.9.9 运行时契约，**不重造第二套**：
- `gate.py`：`ExternalStagingExecutionGate.evaluate(...)` 检查 ① execution_plan_present ② no_real_execution_claimed ③ environment_not_production ④ credential_reference_safety（真实引用喂给 `assert_no_credential_leak`）⑤ resources_honest_pending ⑥ evidence_completeness ⑦ security/full_regression/repository_clean；`_decide` 沿用 4 态裁决（BLOCKED / PENDING_EXTERNAL_STAGING_RESOURCE / PENDING_HUMAN_VERIFICATION / READY_FOR_EXTERNAL_STAGING_HUMAN_REVIEW）。

---

## 11. 执行包生成器 / 校验器

- `generate_external_staging_execution_package.py`：确定性 SHA-256（重生成 hash 稳定 `7ac2f200bee0b957452020c23915957259b491261bb41d7ca00f8060ae2b1d1d`）。
- `validate_external_staging_execution_package.py` → `[PASS]`：phase=3.9.11 / gate=pending_external_staging_resource / hash deterministic / no real secret / no GO。
- 包内 `contains_real_secret=false` / `production_activation_prohibited=true` / `engineering_enabled=false` / `any_real_execution=false`。

---

## 12. 分支完整性脚本

`scripts/check_phase3911_branch_integrity.py` → 4×[PASS]：
- 分支名 = `feat/phase3.9.11-external-staging-execution-qualification`
- git 视图无 forbidden 模块（production_handoff / handoff）
- 无 3.9.12 路径残留
- AuditActionCategory total = 129

---

## 13. 后端 API

### 13.1 执行路由（`backend/app/api/external_staging_execution.py`，7 路由，prefix `/api/external-staging-execution`）
- `GET /status`：`terminal_state` / `gate_status` / `external_pending` / `engineering_enabled`
- `GET /plan`：10 步，含 `any_real_execution` / `step_count` / `steps`
- `GET /gate`：`gate_status` / `gate_checks`
- `GET /evidence`：`count` / `none_contains_secret` / `chain_hash`
- `GET /package`：整个 `_build_package()` 结果
- `GET /resources`：8 资源适配器探针（`probe_all()`，全 PENDING）
- `POST /human-record`：仅登记，用 `ExternalStagingExecutionSecurityValidator().validate_request(...)` 校验 scope/action，**403 拒绝 forbidden action**，不持久化 / 不执行 / 不部署

### 13.2 资格路由注册修复（长期 orphaned）
既有 `backend/app/api/external_staging_qualification.py` 虽存在但**未**在 `app/api/__init__.py` 与 `main.py` 注册。本次一并修复：`__init__.py` 导出两个 router，`main.py` 在 `governance_telemetry_router` 之后、`register_cors(app)` 之前 `include_router`。验证：`app.api` 含 `external_staging_execution_router` 与 `external_staging_qualification_router`。

---

## 14. 前端 UI

`frontend/src/app/external-staging-execution/page.tsx`：只读看板，镜像 qualification 页面；顶部强制 `EXTERNAL STAGING — NOT PRODUCTION` 红条；展示闸门 / 资源 Pending / 计划步数 / 证据数 / 执行计划 10 步 / 8 资源探针 / 闸门检查 / 机器包。**无 GO / Deploy / Rollback 按钮**。`npx tsc --noEmit` exit 0。

---

## 15. API 契约

`.ai/baselines/external_staging_execution_api_contract.json`：执行侧 7 路由 + 资格侧 8 路由；**显式禁止** `/execute` / `/deploy` / `/rollback` / `/apply` / `/migrate` / `/activate` 及 `engineering_approved` 输出。契约校验脚本 → `[PASS] api contract: 7 routes, no execution endpoint`。

---

## 16. 测试套件

| 套件 | 结果 |
|---|---|
| `tests/agents/test_external_staging_execution.py` | 65 passed（fail-closed 矩阵） |
| `tests/agents`（全量） | 2681 passed（含资格测试阶段无关修复） |
| `backend/tests`（全量） | 380 passed |
| `frontend` jest | 117 passed（7 suites） |
| `frontend` tsc | 0 error |
| 包校验器 | [PASS] |
| 分支完整性 | 4×[PASS] |
| 治理仓库完整性 | 通过（9/9 基线） |
| 生产安全 lint | 通过（7/7） |
| 审计账本校验 | [PASS] total=129 |

测试纪律：禁 `skip` / `xfail` / `ignore` / `continue-on-error` 掩盖失败；禁删断言换绿；禁伪造结果。

---

## 17. CI 工作流

`.github/workflows/external-staging-execution-qualification-gate.yml`（镜像 qualification gate，9 job，fail-closed）：
branch-integrity-gate / staging-execution-tests / package-generate-validate / audit-ledger-baseline(total==129) / api-contract-validate(7 routes + no_execution_endpoint) / credential-safety / isolation-check / repo-clean。任一 job 失败即整体 fail-closed。

---

## 18. 确定性包设计

- 确定性 SHA-256：`package_hash=7ac2f200bee0b957452020c23915957259b491261bb41d7ca00f8060ae2b1d1d`（重生成稳定）。
- 包内 `terminal_state=EXTERNAL_STAGING_EXECUTION_QUALIFICATION_BUILT_NO_GO`、`gate.status=pending_external_staging_resource`、`pending_resources=8`、`any_real_execution=false`。

---

## 19. Gate 设计（fail-closed）

`GateStatus` 仅 4 态（禁 APPROVED / PRODUCTION_READY / GO）：
- `BLOCKED`：仓库污染 / 安全未过 / 回归未过 → 真实拦截（测试 `test_gate_blocked_on_repo_pollution` 验证）
- `PENDING_EXTERNAL_STAGING_RESOURCE`：8 资源诚实 Pending（当前态）
- `PENDING_HUMAN_VERIFICATION`：待人工验证
- `READY_FOR_EXTERNAL_STAGING_HUMAN_REVIEW`：仅进入人工评审，不 GO

执行步状态 `ExecutionStepStatus` 无 real-execution 态；`contains_real_secret=false` / `production_activation_prohibited=true` / `engineering_enabled=false`。

---

## 20. 凭据安全

- `assert_no_credential_leak`：`scan_mapping` 仅查 top-level 敏感键；`_looks_like_raw_secret` 仅 `sk-...` 命中。**已显式固化此共享局限**（`test_credential_scanner_nested_value_not_scanned` 不抛）。
- 闸门把登记簿真实引用（`credential_reference` / `source_reference`）喂给扫描器；诚实引用下 PASS（`test_gate_credential_check_reads_real_references`）。
- 禁 Secret 入 Git / log / Audit / API / report；本阶段 0 真实密钥。

---

## 21. 隔离检查

- 9 项隔离约束全 `PENDING`/`VERIFIED-NOT-APPLICABLE`（resource-less 下结构性不可达 Production）。
- 旧 WIP 仅存 stash@{0}/{stash@{7}}/{stash@{8}}，不吸收。
- `test_no_foreign_phase_files_in_tree`：工作树无 `production_handoff` / `production_change` 外国文件。

---

## 22. 运行时健康

复用 3.9.9 运行时契约；执行层不实例化真实运行时（resource-less）。执行计划 10 步 `any_real_execution=false`。

---

## 23. 全量回归（实时数字）

| 维度 | 数字 |
|---|---|
| agents 全量 | 2681 passed |
| backend 全量 | 380 passed |
| frontend jest | 117 passed |
| frontend tsc | 0 error |
| 3.9.11 执行套件 | 65 passed |
| 包校验器 | PASS |
| 分支完整性 | 4×PASS |
| 治理完整性 | 9/9 PASS |
| 生产安全 lint | 7/7 PASS |
| 审计账本 | total=129 PASS |
| API 契约 | 7 routes PASS，无执行端点 |

---

## 24. SSOT 更新

1. **`.ai/PHASE_BOUNDARY_LEDGER.md`**：追加 3.9.11 行（branch / phase_base=`2f4a9838` / HEAD / terminal_state / 报告路径 / 说明「不吸收 Production Handoff WIP」）。
2. **`.ai/project_status.json`**：新增 `phase_3_9_11_status` 块（镜像 3.9.10 结构），含 terminal_state / gate / audit_total_canonical=129 / engineering_enabled=false / tasks_completed / core_modules / pending_human_actions / forbidden_endpoints / report 路径。

---

## 25. 红线守约（fail-closed）

1. 禁 Production Deploy / Migration / Rollback / Secret / Permission / Data / GO —— 全程未触发。
2. 禁 AI 代签 / 改 `engineering_enabled` / Production fallback —— `engineering_enabled=false` 守约。
3. 禁 `skip` / `xfail` / `ignore` / `continue-on-error` 掩盖失败 —— 1 测试误红已正面修复（非掩盖）。
4. 禁 Secret 入 Git / log / Audit / API / report —— 0 命中。
5. 禁自动关闭真实 Incident —— 未涉及。
6. 禁把 External Staging 说成 Production / 复用 Production 资源 —— 看板与文档均标注 NOT PRODUCTION。

---

## 26. fail-closed 不变量

- `contains_real_secret=false`
- `production_activation_prohibited=true`
- `engineering_enabled=false`
- `any_real_execution=false`
- Gate 4 态，禁 GO / APPROVED / PRODUCTION_READY
- 8 资源统一 `PENDING_EXTERNAL_STAGING_RESOURCE`
- 13 证据链 none 含真实密钥

---

## 27. Pending Human Item（人工动作入口，唯一合法出口）

1. 主理人 + 四角色（production-owner / release-manager / security-owner / auditor）线下提供真实 External Staging 资源（DB DSN / Secret / IdP / Storage / Alert）并登记。
2. 真实 External Staging 接入实证 + 跨环境隔离验证（staging 令牌 ≠ production 令牌 / 不复用 production 命名空间）。
3. 四角色在人类终端签署 External Staging Execution Qualification GO。
4. 主理人在人类终端显式置 `engineering_enabled=true`（仅限真实 Production 激活，不属本阶段）。

---

## 28. 不进入项（显式排除）

不进入 3.9.12、不自动激活、不真实部署、不输出 `engineering_approved`、不 AI 生成 GO、不代替四角色签署、不登记真实签署、不写真实密钥、不修改 `engineering_enabled`、不吸收 Production Handoff WIP、不跑 Runbook 真实执行。

---

## 29. 提交策略

- 精确 `git add` 各路径（禁 `git add -A`）。
- 不机械删历史、不 `git reset --hard`、不覆盖已有 Phase 编号。
- 收口提交见 SSOT `current_head`。

---

## 30. git clean 说明

`git status --porcelain` 仅含本阶段 15 项新增/修改，无外国文件、无临时文件污染。

---

## 31. STOP 声明

已 STOP。仅报告 7 项要点（见 §33）。等主理人 + 四角色线下提供真实 External Staging 资源并验证后，由主理人在人类终端显式置 enabled=true。

---

## 32. 已知限制

- 凭据扫描器 `scan_mapping` 不递归扫描嵌套值（与 3.9.10 共享局限），已固化测试；真实引用仍为 top-level 透明登记。
- Track B 全缺：8/8 资源 Pending，13/13 证据链无真实密钥，9/9 隔离未达真实验证。

---

## 33. 后续人类步骤（STOP 后 7 项要点）

1. **终态**：`EXTERNAL_STAGING_EXECUTION_QUALIFICATION_BUILT_NO_GO`（Gate=`pending_external_staging_resource`）。
2. **分支**：`feat/phase3.9.11-external-staging-execution-qualification`，六锚点互为祖先，Branch Integrity 4×PASS。
3. **审计**：total=129，0 新增，0 orphan/ghost/dup。
4. **回归**：agents 2681 / backend 380 / jest 117 / tsc 0 / 执行 65，全绿；治理 9/9、安全 7/7、审计 PASS、包校验 PASS、API 契约 PASS。
5. **资源**：8/8 `PENDING_EXTERNAL_STAGING_RESOURCE`；13/13 证据链 none 含真实密钥；9/9 隔离未达真实验证。**绝不伪造**。
6. **红线**：`engineering_enabled=false` 全程守约；无 GO / Deploy / Rollback / 代签 / 改 enabled。
7. **下一步**：主理人 + 四角色线下提供真实 External Staging 资源并签署后，方可进入真实执行与资格验证；AI 不代责。

---

## 34. 治理 §4 冲突裁决表

| # | Conflict | Decision | Pending Human |
|---|---|---|---|
| 1 | 资格测试硬编码 3.9.10 分支名，3.9.11 分支误红 | 阶段无关断言（模式/派生），意图保留 | 无 |

---

## 35. 证据索引（交付文件清单）

- `agents/external_staging_execution/`
- `scripts/generate_external_staging_execution_package.py` / `validate_*.py` / `check_phase3911_branch_integrity.py`
- `.ai/staging/external_staging_execution_qualification_package.json`
- `.ai/baselines/external_staging_execution_api_contract.json`
- `backend/app/api/external_staging_execution.py` / `__init__.py`（修复）/ `main.py`（修复）
- `frontend/src/app/external-staging-execution/page.tsx`
- `.github/workflows/external-staging-execution-qualification-gate.yml`
- `.ai/runbooks/staging/HUMAN_EXTERNAL_STAGING_EXECUTION_CHECKLIST.md` / `EXTERNAL_STAGING_EXECUTION_RUNBOOK.md`
- `docs/EXTERNAL_STAGING_EXECUTION_QUALIFICATION_GUIDE.md`
- `.ai/packets/external_staging_execution_human_packet.json`
- `tests/agents/test_external_staging_execution.py` + 资格测试阶段无关修复
- `.ai/reviews/phase3.9.11_external_staging_execution_qualification_report.md`
- `.ai/PHASE_BOUNDARY_LEDGER.md`（追加 3.9.11 行）
- `.ai/project_status.json`（新增 `phase_3_9_11_status` 块）

---

## 36. 测试与校验汇总

| 校验 | 结果 |
|---|---|
| 执行套件 | 65 passed |
| agents 全量 | 2681 passed |
| backend 全量 | 380 passed |
| jest | 117 passed |
| tsc | 0 error |
| 包校验 | PASS |
| 分支完整性 | 4×PASS |
| 治理完整性 | 9/9 PASS |
| 安全 lint | 7/7 PASS |
| 审计 | total=129 PASS |
| API 契约 | 7 routes PASS |

---

## 37. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 凭据扫描器不递归嵌套值 | 固化测试；引用 top-level 透明登记；真实密钥不入 Git |
| 阶段推进致分支名硬编码测试误红 | 改为阶段无关断言（本阶段已修复） |
| 旧 WIP 误吸收 | stash 隔离，禁 pop/merge/cherry-pick，文档显式排除 |

---

## 38. 验收标准

- [x] Track A 全部软件工程交付（执行层 + API + UI + CI + Runbook + 指南 + packet + 65 测试）
- [x] 资格路由长期 orphaned 注册修复
- [x] fail-closed 不变量全守约
- [x] 全量回归 0 failed
- [x] 审计 0 新增（129）
- [x] Branch Integrity 4×PASS
- [x] 8 资源诚实 Pending，0 伪造
- [x] STOP，仅报告 7 项要点

---

## 39. 签署与收口

AI 侧收口完成（Track A）。**四角色真实签署与 `engineering_enabled=true` 属主理人 + 四角色线下动作，AI 不代执行、不代签。**

收口终态：`EXTERNAL_STAGING_EXECUTION_QUALIFICATION_BUILT_NO_GO`。
