# BOIP Phase 3.6.1 — Real Activation Evidence Preparation（真实激活证据准备）

- **Phase**：3.6.1
- **标题**：Real Activation Evidence Preparation（真实激活证据准备）
- **日期**：2026-08-02
- **身份**：BOIP AI Chief Architect
- **前置**：Phase 3.6.0 ✅ DRILL PASS（G1-G6 机制可运行 / Rollback 可运行 / Runtime Guard 有效）
- **性质**：**纯模板与清单设计**（非机制运行、非真实数据录入）；所有真实值留空待人工填写
- **结论**：建立 DRILL→REAL 映射 + 四类证据模板 + G1-G6 最终检查表；**激活态维持 NO-GO**
- **权威依据**：`.ai/phase3.6.0_drill/result.json`、`.ai/reviews/phase3.6.0_controlled_activation_execution_report.md`

---

## 0. 红线守约声明（本轮 6 条）

| # | 禁止项 | 本轮守约 |
|---|---|---|
| ① | AI 生成真实工程参数 | ✅ 所有 `value/unit/source_ref` 均为 `<待人工填写>` 占位，未生成任何真实数值 |
| ② | AI 生成专家身份 | ✅ 专家身份仅以 `DRILL-EXPERT-002 → 待真实专家` 标注，AI 未编造 |
| ③ | AI 代签专家 | ✅ 模板仅定义 `signature_record` 结构，签名由真实专家线下完成，AI 不代签 |
| ④ | AI 创建 ReleaseApproval | ✅ 仅提供七字段模板 + 标注「AI 仅 `validate_release_approval`」，未调 `append_approval_record` |
| ⑤ | 自动开启 `engineering_enabled` | ✅ `orchestrator.engineering_enabled` 仍 `false`（未触碰 config.yaml） |
| ⑥ | 输出 `engineering_approved` | ✅ 全程无 `engineering_approved` 输出 |

> ⚠️ 本文件所有「真实值」字段**一律留空**，仅描述结构与落入文件。真实填充、签署、授权均须由主理人/专家人工完成。

---

## 1. 任务 1 — DRILL → REAL 替换映射清单

Phase 3.6.0 DRILL 使用的 `DRILL-*` 占位符，须在主理人/专家线下动作时**逐一对真实资料替换**。下表为映射契约：

| DRILL 占位 | 真实替换项 | 关联接口/阈值 | 责任人 | 落入文件 |
|---|---|---|---|---|
| `E-TH-01` | 真实工程阈值 ID + 参数（风压相关） | wind_pressure | 主理人 + 专家 | `agents/engineering/thresholds/verified.json` |
| `E-TH-02` | 真实工程阈值 ID + 参数（风压相关） | wind_pressure | 主理人 + 专家 | `agents/engineering/thresholds/verified.json` |
| `E-TH-03` | 真实工程阈值 ID + 参数（风压相关） | wind_pressure | 主理人 + 专家 | `agents/engineering/thresholds/verified.json` |
| `DRILL-PRINCIPAL-001`（`verified_by`） | 真实主理人身份标识 | — | 主理人 | `review_log.jsonl` / `verified.json` |
| `DRILL-EXPERT-002`（`expert_verified_by`） | 真实专家身份标识 | — | 专家 | `review_log.jsonl` |
| `DRILL-AUTHORIZER-004`（`authorized_by`） | 真实授权人身份标识 | — | 主理人/授权人 | `agents/engineering/release/release_approvals.jsonl` |
| `DRILL-ROLLBACK-003`（`rollback_owner`） | 真实回滚责任人身份标识 | — | 主理人 | `agents/engineering/release/release_approvals.jsonl` |

**替换规则**：
1. 每个 `DRILL-*` 占位在真实录入时**整体替换**为真实身份/数值，不得保留占位前缀。
2. `verified_by ≠ expert_verified_by`（SoD 硬约束，专家不得兼主理人）。
3. `authorized_by ≠ rollback_owner`（G6 SoD 软约束）。
4. 替换后须重跑 Phase 3.6.0 演练逻辑（或等价人工核对）确认机制仍 PASS，且 `UnifiedActivationGate` 仅在治理层确认后翻 GO。

**关联接口说明**（来自 3.6.0 接口级诊断）：`wind_pressure` 工程接口所需阈值即 E-TH-01/02/03；全局合并表若仍含 `draft` 的 D-TH，则全局 G1/G2 默认 FAIL，须仅对该接口注入真实 E-TH 方可接口级放行（详见 Phase 3.6.0 报告 §4）。

---

## 2. 任务 2 — 真实 Threshold 资料模板（Threshold Evidence Package）

> 字段含义：`value`/`unit`/`source_ref`/`version`/`verification` 全部**待人工填写**；AI 不生成任何真实值。

落盘文件：`agents/engineering/thresholds/verified.json`（经 `ThresholdIntakeWorkflow.finalize_verified` 写入，禁止绕过直接改）

```json
{
  "threshold_id": "E-TH-01",
  "interface": "wind_pressure",
  "param": "<待人工填写：参数名，如 基本风压/阵风系数>",
  "value": "<待人工填写：真实工程数值>",
  "unit": "<待人工填写：单位，如 Pa / kPa / 无量纲>",
  "source_ref": "<待人工填写：规范/标准条文引用（含版本与条款，如 GB 50009-2012 8.1.1）>",
  "version": "<待人工填写：资料版本，如 v1.0>",
  "verification": {
    "status": "pending_verification",
    "verified_by": "<DRILL-PRINCIPAL-001 → 真实主理人标识>",
    "expert_verified_by": "<DRILL-EXPERT-002 → 真实专家标识>",
    "verified_at": "<待人工填写：ISO8601>",
    "expert_verified_at": "<待人工填写：ISO8601>",
    "method": "<待人工填写：专家书面审核 + 管理复核>"
  }
}
```

**填写要求**：
- `value` / `unit`：须源自真实规范/设计计算，AI 不得估算或补全。
- `source_ref`：须可回溯到具体规范条文（含版本/条款），不满足则 `pending_verification` 不得解除。
- `version`：资料版本号，便于后续变更追溯。
- `verification`：四步事件（submit/review/expert_recheck/verified）须由真实人员在 `review_log.jsonl` 落链（见 §5 G4）。

---

## 3. 任务 3 — 专家证据模板（Expert Evidence）

> 字段含义：`qualification`/`domain`/`sign_scope`/`signature_record` 全部**待人工填写**；AI 不生成专家身份、不代签。

落盘文件：建议 `agents/engineering/knowledge/threshold_signing_sessions.json`（专家签署会话登记）或主理人线下签署台账（物理/电子）

```json
{
  "expert_id": "<待人工填写：真实专家唯一标识>",
  "qualification": "<待人工填写：资质 / 职称 / 执业资格，如 一级注册结构工程师>",
  "domain": "<待人工填写：专业领域，如 建筑结构 / 幕墙 / 风工程>",
  "sign_scope": "<待人工填写：可签署阈值范围，如 wind_pressure 接口 E-TH-01~03>",
  "signature_record": {
    "signature_method": "<待人工填写：手写签名 / 电子签名 / 数字证书>",
    "signed_at": "<待人工填写：ISO8601>",
    "signature_ref": "<待人工填写：签名存档引用（扫描件路径 / 证书指纹）>",
    "is_ai_generated": false
  }
}
```

**填写要求**：
- `expert_id`：**真实专家身份**，替换 `DRILL-EXPERT-002`；须与 `verified_by`（主理人）异身份（SoD）。
- `qualification` / `domain`：证明签署资格，须与 `sign_scope` 匹配。
- `signature_record.signature_ref`：签名存档可追溯；`is_ai_generated` 必须 `false`（红线③：AI 不代签）。

---

## 4. 任务 4 — G6 授权模板（EngineeringReleaseApproval）

> 七字段全部**待人工填写**；**AI 仅 `validate_release_approval`（校验存在性/合法性/SoD），绝不 `append_approval_record`**（红线④）。

落盘文件：`agents/engineering/release/release_approvals.jsonl`（append-only，由主理人线下创建后写入）

```json
{
  "approval_id": "<待人工填写：唯一授权ID，如 ERA-WP-2026-001>",
  "interface": "wind_pressure",
  "scope": "<待人工填写：生效范围，如 仅 wind_pressure 接口灰度>",
  "authorized_by": "<DRILL-AUTHORIZER-004 → 真实授权人标识>",
  "effective_time": "<待人工填写：ISO8601 生效时间>",
  "rollback_owner": "<DRILL-ROLLBACK-003 → 真实回滚责任人标识>",
  "approval_document_ref": "<待人工填写：授权文档引用（签字扫描件/内部审批单号）>"
}
```

**AI 校验边界（`validate_release_approval`）**：
- 七字段非空；`effective_time` 须为合法 ISO8601；
- SoD 软校验：`authorized_by ≠ rollback_owner`；
- 不创建、不写入、不代签；真实记录须由主理人书面生成并 append-only 落盘。

---

## 5. 任务 5 — Real Activation Checklist（G1–G6 最终检查表）

> 真实激活解锁前，逐闸门核对。任一闸门未 PASS → 维持 NO-GO。

| 闸门 | 名称 | 所需证据 | 通过条件 | 落入/校验位置 |
|---|---|---|---|---|
| **G1** | governance 治理 | `verified.json` 中 E-TH-01/02/03 `value` 非 null 且 `status=verified`；存在 `Engineering_Approved` 候选 | 阈值状态全 `verified` + 治理候选齐备 | `thresholds/verified.json` |
| **G2** | dual_sign 双签 | `review_log.jsonl` 含 `verified_by`（主理人）+ `expert_verified_by`（专家），且异身份 | SoD 满足、`all_signed=True` | `review_log.jsonl` |
| **G3** | ci 持续集成 | 人类终端 `local_ci.sh` 8/8 绿 | 672 passed / 90.40% / EXIT=0 | `scripts/ci/local_ci.sh` |
| **G4** | audit_chain 审核链 | `review_log.jsonl` 含 `submit/review/expert_recheck/verified` 四类且 `prev_event_id` 链式无断裂 | `chain_intact=True` + 四类齐全 | `review_log.jsonl` |
| **G5** | rollback 回滚就绪 | Rollback Dry Run 通过（snapshot/disable/rollback/restore） | `mechanism_ok=True` 且 `gray_allowed` 恒受 `engineering_enabled=False` 约束 | `GrayReleaseConfig` + `RollbackHandler` |
| **G6** | authorization 授权 | 真实 `EngineeringReleaseApproval` 已创建并 `effective_time` 生效 | 七字段齐全 + SoD + `is_effective=True` | `release/release_approvals.jsonl` |

**顶层不变量**：`load_engineering_enabled() is False` 须保持至主理人**显式**置 `orchestrator.engineering_enabled=true`（且须 G6 授权记录在先）。`UnifiedActivationGate.evaluate` 在六闸门全 PASS 且 `engineering_enabled` 翻转后始翻 GO。

**真实解锁顺序**（全部人工动作）：
1. 经 `ThresholdIntakeWorkflow` 四步录入**真实** E-TH-01/02/03（替换 DRILL 占位）；
2. 确认 `review_log.jsonl` 含完整四类规范事件且链式无断裂（G4）；
3. 线下创建**真实** `EngineeringReleaseApproval`（G6 七字段 + SoD + 生效）；
4. 人类终端 `local_ci.sh` 8/8 绿（G3，已实证可达）；
5. 完成真实 Rollback Dry Run（G5）；
6. **显式**置 `orchestrator.engineering_enabled=true`（G1–G6 全 PASS 后）。

---

## 6. 交付物与状态

| 类型 | 路径 |
|---|---|
| 本证据准备报告 | `.ai/reviews/phase3.6.1_real_activation_evidence_preparation.md` |
| SSOT 更新 | `.ai/project_status.json`（新增 `phase_3_6["3.6.1"]` 块，current_roadmap_version 维持 V6） |
| 路线更新 | `.ai/roadmap_v6.md`（新增 3.6.1 节） |

**激活态**：维持 **NO-GO**。本轮仅建立证据模板与映射清单，未录入真实值、未签署、未授权、未开启 `engineering_enabled`、未输出 `engineering_approved`。**完成后停止**，等待主理人/专家线下填充真实资料。

---

## 7. 下一步（人工动作，非 AI 范畴）

- 主理人依据 §1 映射，逐一对 `DRILL-*` 占位替换为真实身份/数值；
- 专家按 §3 模板完成资质登记与线下签署（`signature_record.is_ai_generated=false`）；
- 主理人按 §4 模板创建真实 `EngineeringReleaseApproval` 并 append-only 落盘；
- 依 §5 检查表逐项核对 G1–G6，全 PASS 后显式置 `engineering_enabled=true`。

> 禁止自动激活：无论模板是否齐备，AI 不得自动置 `engineering_enabled=true`、不得输出 `engineering_approved`、不得代建 `ReleaseApproval`、不得代专家/主理人签署或授权、不得伪造真实工程参数。
