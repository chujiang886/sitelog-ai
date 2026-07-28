# Phase 3.1 专家审核流程设计（phase3.1_expert_review_process.md）

- **生成**：2026-07-28（Phase 3.1 设计阶段 · 任务3）
- **身份**：BOIP AI 首席工程架构师
- **性质**：**纯流程设计，不填写任何真实工程参数、不开启 `engineering_enabled`**。
- **依据**：`agents/design/thresholds/verified.json` + `threshold_loader.py`（2.2.2 治理机制，复用）、`phase3.1_engineering_architecture_design.md` §3/§4、`ADR-phase3.1-engineering-calculation.md`
- **红线**：工程参数（风压/楼层/壁厚/评分权重/防腐等级）未经"主理人 + 行业专家"双签不得转正。

---

## 1. 阈值提交流程（Threshold Submission Workflow）

```
起草(draft) ──► 行业专家评审(expert review) ──► 主理人核准(owner approve) ──► 入库(active)
   │                  │                               │                          │
   │ value=null       │ expert_verified_by/at         │ verified_by/at            │ is_fully_verified=true
   │ source_ref=规范   │ 驳回→退回起草                  │                          │ 计算引擎可消费
   └──────────────────┴──────────────────────────────┴──────────────────────────┘
                                  每步写审核日志（§5）
```

1. **起草**：工程师/AI 生成阈值草案（`param` + 建议 `value` + `source_ref` 引用规范条款），状态 `draft`，`value` 可预填建议值但 `verified=false`。
2. **行业专家评审**：行业专家核对规范条款，确认或驳回；确认则填 `expert_verified_by` / `expert_verified_at`。
3. **主理人核准**：主理人对专家结论做最终核准，填 `verified_by` / `verified_at`。
4. **入库生效**：双签齐全 → `is_fully_verified()` 返回 `True`，`EngineeringValidation` 方可裁定 `engineering_approved`。
5. **审计留痕**：起草/评审/核准每一步写入审核日志（§5），不可篡改。

---

## 2. verified.json 扩展方案

**新建 Engineering 侧阈值库**，与 Design 侧 `agents/design/thresholds/verified.json` 同构、同加载器模式：

- 路径：`agents/engineering/thresholds/verified.json`
- 加载器：新增 `agents/engineering/threshold_loader.py`，复用 `is_fully_verified()` 语义；或复用 Design 侧 `threshold_loader` 指向 Engineering 库。
- 扩展后的条目结构（在 Design 既有字段基础上增加双签字段）：

```json
{
  "E-TH-01": {
    "param": "基本风压（wind_pressure 基准值）",
    "value": null,
    "unit": "pending_verification",
    "verified": false,
    "verified_by": null,
    "verified_at": null,
    "expert_verified_by": null,
    "expert_verified_at": null,
    "source_ref": "待专家签字填入规范条款号 pending_verification",
    "applies_to_scheme": ["economy", "comfort", "performance"]
  }
}
```

**Engineering 阈值 ID 规划（全部 `value=null` 初始态）**：

| ID | 参数 | 关联模块 |
|----|------|---------|
| E-TH-01 | 基本风压（当前 pending_verification） | wind_pressure |
| E-TH-02 | 体型系数 / 风荷载体型（pending_verification） | wind_pressure |
| E-TH-03 | 地面粗糙度类别映射（pending_verification） | wind_pressure |
| E-TH-04 | 五金承载力参数库引用（pending_verification，依赖五金库建设） | hardware |
| E-TH-05 | 腐蚀等级阈值（pending_verification） | installation_risk |
| E-TH-06 | 安装风险评级矩阵（pending_verification） | installation_risk |

> Design 侧 D-TH-01（型材壁厚）/ D-TH-02（玻璃厚度）继续由 Design 治理，Engineering 通过 `threshold_refs` 跨库引用，不重复定义。

---

## 3. verified_by（主理人签字）

- **含义**：主理人对阈值的最终核准签字人标识（姓名 / 工号 / 签名 ID）。
- **填写时机**：流程第 3 步（主理人核准）完成后写入。
- **约束**：`verified_by` 非空是 `is_fully_verified()` 的必要条件之一；为空 → 该阈值恒 `pending_verification`。
- **与现有机制兼容**：沿用 `threshold_loader.is_fully_verified()` 既有字段，不破坏 Design 侧已验收逻辑。

## 4. verified_at（主理人签字时间）

- **格式**：ISO8601（`YYYY-MM-DDTHH:MM:SS+08:00`）。
- **填写时机**：与 `verified_by` 同步骤写入。
- **约束**：与 `verified_by` 成对出现；`is_fully_verified()` 要求两者皆非空。
- **审计价值**：配合审核日志形成"谁、何时、依据哪份规范"的完整追溯链。

## 5. 审核日志（Review Log）

**独立、只追加（append-only）审计文件**：`agents/engineering/thresholds/review_log.jsonl`

每条记录（一行 JSON）：

```json
{
  "event_id": "REV-2026-0001",
  "threshold_id": "E-TH-01",
  "action": "expert_review|owner_approve|reject|submit",
  "signer_role": "industry_expert|owner",
  "signer": "专家/主理人标识",
  "at": "ISO8601",
  "source_ref": "规范条款号 pending_verification",
  "prev_event_id": "REV-2026-0000",
  "note": "自由文本"
}
```

- **不可篡改**：只追加，不修改历史；可选哈希链（`prev_event_id` 串联）增强防抵赖。
- **覆盖范围**：起草、专家评审、主理人核准、驳回退回，全部留痕。
- **查询**：提供 `get_review_history(threshold_id)` 供 UI/API 展示审核时间线。

## 6. 双签机制（Dual-Sign）

**双签 = 行业专家签字 + 主理人核准，二者皆齐备方生效。**

- **字段扩展**：条目在原 `verified/verified_by/verified_at` 基础上，新增 `expert_verified_by` / `expert_verified_at`。
- **`is_fully_verified()` 升级**（设计草案）：

```python
def is_fully_verified(entry):
    if not entry.get("verified"):
        return False
    if not entry.get("verified_by") or not entry.get("verified_at"):
        return False          # 主理人签字
    if not entry.get("expert_verified_by") or not entry.get("expert_verified_at"):
        return False          # 行业专家签字
    return True                # 双签齐全
```

- **失败语义**：任一签字缺失 → 该阈值 `pending_verification`，依赖它的 Engineering 模块结论保持 pending，绝不报送"工程确认"。
- **与审核链联动**：`ExpertBackedEngineeringValidation.validate()` 读取双签状态作为 `expert_signed` 门；双签 + 结构合法 → `engineering_approved`（Level 3）。
- **防滥用**：双签字段仅由审核流程写入，AI 代码不得自动填 `verified=true` 或伪造签字（由"防编造测试"锁死，见任务4）。

---

**END**（本文件为流程设计，不含代码实现；执行须在主理人授权 Phase 3.1 后启动）
