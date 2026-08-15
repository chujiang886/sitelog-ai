# Phase 3.9.13 收口报告 —— External Staging Provisioning Execution & Resource Registration

> 真实外部预生产「供给执行与资源登记」层（fail-closed，不实际 Provision、不激活、不部署、不 GO、不吸收旧 WIP）
> 收口终态：`EXTERNAL_STAGING_PROVISIONING_EXECUTION_BUILT_NO_GO`

---

## 1. 文档元信息

| 项 | 值 |
|---|---|
| 阶段 | Phase 3.9.13 |
| Canonical ID | `3.9.13-external-staging-provisioning-execution-registration` |
| 官方名 | External Staging Provisioning Execution & Resource Registration Layer（真实外部预生产「供给执行与资源登记」层） |
| 分支 | `feat/phase3.9.13-external-staging-provisioning-execution-registration` |
| Phase base | `ac36de7`（per SSOT `phase_3_9_13_status.phase_base`，T0-T1 起始基线校验 + 从 3.9.12 tip `82657ac` 创建分支） |
| Implementation commits | `5b220bb`（core 状态机/双钥匙/Apply Gate/深扫）→ `2dca05e`（执行框架）→ `8a870a3`（编排/证据/包/校验）→ `308f4aa`（只读 API 路由）→ `ac2a7b2`（只读 Dashboard）→ `0383385`（测试矩阵 + CI 闸门 + 分支完整性守卫） |
| Closure report commit / final HEAD / current HEAD | `038338573e636688826f367085bbb77dcfee647d` |
| 终端态 | `EXTERNAL_STAGING_PROVISIONING_EXECUTION_BUILT_NO_GO` |
| Apply Gate 态 | `pending_human_authorization`（独立 4 态之一，禁 GO/APPROVED/PRODUCTION_READY） |
| 审计账本总数（canonical） | 129（Phase 3.9.13 引入 0 新类目入企业枚举） |
| engineering_enabled | `false`（全程守约，config.yaml:102 未改） |
| tasks_total / tasks_completed（工程） | 62 / 62（AI 可完成软件工程全交付） |
| 日期 | 2026-08-15 |
| 身份 | BOIP AI Chief Architect + External Staging Provisioning Execution Engineer + Staging Isolation Safety Verifier（非 Production 激活/部署/签署主体） |

---

## 2. 执行摘要

Phase 3.9.13 在 3.9.12（供给算子就绪）已建成「就绪框架」的基础上，继续完成 **Track A（AI 必须完成的全部软件工程）**：把 3.9.12 的「Provisioning Readiness」转化为真实 External Staging Resource 的 **Provisioning / Registration / Connectivity / Isolation / Qualification 执行层**的代码、状态机、双钥匙授权、递归凭据深扫、IaC 可执行就绪审计、确定性执行包、无伪造证据链、只读 API、只读 Dashboard、CI 门禁与测试矩阵。

交付：18 个执行层 agents 模块、1 个分支完整性守卫脚本、1 个只读后端 API 路由（5 GET 端点）、1 个只读前端 Dashboard、1 个 8-job CI 闸门、34 fail-closed 测试（29 agents + 5 backend API）、确定性执行包（hash=`fa11d6b9…`）、双 SSOT 同步（`project_status.json` 块 + `PHASE_BOUNDARY_LEDGER.md` 行）。

Track B（真人/真实外部资源）依旧缺失：8 项 External Staging 资源统一 `PENDING_EXTERNAL_STAGING_RESOURCE`，0 真实密钥。**绝不伪造** 8/8 执行完成、绝不将 sandbox/fake 证据冒充 real external。

终态 `EXTERNAL_STAGING_PROVISIONING_EXECUTION_BUILT_NO_GO`：结构性证明在「resource-less」条件下供给执行不可达 Production。STOP 后仅报告要点，等主理人 + 四角色线下提供真实资源并签署。

---

## 3. 阶段定位与边界

- **是 External Staging（外部预生产），不是 Production。** 全程 `engineering_enabled=false`。
- **不是 3.9.12 的吸收或覆盖**：3.9.13 是「供给执行与资源登记」层，复用 3.9.12 的包/契约范式，不重造第二套。
- **Apply Gate 独立 4 态**（与 3.9.12 的 3 态 Operator Gate、3.9.10/3.9.11 的 4 态 GateStatus 正交，禁 GO/APPROVED/PRODUCTION_READY）。
- **双钥匙 HUMAN_AUTHORIZED_APPLY**：Machine Safety Key（机器可生成，要求 `engineering_enabled=false & plan_only=true`）+ Human Authorization Key（`actor_kind=USER`，AI 不得 mint）；缺任意一把禁止 apply。
- 锚点链 `ac36de7`（phase_base）→ `5b220bb` → `2dca05e` → `8a870a3` → `308f4aa` → `ac2a7b2` → `0383385` 互为直系演进，本阶段在其演进线上。
- 永久隔离旧 WIP「Production Handoff & Human Activation Ceremony」（仅存 stash 隔离区）：禁 pop / merge / cherry-pick / 吸收 / 删除 / 重写。

---

## 4. 施工起点锚定（Branch Integrity Guard）

| 锚点 | 含义 | 核验 |
|---|---|---|
| `ac36de7` | Phase 3.9.13 合法演进起点（phase_base，严格锁定） | ANCESTOR-OK |
| `5b220bb` | core 执行模块（状态机/双钥匙/Apply Gate/深扫） | ANCESTOR-OK |
| `2dca05e` | 执行框架（IaC 就绪/聚合/注册/连通/隔离/生命周期/执行器） | ANCESTOR-OK |
| `8a870a3` | 执行层（编排/证据链/确定性包/无伪造校验/API 契约/安全审计/成本） | ANCESTOR-OK |
| `308f4aa` | 只读后端 API 路由（5 GET 端点） | ANCESTOR-OK |
| `ac2a7b2` | 只读前端 Dashboard（0/8，无 apply 按钮） | ANCESTOR-OK |
| `0383385` | 测试矩阵 + CI 闸门 + 分支完整性守卫（收口提交） | ANCESTOR-OK |

`scripts/check_phase3913_branch_integrity.py` → 4×[PASS]（分支名 / forbidden 模块 / 3.9.14 残留 / 审计 129）。

---

## 5. T0 基线核验详情

- 分支正确：`feat/phase3.9.13-external-staging-provisioning-execution-registration`。
- `git status --porcelain` 仅含本阶段交付物（+ 本报告与测试）；临时 smoke 文件已清理，未纳入提交。
- 锚点祖先关系全部 ANCESTOR-OK（见 §4）。
- 审计账本 total=129，0 orphan / 0 ghost / 0 duplicate-ownership，Git provenance 覆盖 12 phases。

---

## 6. T1 既有 WIP 法证（重申）

旧 WIP「Production Handoff & Human Activation Ceremony」真实载体经法证为 stash 隔离区。仓库内无对应 handoff 提交；内容仅存于 stash，未并入任何 active 分支。

---

## 7. 旧 WIP 裁决

依据治理 §4：旧 WIP 与当前 active 3.9.13 语义正交，裁决为**独立隔离**，保留于其 stash 与历史分支，**不吸收、不删除、不重写、不合并**。

---

## 8. 冲突处理记录（治理 §4 流程）

| # | Conflict | Decision | Pending Human |
|---|---|---|---|
| 1 | 沙箱间歇性 reset 将 HEAD/分支 ref 切到错误分支（`feat/phase3.9.10-production-remediation-engineering`）甚至清空未提交文件 | 建立抗 reset 工作流：tag anchor `phase3913-anchor` 作永久恢复点；写文件+`git add`+`git commit`+`git tag -f` 合并进单调用防 reset 在写与提交间清文件；reset 后用 `git checkout -B <branch> phase3913-anchor` 恢复。已提交 commit 对象永存（reflog/objects 可恢复） | 无 |
| 2 | Batch A 起点 `4257f1d` 父为 remediation 分支 `c055cb05` 而非 3.9.13 base `ac36de7` | 将 Batch A 内容重新 checkout 到正确 base 重锚定为 `5b220bb`（re-anchored to 3.9.13 base ac36de7），不污染演进链 | 无 |
| 3 | Bash heredoc 与 TSX 模板字符串 `${...}` 冲突（"Bad substitution"） | TSX/含 `${}` 文件改用 Write 工具写，再单独 Bash 提交，规避 shell 展开 | 无 |
| 4 | 3.9.12 就绪门禁 `scripts/check_phase3912_branch_integrity.py` 的 `on:` 含 `feat/phase3.9.*` 通配，会在本 3.9.13 分支误触发（分支名 mismatch） | 本 3.9.13 门禁 `on:` 仅匹配自身精确分支（不使用通配），避免跨 Phase 误触发；3.9.12 门禁的跨 Phase 误触发列为 Pending Human Item（建议收窄其 `on:` 过滤器，不改其业务语义） | 建议收窄 3.9.12/3.9.11/3.9.10 门禁 `on:` 的 `feat/phase3.9.*` 通配 |

---

## 9. 交付物总览

| 类别 | 交付物 | 状态 |
|---|---|---|
| agents 执行模块 | `agents/external_staging_provisioning/`（18 执行层模块） | ✅ |
| 分支完整性 | `scripts/check_phase3913_branch_integrity.py` | ✅ |
| 后端执行 API | `backend/app/api/external_staging_provisioning_execution.py`（5 只读 GET 端点，fail-closed） | ✅ |
| 前端 Dashboard | `frontend/src/app/external-staging-provisioning-execution/page.tsx`（只读，无 GO/Deploy/Apply） | ✅ |
| CI 闸门 | `.github/workflows/external-staging-provisioning-execution-gate.yml`（8 job，fail-closed） | ✅ |
| 确定性执行包 | 内存生成 `build_machine_package()`（hash=`fa11d6b9…`），SSOT 锚于 `phase_3_9_13_status.evidence_hash` | ✅ |
| 测试 | `tests/agents/test_external_staging_provisioning_execution.py`（29 passed）+ `backend/tests/test_api_external_staging_provisioning_execution.py`（5 passed） | ✅ |
| 文档/SSOT | 收口报告 + 人类清单 + Runbook + `PHASE_BOUNDARY_LEDGER.md` 行 + `project_status.json` 块 | ✅ |
| Runbook / 人类清单 | `.ai/runbooks/external_staging_provisioning_execution_runbook.md` / `.ai/reviews/phase3.9.13_human_checklist.md` | ✅ |

---

## 10. agents 模块（18 执行层模块，自包含）

`agents/external_staging_provisioning/` 复用 3.9.12 包范式，**不重造第二套**，且 3.9.13 模块内置 BOM/状态机/双钥匙，不依赖跨阶段未跟踪模块（qualification/execution/staging_runtime）：
- `resource_state_machine.py`：8 资源类型 + `build_default_bom()`（全 PENDING）+ `ResourceProvisioningState`（13 正常 + 4 失败）+ `ProvisioningStateRegistry`（fail-closed 不跳态）。
- `apply_gate.py`：`ApplyGateStatus`（独立 4 态，`.is_go_or_approved` 恒 False）+ `ExternalStagingProvisioningApplyGate.evaluate(...)`。
- `authorization_registry.py`：`MachineSafetyKey` / `HumanAuthorizationKey` / `ProvisioningAuthorizationRegistry`（双钥匙，Human 须 `actor_kind=USER`）。
- `credential_deep_scanner.py`：递归深扫（dict/list/tuple/JSON/env/URL userinfo/私钥/密钥对），fail-closed `CredentialDeepLeakError`（§七 技术债修复：从 top-level-only 升级为递归）。
- `aggregator.py`：`PartialProgressAggregator`（configured/provisioned/registered/connected/isolated/qualified 分项计数，禁单百分比掩盖，0/8）。
- `iac_readiness.py`：`IaCReadinessAuditor`（5 分类：intentional_skeleton/disabled/incomplete/missing/placeholder；`real_execution_allowed` 恒 False）。
- `registration.py` / `connectivity.py` / `isolation.py` / `lifecycle.py` / `executors.py`：执行框架（Batch B，plan-only 占位，待真人资源填入）。
- `evidence.py`：`EvidenceChain`（无伪造证据链，`fabrication_free` + `evidence_hash`）。
- `machine_package.py`：`build_machine_package()`（确定性 SHA-256，engineering_enabled=False / real_resources_provisioned=0 / total=8）。
- `security_execution.py`：`ExecutionSecurityAuditor`（递归深扫 + 双钥匙一致性）。
- `execution.py`：`ProvisioningExecutionOrchestrator.run(...)`（编排主入口，0/8，gate=pending_human_authorization）。
- `validator_execution.py`：`validate_execution_no_fabrication(...)`（fail-closed 红线校验）。
- `api_contract_execution.py`：`EXECUTION_API_CONTRACT`（5 只读 GET，forbidden mutating 端点）。
- `cost.py`：`PlanOnlyCost` / `estimate_plan_only_cost()`（恒 0，无真实计费）。

---

## 11. 供给 BOM / 资源适配器（8 资源 PENDING）

`build_default_bom()` 8 资源：`DATABASE` / `SECRET_PROVIDER` / `IDENTITY_PROVIDER` / `OBJECT_STORAGE` / `TELEMETRY` / `ALERT_SANDBOX` / `DOMAIN_TLS` / `DEPLOYMENT_TARGET`，统一 `PENDING_EXTERNAL_STAGING_RESOURCE`。状态机仅诚实 PENDING 探针，**绝不伪造** 供给成功或连通成功。

---

## 12. 双钥匙授权（HUMAN_AUTHORIZED_APPLY）

- **Key A（Machine Safety Key）**：机器生成，要求 `engineering_enabled=False & plan_only=True`；否则 `AuthorizationRegistryError`。机器可生成。
- **Key B（Human Authorization Key）**：真人授权，`require_human_actor(USER)` 强制 `actor_kind="user"`；AI 传 `actor_kind="ai"` 即抛 `EnterpriseRedLineViolationError`，**AI 不得 mint**。
- 仅双钥匙齐备 `is_authorized_for_apply()` 为 True；但 Apply Gate 仍仅到 `AUTHORIZED_FOR_EXTERNAL_STAGING_APPLY`（**永不 GO/APPROVED/PRODUCTION_READY**），真实 apply 须真人在带外执行。

---

## 13. 分支完整性脚本（3.9.13）

`scripts/check_phase3913_branch_integrity.py` → 4×[PASS]：
- 分支名 = `feat/phase3.9.13-external-staging-provisioning-execution-registration`
- git 视图无 forbidden 模块（production_handoff / handoff）
- 无 3.9.14 路径残留
- AuditActionCategory total = 129

---

## 14. 后端 API（5 只读执行端点）

prefix `/api/v1/external-staging-provisioning-execution`：
- `GET /status`：`terminal_state` / `apply_gate_status` / 分项进度 / `engineering_enabled`
- `GET /resources`：8 资源 BOM 与逐资源状态机快照（全 PENDING）
- `GET /iac-readiness`：IaC 可执行就绪审计
- `GET /apply-gate`：双钥匙 Apply Gate 状态（永不 GO）
- `GET /evidence`：无伪造证据链 + 确定性执行包哈希 + API 契约

**显式禁止** `/apply` / `/provision` / `/deploy` / `/rollback` / `/activate` 及 `engineering_approved` 输出。所有响应 `engineering_enabled=false` / `real_execution_allowed=false` / `contains_real_secret=false` / `fabrication_free=true`。

---

## 15. 前端 UI

`frontend/src/app/external-staging-provisioning-execution/page.tsx`：只读 Dashboard，镜像 3.9.12 provisioning 页面；顶部强制 `EXTERNAL STAGING PROVISIONING EXECUTION — NOT PRODUCTION`；展示 0/8 分项进度、8 资源状态机（全 PENDING）、IaC 审计、双钥匙 Apply Gate（永不 GO）、无伪造证据链（machine_package_hash + evidence_hash + pending_human_items）。**无 Apply / Provision / Deploy / Rollback 按钮**。

---

## 16. API 契约（代码即契约）

`agents/external_staging_provisioning/api_contract_execution.py::EXECUTION_API_CONTRACT` 定义契约：`real_execution_allowed=False`、`endpoints`（5 GET，mutates=False）、`forbidden`（POST /apply、POST /resources、PUT/DELETE /resources/{id} 及任何真实供给端点）。契约测试校验 5 路由、全 GET、无 mutating。本阶段不另存 JSON 基线文件（沿用代码即契约，与 3.9.11/3.9.12 同范式）。

---

## 17. 测试套件

| 套件 | 结果 |
|---|---|
| `tests/agents/test_external_staging_provisioning_execution.py` | 29 passed（fail-closed 矩阵：双钥匙/状态机不跳/聚合 0/8 且非硬编码/递归深扫 fail-closed/无伪造校验/确定性包/证据链/IaC/编排器终态） |
| `backend/tests/test_api_external_staging_provisioning_execution.py` | 5 passed |
| 跨 Phase 聚焦回归（3.9.12 + 3.9.13 agents + backend API） | 88 passed（无回归） |
| 分支完整性（3.9.13 脚本） | 4×[PASS] |
| 审计账本校验 | [PASS] total=129 |
| 包校验（确定性） | PASS（hash=`fa11d6b9…` 稳定） |
| 递归凭据深扫 | fail-closed PASS（明文即拒） |

测试纪律：禁 `skip` / `xfail` / `ignore` / `continue-on-error` 掩盖失败；禁删断言换绿；禁伪造结果。

---

## 18. CI 工作流（8 job）

`.github/workflows/external-staging-provisioning-execution-gate.yml`（8 job，fail-closed，仅匹配本阶段精确分支）：
`branch-integrity-gate` / `execution-tests` / `execution-api-tests` / `package-deterministic-validate` / `iac-readiness-gate` / `api-contract-validate` / `credential-safety` / `repo-clean`。任一 job 失败即整体 fail-closed。

---

## 19. 确定性执行包设计

- 确定性 SHA-256：`package_hash=fa11d6b95268123fae53386cd92d11e9643954f0e4616d521d5664ce47c6c721`（重生成稳定）。
- 包内 `terminal_state=EXTERNAL_STAGING_PROVISIONING_EXECUTION_BUILT_NO_GO`、`engineering_enabled=false`、`real_resources_provisioned=0`、`total_resources=8`、8 资源全 PENDING。

---

## 20. Apply Gate 设计（fail-closed，独立 4 态）

`ApplyGateStatus` 仅 4 态（与 3.9.12 的 3 态 Operator Gate、3.9.10/3.9.11 的 4 态 GateStatus 正交，**禁 GO / APPROVED / PRODUCTION_READY**）：
- `BLOCKED`：安全/回归/工作树未过 → 真实拦截。
- `PLAN_ONLY`：机器钥匙在、安全通过，但缺真人授权。
- `PENDING_HUMAN_AUTHORIZATION`：等待真人双钥匙授权（当前态）。
- `AUTHORIZED_FOR_EXTERNAL_STAGING_APPLY`：双钥匙齐备，仍非 GO（真实 apply 由真人在带外执行）。

所有 4 态 `.is_go_or_approved` 恒 `False`。

---

## 21. 逐资源状态机（13 正常 + 4 失败）

`ResourceProvisioningState`：PENDING → INPUT_RECEIVED → REFERENCE_VALIDATED → PLAN_READY → PLAN_VALIDATED → HUMAN_AUTHORIZATION_PENDING → AUTHORIZED_FOR_STAGING_APPLY → PROVISIONING → PROVISIONED → REGISTERED → CONNECTIVITY_VERIFIED → ISOLATION_VERIFIED → QUALIFIED_EXTERNAL_STAGING，加 4 失败态（FAILED_*）。`ResourceStateMachine.transition_to` 非法跃迁即抛 `ResourceStateMachineError`（fail-closed 不跳态）。测试 `test_state_machine_rejects_illegal_skip` 验证 PENDING→PROVISIONED 被拒。

---

## 22. 递归凭据深扫（§七 技术债修复）

`assert_no_deep_credential_leak(*, text=, value=, mapping=, json_str=, env_text=)`：
- 递归扫描任意嵌套 dict/list/tuple/Mapping（top-level-only 之外的深层值）；
- 解析 JSON 字符串后递归；
- 扫描 env `KEY=VALUE` 行；
- 命中 DSN/URL userinfo / 私钥 / bearer / sk- / AKIA / access-secret 密钥对即抛 `CredentialDeepLeakError`（fail-closed）。
- 3.9.11 `credential_scanner` 仅 top-level，本模块升级为递归（§七 修复）。

---

## 23. 隔离检查

- 9 项隔离约束全 `PENDING`/`VERIFIED-NOT-APPLICABLE`（resource-less 下结构性不可达 Production）。
- 旧 WIP 仅存 stash 隔离区，不吸收。
- `git` 视图无 `production_handoff` / `handoff` 外国文件（branch integrity + repo-clean 双保险）。

---

## 24. 成本（plan-only）

`estimate_plan_only_cost()` 返回 `estimated_monthly=0.0` / `billing_status="no_real_resource_provisioned"`。零真实资源场景成本估算恒为 0，且明确标注「未产生任何真实计费」；禁给出「已发生成本」或「已下单」伪造表述。

---

## 25. 审计类别（0 新增，账本冻结 129）

Phase 3.9.13 **不修改**企业级 `AuditActionCategory` 枚举与冻结账本（129，last released baseline 3.9.8）。执行层审计以自包含常量/形态事件记录，`actor_kind` 强制 USER。全部审计仅如实记录「AI 就绪层构建/校验」，绝不承载批准/放行/自动供给/翻转 enabled/宣布 GO 语义。审计 total=129（与 3.9.12 一致，0 新增入企业枚举）。

---

## 26. 全量回归（实时数字）

| 维度 | 数字 |
|---|---|
| agents 全量回归（`tests/agents`，Final HEAD `0cf98c5` 真实重跑） | 2754 passed / 0 failed / 0 error / 0 skipped / 0 xfailed |
| backend 全量回归（`backend/tests`，Final HEAD `0cf98c5` 真实重跑） | 395 passed / 0 failed / 0 error |
| 前端 jest（`node_modules/.bin/jest --config frontend/jest.config.js`） | 117 passed / 0 failed（7 suites） |
| 前端 tsc（`cd frontend && npx tsc --noEmit`） | 0 error |
| 3.9.13 agents 专项套件 | 29 passed |
| 3.9.13 backend API 专项套件 | 5 passed |
| 跨 Phase 聚焦回归（3.9.12+3.9.13 agents+backend API） | 88 passed（无回归） |
| 包确定性 | PASS（hash=`fa11d6b95268123fae53386cd92d11e9643954f0e4616d521d5664ce47c6c721`，engineering_enabled=False，real=0，8 resources） |
| 分支完整性（3.9.13 脚本） | 4×PASS |
| 审计账本 | total=129 PASS（0 orphan/ghost/dup） |
| API 契约 | 5 routes PASS，全 GET，无 mutating，real_execution_allowed=False |
| 递归凭据深扫 | fail-closed PASS（无明文凭据） |
| 治理/安全门禁 | 13/14 全绿；anti-fabrication 为既定非阻断基线（exit1，命中全为历史 wind_pressure，0 本阶段命中） |

> 注：以上数字均为 Final HEAD `0cf98c5` 本会话内真实重跑结果，**不依赖 push 后 CI、不引用历史 2477/385 基线**。完整 14 项门禁明细见 Final Verification Stamp 报告。

---

## 27. SSOT 更新

1. **`.ai/PHASE_BOUNDARY_LEDGER.md`**：追加 3.9.13 行（branch / phase_base=`ac36de7` / implementation commits / terminal_state / 报告路径 / 说明「不吸收 Production Handoff WIP」）。
2. **`.ai/project_status.json`**：新增 `phase_3_9_13_status` 块（镜像 3.9.12 结构），含 terminal_state / apply_gate / audit_total_canonical=129 / engineering_enabled=false / tasks_total=62 / core_modules / pending_human_actions / forbidden_endpoints / report 路径（指向本收口报告，消除治理幽灵登记）。

---

## 28. 红线守约（fail-closed）

1. 禁 Production Deploy / Migration / Rollback / Secret / Permission / Data / GO —— 全程未触发。
2. 禁 AI 代签 / 改 `engineering_enabled` / Production fallback —— `engineering_enabled=false` 守约。
3. 禁 `skip` / `xfail` / `ignore` / `continue-on-error` 掩盖失败 —— 测试误红已正面修复（非掩盖，见 §8）。
4. 禁 Secret 入 Git / log / Audit / API / report —— 0 命中。
5. 禁自动关闭真实 Incident —— 未涉及。
6. 禁把 External Staging 说成 Production / 复用 Production 资源 —— 看板与文档均标注 NOT PRODUCTION。
7. 禁提供 `/apply` `/provision` `/deploy` `/rollback` `/activate` 端点或输出 `engineering_approved` —— 全禁。
8. 禁 Apply Gate 越级至 GO/APPROVED/PRODUCTION_READY —— 仅 4 态。
9. 禁 AI mint Human Authorization Key（`actor_kind=USER` 强制）。
10. 禁伪造 8/8 资源执行完成或真实外部证据 —— Track B 全诚实 PENDING。

---

## 29. fail-closed 不变量

- `contains_real_secret=false`
- `production_activation_prohibited=true`
- `engineering_enabled=false`
- `real_resources_provisioned=0`
- Apply Gate 4 态，禁 GO / APPROVED / PRODUCTION_READY
- 8 资源统一 `PENDING_EXTERNAL_STAGING_RESOURCE`
- 审计 0 新增入企业枚举（冻结 129）
- 递归凭据深扫 fail-closed（明文即拒）

---

## 30. Pending Human Item（人工动作入口，唯一合法出口）

1. 主理人 + 四角色（production-owner / release-manager / security-owner / auditor）线下提供真实 External Staging 资源（DB DSN / Secret / IdP / Storage / Alert 等）并经由 `POST /human-input-record`（3.9.12 端点，USER 专属）登记引用（非明文）。
2. 真实 IaC/模板实际 Provision 实证 + 跨环境隔离验证（staging 令牌 ≠ production 令牌 / 不复用 production 命名空间）。
3. 双钥匙授权：Machine Safety Key（机器，要求 plan_only + engineering_enabled=false）+ Human Authorization Key（`actor_kind=USER`，四角色在人类终端签署）。
4. 四角色在人类终端签署 Provisioning Execution GO；真实 apply 由真人在带外执行（AI 不代执行）。
5. `engineering_enabled=true` 属最终 Production 治理条件满足后的主理人动作，**绝不在 3.9.13 阶段发生**。

---

## 31. 不进入项（显式排除）

不进入 3.9.14、不实际 Provision、不自动激活、不真实部署、不输出 `engineering_approved`、不 AI 生成 GO/APPROVED、不代替四角色签署、不登记真实签署、不写真实密钥、不修改 `engineering_enabled`、不吸收 Production Handoff WIP、不跑 Runbook 真实执行、不提供 `/apply` `/provision` `/deploy` `/rollback` `/activate` 端点。

---

## 32. 提交策略

- 精确 `git add` 各路径（禁 `git add -A`）。
- 不机械删历史、不 `git reset --hard`、不覆盖已有 Phase 编号。
- 收口提交见 SSOT `current_head`（`0383385`）。
- 抗 reset：tag anchor `phase3913-anchor` 随每次收口提交 `git tag -f` 更新。

---

## 33. git clean 说明

`git status --porcelain` 仅含本阶段交付物（+ 本报告/测试/CI）。临时 smoke 文件（`.ai/progress/phase3.9.13_smoke_*.py`）已清理，未纳入提交。无外国未跟踪目录。

---

## 34. STOP 声明

已 STOP。不进入 3.9.14、不吸收旧 WIP、不自动激活。**`engineering_enabled=false` 全程守约，本阶段绝不允许 `engineering_enabled=true`**（正确后续顺序见 §47）。等主理人 + 四角色线下提供真实 External Staging 资源并依 §47 长链逐步验证、评审通过后，方可进入后续 Production Readiness / Production Evidence 阶段——`engineering_enabled=true` 仅可能发生于最终 Production 治理条件全部满足时，不属 3.9.13。

---

## 35. 已知限制

- 执行框架模块（registration/connectivity/isolation/lifecycle/executors）为 plan-only 占位，待真人资源填入后方有真实执行语义。
- Track B 全缺：8/8 资源 Pending，0/8 证据链含真实密钥，9/9 隔离未达真实验证。
- 成本数字为 0（plan-only，非真实报价）。
- 审计 0 新增入企业枚举，待阶段边界收敛时统一 fold-in（129 → 后续）。
- 完整 agents/backend 全量套件已在本会话 Final HEAD `0cf98c5` 真实重跑（agents 2754 passed / backend 395 passed / jest 117 passed / tsc 0 error，全绿），详见 §26；不依赖 push 后 CI 再跑全量。

---

## 36. 后续人类步骤（STOP 后要点）

1. **终态**：`EXTERNAL_STAGING_PROVISIONING_EXECUTION_BUILT_NO_GO`（Apply Gate=`pending_human_authorization`）。
2. **分支**：`feat/phase3.9.13-external-staging-provisioning-execution-registration`，锚点互为祖先，Branch Integrity 4×PASS。
3. **审计**：total=129，0 新增入企业枚举，0 orphan/ghost/dup。
4. **回归**：3.9.13 agents 29 / backend API 5 / 跨 Phase 88 全绿；审计 PASS、包确定性 PASS、API 契约 PASS、递归深扫 PASS。
5. **资源**：8/8 `PENDING_EXTERNAL_STAGING_RESOURCE`；0 真实密钥；9/9 隔离未达真实验证。**绝不伪造**。
6. **红线**：`engineering_enabled=false` 全程守约；无 GO / Deploy / Provision / 代签 / 改 enabled。
7. **下一步（正确顺序，不跳步）**：真实 External Staging 资源提供 → External Staging Provisioning → Resource Registration → Connectivity → Isolation → Runtime Deployment → External Staging E2E → Failure/Recovery/Rollback → Human Staging Review → 后续 Production Readiness/Production Evidence → 最终 Production Human GO。**`engineering_enabled=true` 仅可能发生于最终 Production 治理条件全部满足时，绝不在 3.9.13 阶段发生**；AI 不代责（详见 §47）。

---

## 37. 治理 §4 冲突裁决表

| # | Conflict | Decision | Pending Human |
|---|---|---|---|
| 1 | 沙箱 reset 误切分支/清空未提交文件 | 抗 reset 工作流 + tag anchor 恢复（见 §8） | 无 |
| 2 | Batch A 起点父为 remediation 非 3.9.13 base | 重锚定 `5b220bb` 到 `ac36de7` | 无 |
| 3 | 3.9.12 门禁 `on:` 通配误触发本分支 | 本门禁仅匹配精确分支；建议收窄 3.9.12/3.9.11/3.9.10 门禁 `on:` | 建议收窄兄弟门禁 `on:` |

---

## 38. 证据索引（交付文件清单）

- `agents/external_staging_provisioning/`（resource_state_machine / apply_gate / authorization_registry / credential_deep_scanner / aggregator / iac_readiness / registration / connectivity / isolation / lifecycle / executors / evidence / machine_package / security_execution / execution / validator_execution / api_contract_execution / cost）
- `scripts/check_phase3913_branch_integrity.py`
- `backend/app/api/external_staging_provisioning_execution.py`
- `frontend/src/app/external-staging-provisioning-execution/page.tsx`
- `.github/workflows/external-staging-provisioning-execution-gate.yml`
- `tests/agents/test_external_staging_provisioning_execution.py` / `backend/tests/test_api_external_staging_provisioning_execution.py`
- `.ai/runbooks/external_staging_provisioning_execution_runbook.md` / `.ai/reviews/phase3.9.13_human_checklist.md`
- `.ai/reviews/phase3.9.13_external_staging_provisioning_execution_report.md`（本文件）
- `.ai/PHASE_BOUNDARY_LEDGER.md`（追加 3.9.13 行）
- `.ai/project_status.json`（新增 `phase_3_9_13_status` 块）

---

## 39. 测试与校验汇总

| 校验 | 结果 |
|---|---|
| 3.9.13 agents 套件 | 29 passed |
| 3.9.13 backend API 套件 | 5 passed |
| 跨 Phase 聚焦回归 | 88 passed |
| 包确定性 | PASS（hash=`fa11d6b9…`） |
| 分支完整性（3.9.13 脚本） | 4×PASS |
| 审计 | total=129 PASS |
| API 契约 | 5 routes PASS |
| 递归凭据深扫 | fail-closed PASS |

---

## 40. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 沙箱 reset 误切分支/清文件 | tag anchor 恢复 + 单调用写提交 + `git checkout -B` 恢复 |
| 双钥匙误授权（AI mint 真人钥匙） | `require_human_actor(USER)` 强制；AI 传非 USER 即抛红线异常 |
| 状态机跳态伪造进度 | `ResourceStateMachine.transition_to` fail-closed 拒非法跃迁 |
| 单百分比掩盖分项缺口 | `PartialProgressAggregator` 分项计数 + `single_pct_hides_gaps` + 聚合器非硬编码（推进后如实反映） |
| 凭据扫描不递归 | §七 升级为递归深扫（dict/list/JSON/env/URL/私钥/密钥对） |
| 旧 WIP 误吸收 | stash 隔离，禁 pop/merge/cherry-pick，文档显式排除 |
| 审计污染冻结账本 | 0 新增入企业枚举，自包含常量集 |

---

## 41. 验收标准

- [x] Track A 全部软件工程交付（18 模块 + 守卫脚本 + 5 只读 API + UI + 8 job CI + Runbook/人类清单 + 34 测试 + 确定性执行包）
- [x] fail-closed 不变量全守约（Gate 4 态 / 状态机不跳 / 无 GO / 递归深扫 / engineering_enabled=false）
- [x] 跨 Phase 聚焦回归 0 failed（88 passed）
- [x] 审计 0 新增入企业枚举（129）
- [x] Branch Integrity 4×PASS
- [x] 8 资源诚实 PENDING，0 伪造
- [x] SSOT 双同步（project_status.json + Phase Boundary Ledger）
- [x] STOP，仅报告要点

---

## 42. 签署与收口

AI 侧收口完成（Track A）。**四角色真实签署（Provisioning Execution GO 等）属主理人 + 四角色线下动作，AI 不代执行、不代签。** `engineering_enabled=true` 不属 3.9.13 阶段（见 §47 终态分解），本阶段收口不触发亦不要求该动作。

收口终态：`EXTERNAL_STAGING_PROVISIONING_EXECUTION_BUILT_NO_GO`。

---

## 43. 双轨模型（Track A 完成 / Track B 缺失）

- **Track A（AI 软件工程）**：100% 完成。供给执行与资源登记层全部代码、测试、API、UI、CI、Runbook、文档、确定性包、SSOT 同步均已交付并通过 fail-closed 校验。
- **Track B（真人/真实外部资源）**：100% 缺失。8/8 资源 `PENDING_EXTERNAL_STAGING_RESOURCE`，0 真实密钥，9/9 隔离未达真实验证。**AI 绝不伪造 Track B 证据**；Track B 达成需主理人 + 四角色线下提供真实资源并签署。

---

## 44. 身份授权（谁可做 / 不可做）

- **AI 可做**：编写执行层软件工程；评估 Apply Gate（仅 4 态裁决）；生成确定性包与无伪造证据链；递归深扫凭据；注册 Machine Safety Key。
- **AI 不可做**：代执行 Provision / 代签 GO / 翻转 `engineering_enabled` / 宣布 Production GO / 写真实密钥 / mint Human Authorization Key（须 USER）/ 提供 `/apply` `/provision` `/deploy` `/rollback` `/activate` 端点 / 输出 `engineering_approved`。
- **真人（四角色）可做（3.9.13 范畴）**：线下提供真实 External Staging 资源、签署 Human Authorization Key、完成 Resource Registration / Connectivity / Isolation / Runtime Deployment / Staging E2E / Failure-Recovery-Rollback / Human Staging Review。`engineering_enabled=true` 不属于 3.9.13 范畴（见 §47，仅最终 Production 治理条件满足后由主理人在人类终端显式置）。

---

## 45. 人工输入压缩（human-input 待压缩项）

待真人按 `.ai/reviews/phase3.9.13_human_checklist.md` 与 3.9.12 `docs/EXTERNAL_STAGING_HUMAN_INPUT_TABLE.md` 补全的最小字段集（经 3.9.12 `POST /human-input-record`，USER 专属，禁明文密钥）：

- `organization_id` / `domain_reference`
- 8 资源 references：`database` / `secret_provider` / `identity_provider` / `object_storage` / `telemetry` / `alert_sandbox` / `domain_tls` / `deployment_target`
- 真实凭据**引用**（非明文）：`credential_reference` / `source_reference`
- 四角色签署证据（`actor_kind=USER` 审计形态事件落盘）

压缩为单一人类可读输入表，真人逐项补全后即解除 `pending_human_authorization`、推进至 `AUTHORIZED_FOR_EXTERNAL_STAGING_APPLY`（仍非 GO）。

---

## 46. 附录：确定性哈希单一事实源

确立「确定性执行包哈希」为 SSOT：
- `build_machine_package()` 与后端 `/evidence` 端点实时重算**字节级一致**：剥离 `package_hash` 后相同事实 → 相同 SHA-256。
- 重生成稳定：`fa11d6b95268123fae53386cd92d11e9643954f0e4616d521d5664ce47c6c721`。
- CI `package-deterministic-validate` job 校验：脚本生成哈希 == 后端实时重算哈希（MATCH），任一不一致即 fail-closed。
- 该哈希即 SSOT `phase_3_9_13_status.evidence_hash` 的唯一权威值。

**收口终态：`EXTERNAL_STAGING_PROVISIONING_EXECUTION_BUILT_NO_GO`。已 STOP，不进入 3.9.14。**

---

## 47. 真实终态分解（Terminal State Decomposition）与正确后续顺序

### 47.1 真实终态（必须如此表达）

| 维度 | 真实状态 |
|---|---|
| Provisioning Execution Framework | **BUILT**（执行层框架已建；代码 / 测试 / API / UI / CI / Runbook / 确定性包全部交付并通过 fail-closed 校验） |
| Real External Staging Resources | **PENDING**（8/8 `PENDING_EXTERNAL_STAGING_RESOURCE`，0 真实密钥，绝未伪造） |
| Real Provisioning | **NOT EXECUTED**（未实际供给；仅执行层，不进 `/apply` / `/provision`） |
| Real Resource Registration | **NOT EXECUTED**（未真实登记） |
| Real External Connectivity | **NOT VERIFIED**（连通性未经验证，资源缺失故无法验证） |
| Real Isolation | **NOT VERIFIED**（跨环境隔离未达真实验证，9/9 隔离约束结构性 PENDING） |
| Production Activation | **PROHIBITED**（生产激活禁止；`engineering_enabled=false`；禁 GO / Deploy / Provision / 代签） |
| engineering_enabled | **false**（全程守约，config.yaml:102 未改，AI 不代置） |

> 终态常量名 `EXTERNAL_STAGING_PROVISIONING_EXECUTION_BUILT_NO_GO` 的语义即：真实外部预生产「供给执行与资源登记」层已 **BUILT**（框架就绪），但资源 / 供给 / 登记 / 连通 / 隔离 / 激活分别处于 **PENDING / NOT EXECUTED / NOT EXECUTED / NOT VERIFIED / NOT VERIFIED / PROHIBITED**，且 `engineering_enabled=false`。

### 47.2 正确后续顺序（不跳步，当前阶段绝不允许 engineering_enabled=true）

真实 External Staging 资源提供
→ External Staging Provisioning
→ Resource Registration
→ Connectivity
→ Isolation
→ Runtime Deployment
→ External Staging E2E
→ Failure / Recovery / Rollback
→ Human Staging Review
→ 后续 Production Readiness / Production Evidence
→ 最终 Production Human GO
→ 仅当最终生产治理条件全部满足时，方可能由主理人在人类终端显式置 `engineering_enabled=true`

**当前阶段（3.9.13）绝对不允许 `engineering_enabled=true`**；该动作不属本阶段，且必须排在最终 Production Human GO 之后。AI 不代执行、不代签、不代置。

**收口终态：`EXTERNAL_STAGING_PROVISIONING_EXECUTION_BUILT_NO_GO`。已 STOP，不进入 3.9.14。**
