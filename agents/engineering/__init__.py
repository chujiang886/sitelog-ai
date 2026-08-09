"""Engineering Agent 包（Phase 3.1 Sprint A 起承载可信审核基础设施）。

子模块：
- ``agent``：Engineering Agent 骨架（2.1.5），五个分析接口契约；
- ``validation``：审核链验证器（PendingEngineeringValidation 骨架 +
  ExpertBackedEngineeringValidation 双签审核链）；
- ``threshold_loader``：Engineering 阈值治理加载器（E-TH-01~06 + 复用 Design D-TH）；
- ``review_log``：append-only 审核日志（审核链溯源）。

红线（Sprint A）：engineering_enabled 保持 false；不填真实工程参数、
不设 verified=true、不编造规范条款、不输出 engineering_approved、不写死工程常数。
所有未知一律 pending_verification。
"""

from __future__ import annotations
