# ADR-2.2.1：Environment 真实数据接入架构决策

- **状态**：✅ ACCEPTED（架构级决策生效；真实 API 厂商选型显式 DEFERRED，见 §11）
- **日期**：2026-07-27
- **决策人**：BOIP AI 高级研发负责人（Phase 2.2 Sprint 1，主理人授权自动执行模式）
- **依据**：`.ai/tasks/2.2.1_environment_data_design.md`（已审核通过）、`agents/environment/agent.py` 实读、2.1.6 Provider 解耦既有模式
- **红线**：本 ADR 不选定真实 API 厂商、不添加任何密钥、不引入规范类数值（风压/阈值）

---

## 1. 数据源架构决策

**采用设计文档 ADR-01 方案 C：Provider 抽象层。**

新增 `agents/environment/providers/` 包，复刻 2.1.6 LLM Provider 解耦模式：

- 抽象基类 + 具体实现分离，配置驱动（`agents/config.yaml::environment_data` 段）；
- 三模式：`disabled`（默认，零行为变化）/ `mock`（CI 与测试）/ `<真实源名>`（注册表扩展位，厂商批准后注册，本 Sprint 不实现任何真实源）；
- 否决方案 A（Agent 内直连 API：耦合、CI 无法 mock）与方案 B（独立 MCP 进程：本阶段部署面过重）。

## 2. Provider 抽象决策

- 契约层：`providers/base.py` 定义 `GeoProvider` / `WeatherProvider` ABC 与冻结数据类 `GeoResult` / `WindClimate`；
- **所有数据结果强制携带三溯源字段**：`source`（源标识）、`fetched_at`（ISO8601）、`raw_ref`（原始响应留痕引用）——缺一即构造失败（fail-fast，与 `Evidence.__post_init__` 同风格）；
- 结果携带 `real_data: bool` 真实性标记：**只有 `real_data=True`（真实外部源返回）才允许字段级 `measured`；mock/推理数据永远保持 pending_verification**；
- 工厂：`providers/factory.py`，`build_geo_provider(cfg)` / `build_weather_provider(cfg)`；`disabled → None`，`mock → Mock*`，未注册的真实源名 → 显式抛错（防错配静默降级）；提供 `register_*_provider(name, factory)` 注册表扩展点，真实厂商批准后**零改工厂**接入。

## 3. GeoProvider 方案

- 职责：地址 → 坐标/省市区（数据缺口 G1）；接口 `async geocode(address) -> GeoResult`；
- 真实厂商候选维持设计 §3.1 盘点（高德/腾讯/百度/OSM），**本 ADR 不拍板**——待主理人提供：①商用/内部使用性质；②月预算；③企业地图账号主体；
- Sprint 1 交付：抽象 + mock + disabled + 注册表扩展位；Agent 集成点在 LLM 调用之前（命中即入 facts + evidence）。

## 4. WeatherProvider 方案

- 职责：坐标 → 多年风况统计（主导风向/平均风速/统计年限，数据缺口 G3）；接口 `async wind_climate(lat, lng) -> WindClimate`；
- **明确要的是多年统计而非实时预报**（下游为 Design 建议与后续 Engineering 阶段的风压分析前置输入——具体风压数值仍属 pending_verification 签字链，不在本任务）；
- 真实厂商候选维持设计 §3.2 盘点（Open-Meteo/和风/彩云/NOAA），不拍板，同 §3 决策输入；
- 失败语义（设计 ADR-03 采纳）：Provider 失败/超时/未配置 → **降级回 LLM 推理路径，字段保持 pending + gaps 登记，invoke 永不因数据源崩溃**。真实数据只增强、绝不阻断。

## 5. ClimateZone 静态数据方案

**采用静态数据集策略，不走 API**（设计 §3.3 采纳）：

- 建筑热工区划为慢变量，做成随代码发布的 `data/climate_zones.json` 静态映射表；
- 每条记录必须带 `source` 出处；整表 `pending_verification=true` **直至主理人核对签字**（沿用 2.2.2 签字机制，Level 2 门槛，见 §7）；
- **实施排期**：表内容属规范衍生数据，未签字不得入库——落在 2.2.1 后续步骤（实施步骤表 Step 5），本 Sprint 只锁定策略，不产表。

## 6. Solar 算法方案

**采用本地天文算法策略，零 API、零密钥、零成本**（设计 §3.4 采纳）：

- 太阳高度角/方位角为确定性天文计算（NOAA 算法族），输入坐标+日期即可复算验证；
- 输出属"可复算的确定性事实"，是唯一无需外部源即可达 `measured` 的通道（算法名+版本作为 `source`，计算时间作 `fetched_at`，输入参数快照作 `raw_ref`）；
- **实施排期**：与缓存层同批（实施步骤表 Step 2），本 Sprint 锁定策略；算法实现须附对照样本测试（与公开天文表比对）后才可标 measured。

## 7. evidence 可信体系 + Environment 数据可信等级模型

沿用 `agents/base.py::Evidence` 四字段（source/observed_at/confidence/content），不改基类。

**数据可信等级模型（本 ADR 正式确立，写入 agent.md 契约）：**

| Level | 名称 | 含义 | pending_verification |
|-------|------|------|---------------------|
| **Level 0** | LLM inferred | LLM/规则常识推理（含 mock 数据） | true |
| **Level 1** | Measured source | 真实数据源返回，含出处与时间戳 | 该字段 false |
| **Level 2** | Expert verified | 主理人/专家核对签字（如气候区划表） | false（带签字记录） |
| **Level 3** | Engineering approved | 工程审核链批准（Phase 3 Engineering 验证机制） | false（带审核链记录） |

- 字段级 `confidence` 约定：`measured`（Level 1+）/ `inferred`（Level 0）/ `mock`（Level 0，显式标记防混淆）/ `unavailable`（源失败且无法推理）；
- 输出新增 **`field_provenance`** 字段级溯源映射（如 `{"prevailing_wind": "measured", "climate_zone": "inferred"}`）；
- **顶层 `pending_verification` 语义修正**（修复 Phase 1 遗留瑕疵）：存在任一非 measured 关键字段（climate_zone / prevailing_wind / solar_exposure）即为 true。LLM 成功路径从此**不再**将 pending 置 false——LLM 推理是 Level 0，永远 pending。既有断言该行为的测试同步修正（属设计 §6 已裁定的语义升级，非降低标准）。

## 8. 缓存策略

采纳设计 §7 全部决策，**实施与真实 Provider 同批**（Step 2/4，本 Sprint 无真实源可缓存，不提前实现）：

- SQLite 单表（`data/env_cache.db`，独立于业务库）；Key = `{kind}:{lat:.2f},{lng:.2f}:{schema_ver}`（1km 网格）；
- TTL：风况 30 天 / 地理编码 90 天 / 太阳轨迹不缓存（纯计算）；
- 惰性过期 + 源失败时降级返回旧值并在 evidence 标 `stale=true`（留痕不隐瞒）；
- 只存坐标网格与统计值，**不存用户原始地址**。

## 9. 成本评估

| 项 | Sprint 1（本次） | 真实源接入后（Step 4，待批） |
|----|-----------------|---------------------------|
| API 费用 | **0**（无真实调用） | 地理编码：国内主流平台免费层日 5k+ 起；风况统计：Open-Meteo 免费层（非商用）或国内源付费层——**具体额度随 ADR-02 厂商批复核定** |
| 基础设施 | 0（无新服务） | 0（缓存用 SQLite，无 Redis/新中间件） |
| 密钥管理 | 0（禁止添加密钥，已守约） | `.env` + gitignore 惯例，CI 第 7 步凭证扫描已覆盖 |
| 维护成本 | 低（mock 无外部依赖，CI 零外网） | 中（源可用性监控 + stale 降级已内置） |

## 10. 商业授权风险

| 风险 | 等级 | 处置 |
|------|------|------|
| 国内地图 API 商用授权不合规（免费层限个人/非商用） | 中 | **未确认使用性质前不接入任何真实源**（本 ADR 强制）；决策输入①②③由主理人提供后才启动 Step 4 |
| Open-Meteo 免费层限非商用 | 中 | 同上；商用场景需付费版或切国内源 |
| 气候区划表版权/规范衍生数据 | 中 | 每条带 source 出处 + 主理人签字（Level 2）前恒 pending |
| mock 数据被误当真实数据（R-01 红线） | 高 | mock 值带 `__mock__` 标记 + `real_data=False` + confidence≠measured，**三重锁 + 测试锁死** |

## 11. 最终推荐方案（本 ADR 生效范围）

**立即执行（Sprint 1 编码范围）：**

1. `agents/environment/providers/` 包：`base.py`（契约）+ `mock_provider.py` + `factory.py`（disabled/mock/注册表）；
2. `agents/config.yaml` 新增 `environment_data` 段，**默认全 disabled**（合入即零行为变化）；
3. `EnvironmentAgent` 集成：invoke 前置数据获取段 + `field_provenance` + 顶层 pending 语义修正 + evidence 溯源增强；
4. 测试：provider 契约/工厂三模式/命中/降级/防编造锁 + 既有用例语义修正，基线只增不减。

**DEFERRED（显式挂起，非遗漏）：**

| 项 | 挂起原因 | 解锁条件 |
|----|---------|---------|
| 真实 GeoProvider / WeatherProvider 厂商选型与实现 | 主理人禁止直接选 API；需商用授权/预算/账号三项决策输入 | 主理人批复 ADR-02 决策输入 |
| API 密钥配置 | 禁止添加密钥 | 同上 |
| 缓存层实现 | 无真实源时无缓存对象 | 随真实 Provider 同批 |
| Solar 本地算法实现 | 需对照样本测试保障后才可标 measured | 2.2.1 Step 2 排期（策略已锁定） |
| climate_zones.json 静态表 | 规范衍生数据需主理人签字 | 主理人核对签字（Level 2） |

---

*ADR-2.2.1 ｜ 生效：2026-07-27 ｜ 上游：.ai/tasks/2.2.1_environment_data_design.md ｜ 下游：.ai/reviews/2.2.1_environment_data_report.md*
