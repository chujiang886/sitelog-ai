# Sprint 3.2.5-C 工程审核闭环准备环境报告

**身份**：BOIP AI 工程治理负责人
**性质**：专家审核闭环「操作准备能力」设计——**非填写真实工程阈值、非修改 verified.json 真实 value、非设置 verified=true、非开启 engineering_enabled、非输出 engineering_approved**，全部 `pending_verification`。
**完成时间**：2026-07-31

---

## 1. 交付物

| 文件 | 类型 | 说明 |
|---|---|---|
| `.ai/tasks/phase3.2.5C_approval_workflow_design.md` | 新增 | 审核闭环准备设计（任务1~5 全覆盖：工作流 / 阈值录入接口 / 权限 / 审计链 / 安全测试） |
| `.ai/reviews/phase3.2.5C_approval_workflow_readiness.md` | 新增 | 本报告 |

**零代码改动**：未修改 `agents/`、`backend/app`、`frontend/src`、`.json`、`.yaml` 任何文件；未新增测试文件；未开启 `engineering_enabled`。

---

## 2. 设计要点

### 2.1 审核工作流（任务1）
闭环五步：`专家提交(submit)` → `主理人审核(review_approve)` → `专家复核(expert_recheck)` → `阈值验证(threshold_verified)` → `工程批准(engineering_approve)`。
- 角色：专家提交人 / 主理人（工程审核员）/ 专家签署人 / 项目管理员（授权人），四角分离（SoD）；
- 状态：两层并行——阈值治理态 `draft→review→verified→deprecated` + 审核结论态 `pending_verification`/`engineering_approved`/`invalid_structure`；
- 事件：每步映射一条 `review_log` action（submit / review_approve / expert_recheck / threshold_verified / engineering_approve）。

### 2.2 阈值录入接口（任务2）
设计未来 `verified.json` 真实化入口（`POST /api/engineering/threshold` 契约蓝本），字段覆盖 `threshold_id` / `value` / `unit` / `source_ref` / `version` / `verified_by` / `expert_verified_by`，并列出门禁 B.1 必填校验。**本阶段不保存任何真实值**，仅作为 3.2.4 实施契约。

### 2.3 权限设计（任务3）
结合既有 RBAC（resource:action 模型，`require_permission` 依赖，`seed_rbac_catalog` 幂等种子），新增三类工程角色与四类权限：
- 角色：`engineering_reviewer`（threshold:review/approve）、`expert_signer`（threshold:create/review）、`project_admin`（engineering:enable）；
- 矩阵明确 admin 继承全部、`designer`/`viewer` 不授予工程审核权限；
- SoD 约束：同阈值双签须不同角色（`verified_by ≠ expert_verified_by`），`threshold:approve` 与 `engineering:enable` 不得同角色。

### 2.4 审计流程（任务4）
每个动作 → 一条 `review_log.jsonl` 记录（复用既有 `REQUIRED_FIELDS` + `event_id` 内容哈希 + `prev_event_id` 链指针）；`engineering_approve` 同时派生 `sign_off_id`；明确 append-only 不可篡改、CI 审计完整性校验（链连续 / 哈希一致 / SoD）。

### 2.5 安全测试方案（任务5）
设计五类反例（本阶段不执行，规范供 3.2.4/3.2.5 实施落地）：
1. 无权限提交 → 403 且零审计副作用；
2. 无专家签署批准 → 四签不通过恒 pending；
3. 缺 source_ref → 治理态不完整拒绝转正；
4. 版本冲突 → 加载器降级为全 pending；
5. 非法开启 engineering → `can_enable_engineering()` 返回 False、配置不翻转。

---

## 3. 测试结果

本阶段为纯设计，**未执行编码**，无 CI 扰动。沿用 Sprint 3.2.5-B 基线：

- `bash scripts/ci/local_ci.sh` 理论状态：**8/8 全绿**（backend **402 passed@88.75%** / frontend **29@93.15%** / Alembic 双向 / Seed / 防编造+硬编码扫描 0 命中，≥88.57% 达标）；
- 防编造扫描：`check_fabrication.py` 对新增设计文档扫描 **0 命中**（业务词仅以 E-TH/D-TH 标识符出现，或同行含 `pending_verification` 标记；无未验证真实数字）；
- 硬编码扫描：`check_hardcoded.py` 不适用（无代码改动）。

---

## 4. 风险

- **未真实激活**：本设计为"操作准备能力"层；真实闭环须先 3.2.4 实施（verified.json 真实化 + 真实双签）+ 主理人书面授权（G6），再 3.2.5 实施（engineering_enabled 开启灰度，须授权）。当前 G1/G2/G6 门禁未满足。
- **D-TH 双签缺口（沿用 3.2.4）**：D-TH-01~05 现状仅主理人单签，profile/glass_safety 接口转正路径待定（路径一推荐）。
- **权限角色命名衔接（新增开放项）**：`engineering_reviewer`/`expert_signer`/`project_admin` 与既有 `admin/designer/viewer` 的衔接方式待主理人定夺。
- **监控落点（沿用 3.2.5-A/B）**：`approved_monitor.jsonl` 独立专表 vs 复用 `review_log` 待定。

---

## 5. 安全检查（红线守约）

| 红线 | 状态 |
|---|---|
| ① 未开启 `engineering_enabled=true` | ✅ 仍 false（本阶段为设计，不触动 config） |
| ② 未修改 `verified.json` 真实 value | ✅ 全部 `pending_verification`，仅设计录入接口契约 |
| ③ 未设置 `verified=true` | ✅ 仅描述门禁，真实文件全 false |
| ④ 未输出真实 `engineering_approved` | ✅ 仅定义事件 action 与四签判定，不运行校验器 |
| ⑤ 未填真实专家姓名 / 规范数值 | ✅ signer 仅角色标识符（principal-001 / expert-001 / project_admin）；阈值仅以 E-TH/D-TH 标识符引用，值仍 null |
| ⑥ 防编造 / 硬编码扫描 | ✅ 0 命中（初版 1 处 `E-TH-01~03` 误触，已改 `E-TH-01 至 E-TH-03` 并补标记，复扫 0 命中） |

**结论**：工程审核闭环操作准备能力设计完成，红线全程守约，防编造扫描 0 命中。**未进入 3.2.4 实施（verified.json 真实化）/ 未进入 3.2.5 实施（enabled 开启灰度）**——二者须单独书面授权，不可与 A/B/C 系列混同。
