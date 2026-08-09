# BOIP Phase 3.2 Sprint 3.2.4-A 完成报告

## 工程阈值治理基础设施落地（Threshold Governance Infrastructure Implementation）

**身份**：BOIP AI 工程治理架构负责人
**日期**：2026-07-30
**性质**：阈值治理设计（Sprint 3.2.4）的可运行基础设施落地；**非真实参数填写、非开启 `engineering_enabled`、非输出 `engineering_approved`**。

---

## 一、修改文件

### 新增
| 文件 | 说明 |
|---|---|
| `agents/engineering/thresholds/schema.py` | 阈值治理结构化类型契约：`ThresholdStatus`（draft/review/verified/deprecated 四态枚举）、`ThresholdSourceRef`（standard/clause/edition/url/retrieved_at 结构化）、`ThresholdGovernanceView`（单条目治理聚合视图 + `governance_ok` / `mgmt_signed` / `expert_signed`）、治理拒绝原因常量。 |
| `tests/agents/test_threshold_governance.py` | 治理门禁测试（**9 用例**），覆盖任务要求的 8 点 + 2 项回归。 |

### 修改
| 文件 | 说明 |
|---|---|
| `agents/engineering/threshold_loader.py` | 引入 `schema` 类型；新增 `governance_status(entry) -> (ok, reason)` 与 `load_governed_thresholds(path)`（deprecated 拒绝加载、其余保留供降级）；既有 `verified`/`mgmt_signed`/`expert_signed`/`is_fully_verified`/`load_verified_thresholds` 语义**零改动**。 |

### 未改动（红线）
- `agents/engineering/thresholds/verified.json`（E-TH-01~06 真实 value 仍 null、verified 仍 false）；
- `agents/design/thresholds/verified.json`（D-TH-01~05 未填真实值）；
- `agents/engineering/validation.py`、`review_log.py`、五工程计算模块、config（`engineering_enabled` 仍 false）。

---

## 二、架构影响

1. **分层清晰**：`schema.py` 承载"治理类型契约"，`threshold_loader` 承载"读取 + 治理筛选"，`validation` 承载"四签状态机"——三层解耦，职责单一。
2. **向后兼容**：
   - 既有 `verified.json` 不强制改造——缺 `threshold_status` 字段自动降级为 `DRAFT`，旧布尔 `verified` 镜像与 `mgmt_signed` 判定逻辑完全保留；
   - 五工程模块（wind_pressure/glass_safety/profile/hardware/installation_risk）与 `ExpertBackedEngineeringValidation` 对 `threshold_loader` 的调用方式零破坏（仅新增 `governance_status`/`load_governed_thresholds` 两个可选导出，现有导入不受影响）。
3. **D-TH 双签兼容（任务3）**：`ThresholdGovernanceView.from_entry` 统一解析 D-TH 既有条目（含 `applies_to_scheme`、自由文本 `source_ref`），并**预留** `expert_verified_by`/`expert_verified_at` 读取能力（缺省 `None`）——不填真实值，仅补 schema 能力。真实 D-TH 现状（仅主理人单签）在治理态下被 `GOV_REASON_EXPERT_MISSING` 捕获，为 3.2.5+ 补专家签字位预留接口。
4. **降级链路贯穿**：`governance_status` 的显式 `reason` 串接"draft/review → 非 verified"、"deprecated → 拒绝加载"、"verified 缺引用/缺双签 → 治理不通过"，与既有 `pending_verification` 全链路一致。

---

## 三、测试结果

`bash scripts/ci/local_ci.sh` → **8/8 PASS**

| 步骤 | 结果 |
|---|---|
| [1/8] Backend lint (Ruff) | PASS（修复 3 处未用导入/变量） |
| [2/8] Backend pytest | **388 passed @ 88.57%**（≥88.47% 达标，379→388 净增 9） |
| [3/8] Frontend Jest | 29 passed @ 93.15% |
| [4/8] Frontend lint (ESLint) | PASS |
| [5/8] Alembic upgrade/downgrade | 双向通过 |
| [6/8] Seed | 通过 |
| [7/8] 编造业务数字扫描 | **0 命中** |
| [8/8] 硬编码业务配置扫描 | **0 命中** |

### 新增测试覆盖（test_threshold_governance.py，9 用例）
1. `test_draft_status_not_governed` — draft 态 → GOV_REASON_NOT_VERIFIED；
2. `test_review_status_not_governed` — review 态 → GOV_REASON_NOT_VERIFIED；
3. `test_verified_missing_source_ref_fails` — verified 缺结构化引用 → GOV_REASON_SOURCE_REF_INCOMPLETE；
4. `test_verified_missing_expert_sign_fails` — verified 缺专家签 → GOV_REASON_EXPERT_MISSING；
5/6. `test_deprecated_rejected_from_load` — deprecated → `governance_status` 拒绝 + `load_governed_thresholds` 剔除（临时文件验证）；
7. `test_d_th_double_sign_field_compatible` — D-TH 既有条目 schema 兼容解析 + 预留专家签位捕获；
8. `test_engineering_enabled_false_keeps_pending` — 即使治理完备，`enabled=False` 永 pending（回归守门）；
9. 附加：`test_real_engineering_verified_json_all_pending`（真实 E-TH 全 pending 回归）、`test_source_ref_structured_roundtrip`（结构化引用解析完整性）。

---

## 四、风险

| 风险 | 等级 | 说明 / 缓解 |
|---|---|---|
| 治理态与旧布尔态语义差异 | 低 | 旧 `is_fully_verified` 仍基于 `verified` 布尔五字段；新 `governance_status` 额外要求 `status=VERIFIED` + 结构化引用。二者并存，调用方按需选择，无强制迁移。 |
| D-TH 双签缺口遗留 | 中 | Design 侧 D-TH-01~05 仍仅主理人单签，治理态下 `profile`/`glass_safety` 接口无法 approved；已在 schema 预留专家签位，待主理人授权后补真实专家签字（3.2.5+）。 |
| deprecated 剔除导致下游 KeyError | 低 | `load_governed_thresholds` 仅剔除 deprecated，其余条目保留原始形态；`validation` 依赖 `get_interface_thresholds` + `is_fully_verified`，不直接依赖 governed 表，无 KeyError 风险。 |
| 覆盖率微边界 | 低 | 新增 9 用例 + schema/loader 新分支，覆盖率 88.47%→88.57%，高于基线。 |

---

## 五、兼容性验证

- ✅ **真实 `verified.json` 零破坏**：`test_real_engineering_verified_json_all_pending` 断言 E-TH-01~06 的 `verified` 仍为 `false`、治理态为 DRAFT、原因 `GOV_REASON_NOT_VERIFIED`；`load_verified_thresholds` 返回值与改造前逐字一致。
- ✅ **既有测试全绿**：原 `test_engineering_validation.py` / `test_expert_sign_flow.py` / 五模块测试（`test_wind_pressure` 等）均未因本次增强失败（全部通过，pending_verification）。
- ✅ **D-TH 兼容**：从 `agents.design.thresholds.verified.json` 直接加载并解析，字段兼容无报错。
- ✅ **防编造/硬编码扫描 0 命中**：新增 schema/loader/测试/本报告均不含未验证业务数值或真实规范条款（标识符 E-TH/D-TH 豁免，含 `pending_verification` 标记行豁免）。

---

## 六、红线守约（全程）

- ✅ 未修改 `verified.json` 真实 value（全 null）；
- ✅ 未设置 `verified=true`（全 false）；
- ✅ 未开启 `engineering_enabled`（仍 false）；
- ✅ 未输出真实 `engineering_approved`（仅内存注入逻辑分支验证，不落盘、不改 config）；
- ✅ 未填写真实专家姓名（`signer` 仅 `principal-001`/`expert-001` 纯标识符）；
- ✅ 未填写真实规范数值（source_ref 仅示例标识符 GB 50009/GB 5237，值仍 null）；
- ✅ 全 `pending_verification`。

---

## 七、状态

改动未 commit，等待主理人验收。**未进入 3.2.5（enabled 开启灰度）/ 未进入真实审核闭环**：二者须单独书面授权，不可与治理基础设施混同。
