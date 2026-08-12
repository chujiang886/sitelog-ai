# Runbook：生产发布回滚（Rollback）

> 阶段：Phase 3.9.2 — Enterprise Production Release Gate & Evidence Package Layer
> 性质：**人工操作 runbook**。本文件描述回滚路径与核对清单，**不是可执行脚本**，
> AI 阶段仅生成「描述性回滚引用」（`ReleaseRollbackReference`），**不执行真实回滚**。
> 真实回滚只能由 `production-owner` / `ops` 在真实生产事件中触发。

---

## 0. 触发条件

- 真实生产发布后出现严重故障（可用性 / 数据完整性 / 安全）。
- 自动探活失败连续超过阈值，或人工判定需回退。

---

## 1. 回滚引用（AI 阶段已产出，描述级）

来自 `ProductionReleaseService.build_rollback_reference()`（`agents/enterprise/production_release/package.py`）：

- `last_known_good_version`：上一个稳定发布版本（如 `3.9.1`）。
- `last_known_good_commit`：稳定提交哈希。
- `rollback_steps`：version / config / database 三类回滚步骤（标注 `reversible=True`）。
- `verified`：当且仅当**全部引用字段齐备**时为 `True`；缺引用即 `False`（fail-closed）。

> 该引用为**只读描述**。AI 阶段 `executed_for_real` 恒 False，绝不触碰生产实例。

---

## 2. 真实回滚执行（仅人类终端）

| # | 步骤 | 命令/动作（占位） | 验证 |
|---|------|------------------|------|
| R1 | 冻结新版本流量 | （ops 网关切换） | 入口流量 0 新版本 |
| R2 | 回退 version | 切至 `last_known_good_version` | 服务版本号回退 |
| R3 | 回退 config | 还原配置快照 | 配置 diff 清空 |
| R4 | 回退 database | 执行已验证的迁移回滚脚本 | 数据一致性校验通过 |
| R5 | 探活 | `/api/v2/ping` | 返回 `{"ok":true}` |
| R6 | 留痕 | 真实 `RollbackDrillReport` 入库（actor=USER） | 审计可溯源 |

---

## 3. 回滚后

- 通知 `production-owner` / `auditor`。
- 复盘写入故障目录（关联 `FailureScenarioCatalog`）。
- 不自动重新激活；重新激活须走 `controlled_activation.md`。

---

## 4. AI 禁区（fail-closed）

- 禁 `execute_real_rollback` / `overwrite_real_database` / `mutate_real_enterprise_record`
  （结构级禁名被 mixin 拦截）。
- AI 不得把 `PENDING_VERIFICATION` 自升为 `VERIFIED`。
- 真实回滚决策与执行只能源于人类终端。
