"""Report 生成包（T11 / TASK-106）。

把 Vision / Environment / Design 三个 Agent 的结构化输出（AgentResult.data）
聚合成一份专业的中文本方案书 PDF。本包是**纯生成模块**，不调用 LLM、
不继承 BaseAgent。
"""

from .generator import generate_project_report

__all__ = ["generate_project_report"]
