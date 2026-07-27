# Phase 2.2 Sprint 2B + 3 收口报告

- **范围**：Sprint 2B（2.2.3 PDF 方案书增强） + Sprint 3（2.2.4 MinIO 图片存储切换）
- **执行身份**：BOIP AI 高级研发负责人
- **收口日期**：2026-07-27
- **依据**：`.ai/tasks/2.2.3_pdf_design.md`、`.ai/tasks/2.2.4_minio_design.md`、`.ai/project_status.json`（SSOT）
- **授权边界**：两个 Sprint 完成后停止，等待主理人验收；**禁止自动进入** 2.2.5 RAG / 2.2.6 RBAC。

---

## 1. 完成任务

| Sprint | 任务 | 状态 | 交付 |
|---|---|---|---|
| 2B | 2.2.3 PDF 方案书增强 | ✅ COMPLETED | 客户可交付 PDF：可信等级可视化 + 三方案对比 + 防编造 |
| 3 | 2.2.4 MinIO 图片存储切换 | ✅ COMPLETED | StorageBackend 抽象 + Local/MinIO/Memory 三后端 + 可配置切换 |

两个 Sprint 均已通过 `local_ci.sh` 8/8 门禁，并完成 SSOT（project_status.json）/ roadmap 刷新与完成报告产出。

---

## 2. 修改文件

### 2.2.3（Sprint 2B）
| 文件 | 类型 | 说明 |
|---|---|---|
| `agents/report/generator.py` | REWRITTEN | 数据可信等级说明章节（Level 0~3）+ 环境可信度列/溯源子表 + 设计经济/舒适/高性能三原型 + 封面咨询需求 + 统一徽标（[已验证]/[AI推理·待确认]/[待确认]） |
| `tests/agents/test_report.py` | EDIT | mock 对齐 2.2.2 语义（pending_verification / field_provenance / threshold_refs） |
| `tests/agents/test_report_provenance.py` | **NEW** | 10 用例：三方案数量 / pending 语义 / provenance / verified 机制一票否决 / 防编造 / 关键章节锚点（pypdf 文本提取） |
| `backend/pyproject.toml` | EDIT | test extras 加 `pypdf>=4.0`（仅测试依赖） |
| `.ai/reviews/2.2.3_pdf_enhancement_report.md` | NEW | 2.2.3 完成报告 |

### 2.2.4（Sprint 3）
| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/core/storage_backends.py` | **NEW** | `StorageBackend(ABC)` + `LocalStorage` / `MemoryStorage` / `MinIOStorage` + `get_storage_backend()` + `migrate_storage()` |
| `backend/app/api/uploads.py` | EDIT | 写盘走 `get_storage_backend().save`，存逻辑 key |
| `backend/app/tasks/vision_tasks.py` | EDIT | 读图走 `get_storage_backend().read`，异常 `STORAGE_READ_FAILED` |
| `backend/tests/test_storage_backends.py` | **NEW** | 15 用例：local/memory roundtrip、read missing、delete、租户隔离、hash 去重、MinIO 未配置 fail-fast、default/memory/unknown、migrate、兼容旧路径、build_image_path、fake-minio |
| `.ai/reviews/2.2.4_minio_storage_report.md` | NEW | 2.2.4 完成报告 |

### 共同 SSOT 刷新
- `.ai/project_status.json`：刷新 `last_known_green_tests`（209 passed / 85%）、`data_layer.storage`、`tech_debt`（TD-015 RESOLVED）、新增 `phase_2_2.2.2.4` 块。
- `.ai/roadmap_v2.md`：2.2.3 / 2.2.4 行标 COMPLETED；测试基线更新；TD-015 标 RESOLVED；OPEN 14→13。

---

## 3. 架构影响

- **PDF 可信体系成型**：report 层消费 2.2.1 的 `field_provenance` / `data_providers` / `real_data` 与 2.2.2 的 `threshold_refs` / `verified`，把"AI 推理"显式标注为待确认，杜绝包装成工程确认。形成 Level 0~3 可信等级模型，客户可一目了然。
- **存储抽象解耦**：图片 I/O 从具体文件系统升级为接口；MinIO 经环境变量切换，密钥仅 `.env`；逻辑 key 统一 `{tenant_id}/{sha256}.{ext}` 为租户隔离 + 内容 hash 去重 + 跨后端迁移零 DB 改动奠基。
- **零回归**：上传/视觉 API 契约不变（前端仅消费 `storage_path` 元数据），旧绝对路径图片仍可识别（兼容性回退）。
- **宏观**：2.2 系列在"稳定架构（2.1）"之上，把 PDF 可交付、环境真实数据、设计专业化、存储云化四块占位能力做实，且全程守住"不编造 / 不降标准 / pending 不关"红线。

---

## 4. 测试结果

### 2.2.3 基线
- backend pytest **194 passed** / coverage **84.58%**；Jest 29 passed / 6 suites / 93.15%。
- 8/8 CI 全绿；新增 10 个 PDF provenance 用例。

### 2.2.4 基线（本次收口最终态）
- backend pytest **209 passed**（+15）/ coverage **85%**（84.58% → 85%，**不降反升**）。
- Jest 29 passed / 6 suites / 93.15%。
- 8/8 CI 全绿：Ruff 0 / pytest 209 / ESLint 0 error / Jest 29 / Alembic 双向 / Seed / 编造扫描 / 硬编码扫描 全通过。

### 覆盖率硬指标
- 规则"覆盖率不得下降"：84.58%（2.2.3）→ **85%**（2.2.4）✅ 达成，且因新增 storage 测试覆盖使整体上升。

---

## 5. 技术债变化

| 债 | 变化 | 说明 |
|---|---|---|
| TD-015 图片存 MinIO | **RESOLVED**（2.2.4） | `StorageBackend` 抽象接入；密钥仅 `.env`；CI 不依赖真实 MinIO |
| TD-004 / TD-012 | 历史已解 | 覆盖率门禁 / AsyncSession |
| OPEN 总数 | 14 → **13** | 偿还 TD-015；距 Phase 2.2 出口 OPEN≤5 仍有差距 |

> 其余 OPEN 债（TD-001/002/003/005/006(已解标记)/007/008/009/010/011/013/014(已解标记)/016）未在本双 Sprint 处理，属 2.1.x / 2.2.5+ / Phase 3 范围。

---

## 6. 未解决风险

| 风险 | 等级 | 说明 | 建议 |
|---|---|---|---|
| PDF 仍全量待确认 | 中 | 三方案依据依赖 LLM 推理（Level 0），verified 全 false，无专家签字转正 | 待 2.1.2/2.1.3 专家评审；当前安全（已显式标注，无编造） |
| MinIO 未真实启用 | 中 | 默认 local；真实 MinIO 集成需部署 + `.env` 配置 + 连通验证 | 上线前运维配置并 smoke（不进代码） |
| MinIO 双向迁移未覆盖 | 低 | `MinIOStorage` 未暴露 `_list_keys`，minio→x 迁移需调用方传 key 列表 | 如确需，补 `list_objects` 实现 |
| 文档仍滞后 | 中 | README 已对齐，CHANGELOG/LLM.md/PHASE0_LOG/AGENTS/API 滞后（D2–D7） | 属 2.1.1 文档配置对齐，未在本授权范围 |
| 工程审核链未闭环 | 高（红灯） | `engineering_enabled=false`；行业阈值全 pending | 上线前置，不擅自开启 |

---

## 7. 下一阶段建议（待主理人决策，不在本授权自动推进）

1. **2.1.1 文档/配置全面对齐**（P0）：刷新 CHANGELOG/LLM.md/PHASE0_LOG/AGENTS/API；清理 `config.yaml` 注释漂移（C1 / TD-017）；补 `.gitignore`；补 `docs/ANALYSIS_REPORT.md`（D7/D8 / TD-018）。
2. **2.1.2 工程阈值专家签字**（P0，pending_verification）：风压/楼层/评分权重 → 部分 `pending` 转正（打通 PDF 三方案"待验证项"闭环）。
3. **2.1.3 Vision prompt 专家调优**（P0）：建筑开口场景化（TD-016）。
4. **2.2.5 知识库 RAG 奠基** / **2.2.6 多租户 / RBAC 基础**：**依授权禁止自动进入，等待主理人验收后另行排期**。
5. **技术债偿还节奏**：Phase 2.2 出口目标 OPEN≤5，当前 13，需还清 TD-002/003/008/011/013/016 等才能达标。

---

**收口结论**：Sprint 2B（2.2.3）+ Sprint 3（2.2.4）均已交付并通过 8/8 CI，覆盖率不降反升，SSOT 与 roadmap 已同步，两阶段专属报告已产出。按授权，双 Sprint 完成后**停止并等待主理人验收**，不自动进入 2.2.5 / 2.2.6。
