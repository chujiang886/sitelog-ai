"""Engineering 阈值录入工作流（Phase 3.2 Sprint 3.2.4-F）。

首批真实工程阈值录入流程实施。本阶段授权范围仅限 E-TH-01、E-TH-02、E-TH-03，
对应首个灰度接口（风压分析，无上游工程依赖，Engineering 侧可独立双签）。

本模块是「录入工作流工具」：接受**人工在调用时显式提供**的真实工程数据
（threshold_id / value / unit / source_ref / version / 签字人），按
提交 → 主理人审核 → 专家复核 → 转正 四步推进，每步写入 review_log 审核链。

最高安全级别（红线，3.2.4-F 任务书）：
- 本模块**绝不**自行生成工程参数、绝不猜测规范值、绝不补充缺失数据、绝不修改
  专家签署信息；上述数据必须由人工提供（value / unit / source_ref / signer 等）；
- 仅授权范围内的阈值可被录入，越权（D-TH / E-TH-04~06）一律拒绝；
- source_ref 强制经 ``validate_source_ref`` 校验，任一 C1-C6 不满足即拒绝进入审核；
- 双签 SoD：专家复核人与主理人核准人**不得为同一身份**；
- 录入流程全程**不开启** ``engineering_enabled``、**不输出** ``engineering_approved``；
  ``evaluate_gates`` 仅执行 G1-G6 检查并确认闸门保持关闭（False），绝不翻转开关、
  绝不写 config.yaml。

注：本模块默认写入路径为 Engineering 签字库 ``verified.json``；真实录入须由人工
提供数据后调用。AI 在 3.2.4-F 阶段**不会**以真实数据调用本工具——仅以合成占位
（value=None）验证工作流机制，红线全程守约。
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from agents.engineering.review_log import append_review_event
from agents.engineering.thresholds.schema import ThresholdStatus
from agents.engineering.thresholds.source_ref_validator import (
    PENDING_PLACEHOLDER as _PENDING,
    _EDITION_PATTERN as _EDITION,
    _HASH_PATTERN as _HASH,
    validate_source_ref,
)
from agents.engineering.threshold_loader import DEFAULT_VERIFIED_PATH


# 本阶段授权录入的阈值 ID 集合（风压接口所需，Engineering 侧可独立双签）。
# 越权（D-TH-01~05 / E-TH-04~06）一律拒绝，详见 submit 授权检查。
DEFAULT_ALLOWED_IDS: frozenset[str] = frozenset({"E-TH-01", "E-TH-02", "E-TH-03"})

DEFAULT_VERSION: str = "1.0.0"
DEFAULT_SCHEMA_VERSION: int = 2


class IntakeOutcome(str, Enum):
    """录入动作结果：受理 / 拒绝。"""

    ACCEPTED = "accepted"
    REJECTED = "rejected"


# 拒绝原因（供测试与日志可追溯）。
REASON_UNAUTHORIZED = "threshold_id 不在本阶段授权录入范围"
REASON_SOURCE_REF_INVALID = "source_ref 校验未通过（C1-C6）"
REASON_ALREADY_VERIFIED = "阈值已转正，禁止重复录入"
REASON_NOT_SUBMITTED = "阈值尚未提交，无法审核"
REASON_SOD_CONFLICT = "SoD 冲突：专家复核人与主理人核准人不得为同一身份"
REASON_NEED_PRINCIPAL_REVIEW = "须先由主理人核准，方可专家复核"
REASON_MISSING_DUAL_SIGN = "双签不完整（缺主理人核准或专家签字），禁止转正"


@dataclass
class IntakeRequest:
    """人工提交的单条阈值录入请求（数据须由人工显式提供，AI 不生成）。

    字段：
    - ``threshold_id``：阈值标识（须属授权集合）；
    - ``value``：真实工程数值（**人工提供**；AI 阶段传 None 占位，不编造）；
    - ``unit``：单位（人工提供）；
    - ``source_ref``：结构化规范来源引用（standard/clause/edition/url/hash 等）；
    - ``version``：阈值版本（缺省 1.0.0）；
    - ``param``：参数中文名（缺省取 threshold_id）；
    - ``submitted_by``：提交人标识（人工提供，纯标识符）。
    """

    threshold_id: str
    value: Any
    unit: str
    source_ref: Mapping[str, Any]
    version: str = DEFAULT_VERSION
    param: str = ""
    submitted_by: str = "submitter-001"


@dataclass
class IntakeResult:
    """单步录入动作的结果。"""

    outcome: IntakeOutcome
    threshold_id: str
    state: str
    message: str
    review_event: dict[str, Any] | None = None
    entry: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        """序列化为 JSON 友好字典。"""

        return {
            "outcome": self.outcome.value,
            "threshold_id": self.threshold_id,
            "state": self.state,
            "message": self.message,
            "review_event": self.review_event,
            "entry": self.entry,
        }


def _now_iso() -> str:
    """返回 UTC ISO8601 时间戳（与 review_log 默认一致）。"""

    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


class ThresholdIntakeWorkflow:
    """阈值录入工作流：提交 → 主理人审核 → 专家复核 → 转正，每步落 review_log。

    设计边界（红线）：
    - 只读/写由 ``verified_path`` 指定的签字库（默认 Engineering ``verified.json``）；
    - 每次写盘前生成快照（``snapshot`` 目录），支持回滚；
    - 绝不写 config.yaml、绝不翻转 ``engineering_enabled``、绝不输出 approved。
    """

    def __init__(
        self,
        *,
        verified_path: "Path | str | None" = None,
        review_log_path: "Path | str | None" = None,
        allowed_ids: "frozenset[str] | None" = None,
        snapshot_dir: "Path | str | None" = None,
    ) -> None:
        self.verified_path: Path = (
            Path(verified_path) if verified_path is not None else DEFAULT_VERIFIED_PATH
        )
        self.review_log_path: Path | None = (
            Path(review_log_path) if review_log_path is not None else None
        )
        self.allowed_ids: frozenset[str] = (
            allowed_ids if allowed_ids is not None else DEFAULT_ALLOWED_IDS
        )
        self.snapshot_dir: Path = (
            Path(snapshot_dir)
            if snapshot_dir is not None
            else self.verified_path.parent / "intake_snapshots"
        )

    # ------------------------------------------------------------------
    # 内部 IO 助手（带快照）
    # ------------------------------------------------------------------

    def _snapshot(self) -> "Path | None":
        """写盘前对当前签字库生成内容快照（复制），返回快照路径；文件缺失则跳过。"""

        if not self.verified_path.is_file():
            return None
        try:
            self.snapshot_dir.mkdir(parents=True, exist_ok=True)
            import hashlib

            digest = hashlib.sha256(self.verified_path.read_bytes()).hexdigest()[:16]
            snap = self.snapshot_dir / f"verified.{digest}.before.json"
            shutil.copy2(self.verified_path, snap)
            return snap
        except OSError:
            return None

    def _read_entries(self) -> dict[str, Any]:
        """读取签字库 thresholds 段；缺失/损坏 → 空 dict。"""

        if not self.verified_path.is_file():
            return {}
        try:
            raw = json.loads(self.verified_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        thresholds = raw.get("thresholds")
        return dict(thresholds) if isinstance(thresholds, dict) else {}

    def _write_entries(self, entries: Mapping[str, Any]) -> None:
        """原子写回签字库（schema_version=2），先临时文件再 replace。"""

        raw: dict[str, Any] = {
            "schema_version": DEFAULT_SCHEMA_VERSION,
            "note": "BOIP Engineering 阈值签字库（经 3.2.4-F 录入工作流写入）。",
            "thresholds": dict(entries),
        }
        tmp = self.verified_path.with_name(f"{self.verified_path.stem}.tmp.json")
        tmp.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        json.loads(tmp.read_text(encoding="utf-8"))  # 回解析校验
        tmp.replace(self.verified_path)

    def _log(
        self,
        *,
        threshold_id: str,
        action: str,
        signer_role: str,
        signer: str,
        source_ref: str,
    ) -> dict[str, Any]:
        """追加一条审核事件（委托 review_log），返回事件记录。"""

        return append_review_event(
            threshold_id=threshold_id,
            action=action,
            signer_role=signer_role,
            signer=signer,
            source_ref=source_ref,
            log_path=self.review_log_path,
        )

    # ------------------------------------------------------------------
    # 步骤 1：提交（含授权 + source_ref 校验）
    # ------------------------------------------------------------------

    def submit(self, request: IntakeRequest) -> IntakeResult:
        """专家/提交人提交一条阈值录入请求。

        检查顺序：授权范围 → source_ref 校验 → 是否已转正；任一不满足即拒绝，
        并写入 ``intake_rejected`` 审核事件（不写入库）。通过则写入草稿态
        （threshold_status=review，verified=false，双签位为空），写 ``submit``。
        """

        tid = (request.threshold_id or "").strip()

        # 授权范围检查（红线：越权阈值禁止录入）。
        if tid not in self.allowed_ids:
            event = self._log(
                threshold_id=tid,
                action="intake_rejected",
                signer_role="system",
                signer="gate",
                source_ref=REASON_UNAUTHORIZED,
            )
            return IntakeResult(
                outcome=IntakeOutcome.REJECTED,
                threshold_id=tid,
                state="rejected",
                message=REASON_UNAUTHORIZED,
                review_event=event,
            )

        # source_ref 强制校验（C1-C6）。
        ok, reason = validate_source_ref(request.source_ref)
        if not ok:
            event = self._log(
                threshold_id=tid,
                action="intake_rejected",
                signer_role="system",
                signer="gate",
                source_ref=reason,
            )
            return IntakeResult(
                outcome=IntakeOutcome.REJECTED,
                threshold_id=tid,
                state="rejected",
                message=f"{REASON_SOURCE_REF_INVALID}:{reason}",
                review_event=event,
            )

        entries = self._read_entries()
        existing = entries.get(tid)
        if isinstance(existing, Mapping) and existing.get("verified") is True:
            event = self._log(
                threshold_id=tid,
                action="intake_rejected",
                signer_role="system",
                signer="gate",
                source_ref=REASON_ALREADY_VERIFIED,
            )
            return IntakeResult(
                outcome=IntakeOutcome.REJECTED,
                threshold_id=tid,
                state="rejected",
                message=REASON_ALREADY_VERIFIED,
                review_event=event,
            )

        # 写入草稿态（仍 pending_verification；仅占位，value 原样来自人工）。
        self._snapshot()
        sr = dict(request.source_ref)
        entry: dict[str, Any] = {
            "param": request.param or tid,
            "value": request.value,
            "unit": request.unit,
            "threshold_status": ThresholdStatus.REVIEW.value,
            "version": request.version or DEFAULT_VERSION,
            "verified": False,
            "verified_by": None,
            "verified_at": None,
            "expert_verified_by": None,
            "expert_verified_at": None,
            "source_ref": sr,
            "applies_to": [],
            "submitted_by": request.submitted_by,
            "submitted_at": _now_iso(),
        }
        entries[tid] = entry
        self._write_entries(entries)

        event = self._log(
            threshold_id=tid,
            action="submit",
            signer_role="submitter",
            signer=request.submitted_by,
            source_ref=json.dumps(sr, ensure_ascii=False),
        )
        return IntakeResult(
            outcome=IntakeOutcome.ACCEPTED,
            threshold_id=tid,
            state=ThresholdStatus.REVIEW.value,
            message="已提交，进入主理人审核",
            review_event=event,
            entry=entry,
        )

    # ------------------------------------------------------------------
    # 步骤 2：主理人审核（核准）
    # ------------------------------------------------------------------

    def review(
        self, *, threshold_id: str, verified_by: str, verified_at: str
    ) -> IntakeResult:
        """主理人核准：写入 verified_by / verified_at（人工提供，AI 不篡改）。

        前置：阈值须处于提交态（threshold_status=review 且未 verified）。
        """

        tid = (threshold_id or "").strip()
        entries = self._read_entries()
        entry = entries.get(tid)
        if not isinstance(entry, Mapping) or entry.get("threshold_status") not in (
            ThresholdStatus.REVIEW.value,
            ThresholdStatus.DRAFT.value,
        ):
            event = self._log(
                threshold_id=tid,
                action="intake_rejected",
                signer_role="system",
                signer="gate",
                source_ref=REASON_NOT_SUBMITTED,
            )
            return IntakeResult(
                outcome=IntakeOutcome.REJECTED,
                threshold_id=tid,
                state="rejected",
                message=REASON_NOT_SUBMITTED,
                review_event=event,
            )

        self._snapshot()
        updated = dict(entry)
        updated["verified_by"] = verified_by
        updated["verified_at"] = verified_at
        entries[tid] = updated
        self._write_entries(entries)

        event = self._log(
            threshold_id=tid,
            action="review",
            signer_role="principal",
            signer=verified_by,
            source_ref=json.dumps(updated.get("source_ref", {}), ensure_ascii=False),
        )
        return IntakeResult(
            outcome=IntakeOutcome.ACCEPTED,
            threshold_id=tid,
            state=ThresholdStatus.REVIEW.value,
            message="主理人已核准",
            review_event=event,
            entry=updated,
        )

    # ------------------------------------------------------------------
    # 步骤 3：专家复核（双签 SoD）
    # ------------------------------------------------------------------

    def expert_recheck(
        self, *, threshold_id: str, expert_verified_by: str, expert_verified_at: str
    ) -> IntakeResult:
        """行业专家复核签字：写入 expert_verified_by / expert_verified_at。

        SoD：专家复核人不得与主理人核准人同一身份（红线）。且须先主理人核准。
        """

        tid = (threshold_id or "").strip()
        entries = self._read_entries()
        entry = entries.get(tid)
        if not isinstance(entry, Mapping) or entry.get("threshold_status") not in (
            ThresholdStatus.REVIEW.value,
            ThresholdStatus.DRAFT.value,
        ):
            event = self._log(
                threshold_id=tid,
                action="intake_rejected",
                signer_role="system",
                signer="gate",
                source_ref=REASON_NOT_SUBMITTED,
            )
            return IntakeResult(
                outcome=IntakeOutcome.REJECTED,
                threshold_id=tid,
                state="rejected",
                message=REASON_NOT_SUBMITTED,
                review_event=event,
            )

        # 须先主理人核准。
        if not entry.get("verified_by"):
            event = self._log(
                threshold_id=tid,
                action="intake_rejected",
                signer_role="system",
                signer="gate",
                source_ref=REASON_NEED_PRINCIPAL_REVIEW,
            )
            return IntakeResult(
                outcome=IntakeOutcome.REJECTED,
                threshold_id=tid,
                state="rejected",
                message=REASON_NEED_PRINCIPAL_REVIEW,
                review_event=event,
            )

        # SoD：专家复核人与主理人核准人不得为同一身份。
        if expert_verified_by == entry.get("verified_by"):
            event = self._log(
                threshold_id=tid,
                action="intake_rejected",
                signer_role="system",
                signer="gate",
                source_ref=REASON_SOD_CONFLICT,
            )
            return IntakeResult(
                outcome=IntakeOutcome.REJECTED,
                threshold_id=tid,
                state="rejected",
                message=REASON_SOD_CONFLICT,
                review_event=event,
            )

        self._snapshot()
        updated = dict(entry)
        updated["expert_verified_by"] = expert_verified_by
        updated["expert_verified_at"] = expert_verified_at
        entries[tid] = updated
        self._write_entries(entries)

        event = self._log(
            threshold_id=tid,
            action="expert_recheck",
            signer_role="expert",
            signer=expert_verified_by,
            source_ref=json.dumps(updated.get("source_ref", {}), ensure_ascii=False),
        )
        return IntakeResult(
            outcome=IntakeOutcome.ACCEPTED,
            threshold_id=tid,
            state=ThresholdStatus.REVIEW.value,
            message="专家已复核签字",
            review_event=event,
            entry=updated,
        )

    # ------------------------------------------------------------------
    # 步骤 4：转正（双签齐全方可）
    # ------------------------------------------------------------------

    def finalize_verified(self, threshold_id: str) -> IntakeResult:
        """转正：双签齐全（主理人核准 + 专家签字）方可置 verified=true。

        缺任一签字即拒绝（不擅自转正）。转正后 threshold_status=verified，
        但仍受 ``engineering_enabled`` 闸门约束（本工作流不翻转该开关）。
        """

        tid = (threshold_id or "").strip()
        entries = self._read_entries()
        entry = entries.get(tid)
        if not isinstance(entry, Mapping):
            event = self._log(
                threshold_id=tid,
                action="intake_rejected",
                signer_role="system",
                signer="gate",
                source_ref=REASON_NOT_SUBMITTED,
            )
            return IntakeResult(
                outcome=IntakeOutcome.REJECTED,
                threshold_id=tid,
                state="rejected",
                message=REASON_NOT_SUBMITTED,
                review_event=event,
            )

        # 双签完整判定：主理人核准（verified_by/at）+ 行业专家签字
        # （expert_verified_by/at）俱全。注意：``verified`` 标志由本步骤置位，
        # 判定"是否可转正"时**不应**要求它已为真，否则自相矛盾。
        mgmt_ok = bool(entry.get("verified_by")) and bool(entry.get("verified_at"))
        expert_ok = bool(entry.get("expert_verified_by")) and bool(entry.get("expert_verified_at"))
        if not (mgmt_ok and expert_ok):
            event = self._log(
                threshold_id=tid,
                action="intake_rejected",
                signer_role="system",
                signer="gate",
                source_ref=REASON_MISSING_DUAL_SIGN,
            )
            return IntakeResult(
                outcome=IntakeOutcome.REJECTED,
                threshold_id=tid,
                state="rejected",
                message=REASON_MISSING_DUAL_SIGN,
                review_event=event,
            )

        self._snapshot()
        updated = dict(entry)
        updated["verified"] = True
        updated["threshold_status"] = ThresholdStatus.VERIFIED.value
        entries[tid] = updated
        self._write_entries(entries)

        event = self._log(
            threshold_id=tid,
            action="verified",
            signer_role="system",
            signer="workflow",
            source_ref=json.dumps(updated.get("source_ref", {}), ensure_ascii=False),
        )
        return IntakeResult(
            outcome=IntakeOutcome.ACCEPTED,
            threshold_id=tid,
            state=ThresholdStatus.VERIFIED.value,
            message="已双签转正（仍受 engineering_enabled 闸门约束）",
            review_event=event,
            entry=updated,
        )

    # ------------------------------------------------------------------
    # 门禁检查（保持 engineering_enabled=false）
    # ------------------------------------------------------------------

    def evaluate_gates(self) -> tuple[bool, list[str]]:
        """执行 G1-G6 门禁检查，并确认闸门保持关闭。

        返回 ``(allowed, reasons)``。即便已双签转正，本方法仍传入
        ``ci_green=False / rollback_ready=False / authorization_present=False``，
        且**绝不**翻转 ``engineering_enabled``、绝不写 config.yaml——
        因此结果恒为 ``(False, reasons)``，确认灰度闸门默认拒绝。
        """

        from agents.engineering.gate.enable_gate import can_enable_engineering

        entries = self._read_entries()
        allowed, reasons = can_enable_engineering(
            thresholds=entries.values(),
            ci_green=False,
            rollback_ready=False,
            authorization_present=False,
            review_log_path=self.review_log_path,
        )
        # 红线保证：录入工作流任何情况下都不允许开启 engineering_enabled。
        return (False, reasons) if allowed else (allowed, reasons)


# ------------------------------------------------------------------
# 演练编排（Sprint 3.2.4-G 真实资料录入演练）
# ------------------------------------------------------------------
# 演练阶段：本模块接受**人工在调用时显式提供**的真实工程资料（value / unit /
# source_ref / version / 签字人），AI 仅做格式校验与流程编排，**绝不**生成参数、
# 绝不猜测缺失、绝不修改专家签署、绝不自动补 source_ref。即便阈值双签转正，
# engineering_enabled 仍恒为 False（红线，由 evaluate_gates 保证）。

DRILL_VERIFICATION_STATUS: str = "pending_verification"


@dataclass
class SourceVerificationReport:
    """source_ref 验证报告（任务3）：逐条 C1-C6 校验 + 总体结论。"""

    threshold_id: str
    source_ref: dict[str, Any]
    passed: bool
    checks: dict[str, dict[str, Any]]
    overall: str

    def as_dict(self) -> dict[str, Any]:
        """序列化为 JSON 友好字典。"""

        return {
            "threshold_id": self.threshold_id,
            "passed": self.passed,
            "overall": self.overall,
            "checks": self.checks,
            "source_ref": self.source_ref,
        }


@dataclass
class IntakeDrillResult:
    """单次录入演练结果（任务1/2/4）：授权、source 报告、步骤链、转正、门禁。"""

    threshold_id: str
    authorized: bool
    source_report: "SourceVerificationReport | None"
    steps: list[str]
    verified: bool
    review_event_id: str | None
    gate_allowed: bool
    gate_reasons: list[str]
    engineering_enabled: bool
    verification_status: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        """序列化为 JSON 友好字典。"""

        return {
            "threshold_id": self.threshold_id,
            "authorized": self.authorized,
            "source_report": self.source_report.as_dict()
            if self.source_report is not None
            else None,
            "steps": self.steps,
            "verified": self.verified,
            "review_event_id": self.review_event_id,
            "gate_allowed": self.gate_allowed,
            "gate_reasons": self.gate_reasons,
            "engineering_enabled": self.engineering_enabled,
            "verification_status": self.verification_status,
            "message": self.message,
        }


def build_source_verification_report(raw_source_ref: Any) -> SourceVerificationReport:
    """构造 source_ref 验证报告（任务3）：逐条 C1-C6 校验。

    与 ``validate_source_ref`` 共用同一组规则常量（standard/clause/edition/url/hash
    的判定正则来自 source_ref_validator），保证报告与准入判定一致。本函数只读取、
    不写盘、不填真实值。

    参数：
    - ``raw_source_ref``：字典（或 ThresholdSourceRef）；缺失字段视为不通过。

    返回：``SourceVerificationReport``（passed=全部 C 通过；checks 含每项标签/结论/摘要）。
    """

    sr = raw_source_ref if isinstance(raw_source_ref, Mapping) else {}

    def _s(key: str) -> str:
        return str(sr.get(key) or "").strip()

    std = _s("standard")
    cla = _s("clause")
    ed = _s("edition")
    url = _s("url")
    h = _s("hash")

    c1_ok = bool(std) and std.lower() != _PENDING
    c2_ok = bool(cla) and cla.lower() != _PENDING
    c3_ok = bool(ed) and bool(_EDITION.fullmatch(ed))
    c4_ok = bool(url) and (url.startswith("http://") or url.startswith("https://"))
    c5_ok = bool(h) and bool(_HASH.fullmatch(h))

    checks = {
        "C1": {
            "label": "标准号完整(standard)",
            "ok": c1_ok,
            "detail": std,
        },
        "C2": {
            "label": "条款号完整(clause)",
            "ok": c2_ok,
            "detail": cla,
        },
        "C3": {
            "label": "版本合规(edition:4位年/显式版本)",
            "ok": c3_ok,
            "detail": ed,
        },
        "C4": {
            "label": "链接可达(http/https 可复核)",
            "ok": c4_ok,
            "detail": url,
        },
        "C5": {
            "label": "内容哈希(64位 sha256 摘要)",
            "ok": c5_ok,
            "detail": (h[:8] + "…") if h else "",
        },
        "C6": {
            "label": "引用完整性(C1 + C2 即 is_complete)",
            "ok": c1_ok and c2_ok,
            "detail": "",
        },
    }
    passed = all(c["ok"] for c in checks.values())
    return SourceVerificationReport(
        threshold_id=str(sr.get("threshold_id") or ""),
        source_ref=dict(sr),
        passed=passed,
        checks=checks,
        overall="通过" if passed else "未通过",
    )


def run_intake_drill(
    *,
    verified_path: "Path | str",
    review_log_path: "Path | str | None" = None,
    snapshot_dir: "Path | str | None" = None,
    request: IntakeRequest,
    verified_by: str,
    verified_at: str,
    expert_verified_by: str,
    expert_verified_at: str,
) -> IntakeDrillResult:
    """真实资料录入演练（任务1/2/3/4 编排）：人工提供资料，AI 仅格式校验。

    流程：授权边界 → source_ref 验证报告 → submit → 主理人审核 → 专家复核 →
    转正 → G1-G6 门禁检查。任一前置不满足即中止并返回对应结论。

    红线保证（3.2.4-G 任务书）：
    - 授权越界（D-TH / E-TH-04~06）→ 拒绝，不进入任何后续步骤；
    - source_ref 任一 C1-C6 不满足 → 拒绝，不入库；
    - SoD：专家复核人与主理人核准人同一身份 → 拒绝（专家复核步骤拦阻）；
    - 即便双签转正，``engineering_enabled`` 恒为 False、``verification_status`` 恒
      为 pending_verification（G1-G6 门禁默认拒绝，且不翻转开关）；
    - 本函数**绝不**生成/猜测/补充真实工程参数，亦**不**修改专家签署信息。

    返回：``IntakeDrillResult``（含 source 报告、步骤链、转正态、门禁结论）。
    """

    wf = ThresholdIntakeWorkflow(
        verified_path=verified_path,
        review_log_path=review_log_path,
        snapshot_dir=snapshot_dir,
    )
    tid = (request.threshold_id or "").strip()

    # 步骤 0：授权边界（红线）。
    if tid not in wf.allowed_ids:
        return IntakeDrillResult(
            threshold_id=tid,
            authorized=False,
            source_report=None,
            steps=[],
            verified=False,
            review_event_id=None,
            gate_allowed=False,
            gate_reasons=[REASON_UNAUTHORIZED],
            engineering_enabled=False,
            verification_status=DRILL_VERIFICATION_STATUS,
            message=REASON_UNAUTHORIZED,
        )

    # 步骤 0：source_ref 验证报告（任务3）。
    src_report = build_source_verification_report(request.source_ref)
    if not src_report.passed:
        return IntakeDrillResult(
            threshold_id=tid,
            authorized=True,
            source_report=src_report,
            steps=[],
            verified=False,
            review_event_id=None,
            gate_allowed=False,
            gate_reasons=[REASON_SOURCE_REF_INVALID],
            engineering_enabled=False,
            verification_status=DRILL_VERIFICATION_STATUS,
            message=REASON_SOURCE_REF_INVALID,
        )

    # 步骤 1-4：四步工作流（每步经 review_log 记录）。
    steps: list[str] = []
    r1 = wf.submit(request)
    if r1.outcome is not IntakeOutcome.ACCEPTED:
        return IntakeDrillResult(
            threshold_id=tid,
            authorized=True,
            source_report=src_report,
            steps=steps,
            verified=False,
            review_event_id=None,
            gate_allowed=False,
            gate_reasons=[r1.message],
            engineering_enabled=False,
            verification_status=DRILL_VERIFICATION_STATUS,
            message=r1.message,
        )
    steps.append("submit")

    r2 = wf.review(
        threshold_id=tid, verified_by=verified_by, verified_at=verified_at
    )
    if r2.outcome is not IntakeOutcome.ACCEPTED:
        return IntakeDrillResult(
            threshold_id=tid,
            authorized=True,
            source_report=src_report,
            steps=steps,
            verified=False,
            review_event_id=None,
            gate_allowed=False,
            gate_reasons=[r2.message],
            engineering_enabled=False,
            verification_status=DRILL_VERIFICATION_STATUS,
            message=r2.message,
        )
    steps.append("review_approve")

    r3 = wf.expert_recheck(
        threshold_id=tid,
        expert_verified_by=expert_verified_by,
        expert_verified_at=expert_verified_at,
    )
    if r3.outcome is not IntakeOutcome.ACCEPTED:
        return IntakeDrillResult(
            threshold_id=tid,
            authorized=True,
            source_report=src_report,
            steps=steps,
            verified=False,
            review_event_id=None,
            gate_allowed=False,
            gate_reasons=[r3.message],
            engineering_enabled=False,
            verification_status=DRILL_VERIFICATION_STATUS,
            message=r3.message,
        )
    steps.append("expert_recheck")

    r4 = wf.finalize_verified(tid)
    if r4.outcome is not IntakeOutcome.ACCEPTED:
        return IntakeDrillResult(
            threshold_id=tid,
            authorized=True,
            source_report=src_report,
            steps=steps,
            verified=False,
            review_event_id=None,
            gate_allowed=False,
            gate_reasons=[r4.message],
            engineering_enabled=False,
            verification_status=DRILL_VERIFICATION_STATUS,
            message=r4.message,
        )
    steps.append("threshold_verified")

    # 门禁检查（保持 engineering_enabled=false）。
    allowed, reasons = wf.evaluate_gates()
    return IntakeDrillResult(
        threshold_id=tid,
        authorized=True,
        source_report=src_report,
        steps=steps,
        verified=True,
        review_event_id=(r4.review_event or {}).get("event_id"),
        gate_allowed=allowed,
        gate_reasons=list(reasons),
        engineering_enabled=False,
        verification_status=DRILL_VERIFICATION_STATUS,
        message=r4.message,
    )


__all__ = [
    "DEFAULT_ALLOWED_IDS",
    "DEFAULT_VERSION",
    "DEFAULT_SCHEMA_VERSION",
    "IntakeOutcome",
    "REASON_UNAUTHORIZED",
    "REASON_SOURCE_REF_INVALID",
    "REASON_ALREADY_VERIFIED",
    "REASON_NOT_SUBMITTED",
    "REASON_SOD_CONFLICT",
    "REASON_NEED_PRINCIPAL_REVIEW",
    "REASON_MISSING_DUAL_SIGN",
    "IntakeRequest",
    "IntakeResult",
    "ThresholdIntakeWorkflow",
    "DRILL_VERIFICATION_STATUS",
    "SourceVerificationReport",
    "IntakeDrillResult",
    "build_source_verification_report",
    "run_intake_drill",
]
