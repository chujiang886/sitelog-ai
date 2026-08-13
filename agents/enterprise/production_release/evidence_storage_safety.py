"""Phase 3.9.6 T13 证据存储安全（Evidence Storage Safety）。

红线⑦的运行时契约：激活证据**只存引用与哈希，永存原文**。本模块把这条约束
变成可复用、可测试的代码，防止任何路径把生产密钥 / 生产数据带进仓库或审计流。

职责
----
1. ``compute_evidence_sha256`` —— 流式读取本地证据引用求 SHA-256，读完即弃，
   不把证据正文驻留内存 / 落库。这是权威实现，``intake_service`` 也复用之；
2. ``EvidenceStorageReceipt`` —— 存储回执只含 ``content_reference`` +
   ``declared_sha256`` / ``computed_sha256``，**不含任何证据正文**；
3. ``EvidenceStoragePolicy`` —— fail-closed 守门：
   - ``ensure_no_inline_content``：拒绝接收任何 inline 证据正文（只收引用）；
   - ``ensure_reference_not_secret``：若引用字符串本身看起来像裸密钥 / 令牌
     （``sk-`` / ``BEGIN PRIVATE KEY`` / ``password=`` / ``token=`` 等），
     拒绝 —— 防止"把密钥当引用存进去"；
   - ``issue_receipt``：在通过上述检查后签发存储回执。

本模块不持有生产状态、不翻转 ``engineering_enabled``、不宣布 GO。
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


#: 计算哈希时的分块大小（流式读取，绝不整块驻留内存 / 绝不保存内容）。
_HASH_CHUNK_BYTES = 1024 * 1024

#: 命中即判定"引用字符串本身疑似裸密钥 / 令牌"的正则（fail-closed 拒绝）。
_SECRET_LIKE_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9]{8,}", re.IGNORECASE),     # OpenAI 类密钥
    re.compile(r"AKIA[0-9A-Z]{16}"),                       # AWS Access Key
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),             # GitHub Token
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),      # PEM 私钥
    re.compile(r"(?i)password\s*=\s*\S+"),                 # password=...
    re.compile(r"(?i)token\s*=\s*\S+"),                    # token=...
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*\S+"),           # api_key=...
    re.compile(r"(?i)secret\s*[:=]\s*\S+"),                # secret=...
)


class EvidenceStorageSafetyError(EnterpriseRedLineViolationError):
    """证据存储安全契约被违反（fail-closed，继承红线异常）。"""


def compute_evidence_sha256(
    content_reference: str, root_dir: str = "."
) -> Optional[str]:
    """对**本地可读**的证据引用流式计算 SHA-256；内容读完即弃（红线⑦）。

    ``content_reference`` 若不是本地存在的文件（如工单号 / 外部 URL / 线下件编号），
    返回 ``None`` —— 不为了"凑一个哈希"去抓取外部内容，更不伪造。

    返回后调用方**不得**持有文件内容；本函数不返回、不缓存任何正文。
    """

    ref = (content_reference or "").strip()
    if not ref:
        return None
    path = ref if os.path.isabs(ref) else os.path.join(root_dir, ref)
    if not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(_HASH_CHUNK_BYTES)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        return None
    # chunk 为局部变量，函数返回后即释放；不保存任何证据正文。
    return digest.hexdigest()


@dataclass(frozen=True)
class EvidenceStorageReceipt:
    """证据存储回执（只含引用与哈希，不含任何证据正文，红线⑦）。"""

    content_reference: str
    declared_sha256: Optional[str] = None
    computed_sha256: Optional[str] = None
    stored_at: str = ""

    @property
    def hash_match(self) -> Optional[bool]:
        if not self.declared_sha256 or not self.computed_sha256:
            return None
        return (self.declared_sha256 or "").strip().lower() == (
            self.computed_sha256 or ""
        ).strip().lower()

    def to_dict(self) -> dict:
        return {
            "content_reference": self.content_reference,
            "declared_sha256": self.declared_sha256,
            "computed_sha256": self.computed_sha256,
            "hash_match": self.hash_match,
            "held_content": False,  # 永不为 True：回执不持有任何原文
            "note": "EVIDENCE_STORAGE_RECEIPT: 仅含引用与哈希，未持有任何证据正文（红线⑦）",
        }


class EvidenceStoragePolicy:
    """证据存储安全守门（fail-closed，默认拒绝一切不安全存储）。"""

    def __init__(self, *, root_dir: str = ".") -> None:
        if not safety_invariants_ok():
            raise EvidenceStorageSafetyError(
                "safety_invariants_ok() 失败：禁止在启用态下存储激活证据（红线①）"
            )
        self._root_dir = root_dir

    # ------------------------------------------------------------------ #
    # 1) 拒绝 inline 证据正文（只收引用）
    # ------------------------------------------------------------------ #
    def ensure_no_inline_content(
        self, *, declared_content: Optional[str]
    ) -> None:
        """若调用方试图直接传入证据**正文**（而非引用），fail-closed 拒绝。

        证据正文永不在本系统内落库 / 驻留；我们只接受指向证据的
        ``content_reference``（本地路径 / 工单号 / 外部 URL / 线下件编号）。
        """

        if declared_content is not None and str(declared_content).strip() != "":
            raise EvidenceStorageSafetyError(
                "evidence MUST be stored by reference only; "
                "passing inline evidence content is forbidden (红线⑦)"
            )

    # ------------------------------------------------------------------ #
    # 2) 拒绝把裸密钥/令牌当成"引用"存进来
    # ------------------------------------------------------------------ #
    def ensure_reference_not_secret(self, content_reference: str) -> None:
        """若 ``content_reference`` 字符串本身疑似裸密钥 / 令牌，fail-closed 拒绝。

        这是防"把密钥直接写进引用字段"的最后一道机器护栏：引用应当是一个坐标
        （路径 / 工单号 / 存档 ID），而不是密钥本身。
        """

        ref = content_reference or ""
        for pat in _SECRET_LIKE_PATTERNS:
            m = pat.search(ref)
            if m:
                # 故意不在异常里回显命中的敏感片段，避免二次泄露。
                raise EvidenceStorageSafetyError(
                    "content_reference looks like an inline secret/token; "
                    "store by reference (path/ticket/archive id), not the secret itself "
                    "(红线⑦)"
                )

    # ------------------------------------------------------------------ #
    # 3) 签发存储回执（通过前两步检查后才允许）
    # ------------------------------------------------------------------ #
    def issue_receipt(
        self,
        *,
        content_reference: str,
        declared_sha256: Optional[str] = None,
        declared_content: Optional[str] = None,
        recompute_hash: bool = True,
    ) -> EvidenceStorageReceipt:
        """在双重安全校验通过后，签发一份"只含引用与哈希"的存储回执。

        流程：no-inline-content → reference-not-secret →（可选）流式重算哈希 →
        签发回执。回执**不**持有任何证据正文。
        """

        self.ensure_no_inline_content(declared_content=declared_content)
        self.ensure_reference_not_secret(content_reference)

        computed = (
            compute_evidence_sha256(content_reference, self._root_dir)
            if recompute_hash
            else None
        )
        from datetime import datetime, timezone

        return EvidenceStorageReceipt(
            content_reference=content_reference,
            declared_sha256=(declared_sha256 or None),
            computed_sha256=computed,
            stored_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    # ------------------------------------------------------------------ #
    # 诊断（fail-closed 语义自述，供测试 / SSOT 使用）
    # ------------------------------------------------------------------ #
    def scan_secret_likeness(self, text: str) -> List[str]:
        """返回 ``text`` 中命中的疑似密钥模式名（仅用于测试与诊断，不泄露片段）。"""

        hits: List[str] = []
        for i, pat in enumerate(_SECRET_LIKE_PATTERNS):
            if pat.search(text or ""):
                hits.append(f"pattern#{i}")
        return hits


__all__ = [
    "EvidenceStorageSafetyError",
    "compute_evidence_sha256",
    "EvidenceStorageReceipt",
    "EvidenceStoragePolicy",
]
