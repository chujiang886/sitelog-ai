# BOIP Phase 3.2 Sprint 3.2.3 — ExpertBackedEngineeringValidation 双签流程演练

- **生成日期**：2026-07-30
- **身份**：BOIP AI 工程审核体系负责人
- **性质**：演练（Drill），**非开启真实工程审核**。本 Sprint 不修改任何生产代码、不开启 `engineering_enabled`、不填写真实参数、不输出真实 `engineering_approved`，全程 `pending_verification`。
- **依据**：
  - `agents/engineering/validation.py`（含 `ExpertBackedEngineeringValidation`）
  - `agents/engineering/review_log.py`（append-only 审核链）
  - `agents/engineering/threshold_loader.py`（双签判定 `mgmt_signed` / `expert_signed`）
  - `tests/agents/test_engineering_validation.py`（Sprint A 既有测试，本 Sprint 不改动）
- **目标**：验证 `ExpertBackedEngineeringValidation` 的四签状态机（`structure_valid` / `threshold_verified` / `expert_signed` / `engineering_enabled`）与 `review_log` 事件—签名链路的正确性，**仅以测试级内存模拟完成，绝不触碰真实 `verified.json` 与 `config.yaml`**。

---

## 1. 当前 validation 流程分析

`ExpertBackedEngineeringValidation.validate()` 目前是一条**结构校验 → 双签判定 → 红线闸门**的三段式审核链：

1. **结构校验段**：先抽取 `REQUIRED_OUTPUT_KEYS`（result / confidence / evidence / verification_status）是否齐备；不齐备直接返回 `invalid_structure`（`structure_valid=False`），**不进入阈值判定**（短路保护）。
2. **双签判定段**：结构合法时，依据 `INTERFACE_THRESHOLD_MAP` 取该接口所需阈值标识（风压接口对齐 E-TH-01、E-TH-02、E-TH-03；玻璃/型材复用 Design 侧 D-TH；五金/安装对齐 E-TH-04、E-TH-05、E-TH-06），逐项用 `mgmt_signed`（主理人核准）与 `expert_signed`（行业专家签字）判定。两条判定**任一缺失即 `False`**，一票否决。
3. **红线闸门段**：仅当 `structure_valid AND threshold_verified AND expert_signed AND engineering_enabled` 四条件**同时为真**，才输出 `engineering_approved` 并派生 `sign_off_id`；否则恒 `pending_verification`、`sign_off_id=None`。

**当前真实态（红线）**：
- `engineering_enabled` 由 `config.yaml` 的 `orchestrator.engineering_enabled` 控制，值为 `false`；
- `verified.json`（E-TH-01 至 E-TH-06）与 Design 侧 `verified.json`（D-TH-01 至 D-TH-05）全部 `value=null`、`verified=false`、双签字段为空；
- 因此真实系统闸门**永不触发** `approved` 分支，`sign_off_id` 恒为 `None`；
- 既有 `test_engineering_validation.py` 已覆盖阈值缺失 / 双签失败 / 双签成功注入 / 日志链 / enabled 保持 false / 防编造六类，但**缺少以"四签状态机矩阵全景 + 模拟签署动作链路"为视角的演练测试**，本 Sprint 补齐（新增独立测试文件，不改动既有测试）。

---

## 2. 四签状态机设计

四签状态机由四个布尔输入驱动，输出 `verification_status` 与 `sign_off_id`：

| 输入 | 含义 | 当前真实取值 |
|---|---|---|
| `structure_valid` | 四字段齐备 | 由 payload 决定（演练中恒 True） |
| `threshold_verified` | 所需阈值主理人核准齐全 | 真实 `verified.json` 全 false → False |
| `expert_signed` | 所需阈值行业专家签字齐全 | 真实 `verified.json` 双签字段空 → False |
| `engineering_enabled` | 工程审核总开关 | `config.yaml` = false |

**状态转移矩阵（本 Sprint 演练要逐一覆盖）**：

| 场景 | structure_valid | threshold_verified | expert_signed | engineering_enabled | 输出 status | sign_off_id |
|---|---|---|---|---|---|---|
| 场景1 缺结构 | **False** | （短路不判） | （短路不判） | （短路不判） | `invalid_structure` | None |
| 场景2 缺主理人核准 | True | **False** | True | —（不影响） | `pending_verification` | None |
| 场景3 缺专家签字 | True | True | **False** | —（不影响） | `pending_verification` | None |
| 场景4 四项满足但开关关 | True | True | True | **False** | `pending_verification` | None |
| 场景5 全部满足+开关开（仅注入） | True | True | True | True（测试注入） | `engineering_approved` | 16位哈希 |

**关键不变量**：
- 场景4 是红线核心保护层：`threshold_verified` 与 `expert_signed` 在测试夹具中可"模拟齐全"，但只要 `engineering_enabled=false`，`approved` 分支**永不触发**；
- 场景5 仅在**内存注入** `engineering_enabled=True` 下验证代码闸门逻辑（证明"若未来授权开启，闸门能正确派生 sign_off_id"），**不写入** `config.yaml`、**不写入** `verified.json`、**不产出**任何可用于生产的交付物；
- 真实系统从场景2/3/4 三态之一进入场景5，必须同时满足：主理人在 `verified.json` 填 `verified=true`+`verified_by`+`verified_at`、专家填 `expert_verified_by`+`expert_verified_at`、主理人显式开启 `engineering_enabled`——三者缺一即退回 pending。

---

## 3. review_log 事件模型

`review_log.py` 提供 append-only 审核链，记录"谁在何时对哪个阈值做了什么动作"，构成不可篡改溯源链：

**记录字段（八字段，确定性）**：
- `event_id`：由 `compute_event_id()` 对 `{threshold_id, action, signer_role, signer, timestamp, source_ref, prev_event_id}` 做 SHA-256 内容寻址哈希，**相同输入恒得相同哈希**（可复核、防篡改）；
- `threshold_id`：被操作的阈值标识（如 E-TH-01，pending_verification）；
- `action`：动作类型（如 `principal_approve` 主理人核准 / `expert_sign` 专家签字 / `schema_established` 种子）；
- `signer_role`：角色（principal / expert / system）；
- `signer`：签署人标识（`pending_verification`，演练中不填真实身份）；
- `timestamp`：UTC ISO8601；
- `source_ref`：来源引用（演练中标记 `test fixture pending_verification`，不指向真实文档）；
- `prev_event_id`：链指针，默认自动链接当前日志末条 `event_id`，形成链式溯源。

**追加语义**：
- `append_review_event()` 仅追加，不修改/删除历史；
- `prev_event_id` 缺省自动取 `_read_last_event_id()`（日志末条），显式传入可强制指定（演练中用于验证自定义链指针）；
- `read_log()` 回放为有序列表，损坏行静默跳过（韧性）。

**审核链与签署流程的对应**：一次完整的"双签"对应两条 `review_log` 记录——先 `principal_approve`（主理人核准），后 `expert_sign`（专家签字），后者 `prev_event_id` 指向前者，形成"主理人→专家"的有向签署链。

---

## 4. sign_off_id 生成规则

`sign_off_id` 是**审核通过态**的不可抵赖标识，仅在 `approved` 时派生（pending 态恒 `None`）：

- 由 `review_log.compute_sign_off_id()` 对 `{interface, threshold_ids, signs}` 做 SHA-256 并取前十六位；
- `signs` 仅包含"主理人与专家双签齐全"的阈值条目，元数据取 `{verified_by, verified_at, expert_verified_by, expert_verified_at}`（不含任何真实工程数值）；
- **可复核性**：复核方可用同一组签名元数据重新派生并比对，确认 `sign_off_id` 未被篡改；
- **红线约束**：演练中不调用真实 `compute_sign_off_id` 写盘路径，仅在场景5 的内存逻辑分支中验证其派生结果与"用同一夹具重算"完全一致（确定性证明）。

---

## 5. 模拟签署流程（演练，非真实签署）

本 Sprint 模拟一条"主理人核准 → 专家签字"的签署动作链，**全程内存态，不落盘**：

1. **准备内存阈值夹具**：构造 E-TH-01、E-TH-02、E-TH-03 双签齐全的内存条目（五字段 `verified=true`+`verified_by`+`verified_at`+`expert_verified_by`+`expert_verified_at` 俱全，但 `value=None`、`unit=pending_verification`），**仅用于测试逻辑，绝不写入 `verified.json`**；
2. **演练审核链写入**：用临时 `log_path` 调用 `append_review_event()` 分别追加 `principal_approve` 与 `expert_sign` 两条记录，断言第二条的 `prev_event_id` 等于第一条的 `event_id`（链正确）；
3. **演练四签判定**：用上述内存夹具构造 `ExpertBackedEngineeringValidation(thresholds=...)`，`engineering_enabled` 保持默认（读 config = false），调用 `validate(interface="wind_pressure", payload=四字段)`；
   - 断言 `threshold_verified=True`、`expert_signed=True`、`verification_status=pending_verification`、`sign_off_id=None`（场景4 红线保护）；
4. **逻辑分支验证（场景5）**：仅在内存注入 `engineering_enabled=True`，再次 `validate()`，断言 `verification_status=engineering_approved` 且 `sign_off_id` 为十六位，并用同一夹具重算的 `compute_sign_off_id` 比对一致；
   - **明确禁止**：不调用任何"写入真实 verified.json"动作、不修改 `config.yaml`、不向任何生产日志写真实签署记录；
5. **pending 保持断言**：遍历五分析接口，在真实 `load_engineering_enabled()=false` 下逐一 `validate()`，断言全部 `verification_status=pending_verification`、`sign_off_id=None`（enabled 关闭保护，真实系统视角）。

---

## 6. 测试方案

新增独立测试文件 `tests/agents/test_expert_sign_flow.py`（不改动 `test_engineering_validation.py`），覆盖五点：

1. **四签状态机矩阵**（五场景）：
   - 场景1：缺 `structure_valid`（四字段不齐）→ `invalid_structure`；
   - 场景2：缺 `threshold_verified`（仅专家签，主理人缺）→ `pending`；
   - 场景3：缺 `expert_signed`（仅主理人核准，专家缺）→ `pending`；
   - 场景4：四签满足但 `enabled=false` → `pending`（红线）；
   - 场景5：注入 `enabled=true`（仅逻辑分支）→ `approved` + `sign_off_id` 确定性。
2. **review_log 链路**：`append_review_event` 主理人→专家两条，`prev_event_id` 链式正确；`event_id` 确定性（同输入同哈希）；`read_log` 顺序与损坏行跳过。
3. **sign_off_id 确定性**：场景5 派生的 `sign_off_id` 与用同一夹具 `compute_sign_off_id` 重算完全一致；长度十六位。
4. **enabled 关闭保护**：真实 `load_engineering_enabled()=false` 下，五接口全 `validate()` 恒 `pending`、`sign_off_id=None`；`EngineeringAgent` 注入 `ExpertBackedEngineeringValidation()` 全链路无 `approved`。
5. **pending 保持**：跨五接口断言 `verification_status=pending_verification` 且不含 `engineering_approved`。

**防编造扫描自查**：测试夹具中业务词（风压等）仅以阈值标识符（E-TH-xx）或在含 `pending_verification` 标记的行内出现，不携带任何未验证真实数值；`signer` 填 `principal-001` / `expert-001` 之类**纯标识符**（非真实姓名/资质编号），`source_ref` 统一含 `test fixture pending_verification`。

**CI 门槛**：`bash scripts/ci/local_ci.sh` 须 8/8 PASS；backend 覆盖率不低于 88.43%（在 Sprint 3.2.2 基线 362 passed@88.43% 之上，新增用例仅提升边际分支覆盖，不降反升）。

---

**END（演练设计，等待主理人验收；不进入 verified.json 真实化 3.2.4）**
