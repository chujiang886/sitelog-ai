"""Knowledge Intelligence Layer（Phase 3.3 Sprint 3.3.9, Phase 2 实现）。

智能层仅做**只读评估 / 发现 / 检测**，绝不：
- 写盘 verified.json / 自身 store 之外的任何文件；
- 翻 engineering_enabled；
- 自动 approve / merge / delete 任何 KnowledgeItem（冲突恒定 review_required）。

导入约束：本包仅依赖 connector.KnowledgeItem 与 source_ref_validator；
**不** import repository（避免循环依赖）。repository 单向 import 本包。
"""
