# BOIP Phase 3.2 Sprint 3.2.4 — 工程阈值治理准备阶段完成报告

> 身份：BOIP AI 工程治理负责人
> 阶段性质：**阈值治理体系准备（Governance Preparation）**——只建立治理体系，不填真实参数、不开启 engineering_enabled、不输出 engineering_approved。
> 完成时间：2026-07-30
> 状态：DESIGN_DONE，等待主理人审核。未进入 3.2.4 实施（verified.json 真实化，须单独书面授权）。

---

## 1. 修改文件清单

本阶段为**纯设计 / 治理准备**，未修改任何生产代码、未修改任何 `verified.json`、未新增测试文件、未运行 `local_ci.sh`。

| 类型 | 文件 | 说明 |
|---|---|---|
| 设计文档（任务1+2+4+5） | `.ai/tasks/phase3.2.4_threshold_governance_design.md` | 七章节 + 附录A/B/C：当前 E-TH 结构分析 / 阈值生命周期 / source_ref / 专家审核流程 / 双签字段规范 / 版本管理 / 回滚 + verified.json 治理方案 + 安全门禁 + 测试方案 |
| 审计流程文档（任务3） | `.ai/tasks/phase3.2.4_threshold_audit_flow.md` | 专家提交→主理人审核→专家复核→verified→可用于 engineering 的 append-only 审核链流程 |
| 完成报告 | `.ai/reviews/phase3.2.4_threshold_governance_report.md` | 本报告 |
| SSOT 同步 | `.ai/project_status.json` | `phase_3_2_status` → `SPRINT_3_2_4_DONE` + `phase_3_2` 信封新增 3.2.4 条目 |
| SSOT 同步 | `.ai/roadmap_v2.md` | 3.2 里程碑条补充 Sprint 3.2.4 DONE |

**未变动**：`agents/engineering/thresholds/verified.json`、Design 侧 `verified.json`、`threshold_loader.py`、`validation.py`、`review_log.py`、所有测试文件、CI 脚本。

---

## 2. 架构影响

- **治理层定义**：在不改动既有双签基础设施（`threshold_loader.is_fully_verified` / `ExpertBackedEngineeringValidation` 四签状态机 / `review_log` append-only 链）的前提下，把"阈值如何从占位安全转正"的规则显式化。
- **生命周期升级方案**：提出将 `verified`（布尔）升级为四态枚举 `threshold_status`（draft / review / verified / deprecated），并保留 `verified` 作为镜像，确保与既有 `mgmt_signed` 判定零冲突。本阶段仅规范，未落地。
- **字段规范**：定义未来 `verified.json` 单条阈值目标形态（含 `threshold_id / value / unit / source_ref / version / verified_by / verified_at / expert_verified_by / expert_verified_at / threshold_status`），并明确 `source_ref` 由自由文本升级为结构化对象（standard / clause / edition / url / retrieved_at）。
- **关键发现 — D-TH 双签缺口**：Design 侧 `D-TH-01~05` 当前**仅主理人单签位**（`verified_by` / `verified_at`），无专家签字位。若不在真实化阶段补 `expert_verified_by` / `expert_verified_at`，则 `profile` / `glass_safety` 接口（复用 D-TH-01 / D-TH-02）在 `is_fully_verified` 语义下**永远无法 approved**。治理方案给出路径一（补专家签字位，推荐）与路径二（放宽复用接口双签要求，不推荐），由主理人验收时定夺。
- **门禁闭环**：定义"进入 `verified=true`"的九项门禁与"进入 `engineering_enabled=true`"的六项门禁，明确 3.2.5 开启须独立书面授权，不与 A/B 系列混同。

---

## 3. 测试结果

本阶段**不新增测试、不运行 CI**（纯设计交付，无代码改动）。既有测试基线维持 Sprint 3.2.3 状态：
- `local_ci.sh` 8/8 全绿（backend 379 passed@88.47% / Jest 29@93.15% / 编造·硬编码扫描 0 命中）。

测试方案（附录C）作为未来 3.2.4 实施 / 3.2.5 灰度的验收清单：覆盖非法 verified、缺 source_ref、缺双签（含 D-TH 单签回归）、版本冲突、回滚五类。

---

## 4. 风险

| 风险 | 等级 | 说明 | 缓解 |
|---|---|---|---|
| D-TH 双签缺口 | 高 | D-TH-01~05 现状仅主理人单签，`profile`/`glass_safety` 无法 approved | 治理默认路径一（补专家签字位）；真实实施待主理人定夺 |
| 单位枚举缺失 | 中 | E-TH-02/03/05/06 的 `unit` 为 `pending_verification` | 治理要求升级为受控单位枚举，禁止自由字符串 |
| source_ref 自由文本 | 中 | 当前为占位长文本 | 结构化改造须向后兼容解析 |
| 授权耦合 | 高 | `engineering_enabled=true` 须独立书面授权 | 门禁 B.2 显式单列，不与 A/B 混同 |
| 版本不兼容回滚 | 中 | schema_version 升级后旧加载器拒绝 | 加载器按 version 解析，不兼容降级为全 pending（零行为变化） |

---

## 5. 安全检查（红线守约）

- ✅ **未修改 verified.json 真实 value**：工程侧 E-TH-01~06 与 Design 侧 D-TH-01~05 全部 `value=null` 未动。
- ✅ **未设置 verified=true**：两库全部 `verified=false` 未动。
- ✅ **未开启 engineering_enabled**：`config.yaml` 中 `orchestrator.engineering_enabled` 仍为 `false`，未触碰。
- ✅ **未填写真实专家姓名**：所有 `signer` 形态规范为角色标识符（principal-001 / expert-001），未出现真实姓名。
- ✅ **未填写真实规范数值**：所有 `value` / `source_ref` 保持 `pending_verification` 占位，无未验证真实数字。
- ✅ **全 pending_verification**：治理文档与方案中所有数值态均声明 `pending_verification`。
- ✅ **防编造扫描**：本阶段仅新增两份设计/流程文档，业务参数（如基本风压、型材壁厚、五金承载力、腐蚀等级、安装风险矩阵等）全部保持占位，未与未验证真实数字同行；标识符 E-TH-xx / D-TH-xx 被扫描器豁免；`check_fabrication.py` 对新增文档零命中（全程 pending_verification 占位）。

---

## 6. 下一步

- 等待主理人审核本报告与两份治理文档。
- 审核通过后，若主理人对 D-TH 双签路径（路径一/二）与门禁清单无异议，**单独书面授权**方可进入：
  - **Sprint 3.2.4 实施**（verified.json 真实化：双签填充、source_ref 结构化、版本管理落地，仍须 `engineering_enabled=false` 直到 3.2.5）；
  - **Sprint 3.2.5**（engineering_enabled 开启灰度，须独立书面授权，不可与 A/B 系列混同）。
- 本阶段按指令已完成并停止，不进入 3.2.4 实施、不进入 3.2.5。
