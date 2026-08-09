# Phase 3.2.2 ReportGenerator 工程章节接线 — 完成报告

> 身份：BOIP AI 产品化架构工程师
> 阶段：BOIP Phase 3.2 Sprint 3.2.2（工程结果产品化展示）
> 日期：2026-07-30
> 状态：**SPRINT_3_2_2_DONE**（已停止，等待主理人验收，不进入真实审核闭环 3.2.4）

---

## 1. 修改文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `agents/report/generator.py` | 修改 | 新增 `_build_engineering_section()`；`generate_project_report` 解析 `engineering` 键并装配「五、工程智能分析」章节（原免责章顺延为「六」）；`_build_disclaimer_section` labels 增加 engineering；模块 docstring dossier 形态补充 `engineering`；`__all__` 增加 `_build_engineering_section` |
| `tests/agents/test_report_engineering.py` | 新增 | 8 个测试函数，覆盖五模块展示 / pending badge / 工程章节生成 / gaps / provenance / 无结果兼容 / 防回归 |
| `.ai/tasks/phase3.2.2_report_engineering_design.md` | 新增 | 设计确认（七章节） |
| `.ai/reviews/phase3.2.2_report_engineering_report.md` | 新增 | 本报告 |

**未改动**（红线）：`agents/engineering/calc/*.py`（计算逻辑）、`agent.py`、`validation.py`、`verified.json`、`engineering_enabled=false` 配置。

---

## 2. 架构影响

- **消费契约**：ReportGenerator 现在直接消费 `EngineeringCalculationResult.as_full()`（Phase 3.2.1 交付的八字段 + interface 结构），无需中间转换层。
- **接入点**：dossier 新增可选 `engineering` 键，形态为 `{interface: as_full()}` 字典 / 单 as_full 对象 / as_full 列表；`_build_engineering_section` 归一化为结果 dict 列表，强类型容错。
- **章节编排**：原「五、免责与待确认声明」顺延为「六」，工程章节插入为「五」，与既有三 Agent 章节（一/二/三/四）并列，PDF 页码自然延展。
- **复用**：`_badge_for`（pending=[待确认] 红色）、`_list_flowable`、`_as_str`、`_as_list`、`_section_safe`、`_escape`、`_badge_table_style` 等既有安全 helper 全部复用，零崩溃约定延续。
- **审核链状态子节**：可视化 `sign_off_id`（None→「未签署」）、`verification_status`（pending→「待工程批准」），为未来 3.2.4 真实签署预留渲染通路。

---

## 3. 测试结果

`bash scripts/ci/local_ci.sh` → **8/8 全绿**：

- Backend pytest **362 passed**（较 3.2.1 的 354 净增 8），coverage **88.43%**（≥88.38% 达标）
- Frontend Jest **29 passed**@93.15%
- Ruff 0 违规；ESLint 0 error
- 业务数字 + key 指纹扫描 **0 命中**；硬编码业务配置扫描 **0 命中**
- Local CI passed

新增 `test_report_engineering.py` 关键断言：
- 五模块锚点（风压/玻璃/型材/五金/安装风险）齐全
- 工程章节省略 `[已验证]` 且含 `[待确认]`
- 工程章节 + 五子节（总览/详情/可信等级/审核链/待确认）齐全
- gaps 中 `upstream_pending` 与 `E-TH-01` 透出
- provenance 键 `wind_pressure.w_k` 透出
- 无 `engineering` 键 / `None` 时 PDF 合法不抛、显示「暂无数据/待补充」
- 防回归：既有一/二/三/四/六章锚点未被破坏

---

## 4. 风险

| 风险 | 等级 | 缓解 |
|---|---|---|
| R-32-2-1 误显已验证 | 低（已闭环） | 全 pending → `verification_status` 恒 pending_verification；`_badge_for` 仅对 `measured/verified` 等级返回绿标，而工程 as_full 不携带该等级；测试断言 `[已验证]` 不在工程章节出现 |
| R-32-2-2 计算逻辑被误改 | 无 | 本 Sprint 未触碰 `calc/*.py`，as_full 契约由 3.2.1 锁定 |
| R-32-2-3 dossier 缺键崩溃 | 极低 | `_section_safe` + 早退分支；测试覆盖无键 / None |
| R-32-2-4 章节编号漂移 | 低 | 已统一顺延为「六、免责」，测试锚点校验 |

---

## 5. 兼容性验证

- **as_full 字节兼容**（3.2.1 已验证）：ReportGenerator 仅读取 as_full 字段，不依赖任何子类特有属性，五模块继承重构对报告层透明。
- **Agent 输出 → dossier 透传**：`EngineeringAgent.invoke` 的 `analyses` 为 as_interface 四键；未来接入时由编排层将 `as_full()` 结果注入 dossier["engineering"]，本报告层接口已 ready，无需再改。
- **既有 PDF 既有测试不破**：`test_report_provenance.py` 全过（其 dossier 无 engineering 键，走兼容分支）。
- **防编造守约**：工程章节省略真实数值（result 恒空），gaps/threshold_refs 透出 `E-TH-0x`/`upstream_pending` 仅为待确认标记（标识符被 `check_fabrication.py` 豁免），扫描 0 命中。

---

## 红线自检

✅ 未修改工程计算逻辑 ✅ 未填写真实工程参数（E-TH-01~06 仍标识符透出、result 恒空）✅ 未修改 `verified.json` ✅ 未开启 `engineering_enabled`（仍 false）✅ 未输出 `engineering_approved` ✅ 全 `pending_verification` ✅ 防编造/硬编码扫描 0 命中。

## 下一步

等待主理人验收本 Sprint；验收通过 + 授权后进入 **Sprint 3.2.3（签署演练：ExpertBackedEngineeringValidation 双签流程演练，仍 enabled=false）**；真实审核闭环（C 系列：3.2.4 verified.json 真实化 + 3.2.5 enabled 开启灰度）须主理人单独书面授权，不可与 A/B 系列混同。仍须 `engineering_enabled=false` 守约直至明确授权。
