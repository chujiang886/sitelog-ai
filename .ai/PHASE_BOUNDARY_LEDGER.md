# Phase Boundary Ledger（阶段边界台账）

> 本文件是 BOIP 各 Phase 边界的**唯一阶段记录（single phase-boundary record）**。
> 目的：杜绝"代码先跑到下一阶段、但阶段报告还停在上一阶段"的漂移。
> 真实状态以 **Git（commit hash）+ 实际测试 + 实际 SSOT 文件** 为准，不以分支名为准。
>
> 维护规则：
> 1. 每个 Phase 登记 branch / start / end / closure report / status / 主要能力 / 是否正式审核。
> 2. 任何新 Phase 必须从本台账登记，且不得在未审核时标 `APPROVED` / `GO` / `PRODUCTION_READY`。
> 3. `engineering_enabled` 在所有 Phase 中**恒为 false**，从未开启。

## 0. 当前冻结态（Phase 3.9.4-R2）

- 冻结分支：`feat/phase3.9.4-r2-definitive-baseline-freeze`
- 冻结 HEAD：`ab1f7cd`（本台账撰写时尚在增长；以 `git rev-parse HEAD` 为准）
- 状态：`PHASE_3_9_4_DEFINITIVE_BASELINE_FROZEN_BUILT_NO_GO`
- 含义：Git 事实唯一、测试事实唯一、Audit 事实唯一（JSON Ledger）、SSOT 唯一、工作树清洁、阶段边界明确、无未提交关键修复、无未来 Phase 污染、无报告与代码矛盾。
- 下一步：等待主理人 + 专家线下真实四角色（production-owner / release-manager / security-owner / auditor）签署，方可推进激活（开启 `engineering_enabled`）。

## 1. 阶段边界总表

| Phase | Branch | Start commit | End commit | Closure report | Status | 主要能力 | 正式审核 |
|-------|--------|--------------|-----------|----------------|--------|----------|----------|
| 3.8.27 | `feat/phase3.8.27-governance-infrastructure` | `7e2a585`（分支起点） | `7384b00` | `.ai/baselines/phase3.8_governance_release_baseline.json` | BUILT_NO_GO | 治理基础设施；`AuditActionCategory` 基线 69 确立（`4aa23fb`） | 否 |
| 3.8.29 | `feat/phase3.8.29-production-security` | — | `1377e8b` | `docs/PRODUCTION_DEPLOYMENT_GUIDE.md` | BUILT_NO_GO | 凭据 Cookie+CSRF、IdP 三态 fail-closed、APP_ENV 隔离、`assert_production_safe()`、7 红线静态扫描 | 否 |
| 3.9.0 | `feat/phase3.9.0-production-readiness-preparation` | — | `a538e1e` | （收口于 3.9.x 总报告） | BUILT_NO_GO | 受控激活准备骨架（只验证准备体系，不激活） | 否 |
| 3.9.1 | `feat/phase3.9.1-staging-validation-disaster-recovery-drill` | — | `66f9b57`（`+9a3dee1` T8 修复） | `phase3.9.1_staging_validation_disaster_recovery_report.md` | BUILT_NO_GO | 预生产验证 + DR 演练（合成）；审计 +4（75→79） | 否 |
| 3.9.2 | `feat/phase3.9.2-production-release-gate` | `ea57245` | `1f223db` | `phase3.9.2_production_release_gate_evidence_package_report.md`（24§） | BUILT_NO_GO（RC 候选冻结，未激活） | 生产发布闸门 + 证据包 + 清单；审计 +4（79→83） | 否 |
| 3.9.3 | `feat/phase3.9.3-production-observability-incident-readiness` | — | `8c7c9c5` | `phase3.9.3_production_observability_incident_readiness_report.md` | BUILT_NO_GO | 可观测性/SRE/事故响应准备（不真接入/不真告警）；审计 +13（83→96） | 否 |
| 3.9.4 | `feat/phase3.9.4-telemetry-synthetic-operations` | `9201a7d` | `a905213` | `phase3.9.4_telemetry_synthetic_operations_report.md`（36§） | BUILT_NO_GO | 生产遥测适配 + 合成运维验证；审计 +4（96→100） | 否 |
| 3.9.4-R1 | `fix/phase3.9.4-final-evidence-quality-closure`（意图分支） | — | 实际落点见下 | `phase3.9.4_r1_final_evidence_quality_closure_report.md` | CLOSED（交付物于 R2 提交） | 证据一致性与质量基线收口；Audit 溯源台账 + 校验器（R1 版）；JWT 修复 `e7952e9` 落 3.9.5 线 | 否 |
| 3.9.4-R2 | `feat/phase3.9.4-r2-definitive-baseline-freeze` | `4983e7b` | （本阶段 HEAD） | `phase3.9.4_r2_definitive_baseline_freeze_report.md`（本文件姊妹报告） | FROZEN_BUILT_NO_GO / AWAITING_HUMAN | 权威基线冻结：Audit JSON Ledger SSOT + build/validator、本台账、CI 三道新门禁、多 CWD 测试稳定、全量回归 | 否 |
| 3.9.5 | `feat/phase3.9.5-release-line-reconciliation` | `e0cae50` | `4983e7b` | `phase3.9.5_release_line_reconciliation_closure_report.md`（27§）+ `phase3.9.2_release_candidate_freeze_activation_gate_closure_report.md`（23§） | RELEASE_LINE_RECONCILED_RC_FROZEN_AWAITING_HUMAN | RC 冻结核心 + 受控激活闸门 + CI release gate + 回滚 runbook + SSOT/roadmap 对账（审计不变，仍 100） | 否 |

## 2. 3.9.5 资产审计结论（R2-6 / R2-7）

`feat/phase3.9.5-release-line-reconciliation` 相对 `feat/phase3.9.4-telemetry-synthetic-operations`（HEAD `a905213`）有 **6 个独有 commit**：

| hash | 内容 | 原始来源/语义 | 应属阶段 | 完整性 | 测试 |
|------|------|---------------|----------|--------|------|
| `e0cae50` | RC 冻结核心（release_candidate/freeze_manifest/freeze_checker/freeze_forbidden）+ rc-spec | 3.9.2 发布闸门遗留的 RC 冻结实现，延后至对账层完成 | 3.9.5（reconciliation） | 完整（570 行真实代码） | 随 3.9.5 套件 |
| `d82cade` | 受控激活闸门 + 人工批准契约 + 激活证据包 + 测试 | 同上，受控激活闸门（fail-closed） | 3.9.5 | 完整（818 行 + 测试） | test_enterprise_rc_freeze_activation_gate.py |
| `e7952e9` | JWT 缺失 secret fail-closed 双命名空间 patch | 即 3.9.4-R1 的 Problem A 修复 | 3.9.5（吸收 R1 修复） | 完整（11 行） | 已并入 agents 全量 2373/0 |
| `49c8c63` | service 编排 + ci_release_gate + release-gate.yml + rollback runbook | RC 冻结编排集成 + CI | 3.9.5 | 完整（658 行） | ci_release_gate / release-gate.yml |
| `833ee8d` | 3.9.5 收口报告（27§）+ RC freeze manifest + SSOT/roadmap 对账 | 收口 + 对账 | 3.9.5 | 完整 | — |
| `4983e7b` | 3.9.2 RC 冻结 & 激活闸门收口报告（23§） | 收口报告 | 3.9.5 | 完整 | — |

**判定**：3.9.5 是**完整阶段**（complete phase），不是 stub / WIP / 部分阶段。其 commit 主题虽写 "Phase 3.9.2 RC freeze"，但分支语义是 "release-line reconciliation"，实际功能 = 把 3.9.2 遗留的 RC 冻结 / 受控激活闸门实现、并加 CI / runbook / 对账，最终产出 27§ + 23§ 两份收口报告。**因此 R2 严禁重复开发 RC 冻结 / 受控激活闸门**——R2 工作（Audit Ledger SSOT、阶段边界台账、CI 三道新门禁、多 CWD 稳定、全量回归）与之正交。

## 3. 跨阶段集成 / cherry-pick 说明

- 3.9.5 的 `e0cae50`/`d82cade`/`49c8c63` 名义上标 "Phase 3.9.2"，实为 **3.9.2 遗留能力的延后实现**（deferred implementation），落点在 3.9.5 对账分支，非 cherry-pick、非重复开发。
- 3.9.4-R1 的 JWT 修复（`e7952e9`）已并入 3.9.5 线，其 CWD 独立性修复（service.py `root_dir` + 两测试）于本 R2（`3043eb4`）精确提交，二者不冲突。
- 所有 Phase 均未 push 到远程（本仓无 origin 强制要求），未 rewrite 历史，未 `git add -A`，未 `reset --hard`。

## 4. 红线与激活态

- `engineering_enabled = false`（agents/config.yaml:102，全 Phase 未改）。
- 无 `engineering_approved`、无真实部署 / 回滚 / 告警 / 数据写 / 密钥 / 授权、无 AI 责任替代。
- 仅主理人 + 专家线下四角色真实签署后，终端显式置 `engineering_enabled=true` 方可激活。

## 5. 与其他 SSOT 的关系

- `AuditActionCategory` 总数 = 100，机器可读 SSOT = `.ai/baselines/audit_action_category_ledger.json`（由 `scripts/build_audit_category_ledger.py` 从 Git 重建），人类可读镜像 = `.ai/AUDIT_ACTION_CATEGORY_LEDGER.md`。
- `project_status.json`：`phase_3_9_5_status = "RELEASE_LINE_RECONCILED_RC_FROZEN_AWAITING_HUMAN"`，与 roadmap §35.7、本台账一致。
- `roadmap_v8.md`：§35.1–§35.7 覆盖 3.9.0–3.9.5；§35.8（本 R2 增补）覆盖 3.9.4-R2。
- 所有 Phase 状态在以上四处一致，无 APPROVED/GO/PRODUCTION_READY 误标。
