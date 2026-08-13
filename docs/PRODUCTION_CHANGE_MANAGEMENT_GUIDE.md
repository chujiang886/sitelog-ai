# 生产变更管控层治理指南（Phase 3.9.7-change）

> 配套文档：部署方速览见 `PRODUCTION_DEPLOYMENT_GUIDE.md` §17；人工动作清单见 `PRODUCTION_CHANGE_HUMAN_CHECKLIST.md`；审计溯源 SSOT 见 `.ai/baselines/audit_action_category_ledger.json`。
> 本指南是 Phase 3.9.7-change「生产变更管控与受控激活编排层」的完整治理纪律。

---

## 0. 一句话定位

**本层只管控「变更如何被安全地提出、评审、模拟、登记、交接」，绝不执行变更本身。** 真实的生产变更（部署 / 迁移 / 回滚 / 激活）由用户在人类终端手工执行，四角色与主理人在线下签署，AI 不代行。

终端态（不可改写）：`PHASE_3_9_7_PRODUCTION_CHANGE_CONTROL_BUILT_NO_GO`

---

## 1. 为什么需要这一层

前序各阶段（3.8.29 安全基座 → 3.9.0 受控激活准备 → 3.9.2 发布闸门 → 3.9.4 遥测合成验证 → 3.9.6 激活证据准备 → 3.9.7 final-review 最终人工评审）已经把「能不能激活」收敛为 BUILT_NO_GO。但还缺一层：**当有一天真的要变更生产时，变更请求 / 计划 / 窗口 / 预检 / 中止 / 回滚 / 后验证 / 证据 / 模拟 这一整套管控平面**，必须在 AI 侧就 fail-closed，使 AI 既不能偷偷执行、也不能把「模拟」伪装成「真实」。

本层即这一平面。它与 final-review 正交（additive），共存于同一集成载体分支。

---

## 2. 范围与不变量

### 2.1 做

- 变更请求 / 计划 / 窗口 / 预检 / 检查点 / 中止策略 / 回滚引用 / 后验证 / 证据 的**只读装配 + 真实 USER 登记**。
- 受控变更模拟（`run_controlled_change_simulation`，纯静态推演，`is_simulation` 恒 True）。
- 失败场景只读评估（`evaluate_failure_scenarios`）。
- 受控变更包构建（`ControlledChangePackageBuilder`，`simulated_only` 恒 True）。
- 后端 API（27 路由：13 GET 只读 + 13 POST 真实 USER 登记 + `/signoff` + `/decision`）。
- 前端只读看板 `frontend/src/app/governance-change/page.tsx`（无 Deploy / Execute / Rollback Now 按钮）。
- 审计溯源：+13 个 `CHANGE_*` 类目（108 → 121）。

### 2.2 不做（红线）

1. **不执行**变更（`execute_change` / `apply_change` 被结构级禁名拦截）。
2. **不部署**（`deploy_production` 禁名）。
3. **不迁移**（`migrate_production` 禁名）。
4. **不回滚**（`rollback_production` 禁名）。
5. **不激活** `engineering_enabled`（保持 `false`；`safety_invariants_ok()` 为所有方法 fail-closed 前置）。
6. **不宣布 GO / APPROVED**（状态机无 `AUTO_*` / `AI_APPROVED`；不输出 `engineering_approved`）。
7. **不自动执行**（执行模式枚举无 `AI_AUTOMATIC`；`create_change_request` 断言 `execution_mode != AI_AUTOMATIC`）。
8. **不替代**四角色或主理人的人工责任（所有登记强制 `actor_kind="user"`）。
9. **不写**真实密钥 / 真实权限 / 真实生产数据。
10. **不提供**任何 `/execute` / `/deploy` / `/rollback` / `/apply` / `/migrate` / `/activate` 端点。

---

## 3. 架构（19 模块）

```
agents/enterprise/production_change/
├── forbidden.py            # 结构级禁名主干（_PRODUCTION_CHANGE_FORBIDDEN，388 项）
├── models.py               # ChangeExecutionMode / ChangeState / ControlledChangePackage 等 frozen 模型
├── permission_boundary.py  # ChangeOperation 白名单（15）+ require_change_operation（USER-only, RELEASE_READ/SIGNOFF 复用）
├── change_request.py       # create_change_request（断言非 AI_AUTOMATIC）/ mark_awaiting_human_review
├── plan.py                 # build_change_plan
├── window.py               # reserve_change_window
├── preflight.py            # evaluate_change_preflight（永不返回 APPROVED）
├── checkpoint.py           # record_change_checkpoint
├── abort_policy.py         # build_change_abort_policy（human_abort_required=True）
├── rollback_reference.py   # build_change_rollback_reference
├── post_change.py          # register_post_change_verification
├── evidence.py             # build_change_evidence / build_change_evidence_chain
├── simulation.py           # run_controlled_change_simulation（仅静态推演，绝不真实变更）
├── failure_scenarios.py    # evaluate_failure_scenarios（只读）
├── package.py              # ControlledChangePackageBuilder（simulated_only 恒 True）
├── service.py              # ProductionChangeControlService（_RedLineForbiddenMixin，__init__ 断言 safety_invariants_ok）
├── validator.py            # check_change_control_invariants（5 项校验）
├── api_contract.py         # build_api_contract（27 present / 8 absent）+ write_api_contract_json
└── __init__.py             # 统一导出
```

后端路由：`backend/app/api/governance_change.py`（`prefix=/governance/change`，CSRF 保护依赖），在 `api/__init__.py` + `main.py` 注册。

---

## 4. fail-closed 三件套

1. **结构级禁名（`_RedLineForbiddenMixin.__getattr__`）**：任何被禁方法名（`execute_change` / `deploy_production` / `rollback_production` / `apply_change` / `migrate_production` / `auto_execute_change` / `declare_change_go` / `flip_engineering_for_change` / `bypass_change_gate` / `promote_simulation_to_production` …）在属性访问时即抛 `EnterpriseRedLineViolationError`，使结构不可达。
2. **权限边界（`require_change_operation`）**：先 `safety_invariants_ok()` → `actor_kind=="user"` → 白名单 → 权限；违例抛 `ChangePermissionBoundaryError`（HTTP 403）。cross-org 一律拒。
3. **状态机不可达自动态**：`ChangeState` 仅 `HUMAN_DRAFTED / AWAITING_HUMAN_REVIEW / HUMAN_COMPLETED / HUMAN_ABORTED`；`ChangeExecutionMode` 仅 `HUMAN_MANUAL / EXTERNAL_CONTROLLED_SYSTEM`。

`PRODUCTION_CHANGE_FORBIDDEN_COUNT = 388`（全链路禁名并集，含变更管控 34 项增量）。

---

## 5. API 契约

**27 条存在路由（prefix `/governance/change`）**

| 类别 | 方法 + 路径 | 说明 |
|---|---|---|
| 只读 GET（13） | `/readiness` `/contract` `/plan` `/window` `/preflight` `/checkpoint` `/abort-policy` `/rollback-reference` `/post-verification` `/evidence` `/simulation` `/failure-scenarios` `/package` `/decision-ledger` | 返回 `engineering_enabled=False`；纯展示 |
| 真实 USER 登记 POST（13） | `/change-request` `/plan` `/window` `/preflight` `/checkpoint` `/abort-policy` `/rollback-reference` `/post-verification` `/evidence` `/simulation` `/failure-scenarios` `/package` `/decision-ledger` | 强制 `actor_kind="user"`，复用 `RELEASE_READ` |
| 真人签署（2） | `/signoff` `/decision` | 须 `RELEASE_SIGNOFF`，仅 admin，非空 `signature_reference` |

**8 条明确不存在的「真实执行」路由**（禁名 + 路由双重保障）：

`/execute` `/deploy` `/rollback` `/apply` `/migrate` `/activate` `/trigger-go` `/auto-execute`

契约基线：`.ai/baselines/production_change_api_contract.json`（由 `api_contract.write_api_contract_json()` 生成，门禁脚本交叉校验）。

---

## 6. 审计溯源（108 → 121）

`audit.py` 新增 13 个 `CHANGE_*` 枚举成员 + 13 个 `record_change_*` / `record_*` 方法（强制 `actor_kind=AuditActorKind.USER`），基线 108 → 121。

新增类目：
`CHANGE_REQUEST_CREATED` · `CHANGE_PLAN_REGISTERED` · `CHANGE_WINDOW_RESERVED` · `CHANGE_PREFLIGHT_CHECKED` · `CHANGE_CHECKPOINT_RECORDED` · `CHANGE_ABORT_POLICY_REGISTERED` · `CHANGE_ROLLBACK_REFERENCE_REGISTERED` · `CHANGE_POST_VERIFICATION_REGISTERED` · `CHANGE_EVIDENCE_SUBMITTED` · `CHANGE_SIMULATION_PERFORMED` · `CHANGE_FAILURE_SCENARIO_EVALUATED` · `CHANGE_PACKAGE_GENERATED` · `CHANGE_HUMAN_DECISION_RECORDED`

SSOT 链：`Git 真实历史 → .ai/baselines/audit_action_category_ledger.json (total=121) → scripts/audit_category_ledger_validator.py (校验 Git↔JSON↔Enum) → .ai/AUDIT_ACTION_CATEGORY_LEDGER.md`。ledger 构建器 `scripts/build_audit_category_ledger.py` 在 PHASES 加 `("3.9.7-change", "7ad04ab", False)` 行后重建。

---

## 7. 人工动作入口（唯一合法出口）

- 只读看板拉取 13 个 GET 端点，了解变更管控平面现状。
- 真实人工登记 / 签署：`POST /governance/change/signoff`、`POST /governance/change/decision`（须真人 + 权限）。
- **真变更执行**：用户在人类终端手工执行；主理人在人类终端显式置 `engineering_enabled=true`。详见 `PRODUCTION_CHANGE_HUMAN_CHECKLIST.md`。

---

## 8. 门禁与测试

- **门禁脚本**：`scripts/check_production_change_control_gate.py` —— 断言 `engineering_enabled=false`、无真实执行端点（8 absent vs 27 present）、无 `AUTO_*` 态、审计类目一致（live=ledger）、契约 JSON 与代码一致。CI 可接入。
- **红线测试**：`tests/agents/test_phase3_9_7_production_change_control.py`（10 例）—— 禁名不可达、态机无 AI 自动、权限 403 / cross-org 阻断、路由数（无 execute/deploy/rollback）、审计 `CHANGE_*` 类目齐全、包 `simulated_only`、模拟非真实。

---

## 9. 验证结果（收口基线）

| 项目 | 结果 |
|---|---|
| agents 全量 | 2449 passed |
| backend pytest | 374 passed |
| frontend jest | 117 passed |
| frontend tsc | 0 error |
| 治理完整性 | 9/9 |
| 生产安全 lint | 7/7 |
| 审计账本校验 | PASS（total=121，0 orphan/0 ghost/0 dup，Git provenance 全 10 阶段） |
| 硬编码扫描 | 0 命中 |
| 变更管控门禁 | PASS |
| 红线测试 | 10 passed |

---

## 10. 收口状态与 STOP

本层状态 **PRODUCTION_CHANGE_CONTROL_BUILT_NO_GO**：生产变更管控平面已建成并通过红线验证，但**无真实生产变更执行**。

**已 STOP**：不进入 3.9.8、不自动激活、不真实执行/部署/回滚/迁移变更、不输出 `engineering_approved`、不 AI 生成 GO、不代替四角色签署。等主理人 + 四角色线下执行真实变更并签署后，由主理人在人类终端显式置 `engineering_enabled=true`。

收口报告：`.ai/reviews/phase3.9.7_production_change_control_report.md`
