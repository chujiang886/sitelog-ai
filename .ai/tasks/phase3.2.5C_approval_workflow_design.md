# BOIP Phase 3.2 Sprint 3.2.5-C 工程审核闭环准备环境设计

**身份**：BOIP AI 工程治理负责人
**日期**：2026-07-31
**性质**：进入真实审核闭环前的「操作准备能力」建设——**设计层面建立专家审核闭环的操作准备能力**；**非填写真实工程阈值、非修改 verified.json 真实 value、非设置 verified=true、非开启 engineering_enabled、非输出 engineering_approved**。全部保持 `pending_verification`。

---

## 0. 准备目标与范围

**目标**：在真实审核闭环（`3.2.4 实施 verified.json 真实化` + `3.2.5 实施 engineering_enabled 开启灰度`，二者须单独书面授权）之前，先把"一次完整的专家审核闭环该如何被操作、被授权、被审计"规范清楚，使后续真实闭环有可执行的角色分工、权限门禁、录入接口与审计回溯。

**红线（全程守约）**：① 不填真实工程阈值 ② 不改 verified.json 真实 value ③ 不置 verified=true ④ 不开 engineering_enabled ⑤ 不输出 engineering_approved。

**范围**：
- 操作角色：专家提交人 / 主理人（工程审核员）/ 专家签署人 / 项目管理员（授权人）
- 操作权限：`threshold:create` / `threshold:review` / `threshold:approve` / `engineering:enable`
- 录入接口：未来 verified.json 真实化入口（`threshold_id` / `value` / `unit` / `source_ref` / `version` / `verified_by` / `expert_verified_by`）
- 审计链路：从 submit 到 engineering_approve 每一步进入 `review_log`（append-only）
- 安全测试：无权限 / 缺签 / 缺源 / 版本冲突 / 非法开启五类反例

**依赖既有能力（不重复造轮子）**：
- `ExpertBackedEngineeringValidation` 四签状态机（structure_valid / threshold_verified / expert_signed / engineering_enabled）
- `review_log.jsonl` 不可篡改链（event_id / threshold_id / action / signer_role / signer / timestamp / source_ref / prev_event_id）
- `threshold_loader.governance_status` / `is_fully_verified`（3.2.4-A）
- 灰度门禁 `can_enable_engineering()` G1~G6（3.2.5-B）
- 既有 RBAC 框架（roles / permissions / role_permissions / user_roles，resource:action 模型）

> 本设计文档仅规范角色 / 权限 / 状态 / 事件 / 录入接口 / 审计链路 / 安全测试，**不落地任何代码、不修改 verified.json、不修改 config.yaml、不新增测试文件**。全部阈值在本阶段一律 `pending_verification`，不出现任何真实工程取值。

---

## 1. 任务1：审核工作流设计

### 1.1 闭环五步

```
专家提交(submit)
   │  draft ──▶ review
   ▼
主理人审核(review_approve)        —— 主理人核准位（mgmt_signed: verified_by / verified_at）
   ▼
专家复核(expert_recheck)          —— 专家签字位（expert_signed: expert_verified_by / expert_verified_at）
   ▼
阈值验证(threshold_verified)      —— 双签 + source_ref 齐备 + value 非空 → threshold_status=verified
   ▼
工程批准(engineering_approve)     —— 校验器四签齐 + engineering_enabled + 灰度门禁通过 → engineering_approved
```

> 步骤 1~4 仅改变阈值治理态（draft → review → verified）与双签位；步骤 5 是 `ExpertBackedEngineeringValidation.validate()` 在运行时对"结构合法 + 阈值 verified + 专家 signed + engineering_enabled"四签的判定，不修改阈值本身。

### 1.2 角色（Role）

| 角色 | 标识 | 职责 | 对应签字位 |
|---|---|---|---|
| 专家提交人 | `submitter`（系统账号或专家角色标识符） | 发起阈值草拟 / 数值填写，提交评审 | 无签字位（仅提交动作） |
| 主理人（工程审核员） | `principal`（角色标识符，如 principal-001） | 主理人审核（review_approve）+ 阈值验证核准 | `verified_by` / `verified_at`（mgmt_signed） |
| 专家签署人 | `expert`（角色标识符，如 expert-001） | 专家复核（expert_recheck）签署 | `expert_verified_by` / `expert_verified_at`（expert_signed） |
| 项目管理员（授权人） | `project_admin`（角色标识符） | 工程批准授权（engineering:enable，G6） | 仅授权动作，不替代双签 |

> 分离职责（SoD）：主理人 ≠ 专家签署人 ≠ 项目管理员，任何人不得同时持有 `threshold:approve` 与 `engineering:enable`，避免"自审自批"。（pending_verification）

### 1.3 权限（Permission）

基于既有 RBAC 的 `resource:action` 模型，新增四类工程审核权限（详见任务3）：

| 权限 | 允许动作 | 典型角色 |
|---|---|---|
| `threshold:create` | 提交阈值草案（draft） | 专家提交人 / 专家签署人 |
| `threshold:review` | 主理人审核 + 专家复核（双签动作） | 工程审核员 / 专家签署人 |
| `threshold:approve` | 阈值验证核准（置 verified=true） | 工程审核员 |
| `engineering:enable` | 授权开启某接口 engineering_enabled（G6） | 项目管理员 |

> 四签状态机与权限映射：structure_valid（结构契约，校验器自检）/ threshold_verified（= mgmt_signed，需 `threshold:approve`）/ expert_signed（= expert_signed，需 `threshold:review` 的 expert 侧）/ engineering_enabled（需 `engineering:enable` 授权）。

### 1.4 状态（State）

两层状态并行：

**(A) 阈值治理态 `threshold_status`（3.2.4 定义）**
`draft → review → verified → deprecated`

**(B) 审核结论态 `verification_status`（校验器输出）**
`pending_verification`（默认）/ `engineering_approved`（四签齐 + enabled）/ `invalid_structure`（结构非法）

**状态转换矩阵**：

| 当前态 | 触发动作 | 下一态 | 约束 |
|---|---|---|---|
| draft | submit | review | 需 `threshold:create` |
| review | review_approve + expert_recheck | verified | 双签 + source_ref 齐备 + value 非空 |
| review | reject | draft / deprecated | 主理人驳回 |
| verified | engineering_approve（运行时） | （仍 verified，仅产出 approved 结论） | 不修改阈值本身 |
| verified / deprecated | 规范修订 / 错误 / 作废 | deprecated | 显式废止 |

### 1.5 事件（Event）

每一步动作在 `review_log.jsonl` 追加一条事件（见任务4）。事件类型枚举：

| 事件 action | 触发步骤 | signer_role | 前置态 → 后置态 |
|---|---|---|---|
| `submit` | 专家提交 | submitter | draft → review |
| `review_approve` | 主理人审核 | principal | review 中（mgmt_signed） |
| `expert_recheck` | 专家复核 | expert | review 中（expert_signed） |
| `threshold_verified` | 阈值验证 | principal + expert | review → verified |
| `engineering_approve` | 工程批准（运行时） | project_admin（授权） | 产出 engineering_approved 结论 |

---

## 2. 任务2：阈值录入接口设计（未来 verified.json 真实化入口）

> 本阶段**仅设计接口契约，不保存任何真实值**。未来在 **3.2.4 实施**（须单独书面授权、仍 enabled=false）中落库。

### 2.1 录入入口形态（设计草案）

推荐以"受 RBAC 保护的写入端点 + 结构化请求体"形态落地（未来实施，非本阶段）：

```http
POST /api/engineering/threshold
Authorization: Bearer <token>   # 需要 threshold:create 权限（专家提交人 / 专家签署人）
Content-Type: application/json

{
  "threshold_id": "E-TH-01",          # 唯一键
  "value": null,                       # 真实工程数值（本阶段 null，pending_verification）
  "unit": "Pa",                        # 受控单位枚举
  "source_ref": {                      # 结构化规范引用
    "standard": "待专家填规范代号 pending_verification",
    "clause": "待专家填条款号 pending_verification",
    "edition": "待专家填版本年份 pending_verification",
    "url": "待专家填可复核链接 pending_verification",
    "retrieved_at": null
  },
  "version": "1.0",                    # 语义化版本
  "verified_by": null,                 # 主理人角色标识符（本阶段 null）
  "expert_verified_by": null           # 行业专家角色标识符（本阶段 null）
}
```

### 2.2 字段契约

| 字段 | 必填条件 | 校验（门禁 B.1，3.2.4 附录B） |
|---|---|---|
| `threshold_id` | 必填，须匹配 `INTERFACE_THRESHOLD_MAP` 键空间 | 悬空引用 → 拒绝 |
| `value` | verified 状态时必填且为数值 / 受控枚举 | null + verified=true → 拒绝 |
| `unit` | 必填，受控枚举（Pa / N / mm / 无量纲） | 自由字符串 → 拒绝 |
| `source_ref.standard` / `source_ref.clause` | verified 状态时必填 | 任一空 → 治理态不完整 → 拒绝转正 |
| `version` | 必填 | 未声明 → 拒绝 |
| `verified_by` / `verified_at` | verified 状态时必填（mgmt_signed） | 缺 → 拒绝 |
| `expert_verified_by` / `expert_verified_at` | verified 状态时必填（expert_signed） | 缺 → 拒绝 |

### 2.3 录入流程与门禁

```
请求 → RBAC 鉴权(threshold:create) → 字段校验 → 落库 draft → 追加 review_log action=submit
                                                          │
                                                          ▼
                              后续 review_approve / expert_recheck / threshold_verified 逐步填充双签位
                                                          │
                                                          ▼
                          治理门禁 B.1 全满足 → threshold_status=verified, verified=true（仅 3.2.4 实施）
```

> 本阶段**不执行**任何落库、不构造任何双签、不置 verified=true。接口设计仅作为 3.2.4 实施的契约蓝本。

---

## 3. 任务3：权限设计（结合现有 RBAC）

### 3.1 现有 RBAC 基础

既有 `backend/app/core/security.py` 已建立：`roles`（admin / designer / viewer）、`permissions`（resource:action）、`role_permissions`、`user_roles` 四表；`require_permission(perm)` 依赖在端点做 403 校验；`seed_rbac_catalog` 幂等写入目录。本设计与该框架**同构扩展**，不另起炉灶。

### 3.2 新增工程审核角色与权限

新增角色（建议，沿用角色标识符语义，不绑定真实姓名）：

| 角色 | 标识（建议） | 授予权限 |
|---|---|---|
| 工程审核员 | `engineering_reviewer` | `threshold:review`, `threshold:approve` |
| 专家签署人 | `expert_signer` | `threshold:create`, `threshold:review` |
| 项目管理员 | `project_admin` | `engineering:enable` |

> 既有 `admin` 默认继承全部四类权限（superuser，沿用现有 ROLE_PERMISSIONS 全量授予逻辑）；`designer` / `viewer` 不授予工程审核权限。

### 3.3 角色—权限矩阵

| 角色 \ 权限 | threshold:create | threshold:review | threshold:approve | engineering:enable |
|---|:---:|:---:|:---:|:---:|
| admin | ✅ | ✅ | ✅ | ✅ |
| engineering_reviewer | — | ✅ | ✅ | — |
| expert_signer | ✅ | ✅ | — | — |
| project_admin | — | — | — | ✅ |
| designer | — | — | — | — |
| viewer | — | — | — | — |

### 3.4 分离职责（SoD）约束

- 同一条阈值的 `review_approve`（主理人）与 `expert_recheck`（专家）**必须由不同角色执行**，校验器 / 门禁须校验 `verified_by ≠ expert_verified_by`（角色标识符层面），否则 `is_fully_verified=False`；
- `threshold:approve`（阈值验证核准）与 `engineering:enable`（开启授权）**不得授予同一角色**，防止"自审自批"；
- 权限变更须经 `project_admin` 书面授权并写入 `review_log action=permission_grant`（设计预留，未来实施）。

### 3.5 端点—权限绑定（设计草案）

| 端点（未来，非本阶段落地） | 所需权限 | 说明 |
|---|---|---|
| `POST /api/engineering/threshold` | `threshold:create` | 提交阈值草案 |
| `POST /api/engineering/threshold/{id}/review` | `threshold:review` | 主理人审核 / 专家复核 |
| `POST /api/engineering/threshold/{id}/approve` | `threshold:approve` | 阈值验证核准 |
| `POST /api/engineering/{interface}/enable` | `engineering:enable` | 授权开启（仍受 G1~G6 门禁） |

---

## 4. 任务4：审计流程设计（动作 → review_log）

### 4.1 事件 Schema（复用既有 REQUIRED_FIELDS）

每条审核动作追加一条 `review_log.jsonl` 记录，字段与既有 `REQUIRED_FIELDS` 对齐：

```
event_id        : compute_event_id(...) 确定性内容哈希
threshold_id    : 关联的阈值 ID（如 E-TH-01）
action          : submit / review_approve / expert_recheck / threshold_verified / engineering_approve
signer_role     : submitter / principal / expert / project_admin
signer          : 角色标识符（principal-001 / expert-001 / admin-001，禁止真实姓名）
timestamp       : UTC ISO8601
source_ref      : 本次动作的规范引用摘要（与阈值 source_ref 对齐，可空于 submit 阶段）
prev_event_id   : 上一条事件 event_id（链指针，append-only 链式溯源）
```

### 4.2 全链路映射

| 工作流步骤 | review_log action | signer_role | 链式约束 |
|---|---|---|---|
| 专家提交 | `submit` | submitter | prev_event_id = 当前链尾（或 null 起链） |
| 主理人审核 | `review_approve` | principal | prev_event_id = submit.event_id |
| 专家复核 | `expert_recheck` | expert | prev_event_id = review_approve.event_id |
| 阈值验证 | `threshold_verified` | principal + expert | prev_event_id = expert_recheck.event_id；且双签位已齐 |
| 工程批准 | `engineering_approve` | project_admin | prev_event_id = 该接口最新阈值事件；同时派 sign_off_id |

### 4.3 不可篡改与复核

- **append-only**：`review_log.jsonl` 仅追加，历史不可改 / 删；回滚仅在链尾追加 `deprecated` 事件（3.2.4 §7），绝不物理删除。
- **确定性 ID**：`event_id` 由动作元数据内容哈希派生，任何篡改将导致哈希不一致，校验器 / CI 可检测。
- **sign_off_id**：`engineering_approve` 通过时，由 `ExpertBackedEngineeringValidation` 调用 `review_log.compute_sign_off_id()` 派生十六位标识（接口 + 阈值 + 双签元数据），复核时可由同一元数据重算比对。
- **监控专表（开放项）**：`engineering_approve` 是否另写 `approved_monitor.jsonl`（3.2.5-A/B 推荐独立专表）待主理人定夺；两表均 append-only、均不记录真实工程数值。

### 4.4 审计完整性校验（CI 门禁预留）

未来 CI 须校验：同一 `threshold_id` 的事件链 `submit → review_approve → expert_recheck → threshold_verified` 连续（prev_event_id 无断裂）、`event_id` 重算一致、SoD（verified_by ≠ expert_verified_by）。任一失败即阻断合入。

---

## 5. 任务5：安全测试方案（设计，非本阶段执行）

> 下列为「安全测试规范」，真实测试用例在 **3.2.4 实施 / 3.2.5 实施**（须单独书面授权）中落地，本阶段不新增测试文件。

### 5.1 无权限提交
- **场景**：持有 `viewer` 角色（无任何 threshold 权限）的用户调用 `POST /api/engineering/threshold`。
- **期望**：`require_permission("threshold:create")` 返回 403；**不写入任何 review_log 事件**（提交被拒，无落库）。
- **覆盖**：端点鉴权 + 审计零副作用。

### 5.2 无专家签署批准
- **场景**：一条阈值仅 `mgmt_signed`（verified_by 在位）但缺 `expert_verified_by`。
- **期望**：`expert_signed=False` → `ExpertBackedEngineeringValidation` 四签不通过 → `verification_status=pending_verification`，**绝不输出 engineering_approved**；重点回归 D-TH 单签现状（3.2.4 §5）。
- **覆盖**：双签语义、SoD。

### 5.3 缺 source_ref
- **场景**：录入请求 `source_ref.standard` 或 `source_ref.clause` 为空（或不完整）。
- **期望**：`threshold_loader.governance_status` 返回 `GOV_REASON_SOURCE_REF_INCOMPLETE` → `is_fully_verified=False` → 阈值无法转正（verified 强制 false / pending_verification）。
- **覆盖**：3.2.4 附录 B.1 门禁第 3 条。

### 5.4 版本冲突
- **场景**：同 `threshold_id` 存在两个 `version` 且缺 `superseded_by` 指针；或 `schema_version` 不兼容。
- **期望**：加载器拒绝加载该阈值（`load_governed_thresholds` 对 deprecated / 冲突降级），整条接口降级为全 `pending_verification`，零行为变化。
- **覆盖**：3.2.4-A `load_governed_thresholds` 降级语义。

### 5.5 非法开启 engineering
- **场景**：未持 `engineering:enable`（或无 G6 书面授权）即尝试置某接口 `engineering_enabled=true`；或直接调用 `can_enable_engineering()` 但 G1 / G2 / G6 未满足。
- **期望**：`can_enable_engineering()` 返回 `(False, reasons)`，配置**不被翻转**；`ExpertBackedEngineeringValidation.validate()` 因 `engineering_enabled=False` 恒 `pending_verification`；CI 门禁拦截。
- **覆盖**：3.2.5-B 门禁 G1~G6 默认拒绝、不可绕过全局闸门。

### 5.6 附加回归（建议）
- **签名链断裂**：`review_log` 缺 `prev_event_id` 或损坏行 → G4 审核链门禁阻塞；
- **专家=主理人自签**：`verified_by == expert_verified_by` → `is_fully_verified=False`；
- **监控记录泄漏**：断言 `approved_monitor.jsonl` 不含任何真实 value / 单位 / 规范条款数值。

---

## 6. 与既有红线的关系

- 本设计全程 `pending_verification`：不填真实阈值、不置 `verified=true`、不置 `engineering_enabled=true`、不输出真实 `engineering_approved`；
- 录入接口（任务2）、权限矩阵（任务3）、审计链（任务4）、安全测试（任务5）**均为契约 / 规范设计**，不落地代码、不改 `verified.json`、不改 `config.yaml`、不新增测试文件；
- 真实闭环（3.2.4 实施 verified.json 真实化 + 3.2.5 实施 enabled 开启灰度）须**单独书面授权**，不可与本阶段（C 系列准备）混同；
- 首个灰度接口仍为 `wind_pressure`（3.2.5-A 锁定），其所需 E-TH-01 至 E-TH-03 可由本准入流程独立双签转正，不依赖 D-TH 路径决策（pending_verification）。

---

## 7. 待主理人定夺的开放项

- **D-TH 双签路径**：D-TH-01~05 现状仅主理人单签，是否补 `expert_verified_by / at`（路径一，推荐）待定（沿用 3.2.4 §5）；
- **监控落点**：`approved_monitor.jsonl` 独立专表 vs 复用 `review_log action=engineering_approve`（沿用 3.2.5-A/B）；
- **权限角色命名**：`engineering_reviewer` / `expert_signer` / `project_admin` 命名与既有 `admin / designer / viewer` 的衔接方式待定；
- **真实授权流程**：`engineering:enable`（G6）的书面授权签署人与 3.2.4 双签是否同一人待定（须满足 SoD）。

---

**本阶段交付边界**：本文档为纯操作准备设计，未修改任何代码、未修改 verified.json、未修改 config.yaml、未新增测试、未开启 engineering_enabled，全部阈值保持 pending_verification。待主理人审核通过后，方可进入 3.2.4 实施（verified.json 真实化，须单独书面授权）与 3.2.5 实施（engineering_enabled 开启灰度，须单独书面授权）。
