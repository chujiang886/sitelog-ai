# BOIP Phase 3.3.9 — Knowledge Intelligence Layer（只读分析 / Phase 1）

- **生成**：2026-08-02
- **身份**：BOIP AI Chief Architect + Senior Backend Engineer
- **性质**：本文件为「第一阶段：只读分析」。仅分析现状、设计集成点，**未修改任何核心代码**（`agents/` 零改动）。
- **下一步**：等待主理人确认后，方进入 Phase 2 实现 `quality.py` / `relationship.py` / `conflict.py` / Repository 只读接口 / 测试。
- **红线状态**：本阶段未触碰 `verified.json` / 未开 `engineering_enabled` / 未建 `ReleaseApproval` / 未输出 `engineering_approved`。

---

## 0. 分析范围与方法

本分析基于以下已落地代码（仅读取，未改）：

| 文件 | 行数 | 角色 |
|---|---|---|
| `agents/engineering/knowledge/connector.py` | ~549 | `KnowledgeItem` / `KnowledgeItemState` / `Extractor` / `SourceRefBinder` / `ExpertBinder` / `ObsidianToBoipConnector` / `ConnectorResult` |
| `agents/engineering/knowledge/repository.py` | 395 | `KnowledgeEvent` / `KnowledgeEventLog` / `KnowledgeRepository`（3.3.8 交付） |
| `tests/agents/test_knowledge_repository.py` | 24 用例 | Repository CRUD / version / audit / connector 集成 |
| `tests/agents/test_knowledge_connector.py` | 20 用例 | Connector 单测（纯标识符夹具） |
| `agents/engineering/gate/enable_gate.py` | 174 | G1–G6 阈值激活门禁（3.2.5，供 3.4.0 复用语义） |

> 注：`agents/engineering/knowledge/intelligence/` 目录当前**不存在**，仅 `knowledge/` 下有 `__init__.py`（空）、`connector.py`、`repository.py`、数据 JSON。

---

## 1. 当前 Repository 架构（只读复盘）

`KnowledgeRepository`（`repository.py`）已具备：

- **存储**：自管 `knowledge_repository.json`，绝不读 `verified.json`（红线③）。
- **CRUD + 检索**：`save()` / `get()` / `exists()` / `query(domain, validation_status, knowledge_type, author, parent_knowledge_id, title_contains, knowledge_id_prefix)` / `version()` / `history()`。
- **版本管理**：每次 `save` 生成版本快照 `_version` 递增；`_canonical_core()`（13 核心字段、排除时间戳与哈希）规范化后由 `compute_content_hash` 得 `content_hash`；幂等判定（内容无变化不新增版本）。
- **审计**：`KnowledgeEventLog` 仅记录 `create`/`update`/`verify`/`deprecated`；`record()` 对 `event_type` 白名单外（含 `approved`）抛 `ValueError`（红线②硬拒）。
- **显式事件**：`record_event()` / `verify(new_status="Source_Verified")` / `deprecate(successor=)`；`verify` 永不置 `Engineering_Approved`。
- **安全护栏**：`safety_invariants_ok()` 静态只读断言 `load_engineering_enabled() is False`（红线①/④）。

**已有可用于智能层的原始数据**：
- 每个 item 的 13 字段（`to_dict()`）；
- 版本快照链 `version(kid)` → 可算 freshness / 演化；
- 审计事件链 `history(kid)` → 可算 audit 完整性；
- `query()` 多维过滤 → 可批量取同 domain / 同 linked_entities 的 item 做关系/冲突发现。

---

## 2. Connector 流程（只读复盘）

`ObsidianToBoipConnector.process_note(note_text, note_path="", repository=None)`：

```
Obsidian Markdown
  → Extractor.extract()        生成 KnowledgeItem（含 frontmatter 解析）
  → SourceRefBinder.bind()     依据 spec_sources 校验 C1–C6，置 validation_status
  → ExpertBinder.bind()        仅校验专家资料存在性，绝不落签署位
  → [若传入 repository]        repository.save(item) 落库 + source_ref 通过补记 verify 事件
  → 返回 ConnectorResult(item, source_ref_result, expert_result, repository_info)
```

- 集成点：Connector 已是「Obsidian → KnowledgeItem → Validation → Repository」单向管道。
- 智能层不插入管道，而是**在落库后对 Repository 内容做离线条分析**（只读），不改变 pipeline 时序。

---

## 3. KnowledgeItem Schema（13 字段 + 七态 + 辅助）

**13 核心字段**（`KnowledgeItem` dataclass）：

`knowledge_id` / `knowledge_type` / `parent_knowledge_id` / `title` / `content` / `source` / `author` / `domain` / `content_hash` / `validation_status` / `linked_entities` / `created_at` / `updated_at`

**辅助字段**（不计入主键）：`confidence="unverified"` / `session_id=""`

**七态**（`KnowledgeItemState`）：

`Captured` → `Pending_Verification` → `Source_Verified` → `Expert_Verified` → `Engineering_Verified` → `Engineering_Approved` → `Deprecated`

> 智能层所有评分必须可追溯到上述字段/状态，**不得虚构行业常数**（如"行业平均完整度 0.85"之类一律禁止）。

---

## 4. 测试结构（只读复盘）

- 位置：`tests/agents/test_knowledge_repository.py`、`tests/agents/test_knowledge_connector.py`。
- 模式：`REPO_ROOT = Path(__file__).resolve().parents[2]`；夹具用**纯标识符**（`SRC-1`/`EXP-1`/`E-TH-01`），不含裸数字（防编造扫描 `[7/8]`）；`tmp_path` 隔离 store，避免污染真实 `knowledge_repository.json`。
- 断言风格：行为断言（CRUD 全链路 / 版本递增与幂等 / content_hash 基于 `_canonical_core` / 审计白名单拒 `approved` / verified.json 字节级不变 / 不建 `release_approvals.jsonl` / `engineering_enabled=False`）。
- 新增 `test_knowledge_intelligence.py` 须沿用该模式（见 §9）。

---

## 5. Task 1 — KnowledgeQualityAnalyzer 设计（待实现）

**新增**：`agents/engineering/knowledge/intelligence/quality.py`

**契约**：

```python
@dataclass
class KnowledgeQualityReport:
    knowledge_id: str
    completeness: float          # 0.0–1.0
    source_strength: float       # 0.0–1.0
    validation_status: str       # 直接映射 item.validation_status
    freshness: float             # 0.0–1.0
    dependency_integrity: float  # 0.0–1.0
    overall: float               # 加权（权重固定，非行业经验值，附说明）
    rationale: dict[str, str]    # 每个维度一句计算依据

class KnowledgeQualityAnalyzer:
    def analyze(self, item: KnowledgeItem) -> KnowledgeQualityReport: ...
```

**五维度计算依据（全部可溯、无虚构）**：

| 维度 | 计算依据 |
|---|---|
| `completeness` | 13 核心字段中非 `pending_verification`/非空的比例（如 11/13 ≈ 0.846）。依据 = 字段计数，非行业经验。 |
| `source_strength` | 由 `validation_status` 映射：Captured/Pending=0.2，Source_Verified=0.5，Expert_Verified=0.75，Engineering_Verified=0.9，Engineering_Approved=1.0，Deprecated=0.0。**映射表为产品定义，非统计估计**。 |
| `validation_status` | 直接透传 `item.validation_status`（作为分类字段，不评分）。 |
| `freshness` | 基于 `updated_at` 与当前时间的相对时长分桶（如 <30d=1.0，<90d=0.7，<1y=0.4，>1y=0.1）。**分桶阈值为策略常量，注明"待主理人确认"，非行业基准**。 |
| `dependency_integrity` | 若 `parent_knowledge_id` 非空：父存在且非 `Deprecated`=1.0，父缺失/废弃=0.0；`linked_entities` 全部可解析（在 Repository 中存在）=1.0，否则按比例扣分。 |

**红线约束**：
- 不输出 `engineering_approved`：`source_strength` 仅在 item 已为 `Engineering_Approved` 时映射 1.0，分析器**不主动产生**该状态。
- 不读 `verified.json`：评分仅用 KnowledgeItem 字段与 Repository 内存数据。
- `overall` 为五维固定权重加权平均（权重在代码注释中声明显式，注明"默认权重，待治理确认"，**不标榜为行业最佳实践**）。

---

## 6. Task 2 — KnowledgeRelationshipEngine 设计（待实现）

**新增**：`agents/engineering/knowledge/intelligence/relationship.py`

**契约**：

```python
@dataclass
class RelationshipCandidate:
    relationship_type: str   # parent_child | related | duplicate_candidate | conflict_candidate
    source_id: str
    target_id: str
    confidence: float
    basis: str               # 发现依据（如 "shared content_hash" / "parent_knowledge_id link"）

class KnowledgeRelationshipEngine:
    def discover(self, items: list[KnowledgeItem]) -> list[RelationshipCandidate]: ...
```

**四类候选（仅产生 candidate，禁止 approve/merge/delete）**：

| 类型 | 发现规则 |
|---|---|
| `parent_child` | `item.parent_knowledge_id` 指向另一 item 的 `knowledge_id`。 |
| `related` | 同 `domain` 且 `linked_entities` 交集 ≥ 1。 |
| `duplicate_candidate` | 两 item 的 `_canonical_core` 哈希（或 `content_hash`）相同 → 疑似重复。 |
| `conflict_candidate` | 同 `domain` + 同 `linked_entities` 交集但 `content` 不同 → 转交 ConflictDetector 复核 |

**护栏**：`discover()` 为**纯函数**，只读 `items` 列表、返回候选；不调用 `repository.save`、不调用 `repository.deprecate`、不写任何事件（红线：禁止自动 merge/delete/approve）。

---

## 7. Task 3 — KnowledgeConflictDetector 设计（待实现）

**新增**：`agents/engineering/knowledge/intelligence/conflict.py`

**契约**：

```python
@dataclass
class ConflictReport:
    conflict_id: str
    domain: str
    conflict_type: str        # parameter | source | status
    item_a: str
    item_b: str
    detail: str
    review_required: bool = True   # 恒定 True，永不自动解决

class KnowledgeConflictDetector:
    def detect(self, items: list[KnowledgeItem]) -> list[ConflictReport]: ...
```

**三类冲突（同 domain 内）**：

| 类型 | 检测 |
|---|---|
| `parameter` | 同 `linked_entities`（指向同一工程实体）但 `content` 数值/表述不同。 |
| `source` | 同 clause 引用但 `source` 的 `standard`/`edition`/`clause` 互相矛盾（如 GB 50009-2012 vs 2012 修订）。 |
| `status` | 一 item 为 `Deprecated`，但仍有他 item 以 `parent_knowledge_id`/ `linked_entities` 引用它（悬垂引用）。 |

**护栏**：`detect()` 返回值 `review_required` 恒定 `True`；**绝不**自动改 `validation_status`、绝不调 `deprecate`、绝不输出解决结论。冲突进入"待人工复核"队列。

---

## 8. Task 4 — Repository Intelligence Integration 设计（待实现，不破现有 API）

在 `KnowledgeRepository` 新增**只读**接口，委托给 intelligence 模块：

```python
# repository.py 顶部新增（避免循环 import：intelligence.* 仅 import KnowledgeItem，
# 不 import repository；repository 单向 import intelligence）
from agents.engineering.knowledge.intelligence.quality import KnowledgeQualityAnalyzer
from agents.engineering.knowledge.intelligence.relationship import KnowledgeRelationshipEngine
from agents.engineering.knowledge.intelligence.conflict import KnowledgeConflictDetector

class KnowledgeRepository:
    def __init__(self, ...):
        ...
        self._quality = KnowledgeQualityAnalyzer()
        self._rel = KnowledgeRelationshipEngine()
        self._conflict = KnowledgeConflictDetector()

    # —— 新增只读接口（不破 save/get/query/history）——
    def _all_items(self) -> list[KnowledgeItem]:
        return [KnowledgeItem.from_dict(v["current"]) for v in self._items.values()]

    def quality_report(self, knowledge_id: str) -> KnowledgeQualityReport:
        item = self.get(knowledge_id)
        if item is None: raise KeyError(...)
        return self._quality.analyze(item)          # 只读，无 save/event

    def find_relationships(self, knowledge_id: str) -> list[RelationshipCandidate]:
        items = self._all_items()
        return [c for c in self._rel.discover(items) if c.source_id == knowledge_id or c.target_id == knowledge_id]

    def detect_conflicts(self, *, knowledge_id: str | None = None, domain: str | None = None) -> list[ConflictReport]:
        items = self._all_items()
        if domain is not None:
            items = [i for i in items if i.domain == domain]
        reports = self._conflict.detect(items)
        if knowledge_id is not None:
            reports = [r for r in reports if r.item_a == knowledge_id or r.item_b == knowledge_id]
        return reports

    def analyze(self, knowledge_id: str | None = None) -> dict:
        """聚合单条 item 的智能视图：quality + relationships + conflicts（只读快照）。"""
        if knowledge_id is not None:
            return {
                "quality": self.quality_report(knowledge_id),
                "relationships": self.find_relationships(knowledge_id),
                "conflicts": self.detect_conflicts(knowledge_id=knowledge_id),
            }
        return {"item_count": self.item_count(),
                "conflicts_total": len(self.detect_conflicts())}
```

**不破坏现有 API 的保证**：
- 上述方法均为**新增**，不修改 `save/get/query/version/history/verify/deprecate/record_event` 的任何签名或语义。
- 全部只读：不写 `knowledge_repository.json`、不记审计事件、不翻 `engineering_enabled`。
- 循环 import 防护：`intelligence/*` 仅 `from agents.engineering.knowledge.connector import KnowledgeItem`；`repository.py` 单向 import `intelligence.*`（沿用 3.3.8 同一防环模式）。

---

## 9. Task 5 — 测试设计（待实现，`tests/agents/test_knowledge_intelligence.py`）

沿用 `tmp_path` + 纯标识符夹具，覆盖：

1. **quality 计算**：构造已知字段填充度的 item → 断言 `completeness` 比例正确、`source_strength` 映射符合 §5 表、`freshness` 分桶正确、`dependency_integrity` 父缺失=0.0。
2. **relationship 发现**：构造 parent→child 对、同 domain 同 linked_entities 对、同 content_hash 对 → 断言分别产出 `parent_child`/`related`/`duplicate_candidate`；构造 content 不同的同实体对 → 产出 `conflict_candidate`。
3. **conflict 检测**：构造同 domain 同实体不同 content（parameter）、矛盾 source（source）、Deprecated 被引用（status）→ 断言三类 `ConflictReport` 且 `review_required` 恒定 `True`。
4. **不修改 verified.json**：测试前快照 `verified.json` 字节，跑 `analyze/quality_report/find_relationships/detect_conflicts` 后比对字节级一致（断言未变）。
5. **不产生 approved 状态**：断言 `quality_report` / `analyze` 返回值中无任何 `engineering_approved` 文本；断言运行后 `repository.history(kid)` 无 `approved` 事件（审计白名单仍硬拒）。
6. **不改变 engineering_enabled**：断言 `KnowledgeRepository.safety_invariants_ok()` 仍为 `True`（= `engineering_enabled is False`）。

---

## 10. 红线检查（本分析阶段已遵守）

| 红线 | 本阶段状态 |
|---|---|
| ① 不开 `engineering_enabled` | ✅ 仅读取 `load_engineering_enabled()`，未置 True |
| ② 不输出 `engineering_approved` | ✅ 智能层定位为"只读评估"，设计上 `verify` 仍仅 `Source_Verified`；`Engineering_Approved` 仅作 `source_strength` 映射输入，绝不由 AI 产生 |
| ③ 不修改 `verified.json` value | ✅ 全程未读未写 `verified.json` |
| ④ 不创建 `ReleaseApproval` | ✅ 未写 `release_approvals.jsonl` |
| ⑤ AI 不代专家审核 | ✅ `ExpertBinder` 仅校验资料存在，智能层不落任何签署/授权位 |

---

## 11. 待主理人确认的决策点（确认后进入实现）

1. **`freshness` 分桶阈值**（<30d / <90d / <1y）是否为治理确认值，还是先以"策略常量、待确认"落地？
2. **`overall` 五维权重**（completeness/source_strength/freshness/dependency_integrity 各占多少）是否需要主理人拍板，还是先取等权（0.25）？
3. **`intelligence/` 包是否纳入 `local_ci.sh` 的防编造/硬编码扫描**（当前扫描覆盖 `.py`，新增文件自动纳入，无需额外动作；仅确认无豁免需求）。
4. **是否同意本分析后的接口签名**（§8）作为实现契约？
5. **实现顺序**：先 `quality.py` → `relationship.py` → `conflict.py` → Repository 集成 → 测试，是否认可？

> ⏸️ **本阶段已停止（Phase 1 只读分析完成）。在收到主理人对上述决策点的确认前，不修改任何核心代码。**
