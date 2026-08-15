# Phase 3.9.12 收口报告 —— External Staging Provisioning Operator Readiness

> 真实外部预生产环境「供给算子就绪」层（fail-closed，不实际 Provision、不激活、不部署、不 GO）
> 收口终态：`EXTERNAL_STAGING_PROVISIONING_OPERATOR_READY_BUILT_NO_GO`

---

## 1. 文档元信息

| 项 | 值 |
|---|---|
| 阶段 | Phase 3.9.12 |
| Canonical ID | `3.9.12-external-staging-provisioning-operator-readiness` |
| 官方名 | External Staging Provisioning Operator Readiness Layer（真实外部预生产「供给算子就绪」层） |
| 分支 | `feat/phase3.9.12-external-staging-provisioning-operator-readiness` |
| Phase base | `6b61e80`（per SSOT `phase_3_9_12_status.phase_base`） |
| Implementation closure commit | `1ecb7ba196bf47936ecd8e560df29685a924a17f` |
| SSOT sync commit | `98fa73d29fcbb4232fe373a6c331da0805f285a2` |
| Closure report commit / final HEAD / current HEAD | `3c52a6b4e3021766687804788f06902f88b93564` |
| 终端态 | `EXTERNAL_STAGING_PROVISIONING_OPERATOR_READY_BUILT_NO_GO` |
| Operator Gate 态 | `pending_human_input`（独立 3 态之一） |
| 审计账本总数（canonical） | 129（Phase 3.9.12 引入 0 新类目入企业枚举；自包含 12 类待 fold-in） |
| engineering_enabled | `false`（全程守约，config.yaml:102 未改） |
| tasks_total / tasks_completed | 54 / 54 |
| 日期 | 2026-08-15 |
| 身份 | BOIP AI Chief Architect + External Staging Provisioning Operator Engineer + Staging Cost/Isolation Safety Verifier（非 Production 激活/部署/签署主体） |

---

## 2. 执行摘要

Phase 3.9.12 在 3.9.11（执行与资格验证）已实现「执行层」的基础上，继续完成 **Track A（AI 必须完成的全部软件工程）**：把「0/8 真实外部资源」推进到「可被真人/运维按明确 Runbook 与 IaC/模板实际 Provision」的**就绪状态**（不实际 Provision）。

交付：11 个供给算子 agents 模块、3 个脚本（生成/校验/分支完整性）、44 + 10 fail-closed 测试、后端 7 只读供给 API、前端只读看板、8 job CI 闸门、确定性算子包（hash=`65cc3060…`）、双 SSOT 同步（`project_status.json` 块 + `PHASE_BOUNDARY_LEDGER.md` 行）。

Track B（真人/真实外部资源）依旧缺失：8 项 External Staging 资源统一 `PENDING_EXTERNAL_STAGING_RESOURCE`，0 真实密钥。**绝不伪造** 8/8 就绪、绝不将 sandbox/fake 证据冒充 real external。

终态 `EXTERNAL_STAGING_PROVISIONING_OPERATOR_READY_BUILT_NO_GO`：结构性证明在「resource-less」条件下供给算子不可达 Production。STOP 后仅报告要点，等主理人 + 四角色线下提供真实资源并签署。

---

## 3. 阶段定位与边界

- **是 External Staging（外部预生产），不是 Production。** 全程 `engineering_enabled=false`。
- **不是 3.9.10/3.9.11 的吸收或覆盖**：3.9.12 是「供给算子就绪」层，复用其契约与包生成范式，不重造第二套。
- **Operator Gate 独立 3 态**（与 3.9.10/3.9.11 的 4 态 GateStatus 正交，禁 GO/APPROVED/PRODUCTION_READY）。
- **StagingProvisioningExecutionMode 仅 PLAN/VALIDATE/DRY_RUN/HUMAN_AUTHORIZED_APPLY**（禁 AUTO/PRODUCTION）。
- 锚点链 `6b61e80`（phase_base）→ `1ecb7ba`（implementation_closure_commit）→ `98fa73d`（ssot_sync_commit）→ `3c52a6b`（closure report commit）互为直系演进，本阶段在其演进线上。
- 永久隔离旧 WIP「Production Handoff & Human Activation Ceremony」（仅存 stash 隔离区）：禁 pop / merge / cherry-pick / 吸收 / 删除 / 重写。

---

## 4. 施工起点锚定（Branch Integrity Guard）

| 锚点 | 含义 | 核验 |
|---|---|---|
| `6b61e80` | Phase 3.9.12 合法演进起点（phase_base，严格锁定） | ANCESTOR-OK |
| `1ecb7ba196bf47936ecd8e560df29685a924a17f` | implementation_closure_commit（44 fail-closed 测试 + 11 模块 + 3 脚本 + 确定性算子包） | ANCESTOR-OK |
| `98fa73d29fcbb4232fe373a6c331da0805f285a2` | ssot_sync_commit（SSOT 块 + Phase Boundary Ledger 行；backend `_build_package` 对齐确定性哈希） | ANCESTOR-OK |
| `3c52a6b4e3021766687804788f06902f88b93564` | closure report commit（46 节收口报告 + 阶段无关分支完整性测试修复） | ANCESTOR-OK |

`scripts/check_phase3912_branch_integrity.py` → 4×[PASS]（分支名 / forbidden 模块 / 3.9.13 残留 / 审计 129）。

---

## 5. T0 基线核验详情

- 分支正确：`feat/phase3.9.12-external-staging-provisioning-operator-readiness`。
- `git status --porcelain` 仅含本阶段交付物（+ 本报告与测试修复）；未跟踪的 `deployment/remediation/`（来自其他分支 sandbox reset 残留）未纳入提交。
- 锚点祖先关系全部 ANCESTOR-OK（见 §4）。
- 审计账本 total=129，0 orphan / 0 ghost / 0 duplicate-ownership，Git provenance 覆盖 11 phases。

---

## 6. T1 既有 WIP 法证（重申）

旧 WIP「Production Handoff & Human Activation Ceremony」真实载体经法证为 stash 隔离区（3.9.10 资格分支与 handoff 分支上的 carryover WIP）。仓库内无对应 handoff 提交；内容仅存于 stash，未并入任何 active 分支。

---

## 7. 旧 WIP 裁决

依据治理 §4：旧 WIP 与当前 active 3.9.12 语义正交，裁决为**独立隔离**，保留于其 stash 与历史分支，**不吸收、不删除、不重写、不合并**。

---

## 8. 冲突处理记录（治理 §4 流程）

| # | Conflict | Decision | Pending Human |
|---|---|---|---|
| 1 | 3.9.11 执行测试 `test_branch_integrity_script_passes` 硬编码 `scripts/check_phase3911_branch_integrity.py`，在 3.9.12 分支误红（期望 3.9.11 分支、禁止 3.9.12 路径） | 改为**阶段无关**断言：从当前分支派生 phase 编号，运行对应 `scripts/check_phase39NN_branch_integrity.py`；意图（Branch Integrity 守约）保留，不绑定具体 Phase，3.9.11 / 3.9.12 分支均能正确校验（延续 3.9.11 §8 范式） | 无（纯测试环境正确性修复） |
| 2 | 治理仓库完整性检查 `test_main_on_real_repository_exits_zero` 报告 SSOT `phase_3_9_12_status.report` 指向的收口报告文件不存在（幽灵登记） | 本收口报告（T42-T43）补齐该文件，幽灵登记消除 | 无（AI 侧补齐，不改业务含义/安全等级/激活状态） |

---

## 9. 交付物总览

| 类别 | 交付物 | 状态 |
|---|---|---|
| agents 供给模块 | `agents/external_staging_provisioning/`（11 模块，复用 qualification 契约） | ✅ |
| 供给包生成器 | `scripts/generate_external_staging_provisioning_package.py` | ✅ |
| 供给包校验器 | `scripts/validate_external_staging_provisioning.py` | ✅ |
| 分支完整性 | `scripts/check_phase3912_branch_integrity.py` | ✅ |
| 供给包产物 | `.ai/staging/external_staging_provisioning_operator_package.json`（hash=`65cc3060…`） | ✅ |
| 后端供给 API | `backend/app/api/external_staging_provisioning.py`（7 只读端点，fail-closed） | ✅ |
| 前端看板 | `frontend/src/app/external-staging-provisioning/page.tsx`（只读，无 GO/Deploy/Provision） | ✅ |
| CI 闸门 | `.github/workflows/external-staging-provisioning-readiness-gate.yml`（8 job，fail-closed） | ✅ |
| Runbook / 指南 / 人工输入表 | `docs/EXTERNAL_STAGING_PROVISIONING_RUNBOOK.md` / `EXTERNAL_STAGING_OPERATOR_GATE.md` / `EXTERNAL_STAGING_HUMAN_INPUT_TABLE.md` / `EXTERNAL_STAGING_RESOURCE_BOM.md` / `EXTERNAL_STAGING_COST_MODEL.md` / `EXTERNAL_STAGING_CAPACITY_BASELINE.md` + 8 资源供给计划 + `EXTERNAL_STAGING_TARGET_ARCHITECTURE.md` | ✅ |
| ADR | `docs/adr/ADR-PHASE-3.9.12-EXTERNAL-STAGING-PROVIDER.md` / `ADR-PHASE-3.9.12-IAC-STRATEGY.md` | ✅ |
| 测试 | `tests/agents/test_external_staging_provisioning.py`（44 passed）+ `test_external_staging_provisioning_services.py` + `backend/tests/test_api_external_staging_provisioning.py`（10 passed） | ✅ |
| SSOT | `.ai/project_status.json`（`phase_3_9_12_status` 块）+ `.ai/PHASE_BOUNDARY_LEDGER.md`（3.9.12 行） | ✅ |

---

## 10. agents 模块（11 模块）

`agents/external_staging_provisioning/` 复用 3.9.10 资格层与 3.9.9 运行时契约，**不重造第二套**：
- `models.py`：`OperatorGateStatus`（独立 3 态枚举）/ `ExternalStagingProvisioningError` / `StagingProvisioningExecutionMode`（禁 AUTO/PRODUCTION）/ `ExternalStagingProvisioningEnvironmentIdentity`。
- `bom.py`：`ProvisioningBom`（8 资源适配器 + `build_default()`），全部诚实 PENDING。
- `dry_run_guard.py`：IaC 干跑校验（占位齐备 / 默认 provider 合规 / 无明文凭据）。
- `gate.py`：`ExternalStagingProvisioningOperatorGate.evaluate(...)`（独立 3 态裁决）。
- `validator.py`：供给包校验器。
- `package.py`：确定性包生成（SHA-256）。
- `api_contract.py`：`build_api_contract()`（7 路由 + 显式禁止端点 + 禁 AUTO/PRODUCTION 模式）。
- `security.py`：human-input-record 校验（仅 USER / 403 拒绝 forbidden action）。
- `cost_guard.py`：`StagingCostGuard`（预算 6000，三档示意区间）。
- `audit.py`：`PROVISIONING_AUDIT_CATEGORIES`（12 类自包含，不污染冻结账本 129）。
- `__init__.py`：导出。

---

## 11. 供给 BOM / 资源适配器（8 资源 PENDING）

`ProvisioningBom` 8 资源：`DATABASE` / `SECRET_PROVIDER` / `IDENTITY_PROVIDER` / `OBJECT_STORAGE` / `TELEMETRY` / `ALERT_SANDBOX` / `DOMAIN_TLS` / `DEPLOYMENT_TARGET`，统一 `PENDING_EXTERNAL_STAGING_RESOURCE`。适配器仅诚实 PENDING 探针（连通性/凭据均标 pending），**绝不伪造** 连通成功或凭据存在。

---

## 12. 供给包生成器 / 校验器

- `generate_external_staging_provisioning_package.py`：确定性 SHA-256（重生成 hash 稳定 `65cc30600c8086d2417244a4c16efd8b2338af1b936538713898cf90de756e01`）。
- `validate_external_staging_provisioning.py` → `[PASS]`：phase=3.9.12 / gate=pending_human_input / hash deterministic / no real secret / no GO。
- 包内 `contains_real_secret=false` / `production_activation_prohibited=true` / `engineering_enabled=false` / `pending_resources=8` / `any_real_provisioning=false`。

---

## 13. 分支完整性脚本（3.9.12）

`scripts/check_phase3912_branch_integrity.py` → 4×[PASS]：
- 分支名 = `feat/phase3.9.12-external-staging-provisioning-operator-readiness`
- git 视图无 forbidden 模块（production_handoff / handoff）
- 无 3.9.13 路径残留
- AuditActionCategory total = 129

---

## 14. 后端 API（7 只读供给端点）

prefix `/api/external-staging-provisioning`：
- `GET /status`：`terminal_state` / `operator_gate` / `pending_resources` / `engineering_enabled`
- `GET /bom`：8 资源适配器探针（全 PENDING）
- `GET /gate`：`operator_gate` / `gate_checks`
- `GET /iac-dry-run`：IaC 干跑校验结果
- `GET /package`：整个 `_build_package()` 结果
- `GET /runbook`：供给 Runbook 索引（只读）
- `POST /human-input-record`：仅登记，用 `ExternalStagingProvisioningSecurityValidator().validate_request(...)` 校验 scope/action，**403 拒绝 forbidden action**，不持久化 / 不执行 / 不部署

**显式禁止** `/provision` / `/apply` / `/deploy` / `/rollback` / `/activate` 及 `engineering_approved` 输出。API 实时重算包哈希 = `65cc3060…` = 落盘 SSOT 包哈希（MATCH，单一事实源，见 §46）。

---

## 15. 前端 UI

`frontend/src/app/external-staging-provisioning/page.tsx`：只读看板，镜像 provisioning 页面；顶部强制 `EXTERNAL STAGING — NOT PRODUCTION` 红条；展示闸门 / 资源 Pending / BOM / 包 / IaC 干跑 / Runbook / 成本护栏 / 人工输入表入口。**无 GO / Deploy / Provision / Rollback 按钮**。`npx tsc --noEmit` exit 0。

---

## 16. API 契约（代码即契约）

`agents/external_staging_provisioning/api_contract.py::build_api_contract()` 定义契约：`total_routes=7`、`no_execution_endpoint=True`、`forbidden_actions`（含 `/provision` `/apply` `/deploy` `/rollback` `/activate` 及 `engineering_approved` 输出）、`forbidden_provisioning_modes=["auto","production"]`、`production_activation_prohibited=true`、`engineering_enabled=false`。契约测试（`tests/agents/test_external_staging_provisioning.py`）校验 7 路由、无 provision 端点、禁 AUTO/PRODUCTION 模式。**本阶段不另存 JSON 基线文件**（沿用代码即契约，与 3.9.11 同范式）。

---

## 17. 测试套件

| 套件 | 结果 |
|---|---|
| `tests/agents/test_external_staging_provisioning.py` | 44 passed（fail-closed 矩阵） |
| `backend/tests/test_api_external_staging_provisioning.py` | 10 passed |
| `backend/tests`（全量） | 390 passed |
| `tests/agents`（全量） | 2725 passed |
| `frontend` jest | 117 passed（7 suites） |
| `frontend` tsc | 0 error |
| 包校验器 | [PASS] |
| 分支完整性（3.9.12 脚本） | 4×[PASS] |
| 治理仓库完整性 | 通过（9/9 基线） |
| 生产安全 lint | 通过（7/7） |
| 审计账本校验 | [PASS] total=129 |

测试纪律：禁 `skip` / `xfail` / `ignore` / `continue-on-error` 掩盖失败；禁删断言换绿；禁伪造结果。

---

## 18. CI 工作流（8 job）

`.github/workflows/external-staging-provisioning-readiness-gate.yml`（8 job，fail-closed）：
`branch-integrity-gate` / `provisioning-tests` / `package-generate-validate` / `audit-ledger-baseline`(total==129) / `api-contract-validate`(7 routes + no_provision_endpoint) / `credential-safety` / `iac-dry-run-gate` / `repo-clean`。任一 job 失败即整体 fail-closed。

---

## 19. 确定性包设计

- 确定性 SHA-256：`package_hash=65cc30600c8086d2417244a4c16efd8b2338af1b936538713898cf90de756e01`（重生成稳定）。
- 包内 `terminal_state=EXTERNAL_STAGING_PROVISIONING_OPERATOR_READY_BUILT_NO_GO`、`operator_gate.status=pending_human_input`、`pending_resources=8`、`any_real_provisioning=false`。

---

## 20. Operator Gate 设计（fail-closed，独立 3 态）

`OperatorGateStatus` 仅 3 态（与 3.9.10/3.9.11 的 4 态 GateStatus 正交，**禁 GO / APPROVED / PRODUCTION_READY**）：
- `BLOCKED`：仓库污染 / 安全未过 / 回归未过 → 真实拦截（测试 `test_gate_blocked_on_repo_pollution` 验证）
- `PENDING_HUMAN_INPUT`：等待真人输入/授权（当前态）
- `READY_FOR_HUMAN_PROVISIONING_REVIEW`：仅「就绪待真人评审」，不含任何「已通过/可上线」语义

复用 qualification 的 `GateCheck` / `assert_no_credential_leak`。闸门 `_decide` 任一 block 级失败 → BLOCKED；等待真人 → PENDING_HUMAN_INPUT；**绝不**越级至 READY/GO。

---

## 21. StagingProvisioningExecutionMode（禁 AUTO/PRODUCTION）

枚举仅 `PLAN` / `VALIDATE` / `DRY_RUN` / `HUMAN_AUTHORIZED_APPLY`（**禁 AUTO / PRODUCTION**）。算子包与 Gate 评估均不进入 AUTO/PRODUCTION 模式；`apply` 仅在 `HUMAN_AUTHORIZED_APPLY` + 真人授权 + 成本护栏通过 后才可触发，且由真人执行，AI 不代执行。

---

## 22. 凭据安全

- `assert_no_credential_leak`：`scan_mapping` 仅查 top-level 敏感键；`_looks_like_raw_secret` 仅 `sk-...` 命中（与 3.9.10/3.9.11 共享局限，已固化测试）。
- human-input-record 仅 USER 可登记，禁 AI / 明文 / 非法 category；真实引用喂给扫描器，诚实引用下 PASS。
- 禁 Secret 入 Git / log / Audit / API / report；本阶段 0 真实密钥。

---

## 23. 隔离检查

- 9 项隔离约束全 `PENDING`/`VERIFIED-NOT-APPLICABLE`（resource-less 下结构性不可达 Production）。
- 旧 WIP 仅存 stash 隔离区，不吸收。
- `test_no_foreign_phase_files_in_tree`：工作树无 `production_handoff` / `production_change` 外国文件。

---

## 24. 成本守卫（StagingCostGuard）

- 默认 `cost_budget=6000`（¥，示意上限，非真实报价）。
- 三档容量基线（A 最小可用 / B 推荐 / C 类生产）**示意月度成本区间下限**，仅用于护栏与规划，不构成任何真实报价/配额承诺。
- `estimate_min()` 按 A 档下限估算 8 资源总月度成本，超预算即阻断 apply（对应 Runbook 的「超预算阻断」）。
- 成本数字均为示意区间。

---

## 25. 审计类别（自包含 12 类，账本冻结 129）

`PROVISIONING_AUDIT_CATEGORIES`（frozenset，12 类，只读事实型）：`external_staging_provisioning_package_validated` / `_human_input_reviewed` / `_iac_dry_run` / `_operator_gate_evaluated` / `_bom_reviewed` / `_runbook_viewed` / `_cost_guard_checked` / `_capacity_reviewed` / `_cleanup_runbook_viewed` / `_authorization_registered` / `_readiness_reviewed` / `_evidence_built`。

**设计决策（治理守约）**：本文件**不**修改企业级 `AuditActionCategory` 枚举与冻结账本（129，last released baseline 3.9.8）；12 类以自包含常量集记录，fold-in 时并入 129 → 141。human-record 以审计形态事件落盘（category 为字符串，不进企业枚举），`actor_kind` 强制 USER。全部 12 类仅如实记录「真实人工查看/登记供给就绪」，绝不承载批准/放行/自动供给/翻转 enabled/宣布 GO 语义。

---

## 26. 全量回归（实时数字）

| 维度 | 数字 |
|---|---|
| agents 全量 | 2725 passed |
| backend 全量 | 390 passed |
| frontend jest | 117 passed |
| frontend tsc | 0 error |
| 3.9.12 provisioning 套件 | 44 passed |
| 3.9.12 backend API 套件 | 10 passed |
| 包校验器 | PASS |
| 分支完整性（3.9.12 脚本） | 4×PASS |
| 治理完整性 | 9/9 PASS |
| 生产安全 lint | 7/7 PASS |
| 审计账本 | total=129 PASS |
| API 契约 | 7 routes PASS，无 provision 端点 |

---

## 27. SSOT 更新

1. **`.ai/PHASE_BOUNDARY_LEDGER.md`**：追加 3.9.12 行（branch / phase_base=`6b61e80` / implementation_closure_commit=`1ecb7ba` / ssot_sync_commit=`98fa73d` / terminal_state / 报告路径 / 说明「不吸收 Production Handoff WIP」）。
2. **`.ai/project_status.json`**：新增 `phase_3_9_12_status` 块（镜像 3.9.11 结构），含 terminal_state / operator_gate / audit_total_canonical=129 / engineering_enabled=false / tasks_total=54 / core_modules / pending_human_actions / forbidden_endpoints / report 路径（指向本收口报告，消除治理幽灵登记）。

---

## 28. 红线守约（fail-closed）

1. 禁 Production Deploy / Migration / Rollback / Secret / Permission / Data / GO —— 全程未触发。
2. 禁 AI 代签 / 改 `engineering_enabled` / Production fallback —— `engineering_enabled=false` 守约。
3. 禁 `skip` / `xfail` / `ignore` / `continue-on-error` 掩盖失败 —— 2 测试误红已正面修复（非掩盖，见 §8）。
4. 禁 Secret 入 Git / log / Audit / API / report —— 0 命中。
5. 禁自动关闭真实 Incident —— 未涉及。
6. 禁把 External Staging 说成 Production / 复用 Production 资源 —— 看板与文档均标注 NOT PRODUCTION。
7. 禁提供 `/provision` `/apply` `/deploy` `/rollback` `/activate` 端点或输出 `engineering_approved` —— 全禁。
8. 禁 Operator Gate 越级至 GO/APPROVED/PRODUCTION_READY —— 仅 3 态。
9. 禁 StagingProvisioningExecutionMode 进入 AUTO/PRODUCTION —— 仅 4 态。
10. 禁伪造 8/8 资源就绪或真实外部证据 —— Track B 全诚实 PENDING。

---

## 29. fail-closed 不变量

- `contains_real_secret=false`
- `production_activation_prohibited=true`
- `engineering_enabled=false`
- `any_real_provisioning=false`
- Operator Gate 3 态，禁 GO / APPROVED / PRODUCTION_READY
- StagingProvisioningExecutionMode 仅 4 态，禁 AUTO / PRODUCTION
- 8 资源统一 `PENDING_EXTERNAL_STAGING_RESOURCE`
- 审计 12 类自包含，不污染冻结账本 129

---

## 30. Pending Human Item（人工动作入口，唯一合法出口）

1. 主理人 + 四角色（production-owner / release-manager / security-owner / auditor）线下提供真实 External Staging 资源（DB DSN / Secret / IdP / Storage / Alert 等）并经由 `POST /human-input-record`（USER 专属）登记。
2. 真实 IaC/模板实际 Provision 实证 + 跨环境隔离验证（staging 令牌 ≠ production 令牌 / 不复用 production 命名空间）。
3. 四角色在人类终端签署 Provisioning GO。
4. 主理人在人类终端显式置 `engineering_enabled=true`（仅限真实 Production 激活，不属本阶段）。

---

## 31. 不进入项（显式排除）

不进入 3.9.13、不实际 Provision、不自动激活、不真实部署、不输出 `engineering_approved`、不 AI 生成 GO/APPROVED、不代替四角色签署、不登记真实签署、不写真实密钥、不修改 `engineering_enabled`、不吸收 Production Handoff WIP、不跑 Runbook 真实执行、不提供 `/provision` `/apply` `/deploy` `/rollback` `/activate` 端点。

---

## 32. 提交策略

- 精确 `git add` 各路径（禁 `git add -A`）。
- 不机械删历史、不 `git reset --hard`、不覆盖已有 Phase 编号。
- 收口提交见 SSOT `current_head`（`3c52a6b`）。

---

## 33. git clean 说明

`git status --porcelain` 仅含本阶段 17 项新增/修改 + 本报告 + 测试修复，无外国文件、无临时文件污染。注：工作树偶现来自其他分支的 sandbox reset 残留 `deployment/remediation/`（未跟踪、非本分支交付物，未纳入提交，亦未删除——非本阶段职责）。

---

## 34. STOP 声明

已 STOP。不进入 3.9.13、不吸收旧 WIP、不自动激活。等主理人 + 四角色线下提供真实 External Staging 资源并验证后，由主理人在人类终端显式置 `engineering_enabled=true`。

---

## 35. 已知限制

- 凭据扫描器不递归扫描嵌套值（与 3.9.10/3.9.11 共享局限），已固化测试；真实引用仍为 top-level 透明登记。
- Track B 全缺：8/8 资源 Pending，0/13 证据链含真实密钥（无证据链含真实密钥），9/9 隔离未达真实验证。
- 成本数字为示意区间，非真实报价。
- 审计 12 类自包含，待阶段边界收敛时统一 fold-in（129 → 141）。
- 无独立 provisioning 人类可读 packet 文件（沿用 `docs/EXTERNAL_STAGING_HUMAN_INPUT_TABLE.md` + API 端点承载，见 §45）。

---

## 36. 后续人类步骤（STOP 后要点）

1. **终态**：`EXTERNAL_STAGING_PROVISIONING_OPERATOR_READY_BUILT_NO_GO`（Operator Gate=`pending_human_input`）。
2. **分支**：`feat/phase3.9.12-external-staging-provisioning-operator-readiness`，锚点互为祖先，Branch Integrity 4×PASS。
3. **审计**：total=129，0 新增入企业枚举，0 orphan/ghost/dup。
4. **回归**：agents 2725 / backend 390 / jest 117 / tsc 0 / provisioning 44 / backend API 10，全绿；治理 9/9、安全 7/7、审计 PASS、包校验 PASS、API 契约 PASS。
5. **资源**：8/8 `PENDING_EXTERNAL_STAGING_RESOURCE`；0 真实密钥；9/9 隔离未达真实验证。**绝不伪造**。
6. **红线**：`engineering_enabled=false` 全程守约；无 GO / Deploy / Provision / 代签 / 改 enabled。
7. **下一步**：主理人 + 四角色线下提供真实 External Staging 资源并签署后，方可实际 Provision；AI 不代责。

---

## 37. 治理 §4 冲突裁决表

| # | Conflict | Decision | Pending Human |
|---|---|---|---|
| 1 | 3.9.11 执行测试硬编码 3.9.11 分支名与脚本，3.9.12 分支误红 | 阶段无关派生校验（从分支名取 phase 编号运行对应脚本），意图保留 | 无 |
| 2 | SSOT `phase_3_9_12_status.report` 指向报告不存在（幽灵登记） | 补齐收口报告文件 | 无 |

---

## 38. 证据索引（交付文件清单）

- `agents/external_staging_provisioning/`（`__init__` / `models` / `bom` / `dry_run_guard` / `gate` / `validator` / `package` / `api_contract` / `security` / `cost_guard` / `audit`）
- `scripts/generate_external_staging_provisioning_package.py` / `validate_external_staging_provisioning.py` / `check_phase3912_branch_integrity.py`
- `.ai/staging/external_staging_provisioning_operator_package.json`
- `backend/app/api/external_staging_provisioning.py`
- `frontend/src/app/external-staging-provisioning/page.tsx`
- `.github/workflows/external-staging-provisioning-readiness-gate.yml`
- `docs/EXTERNAL_STAGING_PROVISIONING_RUNBOOK.md` / `EXTERNAL_STAGING_OPERATOR_GATE.md` / `EXTERNAL_STAGING_HUMAN_INPUT_TABLE.md` / `EXTERNAL_STAGING_RESOURCE_BOM.md` / `EXTERNAL_STAGING_COST_MODEL.md` / `EXTERNAL_STAGING_CAPACITY_BASELINE.md` / 8 资源供给计划（`*_PROVISIONING_PLAN.md`）/ `EXTERNAL_STAGING_TARGET_ARCHITECTURE.md`
- `docs/adr/ADR-PHASE-3.9.12-EXTERNAL-STAGING-PROVIDER.md` / `ADR-PHASE-3.9.12-IAC-STRATEGY.md`
- `tests/agents/test_external_staging_provisioning.py` / `test_external_staging_provisioning_services.py` / `backend/tests/test_api_external_staging_provisioning.py`
- `.ai/reviews/phase3.9.12_external_staging_provisioning_operator_readiness_report.md`（本文件）
- `.ai/PHASE_BOUNDARY_LEDGER.md`（追加 3.9.12 行）
- `.ai/project_status.json`（新增 `phase_3_9_12_status` 块）
- `tests/agents/test_external_staging_execution.py`（阶段无关分支完整性修复）

---

## 39. 测试与校验汇总

| 校验 | 结果 |
|---|---|
| provisioning agents 套件 | 44 passed |
| backend API 套件 | 10 passed |
| backend 全量 | 390 passed |
| agents 全量 | 2725 passed |
| jest | 117 passed |
| tsc | 0 error |
| 包校验 | PASS |
| 分支完整性（3.9.12 脚本） | 4×PASS |
| 治理完整性 | 9/9 PASS |
| 安全 lint | 7/7 PASS |
| 审计 | total=129 PASS |
| API 契约 | 7 routes PASS |

---

## 40. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 凭据扫描器不递归嵌套值 | 固化测试；引用 top-level 透明登记；真实密钥不入 Git |
| 阶段推进致分支名硬编码测试误红 | 改为阶段无关派生校验（本阶段 §8 修复，延续 3.9.11 §8） |
| IaC 占位过多致 apply 误判就绪 | dry_run_guard 校验占位齐备 + 默认 provider 合规 + 无明文；成本护栏超预算阻断 apply |
| 旧 WIP 误吸收 | stash 隔离，禁 pop/merge/cherry-pick，文档显式排除 |
| 审计类别污染冻结账本 | 自包含 12 类常量集，fold-in 时机延后至阶段边界收敛 |

---

## 41. 验收标准

- [x] Track A 全部软件工程交付（11 模块 + 3 脚本 + 7 只读 API + UI + 8 job CI + Runbook/指南/人工输入表 + ADR + 44+10 测试 + 确定性算子包）
- [x] fail-closed 不变量全守约（Gate 3 态 / ExecutionMode 4 态 / 无 GO / 无明文 / engineering_enabled=false）
- [x] 全量回归 0 failed（agents 2725 / backend 390 / jest 117 / tsc 0）
- [x] 审计 0 新增入企业枚举（129）；自包含 12 类待 fold-in
- [x] Branch Integrity 4×PASS
- [x] 8 资源诚实 PENDING，0 伪造
- [x] SSOT 双同步（project_status.json + Phase Boundary Ledger）+ 治理幽灵登记消除
- [x] STOP，仅报告要点

---

## 42. 签署与收口

AI 侧收口完成（Track A）。**四角色真实签署与 `engineering_enabled=true` 属主理人 + 四角色线下动作，AI 不代执行、不代签。**

收口终态：`EXTERNAL_STAGING_PROVISIONING_OPERATOR_READY_BUILT_NO_GO`。

---

## 43. 双轨模型（Track A 完成 / Track B 缺失）

- **Track A（AI 软件工程）**：100% 完成。供给算子就绪层全部代码、测试、API、UI、CI、Runbook、文档、确定性包、SSOT 同步均已交付并通过 fail-closed 校验。
- **Track B（真人/真实外部资源）**：100% 缺失。8/8 资源 `PENDING_EXTERNAL_STAGING_RESOURCE`，0 真实密钥，9/9 隔离未达真实验证。**AI 绝不伪造 Track B 证据**；Track B 达成需主理人 + 四角色线下提供真实资源并签署。

---

## 44. 身份授权（谁可做 / 不可做）

- **AI 可做**：编写就绪层软件工程；评估 Operator Gate（仅 3 态裁决）；登记经由 `POST /human-input-record` 的 USER 输入；生成确定性包与审计形态事件（actor_kind=USER 强制）。
- **AI 不可做**：代执行 Provision / 代签 GO / 翻转 `engineering_enabled` / 宣布 Production GO / 写真实密钥 / 提供 `/provision` `/apply` `/deploy` `/rollback` `/activate` 端点 / 输出 `engineering_approved`。
- **真人（四角色）可做**：线下提供真实 External Staging 资源、签署 Provisioning GO、在主终端置 `engineering_enabled=true`。

---

## 45. 人工输入压缩（human-input 待压缩项）

待真人按 `docs/EXTERNAL_STAGING_HUMAN_INPUT_TABLE.md` 与 Runbook 补全的最小字段集（经 `POST /human-input-record`，USER 专属，禁明文密钥）：

- `organization_id` / `domain_reference`
- 8 资源 references：`database` / `secret_provider` / `identity_provider` / `object_storage` / `telemetry` / `alert_sandbox` / `domain_tls` / `deployment_target`
- 真实凭据**引用**（非明文）：`credential_reference` / `source_reference`
- 四角色签署证据（`actor_kind=USER` 审计形态事件落盘）

压缩为单一人类可读输入表（见 `EXTERNAL_STAGING_HUMAN_INPUT_TABLE.md`），真人逐项补全后即解除 `pending_human_input`、推进至 `READY_FOR_HUMAN_PROVISIONING_REVIEW`。本阶段未生成独立 packet 文件（沿用文档 + API 端点承载，避免重复事实源）。

---

## 46. 附录：确定性哈希单一事实源

确立「API 实时重算 = 落盘 SSOT 包哈希」的单一事实源机制：

- `backend/app/api/external_staging_provisioning.py::_build_package()` 与 `scripts/generate_external_staging_provisioning_package.py` **字节级一致**：`environment_identity` 使用完整 `ExternalStagingEnvironmentIdentity`（8 引用齐全），`human_pending` 保持空，剥离 `package_hash` / `generated_at` 后相同事实 → 相同 SHA-256。
- 重生成稳定：`65cc30600c8086d2417244a4c16efd8b2338af1b936538713898cf90de756e01`。
- CI `package-generate-validate` job 校验：脚本生成哈希 == API 实时重算哈希 == 落盘 SSOT 包哈希（MATCH），任一不一致即 fail-closed。
- 该哈希即 SSOT `phase_3_9_12_status.evidence_hash` 与 `.ai/staging/..._operator_package.json#package_hash` 的唯一权威值。

**收口终态：`EXTERNAL_STAGING_PROVISIONING_OPERATOR_READY_BUILT_NO_GO`。已 STOP，不进入 3.9.13。**
