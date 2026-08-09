# BOIP Phase 3.2 Sprint 3.2.3 — ExpertBackedEngineeringValidation 双签流程演练 完成报告

- **完成日期**：2026-07-30
- **身份**：BOIP AI 工程审核体系负责人
- **性质**：演练（Drill），**非开启真实工程审核**。本 Sprint 不修改任何生产代码、不开启 `engineering_enabled`、不填写真实参数、不输出真实 `engineering_approved`，全程 `pending_verification`。
- **依据设计**：`.ai/tasks/phase3.2.3_expert_sign_design.md`

---

## 1. 修改文件

| 文件 | 类型 | 说明 |
|---|---|---|
| `.ai/tasks/phase3.2.3_expert_sign_design.md` | 新增（设计物） | 六章节设计：当前 validation 流程分析 / 四签状态机 / review_log 事件模型 / sign_off_id 生成规则 / 模拟签署流程 / 测试方案 |
| `tests/agents/test_expert_sign_flow.py` | 新增（测试） | 十七用例，覆盖四签矩阵 / review_log 链 / sign_off_id 确定性 / enabled 关闭保护 / pending 保持 |
| 既有 `tests/agents/test_engineering_validation.py`（Sprint A） | **未改动** | 本 Sprint 独立新增文件补充演练视角，不动既有测试 |
| `agents/engineering/validation.py`、`review_log.py`、`threshold_loader.py` | **未改动** | 演练仅消费既有接口，不修改生产代码 |

---

## 2. 架构影响

- **零生产代码改动**：本次纯演练，所有断言基于既有 `ExpertBackedEngineeringValidation.validate()`、`review_log.append_review_event()` / `compute_event_id()` / `compute_sign_off_id()`、`threshold_loader.mgmt_signed()` / `expert_signed()` 接口，未新增/修改任何工程计算、审核、日志逻辑。
- **四签状态机确认**：四签（`structure_valid` / `threshold_verified` / `expert_signed` / `engineering_enabled`）的矩阵转移逻辑与既有实现一致；演练以全景矩阵（七组合）+ 五场景逐一覆盖，验证闸门在 `enabled=false` 下**永不泄漏** `approved`。
- **review_log 链路确认**：模拟"主理人核准 → 专家签字"两事件，`prev_event_id` 链式正确、`event_id` 确定性可复核、损坏行静默跳过、显式指针可覆盖。
- **sign_off_id 可复核性确认**：场景5 注入 `enabled=true`（仅逻辑分支）派生 `sign_off_id`（十六位），与同一夹具 `compute_sign_off_id` 重算完全一致，证明不可抵赖标识在真实闭环阶段可被复核比对。
- **不变量固化**：双签"模拟齐全"但 `engineering_enabled=false` → 恒 `pending` 且 `sign_off_id=None`，这是红线核心保护层，本次以测试显式钉死。

---

## 3. 测试结果

### 3.1 新增测试（十七用例，全 PASS）

`tests/agents/test_expert_sign_flow.py`：

| 覆盖点 | 用例数 | 关键断言 |
|---|---|---|
| 1. 四签状态机矩阵 | 7 | 场景1 invalid_structure / 场景2 缺主理人核准 pending / 场景3 缺专家签字 pending / 场景4 四签满足但 enabled=false pending / 场景5 注入 enabled=true approved + 16位 sign_off_id / 枚举七组合全景矩阵 |
| 2. review_log 链 | 4 | 主理人→专家 prev 链接正确 / event_id 确定性 / 显式 prev 指针覆盖 / 损坏行跳过 |
| 3. sign_off_id 确定性 | 2 | 派生与重算一致（16位）/ pending 态恒 None |
| 4. enabled 关闭保护 | 3 | 真实 config=false / 五接口全 pending / Agent 全链路无 approved |
| 5. pending 保持 | 2 | 双签齐全+enabled=false 仍 pending / signer 仅纯标识符 |

### 3.2 本地 CI（8/8 PASS）

`bash scripts/ci/local_ci.sh` 全绿：

| 步骤 | 结果 |
|---|---|
| 1/8 Backend lint (Ruff) | 0 违规 |
| 2/8 Backend pytest + coverage | **379 passed@88.47%**（门槛 60%；基线 ≥88.43% 达标；较 3.2.2 净增 17 用例，覆盖率 88.43%→88.47% 微升） |
| 3/8 Frontend lint (ESLint) | 0 error |
| 4/8 Frontend Jest + coverage | 29 passed / 6 suites@93.15%（门槛 50%） |
| 5/8 Alembic upgrade/downgrade | 双向可逆通过 |
| 6/8 Seed script | 通过 |
| 7/8 业务数字扫描 | 0 命中 |
| 8/8 硬编码扫描 | 0 命中 |

---

## 4. 风险

| 风险 | 等级 | 说明与缓解 |
|---|---|---|
| R-DRILL-1 演练逻辑被误当作真实批准 | 中 | 场景5 仅内存注入 `engineering_enabled=True` 验证闸门，**不写** config / verified.json / 任何生产日志；报告与测试文档均显式标注"仅逻辑分支、非真实签署"。缓解：CI 中 `test_enabled_false_in_real_config` 持续断言真实配置恒 false。 |
| R-DRILL-2 模拟签署动作被误接真实链 | 低 | 演练日志全部落临时目录（`tempfile.TemporaryDirectory`），不触碰真实 `review_log.jsonl`；`source_ref` 统一含 `test fixture pending_verification`。 |
| R-DRILL-3 专家身份泄露 | 低 | `signer` 仅填 `principal-001` / `expert-001` 纯标识符，不含真实姓名/资质编号；`value` 恒 `None`。 |
| R-DRILL-4 覆盖率门槛回归 | 低 | 新增十七用例仅提升边际分支覆盖，基线 88.43%→88.47% 不降反升，已达标。 |

**未闭合项（延续）**：真实审核闭环仍需 `verified.json` 权威双签填充（3.2.4，须单独书面授权）+ `engineering_enabled` 开启灰度（3.2.5，须单独书面授权）；本 Sprint 严守红线，未进入二者。

---

## 5. 安全检查

- **红线守约**：①未开启 `engineering_enabled`（真实 config 仍 false，测试断言固化）；②未修改 `verified.json` 真实参数（全部内存夹具 value=None）；③未输出真实 `engineering_approved`（仅内存注入逻辑分支验证，不落盘）；④未填写真实专家身份（signer 仅标识符）；⑤未填写真实工程值（E-TH 仅标识符透出，无任何未验证数值）；⑥全程 `pending_verification`。
- **防编造扫描**：对新增测试文件与设计文档扫描 0 命中（业务词仅以 E-TH 标识符或在含 `pending_verification` 标记行内出现，无未验证真实数字）。
- **硬编码扫描**：0 命中。
- **生产代码零改动**：`validation.py` / `review_log.py` / `threshold_loader.py` / `agent.py` 均未被修改；既有 Sprint A 测试未被改动。

---

## 6. 结论

Sprint 3.2.3 双签流程演练完成：四签状态机矩阵、review_log 事件-签名链路、sign_off_id 可复核性、enabled 关闭保护、pending 保持五点全部以测试级内存模拟验证通过；红线全程守约，local_ci 8/8 全绿（379 passed@88.47%）。**本阶段为演练，不进入 verified.json 真实化（3.2.4）与 enabled 开启灰度（3.2.5），等待主理人验收。**

---

**END（Sprint 3.2.3 DONE，等待主理人验收；不进入真实审核闭环）**
