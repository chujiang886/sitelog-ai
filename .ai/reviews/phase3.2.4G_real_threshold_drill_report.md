# BOIP Phase 3.2 Sprint 3.2.4-G 完成报告：首批真实阈值录入演练（E-TH-01~03）

- **阶段**：Phase 3.2 Sprint 3.2.4-G
- **身份**：BOIP AI 工程治理负责人
- **日期**：2026-07-31
- **状态**：✅ DONE（设计+能力+演练通过；零真实数据写入生产 verified.json）

---

## 0. 摘要

本阶段在 3.2.4-F 录入工作流基础上，新增**录入演练编排层**（drill），以真实资料驱动的方式完整跑通 E-TH-01、E-TH-02、E-TH-03 的「提交 → 主理人审核 → 专家复核 → 转正」四步闭环，并逐项生成 source_ref 验证报告、确认 review_log 审核链完整、确认 G1-G6 门禁在阈值转正后**仍拒绝**开启 `engineering_enabled`。

**最高安全级别全程守约**：AI 仅做格式校验与流程编排；真实工程数值、签字人身份、source_ref 均由人工在调用时显式提供（测试中一律以 `value=None` 占位，不代表任何真实规范值）。未开启 `engineering_enabled`、未输出 `engineering_approved`、未以真实数据写入生产签字库。

---

## 1. 任务1：真实资料录入演练（threshold intake session）

新增 `agents/engineering/threshold_intake.py`：

- `run_intake_drill(*, verified_path, review_log_path, snapshot_dir, request, verified_by, verified_at, expert_verified_by, expert_verified_at) -> IntakeDrillResult`
  - 编排顺序：**授权边界 → source_ref 验证报告 → submit → review → expert_recheck → finalize_verified → G1-G6 门禁检查**；
  - 任一步骤不满足即中止并返回对应结论（不进入后续步骤、不入库）；
  - 返回结构化结果（`IntakeDrillResult`）：`authorized / source_report / steps / verified / review_event_id / gate_allowed / gate_reasons / engineering_enabled / verification_status`，全部可 `as_dict()` 序列化供审计。

授权边界（红线）：仅 `E-TH-01 / E-TH-02 / E-TH-03` 可演练；`D-TH-01~05`、`E-TH-04~06` 一律拒绝，不进入任何后续步骤。

---

## 2. 任务2：审核链演练（review_log）

每次演练每步均经 `append_review_event` 落 `review_log.jsonl`，事件链为：

| 序号 | action | signer_role | 说明 |
|------|--------|-------------|------|
| 1 | `intake_submit` | submitter | 提交草稿态（threshold_status=review） |
| 2 | `intake_review_approve` | principal | 主理人核准（写入 verified_by/at） |
| 3 | `intake_expert_recheck` | expert | 专家复核签字（写入 expert_verified_by/at） |
| 4 | `intake_verified` | system/workflow | 双签齐全转正（verified=true） |

每事件含 `event_id`（内容哈希，确定性）、`prev_event_id`（链式指针）、`sign_off_id` 派生位；拒绝事件记录 `intake_rejected` 并附原因，append-only 不可篡改。测试 `test_drill_review_log_chain_intact` 校验四步有序、`prev_event_id` 链式衔接、`event_id` 重算一致。

---

## 3. 任务3：source_ref 审计（验证报告）

新增 `build_source_verification_report(raw_source_ref) -> SourceVerificationReport`：逐条 C1-C6 校验并产出报告（与 `validate_source_ref` 共用同一组规则常量，保证报告与准入判定一致）。

| 检查项 | 含义 | 判定 |
|--------|------|------|
| C1 | 标准号完整（standard） | 非空且非占位 |
| C2 | 条款号完整（clause） | 非空且非占位 |
| C3 | 版本合规（edition） | 4 位年份或显式版本 |
| C4 | 链接可达（url） | http(s) 可复核 |
| C5 | 内容哈希（hash） | 64 位 sha256 摘要 |
| C6 | 引用完整性（C1+C2） | `is_complete()` 语义 |

**样例验证报告**（测试夹具，结构合法占位，非真实规范）：

```
threshold_id : E-TH-01
overall      : 通过
C1 标准号完整  : ok  -> GB 50009
C2 条款号完整  : ok  -> 8.1.1
C3 版本合规    : ok  -> 2012
C4 链接可达    : ok  -> https://example.org/canonical-reference
C5 内容哈希    : ok  -> <sha256 前8位>…
C6 引用完整性  : ok
```

任一 C 不满足即 `passed=False`，演练拒绝进入审核（测试 `test_drill_rejects_invalid_source_ref`、`test_source_verification_report_each_c_failure` 覆盖各项失败）。

---

## 4. 任务4：G1-G6 检查（engineering_enabled 保持 false）

演练在双签转正后调用 `evaluate_gates()`（委托 `can_enable_engineering`），并**强制返回 `(False, reasons)`**：即便 E-TH-01~03 全部 verified=true，门禁仍以 `ci_green=False / rollback_ready=False / authorization_present=False` 入参，确认 G1-G6 默认拒绝、绝不翻转 `engineering_enabled`、绝不写 config.yaml。

测试结果（`test_drill_enabled_false_protection`）：
- `run_intake_drill(...).engineering_enabled == False`；
- `load_engineering_enabled() == False`；
- `ExpertBackedEngineeringValidation(engineering_enabled=False, ...).validate(interface="wind_pressure", ...)` 返回 `verification_status="pending_verification"`、`sign_off_id=None`。

结论：**阈值转真 ≠ 工程批准**。灰度闸门在单独书面授权 + G1-G6 全绿前，恒保持关闭。

---

## 5. 任务5：测试

新增 `tests/agents/test_threshold_real_drill.py`（9 用例），覆盖任务书六要点 + 边界：

1. 真实资料录入流程（合法演练全四步、`verified=true`、步骤链完整）；
2. source_ref 验证（合法通过 / 逐项 C 失败 / 演练拒绝不入库）；
3. 双签（主理人核准 + 专家复核两套签字位）；
4. review_log 链（四步有序、`prev_event_id` 链式、event_id 确定性）；
5. SoD（专家==主理人 → 演练中止于 expert_recheck）；
6. enabled 保护（`gate_allowed=False`、`engineering_enabled=False`、校验器 pending）；
- 附加：授权越界拒绝（D-TH-01 / E-TH-04）、最终转正拒绝防御分支（fixture）。

`bash scripts/ci/local_ci.sh`：**8/8 PASS**，435 passed，**Total coverage 89.21%**（≥89.10% 达标，由 89.10% → 89.21%）。Ruff 全绿；前端 Jest 29 passed；Alembic/Seed 通过；**防编造扫描 0 命中；硬编码扫描 0 命中**。

---

## 6. 红线守约确认

- ✅ 未自动生成工程参数（测试 `value` 一律 `None` 占位，AI 不编造）；
- ✅ 未猜测/补充缺失参数（source_ref 不完整即拒绝）；
- ✅ 未修改专家签署（signer 仅接受人工显式提供，AI 不篡改）；
- ✅ 未自动补 source_ref（报告仅校验，不回填）；
- ✅ 授权范围严格：仅 E-TH-01~03，D-TH / E-TH-04~06 拒绝；
- ✅ 未开启 `engineering_enabled`（演练 + 校验器双确认恒 False）；
- ✅ 未输出 `engineering_approved`（全程 `pending_verification`）；
- ✅ 未以真实数据写入生产 `verified.json`（演练产物落临时文件，生产库零改动）。

---

## 7. SSOT / Roadmap

- `.ai/project_status.json`：新增 `3.2.4-G` 条目，`_phase_status=SPRINT_3_2_4G_DONE`；`phase_3_2` 信封同步刷新。
- `.ai/roadmap_v2.md`：第 92 行 3.2 里程碑追加 3.2.4-G DONE。

---

## 8. 待主理人定夺 / 下一步

- 本阶段为**演练**（drill），未以真实工程数据执行录入；真实录入须由人工调用 `ThresholdIntakeWorkflow` / `run_intake_drill` 显式提供真实 value/unit/source_ref/签字人。
- 进入 3.2.5 实施（开启 `engineering_enabled` 灰度）前，仍须满足：G1-G6 全绿 + 单独书面授权（SoD：真实化授权与 enabled 授权分离）。
- 待定：D-TH 双签最终采纳方案（A/B）、source_ref.hash 算法、首个真实化范围（建议即 E-TH-01、E-TH-02、E-TH-03 三类阈值，对应首个灰度接口风压分析，pending_verification）。

**本阶段已停止。未开启 engineering_enabled、未输出 engineering_approved、未以真实数据写入生产库。**
