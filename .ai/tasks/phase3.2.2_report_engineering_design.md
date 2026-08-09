# Phase 3.2.2 设计确认：ReportGenerator 工程章节接线

> 身份：BOIP AI 产品化架构工程师
> 阶段定位：工程结果产品化展示（仅接线、不改计算逻辑、不填真实参数）
> 红线：未开启 `engineering_enabled`、未输出 `engineering_approved`、全 `pending_verification`、不改 `verified.json`、不产真实数值。

---

## 1. 当前 ReportGenerator 分析

`agents/report/generator.py`（`generate_project_report(dossier)`）当前聚合 **三 Agent**：

| 章节 | 函数 | 消费键 |
|---|---|---|
| 封面 | `_build_cover` | `project` |
| 一、视觉分析 | `_build_vision_section` | `vision`（SceneType/obstructions 等） |
| 二、环境分析 | `_build_environment_section` | `environment`（field_provenance / data_providers / regulatory_hints） |
| 三、数据可信等级说明 | `_build_credibility_section` | dossier 全局（Level 0~3 模型） |
| 四、设计方案对比 | `_build_design_section` | `design`（candidates / verified / threshold_refs / gaps） |
| 五、免责与待确认声明 | `_build_disclaimer_section` | vision/environment/design 的 `pending_verification` |

**关键事实**：
- dossier 形态约束在模块 docstring：`{"project","vision","environment","design"}`，`engineering` 键**尚不存在**。
- 已有 `_badge_for(level)`：把 `measured/verified → [已验证]`、`inferred/mock → [AI推理·待确认]`、`其他(含 pending_verification) → [待确认]`。**绝不会把 pending 误显为已验证**（Final Integration 已验证）。
- `_list_flowable` / `_as_str` / `_as_list` / `_section_safe` / `_escape` 等安全 helper 全部可复用，零崩溃约定已建立。
- 现有测试（`test_report_provenance.py`）仅断言子串锚点（"环境分析"/"设计方案对比"等），新增章节**不破坏**这些断言。
- 可信等级章（第三章）已写明 "Level 3 工程批准：当前系统未启用"——新工程章节须与之一致，渲染为待确认。

**接入点**：在 `generate_project_report` 的 `story` 装配序列中，于「四、设计方案对比」之后、「五、免责」之前插入「四-乙 / 工程智能分析」章节（重新编号为「五、工程智能分析」，原免责顺延为「六」），并在 dossier 解析处新增 `engineering = _section_safe(dossier.get("engineering"))`。

---

## 2. Engineering 章节结构（PDF 章节：工程智能分析）

章节编号建议：**「五、工程智能分析」**（原「五、免责与待确认声明」顺延为「六」）。

子节（PDF 要求对应的 5 个子块）：
1. **工程模块状态总览**：表格——模块名 | 接口 | 可信状态徽标 | 结论摘要（result 空→「待确认」）。
2. **五模块详情**：按 `interface` 分五个 h2 小节（风压/玻璃/型材/五金/安装风险），每节展示 result / evidence / gaps / threshold_refs / provenance。
3. **可信等级**：复用第三章 Level 模型；本工程章节标注「Level 3 工程批准：当前系统未启用，全待确认」。
4. **审核链状态**：展示 `sign_off_id`（None→「未签署」）、`verification_status`（`pending_verification`→「待工程批准」）、`intermediate` 关键信号（如 w_k 是否 verified）。
5. **待确认事项**：汇总五模块 `gaps` + `threshold_refs`（E-TH-0x 等）统一列出，标红色 warn 样式。

---

## 3. 五模块展示方案

消费 `EngineeringCalculationResult.as_full()`（八字段 + interface）。`as_full()` 字典形态：
```
{
  "interface": "wind_pressure" | "glass_safety" | "profile" | "hardware" | "installation_risk",
  "result": "",                      # pending 态恒空（红线）
  "confidence": "pending_verification",
  "evidence": "",
  "verification_status": "pending_verification",
  "intermediate": {...},             # 上游信号（如 w_k.value / verified 标记）
  "provenance": {"wind_pressure.w_k": "verified"/"pending"},
  "threshold_refs": ["E-TH-01", ...],
  "gaps": ["glass_safety_result: upstream_pending", ...],
  "sign_off_id": None,
}
```

展示映射（每模块 h2 小节）：
- 风压 → `wind_pressure`
- 玻璃安全 → `glass_safety`
- 型材 → `profile`
- 五金 → `hardware`
- 安装风险 → `installation_risk`

每节字段展示：
- **结论 (result)**：`_as_str(r.get("result"))`（pending 时为空 → 显示「待确认」而非空白）。
- **证据 (evidence)**：`_as_str(r.get("evidence"))`。
- **待确认项 (gaps)**：`_list_flowable(r.get("gaps"))`。
- **阈值引用 (threshold_refs)**：`_list_flowable(r.get("threshold_refs"))`（E-TH-0x 透出）。
- **溯源 (provenance)**：`provenance` 为 dict → 展开「key=value」列表（复用 `_escape`）。

---

## 4. Badge 展示规则

工程章节的「可信状态」统一用 `_badge_for()`：
- 模块 `verification_status == "pending_verification"` → `_badge_for("pending_verification")` → `(BADGE_PENDING, "badge_pending")` = `[待确认]`（红色）。
- 不调用 `engineering_approved` 任何分支；`result` 恒空，绝不渲染为工程结论。
- 状态总览表的「可信状态」列：每模块一行，统一 `BADGE_PENDING`。

**红线保障**：当前系统 `verification_status` 恒 `pending_verification`，故工程章节省略 `[已验证]`；即使未来 `verified` 字段被填充，`_badge_for` 仅对 `measured/verified` 等级返回绿标，而工程 `as_full` 不携带此类等级，**误显风险为零**（与 Final Integration 结论一致）。

---

## 5. pending 展示规则

- `result == ""`（空串）→ 结论单元格显示「待确认（pending_verification）」，不为空。
- `verification_status == "pending_verification"` → 状态徽标 `[待确认]`。
- 任一上游 `gaps` 含 `xxx: upstream_pending` → 该模块详情小节额外提示「上游未批准，结论待确认」。
- `sign_off_id is None` → 审核链状态显示「未签署」。
- 章节**顶部**显式声明：「本工程分析由 AI 骨架生成，所有数值与结论待工程批准，不构成施工依据」。

---

## 6. provenance 展示方案

- 模块级 `provenance`（dict）：展开为「`wind_pressure.w_k`: verified/pending」形式，置于每模块 h2 小结的「字段溯源」段（复用 `small` 样式）。
- 跨模块上游信号（如 `intermediate.w_k.verified`）：在状态总览或审核链子节以「风压 w_k 信号：已提供 / 待确认」呈现。
- 严格沿用 `_escape` 防注入；`provenance` 为空 → 显示「暂无溯源」。

---

## 7. 测试方案

新增 `tests/agents/test_report_engineering.py`，**复用** `_base_dossier()` 模式（本文件独立构造 `engineering` 键 mock，不依赖 test_report_provenance 的内部函数）。断言维度：

1. **五模块展示**：构造含五接口 `as_full()`（全部 pending）的 `engineering` 键 → PDF 合法且文本含「风压分析」「玻璃安全分析」「型材分析」「五金分析」「安装风险分析」五个 h2 锚点。
2. **pending badge**：工程章节省略 `[已验证]`，且含 `[待确认]`（`BADGE_PENDING`）。
3. **engineering 章节生成**：文本含「工程智能分析」章节锚点 + 五个子节锚点（总览/详情/可信等级/审核链/待确认）。
4. **gaps 展示**：某模块 `gaps` 含 `E-TH-01` / `upstream_pending` → 文本可检索到该待确认项。
5. **provenance 展示**：模块 `provenance` 含 `wind_pressure.w_k` → 文本含该溯源键。
6. **无 engineering 结果时兼容**：dossier 无 `engineering` 键（或 `None`）→ PDF 仍合法、不抛异常、章节显示「暂无数据/待补充」。

**防回归**：断言现有子串锚点（一/二/三/四/六章）仍存在于含 engineering 的 dossier，确保插入章节未破坏既有三 Agent 渲染链路。

**红线自检覆盖**：测试断言「工程章节省略 `[已验证]`」——若任何实现误将 pending 渲染为绿标，测试失败。

---

## 兼容性 / 风险

- **零破坏**：`dossier` 无 `engineering` 键时走 `if not engineering` 早退分支；既有三 Agent 章节代码不变。
- **as_full 契约**：依赖 Phase 3.2.1 已交付的 `as_full()`（八字段 + interface），字节结构稳定。
- **防编造**：工程章节省略真实数值（result 恒空），gaps/threshold_refs 透出 `E-TH-0x`/`upstream_pending` 仅为待确认标记，非数值；扫描 `check_fabrication.py` 应 0 命中（数字仅出现在 E-TH-0x 标识符，被豁免）。
- **命名**：新增 `_build_engineering_section` 函数 + 在 `generate_project_report` 装配；导出 `__all__` 不变。

## 结论

设计确认：本 Sprint **仅接线、不新增工程能力**，严格守红线。下一步经主理人确认后进入实现（修改 `agents/report/generator.py` + 新增测试），再跑 `local_ci.sh` 要求 8/8、coverage ≥88.38%。
