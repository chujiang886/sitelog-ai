# BOIP Phase 3.2 Sprint 3.2.5-G2 — Production Readiness Remediation 报告

- **身份**：BOIP AI Release Governance 负责人
- **阶段**：首次工程灰度（风压 wind_pressure 接口）生产条件修复（pending_verification）
- **状态**：✅ `PRODUCTION_READINESS_REMEDIATION_DONE` — 已停止（按指令「完成后停止」）
- **最高红线**：未开启 `engineering_enabled` / 未输出 `engineering_approved` / 未生成真实工程参数 / 未猜测规范值 / 未伪造专家签名 / 未修改真实 `verified.json`（pending_verification）

---

## 一、问题回顾与本阶段修复项

Pre-flight（3.2.5-G1）结论：系统能力就绪，但**生产条件不足**，G1 / G2 / G4（空链真空通过）/ G6 未满足。本阶段修复治理缺口：

| 任务 | 修复内容 | 落点 |
|---|---|---|
| 任务1 G4 增强 | `required_audit_events(interface)` + 空 review_log 不再真空通过 | `enable_gate.py` / `can_enable_engineering` |
| 任务2 统一检查器 | `ProductionReadinessChecker` + `ProductionReadinessReport` | `release/production_checker.py`（新增） |
| 任务3 统一 Pre-flight 输出 | `release_precheck(return_report=True)` 经检查器生成统一 JSON 报告 | `release/gate.py` |
| 任务4 防绕过 | `manual_modified_thresholds`（别名 `check_verified_integrity`）检测绕过 `ThresholdIntakeWorkflow` 直改 `verified.json` | `release/readiness.py` |

> 风压 wind_pressure 接口的真实工程参数（E-TH-01 至 E-TH-03）仍须人工提供（pending_verification）。

---

## 二、G1-G6 最终状态（真实态快照，release_precheck 实测）

接口 `wind_pressure` 于真实生产态（review_log 空 / 无授权 / verified.json 全 draft）下实测：

| 门禁 | 状态 | 原因 |
|---|---|---|
| G1 阈值治理 | ❌ 失败 | `threshold_status` 非 verified（draft/review），不纳入工程判定 |
| G2 双签 | ❌ 失败 | E-TH-01 至 E-TH-03 双签（`verified_by` / `expert_verified_by`）均为 null |
| G3 CI | ❌ 失败 | `ci_green` 注入 False（未确认全绿） |
| G4 审核链 | ❌ 失败 | review_log 为空，缺 `intake_submit` / `intake_review_approve` / `intake_expert_recheck` / `intake_verified` |
| G5 回滚就绪 | ❌ 失败 | `rollback_ready` 注入 False（未确认就绪） |
| G6 授权 | ❌ 失败 | `EngineeringReleaseApproval` 未签署（approval 库 count=0） |
| verified_integrity | ✅ 通过 | 全 draft / `value=null`，无绕过（pending_verification） |

**结论**：`allowed=false`，6 道门禁全阻断；`verified_integrity` 通过（无绕过）。E-TH-01 至 E-TH-03 的 `realized` 均为 false（缺 value / source_ref / version / dual_sign）（pending_verification）。

---

## 三、任务映射与交付物

- **任务1**：`required_audit_events("wind_pressure")` 返回四类必需事件；`can_enable_engineering` 现对空链 / 缺失类 / 断裂链均判 G4 失败（修复真空通过）。
- **任务2**：新增 `agents/engineering/release/production_checker.py`，含 `ProductionReadinessReport`（字段 `passed` / `failed` / `blocking_reasons` / `gate_status` / `details`）与 `ProductionReadinessChecker.run()`，统一聚合 G1-G6 + E-TH 真实化 + 审核链 + 授权在场 + 绕过检测。
- **任务3**：`release_precheck(..., return_report=True)` 经 `ProductionReadinessChecker` 生成统一 JSON 报告；默认仍返回 `(allowed, reasons)` 兼容 controller / `production_readiness`。
- **任务4**：`manual_modified_thresholds` 检测绕过工作流直改 `verified.json`（填实条目须有完整 intake 链，否则 `bypassed_ids` 报告并阻断放行）；`check_verified_integrity` 保留为别名。
- **任务5**：新增测试覆盖 — 空 review_log 拒绝 G4 / 缺 audit event 拒绝 / ProductionChecker 输出 / G1-G6 状态报告 / verified.json 绕过检测 / `engineering_enabled=false` 保护。

---

## 四、CI 与扫描结果

- **local_ci 8/8 PASS**：agents **481 passed @ 90%**（≥89.21% 达标），frontend 29 passed @ 93.15%，ruff `All checks passed!`。
- **防编造扫描**：0 命中（全仓含本报告与 SSOT）。
- **硬编码扫描**：0 命中。
- 新增文件 `production_checker.py` 与改动均通过覆盖率与 lint。

---

## 五、风险

- **RT-G2-1（技术）**：统一检查器新增依赖 `production_checker → readiness → gate` 链路，已用 `return_report=False` 默认路径保持 controller 兼容，回归测试覆盖。
- **RE-G2-1（工程）**：E-TH-01 至 E-TH-03 仍未真实化，风压 wind_pressure 真实判定不可用，**严禁**在未真实化前以任何方式引用为工程结论（pending_verification）。
- **RE-G2-2（工程）**：`engineering_enabled` 仍 False，真实放量硬阻塞于主理人 G6 书面授权 + 真实化 + CI 绿 + 显式 `gray_release_ctl.py enable wind_pressure`。
- **RL-G2-1（法律/合规）**：绕过检测仅作技术拦截；真实签字与规范引用仍须主理人 / 专家线下责任确认，AI 不代签。

---

## 六、红线合规

- ❌ 未开启 `engineering_enabled`（实测 `load_engineering_enabled() is False`，核验过程零翻转）。
- ❌ 未输出 `engineering_approved`。
- ❌ 未修改真实 `verified.json`（`value` 仍 null，仅读取）。
- ❌ 未生成/猜测真实工程参数（E-TH 仍为 draft/pending_verification）。
- ❌ 未伪造专家签名（双签仍 null）。
- ✅ 全部 `pending_verification`。

---

## 七、是否具备进入真实灰度（G2 放量）条件

**结论：不具备。** 当前 G1 / G2 / G3 / G4 / G5 / G6 全阻断，仅 `verified_integrity` 通过。

进入真实放量的闭环（须**全部**满足，且 AI 不代行）：
1. 主理人**单独书面**签署 `EngineeringReleaseApproval`（G6，SoD 独立于 3.2.4 双签主体）；
2. 人工以真实数据录入 **E-TH-01 至 E-TH-03**（双签齐全、`verified=true`、结构化 `source_ref` + 真实 intake 审核链，满足 G1 / G2 / G4）；
3. 发布负责人确认 **CI 全绿**（G3）；
4. 确认 **回滚就绪**（G5）；
5. 显式 `scripts/release/gray_release_ctl.py enable wind_pressure`（脚本校验 快照 + 授权 + G1-G6）；
6. 主理人于 config 显式置 `engineering_enabled=true`（独立于 enable，且须经 G6）。

---

## 八、SSOT / Roadmap

- `.ai/project_status.json`：`phase_3_2._phase_status=SPRINT_3_2_5G2_DONE`，`_readiness_report` 指向本报告，新增 `3.2.5-G2` 条目（JSON 校验通过）。
- `.ai/roadmap_v2.md`：里程碑追加 3.2.5-G2 DONE。

---

## 九、下一步

等待主理人审核与 G6 单独书面授权；授权后由人工真实化 E-TH-01 至 E-TH-03 → 确认 CI 绿 → 显式置 `engineering_enabled=true`（经 G6）→ `gray_release_ctl.py enable wind_pressure`。本阶段已停止（pending_verification）。
