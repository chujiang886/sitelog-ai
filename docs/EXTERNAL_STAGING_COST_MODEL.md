# BOIP External Staging — Cost Model (Phase 3.9.12, T6)

> 文档类型：三档成本模型（Track A，规划用）
> 阶段：Phase 3.9.12 External Staging Provisioning & Operator Readiness
> 关联：T3 Provider ADR、T5 BOM、T31 StagingCostGuard

---

## 0. 重要声明（fail-closed）

- 本文所有金额均为**示意性区间（illustrative ranges）**，币种 ¥ (CNY)。
- **不是真实报价**：真实费用须由主理人持真实账号在云厂商计价器/账单中确认。AI **不**调用计费 API、不读取真实账单。
- 成本护栏（`StagingCostGuard`，T31）将设置预算上限；任何 IaC plan 估算超过上限 → `BLOCKED`（不自动放行）。
- `engineering_enabled = false`；本模型仅用于「就绪规划」，不产生任何真实计费。

---

## 1. 三档成本档位

| 档位 | 目标 | 适用 | 资源覆盖 |
|---|---|---|---|
| **A. minimum viable** | 仅证明 provisioning 通路可用 | 单开发者/CI 验证 | 8 资源最小形态，无 HA |
| **B. recommended** | 有意义的预生产验证 | 团队级 staging | 8 资源均衡形态，基础冗余 |
| **C. production-like** | 逼近生产的预生产 | 发布前 staging | 8 资源多 AZ/HA，完整可观测 |

---

## 2. 各档位资源形态

| 资源 | A. minimum viable | B. recommended | C. production-like |
|---|---|---|---|
| `database` | 单节点小规格 PG（如 2C4G） | 主备 PG（如 4C8G + 只读副本） | 多 AZ 高可用 PG 集群 |
| `secret_provider` | 基础密钥库（按量） | 密钥库 + 自动轮换 | 密钥库 + KMS + 审计 |
| `identity_provider` | SaaS 免费层 / 自建最小 | SaaS 标准层 / 自建 | SaaS 企业层 / 高可用自建 |
| `object_storage` | 小容量标准桶 | 标准桶 + 低频层 | 多桶 + 跨区域复制 |
| `telemetry` | 基础日志/指标（短保留） | 日志+指标+追踪（中保留） | 全量可观测（长保留） |
| `alert_sandbox` | 单通知通道 | 多通道 + 静默 | 多通道 + 值班演练 |
| `domain_tls` | 单子域 + 免费 cert | 子域 + 托管 cert 自动续期 | 多子域 + 证书治理 |
| `deployment_target` | 单节点 K8s/单容器 | 小集群（2-3 节点） | 多节点 HA 集群 + 镜像仓库企业版 |

---

## 3. 示意性月度成本区间（¥，须真人确认）

| 档位 | 示意区间（¥/月） | 备注 |
|---|---|---|
| A. minimum viable | ¥300 – ¥1,500 | 极小规格，按量为主 |
| B. recommended | ¥1,500 – ¥6,000 | 团队级均衡 |
| C. production-like | ¥6,000 – ¥20,000+ | 逼近生产，HA 成本显著 |

> 上述区间**不包含**数据出网流量、突发峰值、第三方 SaaS 订阅费；真实数字以云厂商账单为准。AI 不保证准确性。

---

## 4. 预算护栏（StagingCostGuard，T31）

- 在 `infrastructure/staging/` IaC 旁置 `cost_budget` 声明（默认档位 B 上限，示意 ¥6,000/月）。
- `terraform/opentofu plan` 后由 `StagingCostGuard` 解析估算（或人工填入估算值），超过 `cost_budget` → `BLOCKED`。
- 护栏**不**阻断 Track B 真实决策：真人可在人类终端上调高预算并附理由，但须经 release-manager/security-owner 双签。

---

## 5. 成本优化建议（规划用）

1. staging 用**抢占/竞价/按量**实例，禁预留（production 才预留）。
2. 对象存储设生命周期：热→冷→归档。
3. 遥测保留期 staging 短于 production（如 7-15 天）。
4. 非工作时间可缩容/暂停非关键资源（需 Runbook 明确，禁影响生产）。
5. 镜像仓库仅保留必要 tag，定期清理。

---

## 6. 与 BOM/Provider 一致性

- 成本形态对齐 T5 BOM 的 8 资源与 owner 角色。
- 供给方价格以 T3 ADR 首选腾讯云为基准；覆写 provider 时成本形态需重新估算（护栏重算）。
- 所有「已付费/已预算批准」状态 PENDING（Track B），不伪造。
