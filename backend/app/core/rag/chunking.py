"""文档分块策略（Phase 2.2 / 2.2.5）。

``chunk_text``：按段落（``\\n``）切分后贪心累积，单段超长时按字符窗口硬切并带
``overlap`` 重叠，保留语义边界。空文本返回 ``[]``（不入库空 chunk）。
"""

from __future__ import annotations


class ChunkConfigError(ValueError):
    """分块参数错误（overlap >= chunk_size 等）。"""


def chunk_text(text: str, *, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """把文本切成重叠窗口的 chunk 列表。

    - ``chunk_size``：单 chunk 目标字符数（>0）；
    - ``overlap``：相邻 chunk 重叠字符数，必须满足 ``0 <= overlap < chunk_size``。
    """

    if chunk_size <= 0:
        raise ChunkConfigError("chunk_size 必须 > 0")
    if overlap < 0 or overlap >= chunk_size:
        raise ChunkConfigError("overlap 必须满足 0 <= overlap < chunk_size")

    if not text or not text.strip():
        return []

    paragraphs = [p for p in text.split("\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 1 <= chunk_size:
            current = (current + "\n" + para).strip() if current else para
            continue
        # 当前累积已满，先落盘。
        if current:
            chunks.append(current)
            current = ""
        # 单段落超长 → 字符窗口硬切带重叠。
        if len(para) > chunk_size:
            chunks.extend(_hard_split(para, chunk_size, overlap))
        else:
            current = para

    if current:
        chunks.append(current)

    # 对落盘的 chunk 也做重叠补充（仅在多 chunk 时），保证相邻语义连续。
    if overlap > 0 and len(chunks) > 1:
        enriched: list[str] = []
        for idx, c in enumerate(chunks):
            if idx == 0:
                enriched.append(c)
            else:
                prev = chunks[idx - 1]
                tail = prev[-overlap:] if len(prev) >= overlap else prev
                enriched.append((tail + "\n" + c).strip() if tail else c)
        chunks = enriched

    return chunks


def _hard_split(long_text: str, chunk_size: int, overlap: int) -> list[str]:
    """对超长单段按字符窗口硬切（带 overlap）。"""

    out: list[str] = []
    step = max(1, chunk_size - overlap)
    start = 0
    while start < len(long_text):
        out.append(long_text[start : start + chunk_size])
        start += step
    return out


__all__ = ["chunk_text", "ChunkConfigError"]
