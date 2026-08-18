# Phase 3.9.15 — External Staging Real Resource Onboarding & Live Qualification

> 阶段状态记录（single-phase record）。真实状态以 **Git commit + 实际测试 + 实际 SSOT** 为准。
> 终端态：`PHASE_3_9_15_EXTERNAL_STAGING_REAL_RESOURCE_LIVE_QUALIFICATION_BUILT_NO_GO`
> `engineering_enabled = false`（agents/config.yaml:102，全阶段未改）。
> 真实外部 Staging 资源：**0 / 8**（缺真实人工输入 + 双钥匙 + 连通性/隔离/运行时真实验证）。

## 1. 当前进度（本 turn 收口范围）

在既有 `agents/external_staging_live/`（T0/T2/T3/T4 provider acquisition + 状态机/聚合/包/校验器/
apply gate/plan safety）基础上，本 turn 补齐 **3.9.15 上层真实能力**：

| Task | 交付物 | 状态 |
|------|--------|------|
| #402 | 修正 `provider_acquisition.build_report` verdict 诚实性 | ✅ |
| #403 | `live_resource_onboarding.py` 证据门控 8 资源驱动（reuse 状态机/聚合） | ✅ |
| #404 | `human_authorization.py` 双钥匙封装（reuse 3.9.14，pin 3.9.15 终端态） | ✅ |
| #405 | `orchestrator.py` 全量证据装配 + 防伪造包构建/校验 | ✅ |
| #406 | `__init__` 导出 + 10 新增测试 + `check_phase3915_branch_integrity.py` | ✅ |
| #407 | 真实运行 orchestrator 一次，persist 证据 JSON | ✅（见 §5） |

未重造框架：Runtime Gate / Resource Registry / Human Authorization / Deployment Provider /
Isolation Guard 全部复用 `agents/staging_runtime/` 与 `agents/external_staging_runtime/`（3.9.14）。

## 2. #402 Provider-Init 报告诚实性修正

`provider_acquisition.build_report` 原在 `terraform init` rc=0 后**无条件**置
`verdict = "PROVIDER_ACQUIRED_LIVE_INIT_VALIDATE_PLAN_OK"`，即便 `validate`/`plan` 实际失败
（真实 IaC 配置缺陷会在此以 rc=1 暴露）。已改为按真实结果诚实区分：

- init + validate + plan 全 PASS → `PROVIDER_ACQUIRED_LIVE_INIT_VALIDATE_PLAN_OK`
- init OK，validate / plan 失败 → `PROVIDER_ACQUIRED_INIT_ONLY_VALIDATE_PLAN_FAILED`
- init OK + validate OK，plan 失败 → `PROVIDER_ACQUIRED_INIT_VALIDATE_OK_PLAN_FAILED`
- init 失败 → 保持 `classify_init` 的 `BINARY_EGRESS_BLOCKED` / `BINARY_EGRESS_INTERMITTENT` / 等

`real_apply_allowed` 恒 `False`（不变）。新增 3 个测试覆盖上述分支（monkeypatch 工具链 + init/validate/plan）。

## 3. #403 Live Resource Onboarding Driver

`live_resource_onboarding.py`：

- `ResourceOnboardingEvidence`：14 个真实证据旗标，全默认 `False`（诚实 no-forgery）。
- `advance_resource(machine, evidence)`：沿规范化 15+4 状态图逐步推进，**仅当对应证据旗标为 True**
  才转移；缺证据即停在当前态并记录 blocker（绝不跳过/伪造）。
- `ResourceOnboardingDriver`：驱动全部 8 资源；`drive_all` 默认注入空证据 → 8 资源全 PENDING、0/8、
  每资源带 blocker（"missing evidence: …"）。
- 纯复用 `ResourceLiveStateMachine`（邻接转移 + `can_transition` 防非法跳）与 `PartialAggregator`。

## 4. #404 Human Authorization Registry

`human_authorization.py`（reuse 3.9.14 双钥匙基类，fail-closed）：

- `generate_machine_safety_key()`：机器可生成（仅证系统侧安全前置）。
- `wrap_human_authorization_key(key)`：仅接受**真实 USER 已 mint** 的钥匙；基类 `__post_init__`
  已强制 `actor_kind=="USER"` 且 `require_human_actor(USER)` → **AI 物理上无法 mint**。
- `make_dual_key(machine_key, human_key=None)`：组装双钥匙（默认无 human key）。
- `evaluate_live_change_control(auth)`：复用 3.9.14 逻辑（real_apply_allowed=False /
  is_go_or_approved=False / is_production=False），仅将 `terminal_state` 钉到 3.9.15 BUILT_NO_GO。

## 5. #405 Live Qualification Orchestrator

`orchestrator.py`：`build_live_qualification_report(live, acquisition_report, …)` 装配：

1. T2/T3/T4/T5 provider acquisition（注入 report 或 `build_report(live=…)`）
2. T13–T24 8 资源实时入职（默认空证据 → 0/8）
3. 9 隔离维（默认 `NOT_VERIFIED`）
4. 13 运行时实时检查（默认 `NOT_EXECUTED`）
5. T8 plan safety（只读扫描 `infrastructure/staging/*.tf`）
6. 双钥匙 + apply gate + change control（无 human key → PENDING）
7. `build_live_package` + `validate_package`（防伪造：hash 一致 / 终端态合法 / 无密钥泄漏 /
   count 一致 / 8/8 须真实 deploy+E2E / init 非 PASS 不得有合格资源）

**真实运行一次（#407）证据**（2026-08-18T09:41:47Z，sandbox，`live=True`，terraform 工具链可用
于 `/Users/chujiangai/.workbuddy/binaries/iac/bin/terraform`；报告 JSON 落
`.ai/progress/phase3.9.15_live_qualification_report.json`）：

- `terraform init`：**rc=0 PASS**（provider `tencentcloudstack/tencentcloud v1.83.23` 从 lock file
  初始化成功）→ 证实 2026-08-17 的 provider-binary egress 黑洞根因**已解除**（环境已开放），
  init 不再受阻。
- `terraform validate`：**rc=1 FAIL** —— **真实 IaC 配置缺陷**（非环境/非 egress，属 committed
  `infrastructure/staging/*.tf` 的代码缺陷，**Track B 人工整改项，AI 不代修**）：
  - `deployment_target.tf:9` `tencentcloud_kubernetes_cluster.staging`：不支持参数 `subnet_ids`
  - `deployment_target.tf:14` `tencentcloud_tcr_instance.staging`：缺少必填 `instance_type` / `name`
  - `deployment_target.tf:16`：`instance_name` 非预期（应为 `name`）
  - `object_storage.tf:13`：`Invalid resource type`
- `terraform plan`：**rc=1**（因 validate 失败未进入 plan 实质执行，同源配置错误）
- **verdict = `PROVIDER_ACQUIRED_INIT_ONLY_VALIDATE_PLAN_FAILED`**（#402 诚实修正生效：init PASS 但
  validate/plan FAIL，绝不谎报 `_OK`）
- `provider_init_result = PASS`（仅 init 层级；validate/plan 失败 → 无合格资源）
- 真实资源 = **0 / 8**（每资源 blocker："missing evidence: acquisition_locked …"）
- 隔离 = 9 × `NOT_VERIFIED`；运行时 = 13 × `NOT_EXECUTED`
- plan_safety = `SAFE`（0 HIGH findings，committed IaC 静态扫描无硬编码密钥/公开库/0.0.0.0/销毁操作）
- change_control = PENDING_HUMAN_AUTHORIZATION / real_apply_allowed=False / 终端态 BUILT_NO_GO
- apply_gate = PENDING_HUMAN_AUTHORIZATION / is_go_or_approved=False / is_production=False
- package 校验 = **valid=True**（诚实 0/8，hash 一致，无伪造）

> 结论：Provider Acquisition 主线 **T0→T2→T3→T5 init** 已真实跑通（init PASS）；**T6 validate /
> T7 plan** 因真实 IaC 配置缺陷失败，已诚实记录为 Track B 人工整改项（不伪造 PASS、不 AI 代修
> `.tf`）。真实资源仍 0/8，终端态 BUILT_NO_GO，STOP 等待主理人线下动作（见 §9）。

## 6. #406 接线 + 测试 + 分支完整性

- `__init__.py` 导出：`ResourceOnboardingDriver` / `ResourceOnboardingEvidence` / `advance_resource` /
  `evaluate_live_change_control` / `generate_machine_safety_key` / `make_dual_key` /
  `wrap_human_authorization_key` / `LiveQualificationReport` / `build_live_qualification_report`。
- 新增 `tests/agents/test_external_staging_live_orchestrator.py`（10 测试）：#402 verdict 诚实性（3）+
  onboarding 默认 0/8 与 happy-path 结构推进（3）+ human auth 机器钥匙可生成/AI 不可 mint/无 human key
  即 PENDING（3）+ orchestrator 0/8 + 包校验通过 + BUILT_NO_GO（2）。
- 新增 `scripts/check_phase3915_branch_integrity.py`（mirror 3.9.14，分支=3.9.15、下一 Phase=3.9.16、
  Audit total=129）。直接运行 PASS（exit 0）。

## 7. 测试基线（本 turn）

- `tests/agents/test_external_staging_live.py`：**16 passed**
- `tests/agents/test_external_staging_live_orchestrator.py`：**10 passed**
- `tests/agents` 全量回归：**2838 passed / 0 failed**（含 branch integrity 3.9.15 PASS）

## 8. fail-closed 不变量（全程守约）

- 真实资源 0/8 如实上报，无伪造；`real_apply_allowed` 恒 False。
- 双钥匙：Human Authorization Key 须 `actor_kind=USER`，AI 不得 mint。
- 终端态含 `BUILT_NO_GO`，无 `GO`/`APPROVED`/`PRODUCTION_READY`。
- `engineering_enabled=false` 未改；不进 Production / Handoff / 3.9.16。
- Provider acquisition 环境黑洞 → 明确 `BLOCKED`，不伪造 PASS。

## 9. STOP — 待主理人线下动作

本 turn 收口后 **STOP**，等待轩哥 + 四角色（production-owner / release-manager / security-owner /
auditor）线下：
1. 提供真实 External Staging 资源（账号/密钥/连通性/隔离真实验证）；
2. 真实 USER 双钥匙签署（Human Authorization Key 须 USER mint，AI 不代）；
3. 真实 `terraform init/validate/plan` 在 egress-enabled 环境跑通（Track B）；
4. 主理人在人类终端显式置 `engineering_enabled=true`（唯一 AI 不代执行之动作）。

未 push、未进 3.9.16、未改 `engineering_enabled`、未做任何真实 Production 动作。
