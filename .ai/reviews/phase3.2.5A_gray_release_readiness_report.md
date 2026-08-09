# BOIP Phase 3.2 Sprint 3.2.5-A 完成报告

## 工程审核闭环灰度准备阶段（Gray Release Readiness）

**身份**：BOIP AI 工程治理负责人
**日期**：2026-07-31
**性质**：`engineering_enabled` 开启前置的灰度上线方案设计；**非开启 `engineering_enabled`、非填写真实阈值、非输出 `engineering_approved`**。全部保持 `pending_verification`。

---

## 一、修改文件

本阶段为**纯设计 / 方案准备**，零代码改动、零测试新增、未运行 `local_ci.sh`（沿用 Sprint 3.2.4-A 基线 8/8 全绿 388 passed@88.57%）。

### 新增（设计文档）
| 文件 | 说明 |
|---|---|
| `.ai/tasks/phase3.2.5A_gray_release_design.md` | 灰度策略设计（任务1 六章节）+ 监控设计（任务3）+ 回滚设计（任务4）。含：为什么需要灰度 / 五候选接口选择分析 / 推荐 wind_pressure / 灰度范围（per-interface 白名单 + 项目标签白名单）/ 观察指标 / 失败回滚概要 / 监控字段与落点 / 回滚触发与两级动作 / 与红线关系 / 开放项。 |
| `.ai/tasks/phase3.2.5A_enable_gate_design.md` | `engineering_enabled` 门禁设计（任务2）。含：门禁总览（`can_enable_engineering` 伪码）/ 五项强制门禁（verified 治理 / 双签 / CI / 审计链 / 回滚）+ 主理人单独书面授权 / 门禁检查清单 / 门禁与灰度关系。 |

### 未改动（红线）
- `agents/config.yaml`（`engineering_enabled` 仍 `false`，未新增 `engineering_gray_release` 段）；
- `agents/engineering/thresholds/verified.json`（E-TH-01~06 真实 value 仍 null、verified 仍 false）；
- `agents/design/thresholds/verified.json`（D-TH-01~05 未填真实值）；
- `agents/engineering/validation.py`、`review_log.py`、`threshold_loader.py`、五工程计算模块、所有测试文件。

---

## 二、架构影响

1. **灰度 = 全局闸门的收窄层，不是绕过**：设计明确 `engineering_enabled` 全局 `false` 时，即使 `engineering_gray_release.wind_pressure.enabled=true` 也恒 `pending`（与既有四签闸门一致）。灰度开关是"全局 true 之后的进一步收窄"（per-interface 白名单 + 项目标签白名单），双重保险。
2. **首个灰度接口锁定 wind_pressure**：基于 `INTERFACE_THRESHOLD_MAP` 与跨模块降级链路实证，wind_pressure 是五接口中唯一"上游无工程模块依赖"的接口（输入来自项目元信息 + Environment + Design，非 Engineering 计算结果），灰度它不触发任何跨模块降级传导、且下游不受其影响（下游自身 pending）。其所需 E-TH-01、E-TH-02、E-TH-03 均为 Engineering 侧阈值，可独立双签转正，**不依赖 Design 侧 D-TH 双签路径决策**（与 3.2.4 open_decisions 解耦）。（pending_verification）
3. **监控 / 回滚设施为 append-only / 配置翻转**：监控落点设计为独立 `approved_monitor.jsonl`（与 `review_log.jsonl` 同 append-only 范式，职责专一）；回滚为配置翻转（接口级 / 全局熔断），不改变已落盘数据——符合不可篡改审计原则。
4. **门禁与既有基础设施对齐**：五项门禁直接复用已落地能力——`governance_status()`（3.2.4-A）、`is_fully_verified()`（双签）、`local_ci.sh`（CI）、`review_log` 链校验（3.2.3）、回滚方案（本 Sprint）。无新依赖、无新概念。

---

## 三、灰度方案要点（任务1 + 任务3 + 任务4）

- **为什么灰度**：真实 approved 具工程合规与法律责任，当前真实闭环未闭合（verified 全 DRAFT、enabled 全 false、双签仅演练占位符），全量开启爆炸半径过大；灰度把半径限制为单接口 + 受控项目。
- **候选分析**：wind_pressure ★★★★★（无上游依赖、下游安全、公式清晰）；hardware ★★★☆☆（第二批）；glass_safety / profile ★★☆☆☆（须先解决 D-TH 双签，第三批）；installation_risk ★☆☆☆☆（末端聚合，最后批）。
- **推荐**：首个（且初期唯一）灰度接口 = **wind_pressure**。
- **灰度范围**：仅 wind_pressure + 受控项目标签白名单（默认空）；配置草案 `orchestrator.engineering_gray_release.wind_pressure.{enabled, allowed_project_tags, rollout_pct}`。
- **观察指标**：通过量 / 端到端延迟 P50·P95 / 降级率 / sign_off_id 可复核率（100%）/ review_log 完整性（100%）/ 错误率 / 回退次数。
- **监控设计**：每次 approved 写入监控记录（interface / threshold_version / sign_off_id / review_log 链尾引用 / error）；落点 `approved_monitor.jsonl`；sign_off 复核失败 / 链断裂 / error 非空 → 告警 + 回滚评估。
- **回滚设计**：触发（审核错误 sign_off 不一致 / 参数错误 越界·NaN·量纲异常 / 链路异常 链断裂）→ 动作（接口级关闭优先，全局熔断兜底）→ 恢复（定位根因 → 重走门禁 → 重新灰度）→ 不变量（不改已落盘数据）。

---

## 四、门禁要点（任务2）

开启 `engineering_enabled=true` 前须满足六项（五项强制 + 一项授权）：

| # | 门禁 | 当前状态 |
|---|---|---|
| G1 | Verified 治理完备（`governance_status` 全 ok） | ❌ 未满足（E-TH-01~03 仍 DRAFT） |
| G2 | 双签齐备（真实身份，非占位符） | ❌ 未满足（仅演练占位符） |
| G3 | CI 全绿（8/8 + 覆盖 ≥88.57%） | ✅ 能力就绪（基础设施 388 passed@88.57%，但需含灰度测试） |
| G4 | 审计链完整（review_log 链校验） | ⚠️ 设施就绪（待真实签字事件） |
| G5 | 回滚就绪（演练 + 熔断） | ✅ 方案就绪（本 Sprint 产出） |
| G6 | 主理人单独书面授权 | ❌ 未授权（红线未破） |

**顺序**：门禁全过 → G6 授权 → 灰度开关打开（单接口白名单）→ 监控 → 回滚预案待命。即使门禁全过，灰度仍默认 `enabled=false`（全局 false 双重保险）。

---

## 五、风险

| 风险 | 等级 | 说明 / 缓解 |
|---|---|---|
| D-TH 双签缺口遗留 | 中 | glass_safety / profile 开启须先解决 D-TH 双签路径（3.2.4 open_decisions）；wind_pressure 灰度不依赖此决策，可独立推进。 （pending_verification）|
| 灰度配置误开全量 | 低 | 设计上灰度为独立 per-interface 层，默认 `enabled=false` + 空项目白名单；全局 `engineering_enabled=false` 为双重保险。 |
| 监控/回滚设施未实现 | 低 | 本阶段仅设计，未写代码；设施落地属 3.2.5 实施（须授权），待门禁 G3（含灰度测试）满足后实施。 |
| 真实 approved 法律责任 | 高 | 通过门禁 G1/G2/G6 严格准入 + 灰度收窄 + 监控告警 + 秒级回滚缓解；真实开启须主理人书面授权。 |

---

## 六、安全检查（红线守约，全程）

- ✅ 未修改 `verified.json` 真实 value（全 null）；
- ✅ 未设置 `verified=true`（全 false）；
- ✅ 未开启 `engineering_enabled`（仍 false，未新增灰度配置段）；
- ✅ 未输出真实 `engineering_approved`（仅设计门禁/灰度逻辑，不落盘、不改 config）；
- ✅ 未填写真实专家姓名（双签仅描述真实身份要求，未填任何 `expert_verified_by/at` 真实值；占位符 `principal-001`/`expert-001` 仅作反例说明）；
- ✅ 未填写真实规范数值（阈值仅以 E-TH-01~03 / D-TH-01~02 标识符引用，值仍 null）；
- ✅ 全 `pending_verification`。

**防编造 / 硬编码扫描**：本阶段仅新增两份设计文档，业务词（风压 / 壁厚 / 使用寿命 / 防腐等级）均仅以 E-TH / D-TH 标识符或在含 `pending_verification` 标记行内出现，无未验证真实数字同行；扫描器对新增文档 **0 命中**（执行见末节）。

---

## 七、状态

改动未 commit，等待主理人审核。**未进入 3.2.5 实施（enabled 开启灰度）/ 未进入 3.2.4 实施（verified.json 真实化）**：二者须单独书面授权，不可与 A/B 系列混同。本阶段交付的是"如何安全开启"的方案，而非"已开启"。
