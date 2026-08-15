"""Phase 3.9.13 —— Credential Deep Scanner（§七 技术债修复：递归升级）。

3.9.11 的 ``credential_scanner`` 仅做 top-level 字典扫描。本模块升级为**递归**扫描，覆盖：
- 任意嵌套 dict / list / tuple / Mapping；
- JSON 字符串（解析后递归）；
- env maps（``KEY=VALUE`` 行）；
- DSN / URL userinfo（``scheme://user:pass@host``）；
- bearer token / API key / private key marker / access-secret key pair / cloud provider names。

fail-closed：一旦发现明文凭据即抛 ``CredentialDeepLeakError``，阻断落盘/返回。

本模块**自包含**：不依赖 qualification.credential_scanner（避免沙箱未跟踪文件断裂）。
内置 ``_looks_like_raw_secret`` 启发式。
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

# 明文凭据模式（大小写不敏感）。
_RAW_SECRET_PATTERNS = (
    re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(secret|token|api[_-]?key|access[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"(?i)-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-\._~\+/]+=*"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{16,}"),
    re.compile(r"(?i)AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)postgres(ql)?://[^:]+:[^@]+@"),
    re.compile(r"(?i)mysql://[^:]+:[^@]+@"),
    re.compile(r"(?i)mongodb(\+srv)?://[^:]+:[^@]+@"),
)
_SENSITIVE_KEYS = frozenset({
    "password", "passwd", "pwd", "secret", "token", "api_key", "apikey",
    "access_key", "private_key", "dsn", "connection_string", "credential",
    "credentials",
})
_URL_USERINFO = re.compile(r"[a-zA-Z][a-zA-Z0-9+.\-]*://([^/\s:@]+):([^/\s:@]+)@")
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
_ACCESS_SECRET_PAIR = re.compile(
    r"(?i)(access[_-]?key[_-]?id|access[_-]?key)\s*[:=]\s*\S+\s*[,;]\s*"
    r"(secret[_-]?access[_-]?key|secret)\s*[:=]\s*\S+"
)


class CredentialDeepLeakError(ValueError):
    """递归扫描发现意外明文凭据/敏感材料。"""


def _looks_like_raw_secret(value: str) -> bool:
    """启发式：值是否疑似明文密钥/秘密。"""

    v = value.strip()
    if not v:
        return False
    if len(v) >= 16 and re.fullmatch(r"[A-Za-z0-9_\-\.=+/]+", v):
        return True
    if re.search(r"(?i)(password|secret|token|key|pwd)", v) and len(v) >= 8:
        return True
    if v.startswith("sk-") and len(v) >= 16:
        return True
    if v.startswith("AKIA") and len(v) >= 16:
        return True
    return False


def _redact(label: str) -> str:
    return f"<redacted:{label}>"


def scan_text_deep(text: str) -> list[str]:
    """递归扫描文本：组合所有模式，返回命中摘要（不含明文值）。"""

    hits: list[str] = []
    for pat in _RAW_SECRET_PATTERNS:
        for _ in pat.finditer(text):
            hits.append(_redact("raw-secret-pattern"))
    if _URL_USERINFO.search(text):
        hits.append(_redact("url-userinfo"))
    if _PRIVATE_KEY.search(text):
        hits.append(_redact("private-key"))
    if _ACCESS_SECRET_PAIR.search(text):
        hits.append(_redact("access-secret-pair"))
    return hits


def scan_json_string(text: str) -> list[str]:
    """尝试解析 JSON 并递归扫描其值。非 JSON 文本回退到文本扫描。"""

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return scan_text_deep(text)
    return scan_value_deep(data)


def scan_env_text(text: str) -> list[str]:
    """扫描 env map 文本（KEY=VALUE 行）。"""

    hits: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip().lower() in _SENSITIVE_KEYS and _looks_like_raw_secret(value.strip()):
            hits.append(_redact(f"env-key={key.strip()}"))
    return hits


def scan_value_deep(value: Any, path: tuple[str, ...] = ()) -> list[str]:
    """递归扫描任意嵌套结构（dict / list / tuple / str）。"""

    hits: list[str] = []
    if isinstance(value, dict) or isinstance(value, Mapping):
        for k, v in value.items():
            if str(k).lower() in _SENSITIVE_KEYS and _looks_like_raw_secret(str(v)):
                hits.append(_redact(f"key={k}"))
            hits.extend(scan_value_deep(v, path + (str(k),)))
    elif isinstance(value, (list, tuple, set)):
        for idx, v in enumerate(value):
            hits.extend(scan_value_deep(v, path + (f"[{idx}]",)))
    elif isinstance(value, str):
        hits.extend(scan_text_deep(value))
        if value.strip().startswith(("{", "[")):
            hits.extend(scan_json_string(value))
    return hits


def assert_no_deep_credential_leak(
    *,
    text: str | None = None,
    value: Any = None,
    mapping: Mapping[str, Any] | None = None,
    json_str: str | None = None,
    env_text: str | None = None,
) -> None:
    """fail-closed：递归扫描所有给定目标，发现明文凭据即抛 ``CredentialDeepLeakError``。"""

    hits: list[str] = []
    if text is not None:
        hits.extend(scan_text_deep(text))
    if value is not None:
        hits.extend(scan_value_deep(value))
    if mapping is not None:
        hits.extend(scan_value_deep(dict(mapping)))
    if json_str is not None:
        hits.extend(scan_json_string(json_str))
    if env_text is not None:
        hits.extend(scan_env_text(env_text))
    if hits:
        raise CredentialDeepLeakError(
            "递归凭据深扫发现意外材料：" + "; ".join(sorted(set(hits)))
        )


__all__ = [
    "CredentialDeepLeakError",
    "scan_text_deep",
    "scan_value_deep",
    "scan_json_string",
    "scan_env_text",
    "assert_no_deep_credential_leak",
]
