"""Phase 3.9.10 —— Credential Reference Safety Scanner（Task 5）。

扫描文本/字典/对象，识别是否意外落入：

- 明文 Secret / Password / Token / Private key / 含密码的 DSN；
- 不应进入 Git / Audit / API / Dashboard / Evidence / Report 的敏感材料。

fail-closed：一旦发现即报 ``CredentialLeakError``，阻断落盘/返回。
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from agents.external_staging_qualification.models import _looks_like_raw_secret

# 明文凭据模式（大小写不敏感）。
_RAW_SECRET_PATTERNS = (
    re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(secret|token|api[_-]?key|access[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"(?i)-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-\._~\+/]+=*"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{16,}"),
    re.compile(r"(?i)AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"(?i)postgres(ql)?://[^:]+:[^@]+@"),  # DSN with embedded password
    re.compile(r"(?i)mysql://[^:]+:[^@]+@"),
    re.compile(r"(?i)mongodb(\+srv)?://[^:]+:[^@]+@"),
)

# 应被扫描的键名（其对应值视为敏感，需确认仅存引用）。
_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "access_key",
        "private_key",
        "dsn",
        "connection_string",
        "credential",
        "credentials",
    }
)


class CredentialLeakError(ValueError):
    """检测到意外明文凭据/敏感材料。"""


def scan_text(text: str) -> list[str]:
    """扫描文本，返回命中的敏感片段摘要（不含明文值本身）。"""

    hits: list[str] = []
    for pat in _RAW_SECRET_PATTERNS:
        for m in pat.finditer(text):
            snippet = m.group(0)
            # 仅记录模式类型，不回显值
            hits.append(f"<redacted:{_pattern_label(pat)}>")
    return hits


def scan_mapping(mapping: Mapping[str, Any]) -> list[str]:
    """扫描字典：检查敏感键对应值是否仅为引用（非明文）。"""

    hits: list[str] = []
    for key, value in mapping.items():
        if str(key).lower() in _SENSITIVE_KEYS:
            sval = str(value)
            if _looks_like_raw_secret(sval):
                hits.append(f"<redacted:key={key}>")
    return hits


def assert_no_credential_leak(
    *, text: str | None = None, mapping: Mapping[str, Any] | None = None
) -> None:
    """fail-closed：若发现明文凭据泄漏即抛 ``CredentialLeakError``。"""

    hits: list[str] = []
    if text is not None:
        hits.extend(scan_text(text))
    if mapping is not None:
        hits.extend(scan_mapping(mapping))
    if hits:
        raise CredentialLeakError(
            "检测到意外凭据材料进入扫描目标：" + "; ".join(sorted(set(hits)))
        )


def _pattern_label(pat: re.Pattern[str]) -> str:
    src = pat.pattern
    if "password" in src.lower() or "passwd" in src.lower() or "pwd" in src.lower():
        return "password"
    if "secret" in src.lower() or "token" in src.lower() or "api" in src.lower():
        return "secret-or-token"
    if "private key" in src.lower():
        return "private-key"
    if "bearer" in src.lower():
        return "bearer"
    if "sk-" in src.lower():
        return "openai-style-key"
    if "AKIA" in src:
        return "aws-access-key"
    if "://" in src and "@" in src:
        return "dsn-with-password"
    return "sensitive"


__all__ = [
    "CredentialLeakError",
    "scan_text",
    "scan_mapping",
    "assert_no_credential_leak",
]
