"""JSON 鲁棒提取工具（Phase 2 / T15）。

处理真实 LLM 常见的 JSON 输出变体：
- markdown 代码块包裹（```json ... ```）
- 前后多余文本 / 解释性文字
- 直接合法 JSON

统一返回 dict；无法提取时抛 ``ValueError``，由调用方决定降级策略。
"""

from __future__ import annotations

import json
from typing import Any


def extract_json(text: str) -> dict[str, Any]:
    """从 LLM 文本响应中提取第一个合法 JSON 对象。

    处理顺序：
    1. 直接 ``json.loads`` 整段（最常见于严格 JSON 模式）；
    2. 剥离 ```json / ``` 代码块后解析；
    3. 截取首个 ``{`` 到末个 ``}`` 之间的子串解析。

    任何一步成功且结果为 dict 即返回；全部失败抛 ``ValueError``。
    """

    if not isinstance(text, str):
        raise ValueError(f"extract_json 期望 str，收到 {type(text).__name__}")
    stripped = text.strip()
    if not stripped:
        raise ValueError("响应内容为空，无法提取 JSON")

    # 1) 直接解析
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    # 2) 剥离 ```json / ``` 代码块
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        block = "\n".join(lines).strip()
        try:
            parsed = json.loads(block)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    # 3) 截取首个 { 到末个 }
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = stripped[start : end + 1]
        try:
            parsed = json.loads(snippet)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    raise ValueError(f"无法从响应中提取 JSON 对象: {stripped[:200]}")


__all__ = ["extract_json"]
