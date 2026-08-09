"""Phase 3.3 Sprint 3.3.9 — Knowledge Intelligence Layer 测试。

覆盖：
- quality 计算（completeness / source_strength / freshness / dependency_integrity / overall）
- relationship 发现（parent_child / related / duplicate_candidate / conflict_candidate）
- conflict 检测（parameter / source / status，review_required 恒 True）
- verified.json 字节级不变
- engineering_enabled=False（safety_invariants_ok）
- 不产生 approved 审计事件

夹具：纯标识符（SRC-1 / EXP-1 / E-TH-01），不含裸数字业务词（防编造扫描 [7/8]）；
store 用 tmp_path 隔离，不污染真实 knowledge_repository.json。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from agents.engineering.knowledge.connector import KnowledgeItem, PENDING_PLACEHOLDER
from agents.engineering.knowledge.intelligence.conflict import (
    CONFLICT_PARAMETER,
    CONFLICT_SOURCE,
    CONFLICT_STATUS,
    ConflictReport,
    KnowledgeConflictDetector,
)
from agents.engineering.knowledge.intelligence.quality import (
    KnowledgeQualityAnalyzer,
    KnowledgeQualityReport,
)
from agents.engineering.knowledge.intelligence.relationship import (
    REL_CONFLICT,
    REL_DUPLICATE,
    REL_PARENT_CHILD,
    REL_RELATED,
    KnowledgeRelationshipEngine,
    RelationshipCandidate,
)
from agents.engineering.knowledge.repository import (
    EVENT_TYPES,
    FORBIDDEN_EVENT_TYPE,
    KnowledgeRepository,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFIED_JSON = REPO_ROOT / "agents" / "engineering" / "thresholds" / "verified.json"
RELEASE_APPROVALS = REPO_ROOT / "agents" / "engineering" / "release" / "release_approvals.jsonl"


def _now_iso(offset_days: int = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=offset_days)
    return dt.isoformat()


def make_item(knowledge_id: str = "KI-TEST-0001", **overrides: Any) -> KnowledgeItem:
    """构造一个字段齐全的 KnowledgeItem（纯标识符夹具，无业务裸数）。"""
    base = dict(
        knowledge_id=knowledge_id,
        knowledge_type="threshold",
        parent_knowledge_id=PENDING_PLACEHOLDER,
        title=f"Title for {knowledge_id}",
        content=f"Reference body for {knowledge_id}.",
        source="SRC-1",
        author="EXP-1",
        domain="wind_load",
        content_hash="a" * 64,
        validation_status="Source_Verified",
        linked_entities=["E-TH-01"],
        created_at=_now_iso(),
        updated_at=_now_iso(),
    )
    base.update(overrides)
    return KnowledgeItem(**base)


# --------------------------------------------------------------------------- #
# Task 1 — Quality Analyzer
# --------------------------------------------------------------------------- #
class TestQualityAnalyzer:
    def test_completeness_full(self) -> None:
        item = make_item(parent_knowledge_id="KI-ROOT-0")
        rep = KnowledgeQualityAnalyzer().analyze(item)
        assert rep.completeness == 1.0
        assert "13/13" in rep.rationale["completeness"]

    def test_completeness_partial(self) -> None:
        item = make_item(
            parent_knowledge_id=PENDING_PLACEHOLDER,
            source=PENDING_PLACEHOLDER,
            author=PENDING_PLACEHOLDER,
            linked_entities=[],
        )
        rep = KnowledgeQualityAnalyzer().analyze(item)
        # 4 字段未填 -> 9/13
        assert rep.completeness == pytest.approx(9 / 13)
        assert "9/13" in rep.rationale["completeness"]

    def test_source_strength_mapping(self) -> None:
        analyzer = KnowledgeQualityAnalyzer()
        assert analyzer.analyze(make_item(validation_status="Pending_Verification")).source_strength == 0.2
        assert analyzer.analyze(make_item(validation_status="Source_Verified")).source_strength == 0.5
        assert analyzer.analyze(make_item(validation_status="Expert_Verified")).source_strength == 0.75
        assert analyzer.analyze(make_item(validation_status="Engineering_Verified")).source_strength == 0.9
        assert analyzer.analyze(make_item(validation_status="Engineering_Approved")).source_strength == 1.0
        assert analyzer.analyze(make_item(validation_status="Deprecated")).source_strength == 0.0

    def test_validation_status_passthrough(self) -> None:
        item = make_item(validation_status="Expert_Verified")
        rep = KnowledgeQualityAnalyzer().analyze(item)
        assert rep.validation_status == "Expert_Verified"

    def test_freshness_buckets(self) -> None:
        analyzer = KnowledgeQualityAnalyzer()
        # 最新 -> 1.0
        assert analyzer.analyze(make_item(updated_at=_now_iso(0))).freshness == 1.0
        # 60 天前 -> 0.7 桶
        assert analyzer.analyze(make_item(updated_at=_now_iso(60))).freshness == 0.7
        # 200 天前 -> 0.4 桶
        assert analyzer.analyze(make_item(updated_at=_now_iso(200))).freshness == 0.4
        # 400 天前 -> 0.1 桶
        assert analyzer.analyze(make_item(updated_at=_now_iso(400))).freshness == 0.1
        # 缺失 -> 0.0
        assert analyzer.analyze(make_item(updated_at="")).freshness == 0.0

    def test_overall_is_weighted(self) -> None:
        item = make_item(parent_knowledge_id="KI-ROOT-0")
        rep = KnowledgeQualityAnalyzer().analyze(item)
        # overall 必须是四数值维度按固定权重的加权平均（内部一致性）。
        expected = (
            rep.completeness * 0.30
            + rep.source_strength * 0.30
            + rep.freshness * 0.20
            + rep.dependency_integrity * 0.20
        )
        assert rep.overall == pytest.approx(expected)
        assert 0.0 <= rep.overall <= 1.0
        assert set(rep.rationale.keys()) >= {
            "completeness",
            "source_strength",
            "validation_status",
            "freshness",
            "dependency_integrity",
            "overall",
        }

    def test_no_engineering_approved_produced(self) -> None:
        # 分析器绝不产出 Engineering_Approved：低状态 item 的 report 不含该态。
        item = make_item(validation_status="Source_Verified")
        rep = KnowledgeQualityAnalyzer().analyze(item)
        assert rep.validation_status != "Engineering_Approved"
        assert "Engineering_Approved" not in str(rep.to_dict())

    def test_dependency_integrity_via_repo(self, tmp_path: Path) -> None:
        analyzer = KnowledgeQualityAnalyzer()
        # 无 parent -> 1.0
        assert analyzer.analyze(make_item()).dependency_integrity == 1.0
        # 孤立（无 repo）声明 parent -> 0.6
        with_parent = make_item(parent_knowledge_id="KI-PARENT-1")
        assert analyzer.analyze(with_parent).dependency_integrity == 0.6
        # 经 repo：父存在且未废弃 -> 1.0
        repo = KnowledgeRepository(store_path=tmp_path / "store.json")
        repo.save(make_item(knowledge_id="KI-PARENT-1", validation_status="Source_Verified"))
        assert analyzer.analyze(with_parent, repo=repo).dependency_integrity == 1.0
        # 经 repo：父缺失 -> 0.0
        orphan = make_item(knowledge_id="KI-ORPHAN", parent_knowledge_id="KI-MISSING-9")
        assert analyzer.analyze(orphan, repo=repo).dependency_integrity == 0.0
        # 经 repo：父已废弃 -> 0.0
        repo.save(make_item(knowledge_id="KI-DEP-1", validation_status="Deprecated"))
        deprecated_child = make_item(knowledge_id="KI-CHILD-D", parent_knowledge_id="KI-DEP-1")
        assert analyzer.analyze(deprecated_child, repo=repo).dependency_integrity == 0.0


# --------------------------------------------------------------------------- #
# Task 2 — Relationship Engine（纯函数，只读，不 merge/delete/approve）
# --------------------------------------------------------------------------- #
class TestRelationshipEngine:
    def test_parent_child(self) -> None:
        parent = make_item(knowledge_id="KI-P-1")
        child = make_item(knowledge_id="KI-C-1", parent_knowledge_id="KI-P-1")
        cands = KnowledgeRelationshipEngine().discover([parent, child])
        pc = [c for c in cands if c.relationship_type == REL_PARENT_CHILD]
        assert len(pc) == 1
        assert pc[0].source_id == "KI-C-1"
        assert pc[0].target_id == "KI-P-1"
        assert pc[0].confidence == 1.0

    def test_related_and_conflict_candidate(self) -> None:
        a = make_item(knowledge_id="KI-A-1", content="body A", linked_entities=["E-TH-01"])
        b = make_item(knowledge_id="KI-A-2", content="body B different", linked_entities=["E-TH-01"])
        cands = KnowledgeRelationshipEngine().discover([a, b])
        types = {c.relationship_type for c in cands}
        assert REL_RELATED in types
        assert REL_CONFLICT in types
        # related 与 conflict_candidate 不应互为重复（不同 type）
        assert len([c for c in cands if c.relationship_type == REL_RELATED]) == 1
        assert len([c for c in cands if c.relationship_type == REL_CONFLICT]) == 1

    def test_duplicate_candidate(self) -> None:
        a = make_item(knowledge_id="KI-D-1", content="same body", linked_entities=["E-TH-01"])
        b = make_item(knowledge_id="KI-D-2", content="same body", linked_entities=["E-TH-02"])
        cands = KnowledgeRelationshipEngine().discover([a, b])
        dup = [c for c in cands if c.relationship_type == REL_DUPLICATE]
        assert len(dup) == 1
        assert dup[0].confidence == 0.9

    def test_discover_is_pure_no_mutation(self) -> None:
        a = make_item(knowledge_id="KI-M-1", parent_knowledge_id="KI-M-2")
        b = make_item(knowledge_id="KI-M-2")
        snapshot_a = a.to_dict()
        snapshot_b = b.to_dict()
        KnowledgeRelationshipEngine().discover([a, b])
        # 纯函数：item 不被修改、不被落库、不被删除。
        assert a.to_dict() == snapshot_a
        assert b.to_dict() == snapshot_b


# --------------------------------------------------------------------------- #
# Task 3 — Conflict Detector（review_required 恒 True）
# --------------------------------------------------------------------------- #
class TestConflictDetector:
    def test_parameter_conflict(self) -> None:
        a = make_item(knowledge_id="KI-P-1", content="value A", linked_entities=["E-TH-01"])
        b = make_item(knowledge_id="KI-P-2", content="value B", linked_entities=["E-TH-01"])
        reports = KnowledgeConflictDetector().detect([a, b])
        param = [r for r in reports if r.conflict_type == CONFLICT_PARAMETER]
        assert len(param) == 1
        assert param[0].review_required is True

    def test_source_conflict(self) -> None:
        a = make_item(knowledge_id="KI-S-1", source="SRC-1", linked_entities=["E-TH-01"])
        b = make_item(knowledge_id="KI-S-2", source="SRC-2", linked_entities=["E-TH-01"])
        reports = KnowledgeConflictDetector().detect([a, b])
        src = [r for r in reports if r.conflict_type == CONFLICT_SOURCE]
        assert len(src) == 1
        assert src[0].review_required is True

    def test_status_conflict_dangling_reference(self) -> None:
        deprecated = make_item(knowledge_id="KI-X-1", validation_status="Deprecated")
        child = make_item(knowledge_id="KI-X-2", parent_knowledge_id="KI-X-1")
        reports = KnowledgeConflictDetector().detect([deprecated, child])
        status = [r for r in reports if r.conflict_type == CONFLICT_STATUS]
        assert len(status) == 1
        assert status[0].item_a == "KI-X-1"
        assert status[0].item_b == "KI-X-2"
        assert status[0].review_required is True

    def test_review_required_always_true(self) -> None:
        items = [
            make_item(knowledge_id="KI-R-1", content="a", linked_entities=["E-TH-01"]),
            make_item(knowledge_id="KI-R-2", content="b", linked_entities=["E-TH-01"]),
        ]
        for r in KnowledgeConflictDetector().detect(items):
            assert r.review_required is True

    def test_no_auto_resolution(self) -> None:
        # detect 不改任何 item 状态、不返回解决结论。
        a = make_item(knowledge_id="KI-N-1", content="a", linked_entities=["E-TH-01"])
        b = make_item(knowledge_id="KI-N-2", content="b", linked_entities=["E-TH-01"])
        before = (a.validation_status, b.validation_status)
        KnowledgeConflictDetector().detect([a, b])
        assert (a.validation_status, b.validation_status) == before


# --------------------------------------------------------------------------- #
# Task 4 — Repository 只读集成（不破坏 save/get/query/history/verify/deprecate）
# --------------------------------------------------------------------------- #
class TestRepositoryIntelligenceIntegration:
    def _seeded_repo(self, tmp_path: Path) -> KnowledgeRepository:
        repo = KnowledgeRepository(store_path=tmp_path / "store.json")
        repo.save(make_item(knowledge_id="KI-I-1", content="body one", linked_entities=["E-TH-01"]))
        repo.save(make_item(knowledge_id="KI-I-2", content="body two", linked_entities=["E-TH-01"]))
        repo.save(make_item(knowledge_id="KI-I-3", parent_knowledge_id="KI-I-1"))
        return repo

    def test_quality_report(self, tmp_path: Path) -> None:
        repo = self._seeded_repo(tmp_path)
        rep = repo.quality_report("KI-I-1")
        assert isinstance(rep, KnowledgeQualityReport)
        assert rep.knowledge_id == "KI-I-1"
        assert 0.0 <= rep.overall <= 1.0

    def test_find_relationships(self, tmp_path: Path) -> None:
        repo = self._seeded_repo(tmp_path)
        rels = repo.find_relationships("KI-I-1")
        assert all(isinstance(r, RelationshipCandidate) for r in rels)
        types = {r.relationship_type for r in rels}
        assert REL_PARENT_CHILD in types  # KI-I-3 -> KI-I-1
        assert REL_RELATED in types or REL_CONFLICT in types  # KI-I-1 与 KI-I-2 同实体

    def test_detect_conflicts(self, tmp_path: Path) -> None:
        repo = self._seeded_repo(tmp_path)
        reports = repo.detect_conflicts()
        assert all(isinstance(r, ConflictReport) for r in reports)
        assert all(r.review_required is True for r in reports)

    def test_analyze_item_view(self, tmp_path: Path) -> None:
        repo = self._seeded_repo(tmp_path)
        view = repo.analyze(knowledge_id="KI-I-1")
        assert view["knowledge_id"] == "KI-I-1"
        assert isinstance(view["quality"], KnowledgeQualityReport)
        assert isinstance(view["relationships"], list)
        assert isinstance(view["conflicts"], list)

    def test_analyze_repo_summary(self, tmp_path: Path) -> None:
        repo = self._seeded_repo(tmp_path)
        summary = repo.analyze()
        assert summary["item_count"] == 3
        assert "conflicts_total" in summary
        assert "relationships_total" in summary

    def test_existing_apis_untouched(self, tmp_path: Path) -> None:
        repo = self._seeded_repo(tmp_path)
        # save/get/query/history/version 仍正常。
        assert repo.get("KI-I-1") is not None
        assert len(repo.query(domain="wind_load")) == 3
        assert len(repo.version("KI-I-1")) == 1
        assert repo.item_count() == 3
        # 只读接口不写盘：运行 analyze 后 store 内容不含 quality/conflict 字段。
        raw = (tmp_path / "store.json").read_text(encoding="utf-8")
        assert "knowledge_quality" not in raw and "conflict_report" not in raw


# --------------------------------------------------------------------------- #
# Task 5 — 红线：verified.json 不变 / engineering_enabled=False / 无 approved 事件
# --------------------------------------------------------------------------- #
class TestRedLines:
    def test_verified_json_unchanged_and_no_release_approval(self, tmp_path: Path) -> None:
        verified_before = VERIFIED_JSON.read_bytes() if VERIFIED_JSON.is_file() else b""
        repo = KnowledgeRepository(store_path=tmp_path / "store.json")
        repo.save(make_item(knowledge_id="KI-R1", content="x", linked_entities=["E-TH-01"]))
        repo.save(make_item(knowledge_id="KI-R2", content="y", linked_entities=["E-TH-01"]))
        # 跑全部只读智能接口。
        repo.analyze()
        repo.analyze(knowledge_id="KI-R1")
        repo.quality_report("KI-R1")
        repo.find_relationships("KI-R1")
        repo.detect_conflicts()
        # 红线③：verified.json 字节级不变。
        if VERIFIED_JSON.is_file():
            assert VERIFIED_JSON.read_bytes() == verified_before
        # 红线④：不创建 ReleaseApproval。
        assert not RELEASE_APPROVALS.exists()

    def test_engineering_enabled_false(self) -> None:
        # 红线①：safety_invariants_ok 维持 True（= engineering_enabled is False）。
        assert KnowledgeRepository.safety_invariants_ok() is True

    def test_no_approved_audit_event(self, tmp_path: Path) -> None:
        repo = KnowledgeRepository(store_path=tmp_path / "store.json")
        repo.save(make_item(knowledge_id="KI-EV-1"))
        # 只读智能接口运行后，不应产生任何审计事件，更不含 approved。
        repo.analyze(knowledge_id="KI-EV-1")
        assert all(e.event_type != "approved" for e in repo.history("KI-EV-1"))
        # 审计白名单硬拒 approved（红线②）：record('x','approved') 必抛错。
        with pytest.raises(ValueError):
            repo.record_event("KI-EV-1", FORBIDDEN_EVENT_TYPE)
        # EVENT_TYPES 不含 approved（白名单语义）。
        assert "approved" not in EVENT_TYPES
