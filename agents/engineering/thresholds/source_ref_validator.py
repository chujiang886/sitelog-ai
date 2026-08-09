"""source_ref validator（Phase 3.2 Sprint 3.2.4-E）。

实现 ``validate_source_ref``：对 v2 结构化引用做 C1-C6 校验，缺失即返回明确 reason。
落地 3.2.4-D 迁移方案 §4 的 validator 设计：

- C1 标准号完整：``standard`` 非空且非 ``pending_verification`` 占位；
- C2 条款号完整：``clause`` 非空且非占位；
- C3 版本合规：``edition`` 为 4 位年份或显式版本标识（vX.Y / X.Y）；
- C4 链接可达：``url`` 非 http(s) 可公开复核链接；
- C5 内容哈希：``hash`` 为 64 位十六进制 sha256 摘要；若提供 ``content``，
  则比对内容摘要一致性（实施时由脚本计算并比对，禁止手写）；
- C6 引用完整性：C1 + C2 即 ``ThresholdSourceRef.is_complete()`` 语义。

设计衔接：C1+C2 即 3.2.4-A ``ThresholdSourceRef.is_complete()`` 语义；C3-C5 为
v2 新增增强层，由迁移步骤 M5 在真实化时填充，本阶段不填真实值。

红线（3.2.4-E）：本模块只校验结构/格式与可选的内容一致性，不填写任何真实
规范值、不输出任何 approved、不修改磁盘 verified.json、不开启 engineering_enabled。
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from agents.engineering.thresholds.schema import ThresholdSourceRef


# 校验失败原因（供测试与日志可追溯，与 3.2.4-D §4.2 一一对应）。
SOURCE_REF_STANDARD_MISSING = "source_ref.standard 缺失或仍为占位 pending_verification"
SOURCE_REF_CLAUSE_MISSING = "source_ref.clause 缺失或仍为占位 pending_verification"
SOURCE_REF_EDITION_INVALID = "source_ref.edition 非 4 位年份或显式版本标识"
SOURCE_REF_URL_INVALID = "source_ref.url 非 http(s) 可复核链接"
SOURCE_REF_HASH_MISSING = "source_ref.hash 缺失"
SOURCE_REF_HASH_FORMAT_INVALID = "source_ref.hash 非 64 位十六进制 sha256 摘要"
SOURCE_REF_HASH_MISMATCH = "source_ref.hash 与引用内容摘要不一致"

PENDING_PLACEHOLDER: str = "pending_verification"

# edition 合规：4 位年份（2012）或显式版本（v1.0 / 1.0.0 / 2.3）。
_EDITION_PATTERN: re.Pattern[str] = re.compile(r"^(?:\d{4}|v?\d+\.\d+(?:\.\d+)?)$")
# hash 合规：64 位十六进制 sha256。
_HASH_PATTERN: re.Pattern[str] = re.compile(r"^[0-9a-f]{64}$")


def compute_content_hash(content: str) -> str:
    """计算引用源内容的 sha256 摘要（v2 hash 字段的唯一合法来源）。"""

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def validate_source_ref(
    ref: Any,
    *,
    content: str | None = None,
) -> tuple[bool, str]:
    """校验单条结构化 source_ref 是否满足 v2 增强要求。

    参数：
    - ``ref``：``ThresholdSourceRef`` 实例、字典或自由文本（自动按 v2 解析）；
    - ``content``：可选，引用源文档内容字符串；提供时比对 ``hash`` 一致性。

    返回：``(ok, reason)``
    - ``ok=True``：C1-C6 全部通过；
    - ``ok=False``：首个不满足项的显式 reason（供测试/日志追溯）。

    红线：仅校验，不写盘、不填真实值、不输出 approved。
    """

    sr: ThresholdSourceRef = (
        ref if isinstance(ref, ThresholdSourceRef) else ThresholdSourceRef.from_raw(ref)
    )

    # C1 标准号完整。
    std = sr.standard.strip()
    if not std or std.lower() == PENDING_PLACEHOLDER:
        return False, SOURCE_REF_STANDARD_MISSING

    # C2 条款号完整。
    cla = sr.clause.strip()
    if not cla or cla.lower() == PENDING_PLACEHOLDER:
        return False, SOURCE_REF_CLAUSE_MISSING

    # C3 版本合规。
    ed = sr.edition.strip()
    if not ed or not _EDITION_PATTERN.fullmatch(ed):
        return False, SOURCE_REF_EDITION_INVALID

    # C4 链接可达（http / https 可复核）。
    url = sr.url.strip()
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return False, SOURCE_REF_URL_INVALID

    # C5 内容哈希。
    h = sr.hash.strip()
    if not h:
        return False, SOURCE_REF_HASH_MISSING
    if not _HASH_PATTERN.fullmatch(h):
        return False, SOURCE_REF_HASH_FORMAT_INVALID
    if content is not None and compute_content_hash(content) != h:
        return False, SOURCE_REF_HASH_MISMATCH

    return True, "source_ref_ok"


__all__ = [
    "SOURCE_REF_STANDARD_MISSING",
    "SOURCE_REF_CLAUSE_MISSING",
    "SOURCE_REF_EDITION_INVALID",
    "SOURCE_REF_URL_INVALID",
    "SOURCE_REF_HASH_MISSING",
    "SOURCE_REF_HASH_FORMAT_INVALID",
    "SOURCE_REF_HASH_MISMATCH",
    "PENDING_PLACEHOLDER",
    "compute_content_hash",
    "validate_source_ref",
]
