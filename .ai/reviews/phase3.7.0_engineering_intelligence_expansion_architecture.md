# Phase 3.7.0 — Engineering Intelligence Expansion Architecture（工程智能能力扩展架构）

> 文档类型：架构设计报告（非实现、非激活）
> 生成身份：BOIP AI Chief Architect
> 前置状态：Phase 3.3 ✅ Knowledge Infrastructure / 3.4 ✅ Activation Governance / 3.5 ✅ Human Activation Governance / 3.6 ✅ Evidence Governance
> 本轮红线（继承）：① 不自动开启 `engineering_enabled` ② 不输出 `engineering_approved` ③ 不绕过 `UnifiedActivationGate` ④ 不伪造工程参数
> 关键事实：**本轮未收到任何真实人工证据/参数载荷**，AI 仅基于**真实代码只读扫描**做能力盘点与架构设计，不产出任何真实工程数值，不开启 `engineering_enabled`，不输出 `engineering_approved`。

---

## 0. 执行事实声明

- 本报告的每一项能力结论均来自对 `agents/engineering/` 真实源码的逐文件读取（见 §1 代码锚点），**未虚构任何工程能力**。
- 真实激活态：`agents/config.yaml` → `orchestrator.engineering_enabled = false`（本轮核实）。
- 5 个工程计算单元（WindPressure / Glass / Profile / Hardware / InstallationRisk）当前**均为符号结构装配器**，不产生真实数值（`result=""`，`verification_status=PENDING_VERIFICATION`，中间量 `value=None/verified=False`）。
- 已有的 "Engineering Intelligence" 能力集中在 `agents/engineering/knowledge/intelligence/`（关系发现 / 质量评估 / 冲突检测），**全部只读、review_required 恒 True、不自动 merge/approve/delete**。
- 结论：**BOIP 当前工程智能 = 符号结构装配 + 只读知识分析**，尚无数值推理、无真实参数、无成本/图纸解析实现。这正是 3.7.0 要规划扩展的方向。

---

## 1. 任务1：当前工程 Agent 能力矩阵（基于真实代码扫描）

### 1.1 五工程计算单元能力矩阵

| Agent | 代码锚点 | 接口标识 | 上游依赖 | 消费阈值 | 真实计算？ | AI 推理？ | 当前产出 | 状态 |
|---|---|---|---|---|---|---|---|---|
| **WindPressure** | `calc/wind_pressure.py` `WindPressureCalculator` | `wind_pressure` | Environment / Design / Project（均为 inferred/unavailable） | E-TH-01, E-TH-02, E-TH-03 | ❌ 符号占位 | ❌ 确定性装配 | `result=""` + `intermediate`(w_0/mu_s/mu_z/beta/w_k 全 None) + `gaps` | `PENDING_VERIFICATION` |
| **Glass（玻璃安全）** | `calc/glass_safety.py` `GlassSafetyCalculator` | `glass_safety` | **wind_pressure**（跨模块闸门：上游须 `Engineering_Approved` 且 w_k 真实可得） | D-TH-02 | ❌ 符号占位 | ❌ 确定性装配 | `result=""` + `intermediate`(t/A/support/sigma_g/sigma_allow/K/A_max 全 None) | `PENDING_VERIFICATION` |
| **Profile（型材）** | `calc/profile.py` `ProfileCalculator` | `profile` | **wind_pressure**（同上跨模块闸门） | D-TH-01 | ❌ 符号占位 | ❌ 确定性装配 | `result=""` + `intermediate`(t/I/W/A/f/E/L/sigma/delta 等全 None) | `PENDING_VERIFICATION` |
| **Hardware（五金）** | `calc/hardware.py` `HardwareCalculator` | `hardware` | **profile**（跨模块闸门：上游须 `Engineering_Approved`；**禁止重算型材受力**） | E-TH-04 | ❌ 符号占位 | ❌ 确定性装配 | `result=""` + `intermediate`(F_demand/F_hardware/load_class/cycle_life 等全 None) | `PENDING_VERIFICATION` |
| **InstallationRisk（安装风险）** | `calc/installation_risk.py` `InstallationRiskCalculator` | `installation_risk` | **glass_safety + profile + hardware**（末端聚合，三上游须 `Engineering_Approved`；**禁止重算玻璃重量/型材/五金**） | E-TH-05, E-TH-06 | ❌ 符号占位 | ❌ 确定性装配 | `result=""` + `intermediate`(Risk_total/lift_condition/D_safe 等全 None) | `PENDING_VERIFICATION` |

> 接口→阈值映射（`threshold_loader.INTERFACE_THRESHOLD_MAP`，运行时核实）：
> `wind_pressure → (E-TH-01, E-TH-02, E-TH-03)`；`glass_safety → (D-TH-02)`；`profile → (D-TH-01)`；`hardware → (E-TH-04)`；`installation_risk → (E-TH-05, E-TH-06)`。
> 规则常量（符号级，无数值）：`WIND_PRESSURE_FORMULA="w_k = beta * mu_s * mu_z * w_0"`；`GLASS_SAFETY_FORMULAS` / `PROFILE_FORMULAS` / `HARDWARE_FORMULAS` / `INSTALLATION_FORMULAS`（`rules/*.py`）。

### 1.2 工程智能支撑层（Knowledge Intelligence，Phase 3.3.9 已建，只读）

| 组件 | 代码锚点 | 能力 | 是否只读 | 是否自动决策 |
|---|---|---|---|---|
| `KnowledgeRelationshipEngine` | `knowledge/intelligence/relationship.py` | 发现 4 类候选关系：parent_child / related / duplicate_candidate / conflict_candidate | ✅ 纯函数只读 | ❌ 仅产生 candidate，禁止 approve/merge/delete |
| `KnowledgeQualityAnalyzer` | `knowledge/intelligence/quality.py` | 5 维质量评分（completeness / source_strength / validation_status / freshness / dependency_integrity），权重为 pending_verification 策略常量 | ✅ 只读 | ❌ 不主动产生 `Engineering_Approved` |
| `KnowledgeConflictDetector` | `knowledge/intelligence/conflict.py` | 检测 3 类冲突：parameter / source / status（悬垂引用），`review_required` 恒 True | ✅ 只读 | ❌ 永不自动解决 |
| `ObsidianToBoipConnector` | `knowledge/connector.py` | Obsidian→BOIP 单向采集 + 7 态生命周期（Captured→…→Engineering_Approved→Deprecated）+ SourceRef 绑定（C1-C6）+ Expert 资格/范围/SoD 校验 | ✅ 不写 verified.json、不翻 enabled | ❌ 不代签/不代授权 |

### 1.3 能力矩阵结论

- **已具备（符号级 / 只读）**：五模块计算结构装配、跨模块依赖闸门、溯源标签（provenance）、gaps 检测、证据生成、知识关系/质量/冲突的只读分析、知识 ingestion 与 7 态生命周期。
- **缺失（待建，属 3.7 扩展目标）**：真实数值计算（依赖双签阈值 + `engineering_enabled`）、图纸解析、方案自动生成与比选、成本/BOM 计算、图遍历式知识推理、跨 Agent 编排调度器（现有为函数级跨模块闸门，非运行时编排）。
- **红线约束下的本质**：所有"智能"当前都是**结构化装配 + 只读分析**，任何"结论"均 `PENDING_VERIFICATION`，真实决策必须由人类在阈值双签 + 显式开启 `engineering_enabled` 后作出。

---

## 2. 任务2：Engineering Intelligence Roadmap

> 规划 5 条能力路线。每条标注：**当前代码态 / AI 辅助范围 / 人工审核必过点**。所有路线在 `engineering_enabled=false` 时仅产出候选，不产出批准结论。

### 2.1 图纸解析（Drawing Parsing）
- **当前态**：无独立图纸解析模块。几何/开启形式/玻璃配置当前以 `inferred` 占位进入 Design candidate（见 `wind_pressure._read_provenance` 等）。Vision 多模态能力在 Phase 2 已接入（腾讯混元 TokenHub），但未接入工程计算链路。
- **AI 辅助**：从 CAD/PDF/照片提取门窗洞口尺寸、开启形式、玻璃配置、楼层高度类别 → 生成 Design candidate 的 `field_provenance`；自动标注"测量/推理"来源。
- **人工审核**：尺寸实测值核验、规范条款映射（如 GB 50009 / JGJ 214）、解析结果签收。
- **里程碑**：`Vision → DesignCandidate` 适配器；解析结果进入 `KnowledgeItem`（knowledge_type=`drawing_parse`）并绑定 source_ref。

### 2.2 方案生成（Solution Generation）
- **当前态**：5 计算单元可产出**符号 scaffold**（结构装配 + gaps），但无"方案比选/参数化变体"。
- **AI 辅助**：基于 Design candidate + 阈值库生成多组型材/玻璃/五金参数化变体；用符号 scaffold 做可行性预筛（仅排除硬冲突，不评优劣数值）。
- **人工审核**：最终方案选型、`Engineering_Approved` 由人类在主理人+专家双签后作出；AI 不得替选。
- **里程碑**：`SolutionGenerator` 编排 `WindPressure→Glass/Profile→Hardware→InstallationRisk` 链，输出候选集（全部 `PENDING_VERIFICATION`）。

### 2.3 成本计算（Cost Calculation）
- **当前态**：**未实现**（代码中无 cost / BOQ / pricing 模块）。
- **AI 辅助**：从方案 BOM（型材长度/截面、玻璃面积/厚度、五金件清单）生成材料用量清单；结合 `Case`/`Rule` 中的单价规则做估算草稿。
- **人工审核**：单价来源（`source_ref` 须 `verified_source`）、地区系数是非、最终报价签署；成本结论 `PENDING_VERIFICATION` 直至人工确认。
- **里程碑**：新增 `calc/cost.py` + `rules/cost_rules.py`，单价以 `KnowledgeItem(knowledge_type=cost_rule)` + `Case`（历史工程）驱动。

### 2.4 知识推理（Knowledge Reasoning）
- **当前态**：已有只读三类分析（关系/质量/冲突）。缺图遍历、缺基于图谱的检索增强（RAG 旁路已在 3.4 防护）。
- **AI 辅助**：在 §3 定义的 Knowledge Graph 上做遍历推理（如"某 Threshold 被哪些 KnowledgeItem/Case 引用→冲突面"）、质量加权检索、冲突聚类。
- **人工审核**：所有推理产物进入"待人工复核"队列（`review_required=True`）；`merge/deprecate/approve` 由人类经 ESW 窗口决定。
- **里程碑**：`KnowledgeGraphEngine`（图谱存储 + 遍历 API）；与 `KnowledgeRelationshipEngine` 衔接，将 candidate 升级为可查询边。

### 2.5 多 Agent 协作（Multi-Agent Orchestration）
- **当前态**：跨模块闸门为**函数级**（`_is_wind_pressure_approved` / `_is_profile_approved` / `_is_upstream_approved`），无运行时编排器。
- **AI 辅助**：声明式编排（DAG：wind_pressure 为根，glass/profile 并行，hardware 依赖 profile，installation_risk 聚合三者）；依赖解析、失败短路、gaps 归并。
- **人工审核**：编排结果仍受 `UnifiedActivationGate` 约束；整体 `engineering_enabled` 与 `engineering_approved` 只能由人类终端置位。
- **里程碑**：`agents/engineering/orchestration.py`（DAG scheduler，复用现有跨模块闸门函数）。

---

## 3. 任务3：Knowledge Graph 需求

### 3.1 五类实体（基于真实数据模型）

| 实体 | 真实来源 | 关键字段 |
|---|---|---|
| **KnowledgeItem** | `knowledge/connector.py::KnowledgeItem`（13 核心字段） | `knowledge_id, knowledge_type, parent_knowledge_id, domain, linked_entities[], author, validation_status(7 态), content_hash` |
| **Case** | **待建**（建议 `knowledge_type=case` 落于 KnowledgeItem，或独立 `cases.json`） | `case_id, project_ref, used_threshold[], used_rule[], cost_ref, outcome` |
| **Rule** | `rules/*.py`（符号公式常量）+ 建议 `knowledge_type=rule_candidate` | `rule_id, formula, applies_to_interface, source_ref` |
| **Threshold** | `thresholds/verified.json` + `threshold_entry_sessions.json` | `threshold_id(E/D-TH-*), value(None), verified(False), domain` |
| **Expert** | `knowledge/experts.json` | `expert_id, qualification_status, sign_scope[], sod_role` |

### 3.2 实体关系图（节点 + 边 + 基数 + 方向）

```
KnowledgeItem ──linked_entities──▶ Threshold        (references, 1:N, 方向 KI→TH)
KnowledgeItem ──author──────────▶ Expert            (authored_by / verified_by, N:1)
KnowledgeItem ──parent_knowledge_id▶ KnowledgeItem   (parent_child, N:1, 自环)
KnowledgeItem ──source──────────▶ SourceRef         (sourced_from, N:1; spec_sources.json)
Threshold    ◀──consumed_by─────── CalcAgent         (used_by, 1:N; INTERFACE_THRESHOLD_MAP)
Rule         ──applies_to────────▶ CalcAgent         (applies, 1:N; rules/*.py)
Case         ──cites────────────▶ KnowledgeItem      (cites, N:M)
Case         ──cites────────────▶ Threshold          (cites, N:M)
Case         ──cites────────────▶ Rule               (basis, N:M)
Case         ──cites────────────▶ Expert             (witnessed_by, N:M)
Expert       ──signs────────────▶ KnowledgeItem      (signs, 1:N; ExpertBinder + 双签 session)
Expert       ──signs────────────▶ Threshold          (signs, 1:N; threshold_signing_sessions.json)
```

### 3.3 机器可读关系 schema（KG 边定义）

```json
{
  "kg_version": "phase3.7.0-draft",
  "entities": ["KnowledgeItem", "Case", "Rule", "Threshold", "Expert", "SourceRef", "CalcAgent"],
  "edges": [
    {"type": "references",        "from": "KnowledgeItem", "to": "Threshold",   "cardinality": "1:N", "via": "linked_entities",        "direction": "KI→TH", "auto_resolve": false},
    {"type": "authored_by",       "from": "KnowledgeItem", "to": "Expert",      "cardinality": "N:1", "via": "author",                 "direction": "KI→EX", "auto_resolve": false},
    {"type": "parent_child",      "from": "KnowledgeItem", "to": "KnowledgeItem","cardinality": "N:1", "via": "parent_knowledge_id",    "direction": "child→parent", "auto_resolve": false},
    {"type": "sourced_from",      "from": "KnowledgeItem", "to": "SourceRef",   "cardinality": "N:1", "via": "source",                 "direction": "KI→SR", "auto_resolve": false},
    {"type": "used_by",           "from": "Threshold",     "to": "CalcAgent",   "cardinality": "1:N", "via": "INTERFACE_THRESHOLD_MAP","direction": "TH→CA", "auto_resolve": false},
    {"type": "applies",           "from": "Rule",          "to": "CalcAgent",   "cardinality": "1:N", "via": "rules/*_FORMULAS",        "direction": "RULE→CA","auto_resolve": false},
    {"type": "cites",             "from": "Case",          "to": "KnowledgeItem","cardinality": "N:M","via": "used_knowledge[]",        "direction": "CASE→KI","auto_resolve": false},
    {"type": "cites",             "from": "Case",          "to": "Threshold",   "cardinality": "N:M", "via": "used_threshold[]",        "direction": "CASE→TH","auto_resolve": false},
    {"type": "basis",             "from": "Case",          "to": "Rule",        "cardinality": "N:M", "via": "used_rule[]",             "direction": "CASE→RULE","auto_resolve": false},
    {"type": "witnessed_by",      "from": "Case",          "to": "Expert",      "cardinality": "N:M", "via": "expert_ref[]",            "direction": "CASE→EX","auto_resolve": false},
    {"type": "signs",             "from": "Expert",        "to": "KnowledgeItem","cardinality": "1:N","via": "ExpertBinder+signing",    "direction": "EX→KI", "auto_resolve": false},
    {"type": "signs",             "from": "Expert",        "to": "Threshold",   "cardinality": "1:N", "via": "threshold_signing_sessions","direction":"EX→TH", "auto_resolve": false}
  ],
  "invariants": [
    "I1: 任一边的创建/解析不修改 engineering_enabled",
    "I2: Expert→* signs 边仅由人类在双签 session 中落库，AI 不代签",
    "I3: ConflictCandidate/ConflictReport.review_required 恒 True，不自动 merge/delete",
    "I4: Threshold.value 仍为 None 时，used_by 链不得产生真实数值结论",
    "I5: Case 为新增实体，其 cites 边仅引用已 Source_Verified 及以上态的实体"
  ]
}
```

---

## 4. 任务4：Phase 3.7 架构边界（AI 辅助 vs 人工审核）

### 4.1 边界总原则
- **AI 辅助（可在 `engineering_enabled=false` 下执行，产出候选/分析）**：符号结构装配、gaps/溯源生成、只读知识分析（关系/质量/冲突）、图纸解析草稿、方案变体预筛、BOM/成本草稿、图谱遍历推理、多 Agent 编排调度。
- **人工审核（强制 human-in-loop，AI 不代决）**：真实阈值双签（`verified=true` + `value` 填充）、`engineering_enabled` 显式置位、`engineering_approved` 输出、专家/主理人签署、冲突 merge/deprecate、图纸尺寸实测核验、最终方案与报价批准。
- **fail-closed 不变量**：任何 AI 辅助产物默认 `PENDING_VERIFICATION`；跨模块闸门（§1.1）与 `UnifiedActivationGate`（§0）确保无真实结论可在未双签/未开启时流出。

### 4.2 能力边界矩阵

| 能力 | AI 辅助范围 | 人工审核必过点 |
|---|---|---|
| 风压/玻璃/型材/五金/风险计算 | 符号 scaffold + 公式装配 + gaps | 真实阈值双签 + `enabled` + `approved` |
| 图纸解析 | 几何/配置提取 + 来源标注 | 实测尺寸核验 + 规范条款映射签收 |
| 方案生成 | 参数化变体 + 硬冲突预筛 | 方案选型 + `Engineering_Approved` |
| 成本计算 | BOM + 单价估算草稿 | 单价 source_ref + 地区系数 + 报价签署 |
| 知识推理 | 图谱遍历 + 质量加权检索 + 冲突聚类 | `review_required` 队列由人类 merge/deprecate/approve |
| 多 Agent 协作 | DAG 编排 + 依赖解析 + 失败短路 | 整体受 `UnifiedActivationGate` 约束，enabled/approved 仅人类置位 |
| 知识 ingestion | Obsidian→BOIP 抽取 + 7 态 + C1-C6 + 专家资格校验 | 专家 actual 签署（ExpertBinder 仅校验不落签） |

### 4.3 与红线的对应
- 红线①（不自动开 enabled）：所有 AI 辅助路径不调用 `can_write_engineering_enabled`（真实代码 `read_boundary.can_write_engineering_enabled()=False`），enabled 仅人类在 `config.yaml` 显式置位。
- 红线②（不输出 approved）：`KnowledgeQualityAnalyzer` 不主动产生 `Engineering_Approved`；计算单元 `result=""`；所有 `verification_status` 止步 `PENDING_VERIFICATION`。
- 红线③（不绕过 Gate）：跨模块闸门 + `UnifiedActivationGate` 双层 fail-closed；编排器（2.5）复用既有关卡函数。
- 红线④（不伪造参数）：本报告及未来 3.7 实现中，凡代码未双签的数值一律 `None/pending_verification`，零硬编码工程常数。

---

## 5. 六红线守约汇总（本轮）

| # | 红线 | 本轮遵守 |
|---|---|---|
| 1 | 不自动开启 `engineering_enabled` | ✅ 未调用任何写 enabled 路径；真实 `config.yaml` 仍为 `false` |
| 2 | 不输出 `engineering_approved` | ✅ 全文未输出 approved；所有状态止步 `PENDING_VERIFICATION` |
| 3 | 不绕过 `UnifiedActivationGate` | ✅ 架构设计复用现有 fail-closed 闸门，未设计任何绕过 |
| 4 | 不伪造工程参数 | ✅ 能力矩阵/路线图/KG 全部基于真实代码；零虚构数值、零硬编码常数 |
| 5 | 不创建 ReleaseApproval | ✅ 未创建 |
| 6 | 不 AI 代签/代授权 | ✅ ExpertBinder 仅校验资格/范围/SoD，不落 `expert_verified_by/verified_by` |

---

## 6. 交付物清单

1. `.ai/reviews/phase3.7.0_engineering_intelligence_expansion_architecture.md`（本报告，含 §1–§5）
2. `.ai/project_status.json` → 新增 `task_status.phase_3_7.3.7.0` 块
3. `.ai/roadmap_v7.md` → 新增 Phase 3.7.0 章节

---

## 7. 激活态与停止声明

- **`engineering_enabled = false`**：真实读取 `agents/config.yaml` `orchestrator.engineering_enabled = false` 确认。
- **未输出 `engineering_approved`**。
- **ESW 窗口维持 `OPEN_EMPTY`**（继承自 3.6.8/3.6.9）：本轮 0 真实证据/参数进入。
- **任务5 级 Gate 关联延续 3.6.9 实证**：证据/能力状态变化均不自动开启 `engineering_enabled`（真实代码 `config_loader` 只读 / `read_boundary.can_write=False` / `unified_activation_gate` 强断言 `is False`）。
- **按指令停止**：完成架构设计即止，不进入编码实现、不开启 enabled、不输出 approved。
- **后续解锁路径（纯人工）**：主理人+专家经 ESW 窗口提交真实双签阈值（E/D-TH-* `verified=true` + 真实 `value`）→ 人类终端显式置 `engineering_enabled=true` → 人类对方案/报价作 `Engineering_Approved`。AI 仅在该状态下执行数值计算与编排，且不替代任何人工签署。
