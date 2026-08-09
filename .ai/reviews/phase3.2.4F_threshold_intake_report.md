# BOIP Phase 3.2 Sprint 3.2.4-F — 首批工程阈值录入流程实施就绪报告

**身份**：BOIP AI 工程治理负责人
**日期**：2026-07-31
**性质**：首批真实工程阈值录入流程（授权范围 E-TH-01、E-TH-02、E-TH-03，对应首个灰度接口风压分析）的「录入工作流工具」落地。**最高安全级别**：本阶段工具已具备、真实数据录入机制就绪，但 AI **不**自行生成/猜测/补充真实工程参数、不修改专家签署信息；真实数值须由人工在调用时显式提供。本阶段**不开启** engineering_enabled、**不输出** engineering_approved，全部保持 pending_verification。

---

## 0. 目标达成

把 3.2.4-D 实施方案的「真实录入流程（专家提供 → 主理人审核 → 专家复核 → verified）」与 3.2.5-C 的「审核闭环 + 双签 + 审计链」从设计落地为可执行的录入工作流代码与测试，使首批 E-TH-01~03 具备：提交校验、主理人核准、专家复核、双签转正、每步落 review_log、G1-G6 门禁检查且闸门保持关闭的完整能力。

---

## 1. 任务交付（对应任务1~5）

### 任务1：真实录入流程工具（新增 `agents/engineering/threshold_intake.py`）
- `IntakeRequest`：人工提交请求（threshold_id / value / unit / source_ref / version / param / submitted_by），数据须人工提供；
- `ThresholdIntakeWorkflow`：四步工作流 `submit → review → expert_recheck → finalize_verified`；
  - `submit`：授权范围检查（仅 E-TH-01~03）→ source_ref 强制校验（C1-C6）→ 写入草稿态（threshold_status=review、verified=false、双签位空）→ 落 `intake_submit`；
  - `review`：主理人核准，写入 verified_by / verified_at → 落 `intake_review_approve`；
  - `expert_recheck`：专家复核，SoD 校验（专家≠主理人）→ 写入 expert_verified_by/at → 落 `intake_expert_recheck`；
  - `finalize_verified`：双签齐全方可置 verified=true、threshold_status=verified → 落 `intake_verified`；
  - 每步写盘前生成内容快照（支持回滚）；
  - 拒绝动作均落 `intake_rejected` 审核事件（不入库）。

### 任务2：source_ref 验证（强制）
- `submit` 调用 `validate_source_ref`（C1-C6：标准号/条款号/版本/链接/内容哈希/完整性）；
- 任一不满足即拒绝进入审核，返回明确 reason，且**不写入库**（红线：绝不补充缺失数据）。

### 任务3：双签流程（SoD）
- 主理人：`verified_by` / `verified_at`；专家：`expert_verified_by` / `expert_verified_at`；
- `expert_recheck` 强制 SoD：专家复核人与主理人核准人**同一身份 → 拒绝**（REASON_SOD_CONFLICT）；
- 签字人仅接受人工显式提供，AI 绝不篡改/生成签署信息。

### 任务4：门禁检查（保持 engineering_enabled=false）
- `evaluate_gates()`：传入 `ci_green=False / rollback_ready=False / authorization_present=False`，委托 `can_enable_engineering` 执行 G1-G6；
- 工作流**绝不**翻转 engineering_enabled、**绝不**写 config.yaml，结果恒为 `(False, reasons)`——即使 E-TH-01~03 已双签转正，灰度闸门仍默认拒绝；
- 测试断言 `evaluate_gates() == (False, reasons)` 且 `load_engineering_enabled() is False`。

### 任务5：测试（新增 `tests/agents/test_real_threshold_intake.py`）
覆盖七要点 + 授权越界拒绝 + 重复提交拒绝 + 未提交即审核拒绝 + 缺主理人即专家复核拒绝，共 11 用例：
1. 合法录入流程（双签齐全、verified=true）；
2. source_ref 失败（缺 clause / 缺 hash → 拒绝不入库）；
3. 缺专家签（未复核即转正 → 拒绝）；
4. SoD 冲突（专家=主理人 → 拒绝）；
5. review_log 链（四步事件有序、prev_event_id 衔接、event_id 确定性）；
6. migration 兼容（录入产物 schema v2，可被 loader 读取、喂入迁移判 noop）；
7. enabled=false 保护（evaluate_gates 恒 False；即便全双签转正，校验器 enabled=False 仍 pending_verification）；
- 授权越界（D-TH-01 / E-TH-04 拒绝）、已转正重复提交拒绝、未提交审核拒绝、缺主理人即专家复核拒绝。

---

## 2. 质量门禁（local_ci 8/8）

| 阶段 | 结果 |
|---|---|
| [1/8] Ruff lint | 通过 |
| [2/8] Pytest 覆盖率 | 426 passed，**Total coverage 89.10%**（≥88.92%） |
| [3/8] 前端 ESLint | 通过 |
| [4/8] 前端 Jest | 29 passed |
| [5/8] Alembic 升降级 | 通过 |
| [6/8] Seed | 通过 |
| [7/8] 防编造扫描 | 0 命中 |
| [8/8] 硬编码扫描 | 0 命中 |

> 覆盖率由 3.2.4-E 的 88.92% 提升至 89.10%（新增录入工作流全被测试覆盖，仅异常守卫分支未覆盖，属合理）。

---

## 3. 红线守约（最高安全级别）

- AI **未**自行生成工程参数（测试 value 一律传 None 占位，source_ref 为结构合法合成占位）；
- AI **未**猜测规范值、**未**补充缺失数据（source_ref 不完整即拒绝，不填）；
- AI **未**修改专家签署信息（signer 仅接受人工显式提供，工具绝不编造）；
- **未开启** engineering_enabled（evaluate_gates 恒 False + 校验器 enabled=False 双重确认）；
- **未输出** engineering_approved（工作流不产出 approved、不翻转开关）；
- 授权边界严格：仅 E-TH-01~03 可录入，D-TH / E-TH-04~06 一律拒绝；
- 全 pending_verification；防编造 / 硬编码扫描 0 命中。

---

## 4. 待主理人定夺的开放项

- **真实数据录入触发**：本工具已就绪，但真实数值（value / unit / 真实 source_ref 内容 / 真实签字人）须由人工在调用时显式提供；AI 在本阶段不会以真实数据执行录入；
- **D-TH 双签最终采纳**：仍为方案 A 方向待书面授权；本阶段未触及 D-TH；
- **首个真实化范围确认**：建议先 E-TH-01~03（首个灰度接口所需），不阻塞 D-TH 决策；
- **G3/G5/G6 前置条件**：真实录入后仍需 CI 全绿、回滚就绪、主理人单独书面授权，方可 3.2.5 实施开启 engineering_enabled 灰度。

---

## 5. 下一步

等待主理人审核 + 单独书面授权后：
（a）由人工以真实工程数据调用 `ThresholdIntakeWorkflow` 录入 E-TH-01~03；
（b）满足 G1-G6 + 主理人书面授权，进入 3.2.5 实施（engineering_enabled 开启灰度）。
**本阶段已停止，未开启 engineering_enabled、未输出 engineering_approved、未以真实数据执行录入。**

---

**本阶段交付边界**：新增 `agents/engineering/threshold_intake.py`、`tests/agents/test_real_threshold_intake.py`；零既有逻辑破坏、红线全程守约（最高安全级别）、防编造/硬编码扫描 0 命中、local_ci 8/8 全绿 426 passed@89.10%。
