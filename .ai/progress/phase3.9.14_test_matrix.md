# Phase 3.9.14 测试矩阵（Test Matrix）—— External Staging Runtime Deployment & End-to-End Qualification

> 终态：`PHASE_3_9_14_EXTERNAL_STAGING_RUNTIME_E2E_QUALIFICATION_BUILT_NO_GO`
> 生成时间：2026-08-15｜分支：`feat/phase3.9.14-external-staging-runtime-deployment-e2e-qualification`
> 全部测试在本 Phase 分支、沙箱离线环境下运行；`engineering_enabled=false` 全程守约。

## 0. 总览

| 类别 | 入口 / 命令 | 结果 |
|------|------------|------|
| Agent 单元/E2E | `pytest tests/agents/test_external_staging_runtime_e2e.py -q` | **15 passed** |
| Backend 只读 API | `pytest backend/tests/test_api_external_staging_runtime_e2e.py -q` | **8 passed** |
| 分支完整性守卫 | `python scripts/check_phase3914_branch_integrity.py` | **exit 0 (PASS)** |
| 运行时包自审 | `run_self_audit()` | **7/7 passed** |
| CI 门禁 | `.github/workflows/external-staging-runtime-e2e-qualification-gate.yml` | **6 jobs (fail-closed)** |
| 确定性包哈希 | `build_machine_package()['package_hash']` | `d632d6610e20c48ec72a2a7a04dbd17aee8c76ccdb436541960147fc5d4b9839`（稳定，两次一致） |

**合计：23 自动化测试 + 1 分支守卫 + 1 自审套件（7 项）全绿；0 failed / 0 error。**

---

## 1. Agent 测试（15 passed）

覆盖 `agents/external_staging_runtime/` 七层聚合 + 确定性包 + 只读 API + Dashboard + 自审：

| 测试 | 验证点 |
|------|--------|
| test_machine_package_deterministic | 两次构建哈希一致（剔除 `generated_at`） |
| test_machine_package_validate_passes | `validate_package` fail-closed 通过 |
| test_machine_package_validate_rejects_tamper | 3 种篡改（engineering_enabled=True / hash 置 0 / 注入 is_go_or_approved=True）均 `AssertionError` 拒绝 |
| test_package_no_generated_at_in_hashed_content | 哈希内容不含时间戳 |
| test_readonly_endpoint_present_and_fail_closed[7 参数] | 7 端点均含 6 个 FB_KEYS 且 False/True 正确 |
| test_readonly_unknown_endpoint_raises | 未知端点抛 `KeyError` |
| test_dashboard_valid | 只读 Dashboard `package_valid=True` |
| test_api_contract_readonly | API 契约 7 只读 GET，禁 mutating |
| test_self_audit_passes | 7 项不变量自审全过 |

---

## 2. Backend 只读 API 测试（8 passed）

覆盖 `backend/app/api/external_staging_runtime_e2e.py` 7 个 GET 端点 + 方法约束：

| 测试 | 验证点 |
|------|--------|
| test_status | package_hash len 64 / deterministic / 8 资源 / 7 层 |
| test_isolation_no_production_leakage | 9 域 / production_leakage=False / real_resources_present=0 |
| test_qualification_structural_only | 13 项 / code_verified=13 / runtime_executed=0 |
| test_health_plan_only | overall_status=PLAN_ONLY |
| test_e2e_structural_ok | 6 步 PLAN_ONLY_STRUCTURAL_OK |
| test_change_control_never_go | is_go_or_approved=False / 4 态之一 / 双钥匙未授权 |
| test_evidence_no_leakage | 7 items / violations=[] / integrity_hash 64 |
| test_forbidden_methods_rejected | POST/PUT/DELETE → 404/405 |

所有端点统一断言：`engineering_enabled=False` / `real_execution_allowed=False` / `real_apply_allowed=False` / `is_production=False` / `contains_real_secret=False` / `fabrication_free=True` / `terminal_state` 匹配。

---

## 3. 分支完整性守卫（PASS）

`scripts/check_phase3914_branch_integrity.py` 检查项：

1. 分支 = `feat/phase3.9.14-external-staging-runtime-deployment-e2e-qualification` ✅
2. git 视图无 forbidden 模块（production_handoff / handoff）✅
3. 无 3.9.15 路径残留 ✅
4. AuditActionCategory total = 129（本阶段 0 新增企业类目）✅

---

## 4. 自审套件（7/7）

`agents/external_staging_runtime/self_audit.run_self_audit()`：

- machine_package_fail_closed
- api_contract_readonly
- change_control_never_go
- isolation_no_production_leakage
- qualification_structural_only
- production_rollback_forbidden
- evidence_no_leakage

---

## 5. CI 门禁（6 jobs, fail-closed）

`.github/workflows/external-staging-runtime-e2e-qualification-gate.yml`：

| Job | 内容 |
|-----|------|
| branch-integrity-gate | 分支/模块/Phase 编号/审计漂移 |
| runtime-e2e-tests | `tests/agents/test_external_staging_runtime_e2e.py` |
| package-deterministic-validate | 确定性包生成 + `validate_package` |
| api-contract-validate | 7 只读端点契约基线 |
| credential-safety | 递归凭据深扫（无明文） |
| repo-clean | 无 forbidden / 无 3.9.15 |

`on:` 仅匹配本 Phase 分支 + `main` + `release/**`（不使用 `feat/phase3.9.*` 通配，避免与长兄门禁互触）。

---

## 6. 红线守约结论

- `engineering_enabled=false` 全程未改（config.yaml:102 未动）。
- 0 真实资源供给 / 0 真实部署 / 0 真实 E2E / 0 真实密钥 / Apply Gate 永不 GO。
- 旧 WIP「Production Handoff & Human Activation Ceremony」隔离于 stash，不吸收。
- 审计账本 total=129（0 新增企业类目）。
