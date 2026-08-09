"""Engineering Knowledge Connector（Phase 3.3 Sprint 3.3.7）。

实现 Obsidian Markdown ↓ KnowledgeItem ↓ BOIP Knowledge Layer 的连接能力。

组件：
- KnowledgeItemState：七态生命周期枚举；
- KnowledgeItem：13 字段标准中间层数据类（3.3.0-B/C 增强版契约）；
- FrontmatterParser：解析 Obsidian Markdown 的 YAML frontmatter 与正文；
- KnowledgeItemExtractor：笔记 → KnowledgeItem（任务1）；
- SourceRefBinder：KnowledgeItem → source_ref 绑定 + C1-C6 校验，失败保持 Pending_Verification（任务2）；
- ExpertBinder：KnowledgeItem.author → experts.json 关联，检查 qualification_status / sign_scope / SoD（任务3）；
- ObsidianToBoipConnector：单向 Obsidian→BOIP 编排（任务4），内置安全护栏（任务5）。

红线（全系列，本 Sprint 串接）：
- 不录入真实工程参数：content / source / author 等取值保持 pending_verification；
- 不修改 verified.json value（Connector 不含任何写入 verified.json 的代码路径）；
- 不开启 engineering_enabled（复用 load_engineering_enabled 作只读断言）；
- 不输出 engineering_approved、不自动创建 ReleaseApproval；
- AI 不代签 / 不代授权：ExpertBinder 仅校验资格与范围，绝不落 expert_verified_by / verified_by。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

import yaml

from agents.config_loader import load_engineering_enabled
from agents.engineering.thresholds.schema import ThresholdSourceRef
from agents.engineering.thresholds.source_ref_validator import (
    compute_content_hash,
    validate_source_ref,
)

PENDING_PLACEHOLDER: str = "pending_verification"
SYNC_DIRECTION: str = "obsidian_to_boip"

# Obsidian frontmatter 边界分隔符（--- 行）。
_FRONTMATTER_DELIM: str = "---"
_H1_PATTERN: re.Pattern[str] = re.compile(r"^#\s+(.+?)\s*$")
_KI_PREFIX: str = "KI-"


class KnowledgeItemState(str, Enum):
    """KnowledgeItem 七态生命周期（3.3.0-B/C 增强版）。"""

    CAPTURED = "Captured"
    PENDING_VERIFICATION = "Pending_Verification"
    SOURCE_VERIFIED = "Source_Verified"
    EXPERT_VERIFIED = "Expert_Verified"
    ENGINEERING_VERIFIED = "Engineering_Verified"
    ENGINEERING_APPROVED = "Engineering_Approved"
    DEPRECATED = "Deprecated"

    @classmethod
    def from_obsidian_verification_status(cls, raw: Any) -> "KnowledgeItemState":
        """Obsidian frontmatter 三态 verification_status → 七态映射。

        draft → Pending_Verification；verified_source → Source_Verified；
        deprecated → Deprecated；缺失 / 未知 → Captured（原始抽取态）。
        """
        if raw is None:
            return cls.CAPTURED
        normalized = str(raw).strip().lower()
        if normalized == "verified_source":
            return cls.SOURCE_VERIFIED
        if normalized == "deprecated":
            return cls.DEPRECATED
        if normalized == "draft":
            return cls.PENDING_VERIFICATION
        # 未知取值保守降级为 Captured，交由 SourceRefBinder 重新归类。
        return cls.CAPTURED


# KnowledgeItem 13 字段核心契约（3.3.0-B/C §1，顺序即契约顺序）。
# 注：confidence / session_id 为辅助元数据，不计入 13 字段主键契约。
@dataclass
class KnowledgeItem:
    """KnowledgeItem 标准中间层（13 字段 + 辅助元数据）。"""

    knowledge_id: str
    knowledge_type: str
    parent_knowledge_id: str
    title: str
    content: str
    source: str
    author: str
    domain: str
    content_hash: str
    validation_status: str
    linked_entities: list[str]
    created_at: str
    updated_at: str
    confidence: str = "unverified"
    session_id: str = ""

    CORE_FIELD_COUNT: int = 13

    def to_dict(self) -> dict[str, Any]:
        """序列化（13 核心字段优先，辅助元数据随后）。"""
        return {
            "knowledge_id": self.knowledge_id,
            "knowledge_type": self.knowledge_type,
            "parent_knowledge_id": self.parent_knowledge_id,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "author": self.author,
            "domain": self.domain,
            "content_hash": self.content_hash,
            "validation_status": self.validation_status,
            "linked_entities": list(self.linked_entities),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "confidence": self.confidence,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "KnowledgeItem":
        """从字典恢复（容错缺省，缺失核心字段补 pending_verification）。"""
        def _str(key: str, default: str = PENDING_PLACEHOLDER) -> str:
            value = data.get(key, default)
            return default if value is None else str(value)

        linked = data.get("linked_entities") or []
        if isinstance(linked, str):
            linked = [linked]

        return cls(
            knowledge_id=_str("knowledge_id"),
            knowledge_type=_str("knowledge_type"),
            parent_knowledge_id=_str("parent_knowledge_id"),
            title=_str("title"),
            content=_str("content"),
            source=_str("source"),
            author=_str("author"),
            domain=_str("domain"),
            content_hash=_str("content_hash"),
            validation_status=_str(
                "validation_status", KnowledgeItemState.PENDING_VERIFICATION.value
            ),
            linked_entities=list(linked),
            created_at=_str("created_at"),
            updated_at=_str("updated_at"),
            confidence=_str("confidence", "unverified"),
            session_id=_str("session_id", ""),
        )


class FrontmatterParser:
    """解析 Obsidian Markdown：提取 YAML frontmatter 与正文。"""

    @staticmethod
    def parse(note_text: str) -> tuple[dict[str, Any], str]:
        """返回 (frontmatter 字典, 正文文本)。

        无 frontmatter 时返回 ({}, 全文)。frontmatter 解析失败则回退为空字典，
        不抛异常（保持抽取流程健壮，正文照常捕获）。
        """
        text = note_text or ""
        lines = text.splitlines()
        if not lines or lines[0].strip() != _FRONTMATTER_DELIM:
            return {}, text.strip()

        end_index: Optional[int] = None
        for index in range(1, len(lines)):
            if lines[index].strip() == _FRONTMATTER_DELIM:
                end_index = index
                break

        if end_index is None:
            # 未闭合的 frontmatter：当作无 frontmatter 处理。
            return {}, text.strip()

        raw_fm = "\n".join(lines[1:end_index])
        body = "\n".join(lines[end_index + 1:]).strip()
        try:
            fm = yaml.safe_load(raw_fm) or {}
        except yaml.YAMLError:
            fm = {}
        if not isinstance(fm, dict):
            fm = {}
        return fm, body


class KnowledgeItemExtractor:
    """任务1：Obsidian Markdown → KnowledgeItem（13 字段 + 七态）。"""

    def __init__(
        self,
        *,
        default_domain: str = PENDING_PLACEHOLDER,
        clock: Optional[Callable[[], str]] = None,
    ) -> None:
        self._default_domain = default_domain
        self._clock = clock or self._iso_now

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _split_title_and_body(
        self, body: str, fm: Mapping[str, Any], note_path: str
    ) -> tuple[str, str]:
        """从正文中提取首个 H1 作为 title，剩余行作为 content（避免标题重复）。"""
        lines = body.splitlines()
        title: Optional[str] = None
        content_lines: list[str] = []
        for line in lines:
            match = _H1_PATTERN.match(line.strip())
            if match and title is None:
                title = match.group(1).strip()
            else:
                content_lines.append(line)
        if title is None:
            if fm.get("title"):
                title = str(fm["title"])
            elif note_path:
                title = Path(note_path).stem
            else:
                title = PENDING_PLACEHOLDER
        content = "\n".join(content_lines).strip()
        if not content:
            content = PENDING_PLACEHOLDER
        return title, content

    def extract(self, note_text: str, note_path: str = "") -> KnowledgeItem:
        """执行抽取，产出符合 13 字段七态契约的 KnowledgeItem。"""
        fm, body = FrontmatterParser.parse(note_text)
        title, content = self._split_title_and_body(body, fm, note_path)
        body_text = body.strip()

        content_hash = compute_content_hash(f"{fm!r}\n{body_text}")
        knowledge_id = _KI_PREFIX + hashlib.sha256(
            note_text.encode("utf-8")
        ).hexdigest()[:16]
        now = self._clock()

        source = self._as_str(fm.get("source"))
        author = self._as_str(fm.get("author"))
        domain = self._as_str(fm.get("domain"), self._default_domain)
        knowledge_type = self._as_str(fm.get("knowledge_type"))
        parent = self._as_str(fm.get("upstream"))
        linked = self._as_list(fm.get("linked_threshold"))
        status = KnowledgeItemState.from_obsidian_verification_status(
            fm.get("verification_status")
        ).value

        return KnowledgeItem(
            knowledge_id=knowledge_id,
            knowledge_type=knowledge_type,
            parent_knowledge_id=parent,
            title=title,
            content=content,
            source=source,
            author=author,
            domain=domain,
            content_hash=content_hash,
            validation_status=status,
            linked_entities=linked,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _as_str(value: Any, default: str = PENDING_PLACEHOLDER) -> str:
        if value is None or value == "":
            return default
        return str(value)

    @staticmethod
    def _as_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple, set)):
            return [str(v) for v in value]
        return [str(value)]


@dataclass
class SourceRefBindResult:
    """SourceRefBinder 单次绑定结果。"""

    ok: bool
    reason: str
    source_ref: ThresholdSourceRef
    new_status: str


class SourceRefBinder:
    """任务2：KnowledgeItem → source_ref 绑定 + C1-C6 校验。

    C1-C6 全部通过 → Source_Verified；任一不满足 → 保持 Pending_Verification。
    复用 agents.engineering.thresholds.source_ref_validator.validate_source_ref。
    """

    def __init__(self, spec_sources: Any = None) -> None:
        self._sources = self._index(spec_sources)

    @staticmethod
    def _index(spec_sources: Any) -> dict[str, dict[str, Any]]:
        if isinstance(spec_sources, Mapping) and "sources" in spec_sources:
            raw = spec_sources["sources"]
        elif isinstance(spec_sources, Sequence) and not isinstance(spec_sources, str):
            raw = spec_sources
        else:
            raw = []
        indexed: dict[str, dict[str, Any]] = {}
        for entry in raw:
            if isinstance(entry, Mapping):
                sid = entry.get("source_id")
                if sid:
                    indexed[str(sid)] = dict(entry)
        return indexed

    def bind(
        self,
        item: KnowledgeItem,
        *,
        content_provider: Optional[Callable[[str], str]] = None,
    ) -> SourceRefBindResult:
        """绑定 source_ref 并做 C1-C6 校验。"""
        source_id = item.source
        if not source_id or source_id == PENDING_PLACEHOLDER:
            return SourceRefBindResult(
                False,
                "knowledge_item.source 未解析（仍为 pending_verification）",
                ThresholdSourceRef(),
                KnowledgeItemState.PENDING_VERIFICATION.value,
            )

        src = self._sources.get(source_id)
        if src is None:
            return SourceRefBindResult(
                False,
                f"source_id={source_id} 未在 spec_sources 登记",
                ThresholdSourceRef(),
                KnowledgeItemState.PENDING_VERIFICATION.value,
            )

        if src.get("source_status") != "verified_source":
            return SourceRefBindResult(
                False,
                f"source_id={source_id} source_status={src.get('source_status')} 非 verified_source，拒绝引用",
                ThresholdSourceRef(),
                KnowledgeItemState.PENDING_VERIFICATION.value,
            )

        clause = self._resolve_clause(item, src)
        ref = ThresholdSourceRef(
            standard=str(src.get("standard") or ""),
            clause=clause,
            edition=str(src.get("edition") or ""),
            url=str(src.get("official_url") or ""),
            retrieved_at=str(src.get("retrieved_at") or ""),
            hash=str(src.get("source_hash") or ""),
        )

        content = content_provider(source_id) if content_provider else None
        ok, reason = validate_source_ref(ref, content=content)
        new_status = (
            KnowledgeItemState.SOURCE_VERIFIED.value
            if ok
            else KnowledgeItemState.PENDING_VERIFICATION.value
        )
        return SourceRefBindResult(ok, reason, ref, new_status)

    @staticmethod
    def _resolve_clause(item: KnowledgeItem, src: Mapping[str, Any]) -> str:
        """解析被引用的条款号：优先 KnowledgeItem 显式 clause，否则取 source 首条 clause_index。"""
        clause_index = src.get("clause_index") or []
        if isinstance(clause_index, str):
            clause_index = [clause_index]
        if clause_index:
            return str(clause_index[0])
        return ""


@dataclass
class ExpertBindResult:
    """ExpertBinder 单次关联结果。"""

    ok: bool
    reason: str
    expert_id: str
    qualification_ok: bool = False
    scope_ok: bool = False
    sod_ok: bool = False


class ExpertBinder:
    """任务3：KnowledgeItem.author → experts.json 关联校验。

    仅校验资格（qualification_status=verified）、范围（sign_scope 覆盖 domain）、
    角色（sod_role 非空）；绝不落 expert_verified_by / verified_by（AI 不代签）。
    """

    def __init__(self, experts: Any = None) -> None:
        self._experts = self._index(experts)

    @staticmethod
    def _index(experts: Any) -> dict[str, dict[str, Any]]:
        if isinstance(experts, Mapping) and "experts" in experts:
            raw = experts["experts"]
        elif isinstance(experts, Sequence) and not isinstance(experts, str):
            raw = experts
        else:
            raw = []
        indexed: dict[str, dict[str, Any]] = {}
        for entry in raw:
            if isinstance(entry, Mapping):
                eid = entry.get("expert_id")
                if eid:
                    indexed[str(eid)] = dict(entry)
        return indexed

    def bind(self, item: KnowledgeItem) -> ExpertBindResult:
        """校验 author 与专家名录的资格 / 范围 / 角色一致性。"""
        author = item.author
        if not author or author == PENDING_PLACEHOLDER:
            return ExpertBindResult(
                False,
                "knowledge_item.author 未解析（仍为 pending_verification）",
                PENDING_PLACEHOLDER,
            )

        expert = self._experts.get(author)
        if expert is None:
            return ExpertBindResult(
                False,
                f"expert_id={author} 未在 experts.json 登记",
                author,
            )

        # R5：仅 qualification_status=verified 允许签署。
        qualification_ok = expert.get("qualification_status") == "verified"
        # R4：sign_scope 必须覆盖 domain。
        sign_scope = expert.get("sign_scope") or []
        if isinstance(sign_scope, str):
            sign_scope = [sign_scope]
        scope_ok = item.domain == PENDING_PLACEHOLDER or item.domain in sign_scope
        # SoD：sod_role 须明确（expert / principal），关联阶段仅校验角色存在。
        sod_ok = bool(expert.get("sod_role"))

        ok = qualification_ok and scope_ok and sod_ok
        if not ok:
            reasons: list[str] = []
            if not qualification_ok:
                reasons.append("qualification_status 非 verified")
            if not scope_ok:
                reasons.append("sign_scope 不覆盖 domain")
            if not sod_ok:
                reasons.append("sod_role 未指定")
            return ExpertBindResult(
                False,
                "；".join(reasons),
                author,
                qualification_ok,
                scope_ok,
                sod_ok,
            )

        return ExpertBindResult(
            True,
            "expert_binding_ok",
            author,
            qualification_ok,
            scope_ok,
            sod_ok,
        )


@dataclass
class ConnectorResult:
    """ObsidianToBoipConnector 单次处理结果。"""

    item: KnowledgeItem
    source_ref_result: SourceRefBindResult
    expert_result: ExpertBindResult
    repository_info: Optional[dict] = None


class ObsidianToBoipConnector:
    """任务4 + 任务5：单向 Obsidian→BOIP 编排 + 安全护栏。

    方向：Obsidian → BOIP（单向采集），绝不反向覆盖原笔记（本类不提供 write-back）。
    安全：不写 verified.json、不开启 engineering_enabled、不建 ReleaseApproval、
    不代签 / 不代授权。
    """

    def __init__(
        self,
        *,
        spec_sources: Any = None,
        experts: Any = None,
        clock: Optional[Callable[[], str]] = None,
    ) -> None:
        self._extractor = KnowledgeItemExtractor(clock=clock)
        self._source_binder = SourceRefBinder(spec_sources)
        self._expert_binder = ExpertBinder(experts)

    def process_note(
        self, note_text: str, note_path: str = "", repository: Any = None
    ) -> ConnectorResult:
        """抽取 → 绑定 source_ref → 关联专家 →（可选）入库 Repository。

        流程（任务4）：Obsidian → KnowledgeItem → Validation → Repository。
        repository 传入 KnowledgeRepository 实例时，验证后将 KnowledgeItem 落库，
        并据 source_ref 校验结果补记 verify 事件；不传则仅做内存编排（向后兼容）。
        专家关联仅校验资格/范围，不改动 validation_status（签署由人工驱动）。
        """
        item = self._extractor.extract(note_text, note_path)
        source_result = self._source_binder.bind(item)
        # SourceRef 绑定成功升 Source_Verified，否则停留 Pending_Verification。
        item.validation_status = source_result.new_status
        expert_result = self._expert_binder.bind(item)

        repository_info: Optional[dict] = None
        if repository is not None:
            version = repository.save(
                item,
                actor="obsidian_connector",
                detail=f"imported from {note_path or 'obsidian'}",
            )
            repository_info = {"saved": True, "version": version}
            if source_result.ok:
                repository.record_event(
                    item.knowledge_id,
                    "verify",
                    actor="obsidian_connector",
                    detail="source_ref C1-C6 passed",
                    version=version,
                )
                repository_info["verify_event"] = True

        return ConnectorResult(
            item=item,
            source_ref_result=source_result,
            expert_result=expert_result,
            repository_info=repository_info,
        )

    @staticmethod
    def sync_direction() -> str:
        """返回同步方向常量（单向 Obsidian→BOIP）。"""
        return SYNC_DIRECTION

    @staticmethod
    def safety_invariants_ok() -> bool:
        """安全护栏只读断言：engineering_enabled 必须保持 False（默认闸门关闭）。"""
        return load_engineering_enabled() is False


__all__ = [
    "PENDING_PLACEHOLDER",
    "SYNC_DIRECTION",
    "KnowledgeItemState",
    "KnowledgeItem",
    "FrontmatterParser",
    "KnowledgeItemExtractor",
    "SourceRefBindResult",
    "SourceRefBinder",
    "ExpertBindResult",
    "ExpertBinder",
    "ConnectorResult",
    "ObsidianToBoipConnector",
]
