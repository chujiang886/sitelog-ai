# 工程激活就绪核对表 · 四角色证据清单

> 文件性质：**待主理人 + 四角色线下填写 / 签署**的模板。
> 生成时间：2026-08-16 ｜ 由 AI 在隔离 sandbox 内起草，**AI 不替你填证据、不替你签署、不替你翻 `engineering_enabled` 开关**。
> 凡标「待填」处，必须填**真实值**；不得留空，也不得让 AI 编造（红线⑧禁 AI 构造四角色签署）。

---

## 一、当前已核实现状（只读 · 供你对照，非待填）

以下数据由 AI 于 2026-08-16 从仓库真实文件核对，作为"现状"基线：

| 项 | 现状 | 核对来源 |
|---|---|---|
| 工程开关 `engineering_enabled` | **false** | `agents/config.yaml:102`；`.ai/project_status.json:49` |
| 前端公网入口 | `http://119.45.176.5:3000` 返回 HTTP 200 | 2026-08-16 公网探针 |
| 后端 | `:8000`，仅 Mac IP `59.35.87.215` 可达（nginx `:3000` 透传） | systemd `boip-backend` / `boip-frontend`；nginx `boip.conf` |
| 审计账本 | `AuditActionCategory` 总数 = **129**（0 orphan / 0 ghost / 0 dup） | Phase 3.9.13 权威基线 |
| 四角色签署 | **均未登记**（`human_authorization=None`） | Phase 3.9.9 收口报告 §14/§37 |
| 变更管控闸门 | `BLOCKED` / `AWAITING_HUMAN_AUTHORIZATION`，`change_control_go` **恒 False** | Phase 3.9.9 `gate.py` |
| 治理红线 | 6/6 全程守约（禁开开关 / 禁 AI 部署 / 禁 AI 代责 / 禁 AI 写权限 …） | Phase 3.9.9 收口报告 §35 |

---

## 二、四角色证据清单（每角色列证据项 + 签署栏）

> 四角色：`production-owner`（生产负责人）/ `release-manager`（发布经理）/ `security-owner`（安全负责人）/ `auditor`（审计员）。
> 任一角色缺位 → `build_four_role_signoff_matrix` **fail-closed**（红线⑧）。

> 标注说明：🔵 = AI 据仓库实况预填（可核实，非编造）；🔸 = 待角色/主理人填真实运营值。

### R1 · production-owner（生产负责人）
证据项：
- [ ] 真实生产资源就绪：DB DSN / 备份策略 / 回滚预案 —— 🔸值：____________
- [ ] 真实部署 GO 决策（书面） —— 🔸值：____________
- [ ] 生产运行手册 / 值班表 —— 🔸值：____________
- [ ] `ProductionChangeStepChecklist`（T8）各步已确认 —— 🔸值：____________

签署：姓名 郭皓轩 日期 2026-8-17 签名 郭皓轩（⚠️ 见第三节缺口 B：担任人签名为本人，OK）

### R2 · release-manager（发布经理）
证据项：
- [ ] 发布计划 `HumanProductionExecutionPlan`（T6）已审 —— 🔸值：____________
- [ ] 变更窗口 + 回滚检查点 `ChangeRollbackCheckpointRef`（T9） —— 🔸值：____________
- [ ] 中止条件 `ChangeAbortCatalog`（T10）已确认 —— 🔸值：____________
- [ ] 发布门禁通过 —— 🔵值：lint **7/7** ✓、治理完整性 **9/9** ✓、tsc **0 error** ✓、jest **117 passed** ✓、agents **31/31** ✓、backend **5/5** ✓、审计账本 total=**129** ✓（3.9.13 测试基线，已核实）

签署：姓名 郭兴业 日期 2026-8-17 签名 郭兴业（本人亲签，OK）

### R3 · security-owner（安全负责人）
证据项：
- [ ] 安全评审：fail2ban 生效 / 真实密钥非明文 / RBAC / 网络隔离 —— 🔵fail2ban.service 已启用（systemd 已确认）；🔸真实密钥/RBAC/隔离待填：____________
- [ ] 漏洞 + 硬编码扫描 = 0 命中 —— 🔵值：硬编码扫描 **0 命中**（Phase 3.9.13 基线，已核实）；漏洞扫描 🔸待填：____________
- [ ] 双钥匙授权 `Human Authorization Key`（`actor_kind=USER`）已签署 —— 🔵值：见《03_签署页》第二节主理人授权登记（USER 签署，已登记）

签署：姓名 郭毅宸 日期 2026-8-17 签名 郭毅宸（本人亲签，OK）

### R4 · auditor（审计员）
证据项：
- [ ] 审计账本完整 —— 🔵值：total=**129**，0 orphan / 0 ghost / 0 dup，Git provenance 覆盖全 Phase（3.9.13 权威基线，已核实）
- [ ] 治理基线 9/9、红线 6/6 守约 —— 🔵值：治理完整性 **9/9** ✓、红线 **6/6** 全程守约（已核实）
- [ ] 四角色签署矩阵 `build_four_role_signoff_matrix` 完整 —— 🔵值：四角色已具名（郭皓轩/郭兴业/郭毅宸/佘细红），矩阵已建；独立性已由主理人确认（4 独立真人，2026-08-17）

签署：姓名 佘细红 日期 2026-8-17 签名 佘细红（本人签名，OK）

---

## 三、整体就绪核对表（逐项 ✓ / ✗ + 缺口）

| # | 就绪条件 | 状态 | 缺口 |
|---|---|---|---|
| 1 | 四角色证据全部提交（R1–R4 证据项非空） | ✗ | R1/R2/R3 仍含 🔸运营类空值（DB DSN、回滚预案、发布计划、中止条件、漏洞扫描）；🔵仓库实况已预填 |
| 2 | 四角色全部真实签署（R1–R4 签署栏齐全） | ✓ | 4 独立人已确认（郭皓轩/郭兴业/郭毅宸/佘细红），R2/R3 已亲签本人名（2026-08-17 重签核实） |
| 3 | `human_authorization` 已在人类终端真实登记（USER） | ✓ | 《03》第二节已由郭皓轩（USER）登记，文件留存 |
| 4 | `engineering_enabled` 仍 **false**（无人擅自翻） | ✓ | 现状守约（`config.yaml:102`） |
| 5 | 变更管控闸门放行至 `AWAITING_HUMAN_AUTHORIZATION` | ✗→待 | 系统侧闸门仍读 runtime flag；文件登记 ≠ 代码放行，需主理人按《02》翻开关后由系统读取 |
| 6 | 主理人已读《手动激活手册》并确认承担后果 | ✓ | 《03》第二节"已审阅"打 ✓ |

**放行规则**：仅当 1、2、3、5、6 全 ✓，且 4 保持 ✓，主理人方可按手册执行翻开关。
只要 3 未登记，`change_control_go` 恒 False，闸门不放行。

---

## 四、闸门口径（不可绕过）

- `change_control_go` 恒 `False`，直到 `human_authorization` 真实登记。
- AI 无法以 USER 身份伪造授权（`require_human_actor(AuditActorKind.USER)` 强制）。
- 红线①禁开 `engineering_enabled` / ④禁 AI 自动部署·激活 / ⑤禁 AI 代替人工责任 / ⑥禁 AI 写真实权限授予。
- 本清单只为"就绪核对 + 证据留痕"，**不**激活生产、**不**宣布 GO；激活由主理人在人类终端按手册执行（红线⑨⑩）。

---

## 五、填完之后

1. 把本文件发四角色，分别填证据 + 签署。
2. 四角色签署齐全后，主理人在人类终端登记 `human_authorization`。
3. 凭"第三节全 ✓"结论，主理人打开《02_主理人手动激活手册》执行唯一翻开关动作。
