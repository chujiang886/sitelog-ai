"""Phase 3.9.14 External Staging Runtime Deployment & End-to-End Qualification.

本包在 3.9.13 `staging_runtime` 运行环境层之上，新增「运行时部署 + E2E 资格」可执行能力：
- ``iac_executor``：工具链感知的 IaC 执行器（validate / plan-only，严禁 apply）。
- ``iac_readiness``：8 模块可执行矩阵（接入工具链真实校验）。
- ``runtime_manifest`` / ``deployment_adapter``：运行时部署产物 / 适配器（plan-only）。
- ``e2e_harness``：端到端资格harness（本地沙箱运行时，fail-closed）。
- ``isolation`` / ``failure_recovery`` / ``evidence`` / ``machine_package`` / ``validators`` / ``api_contract``。

最高红线（fail-closed，覆盖本阶段）：
① 全程 ``engineering_enabled=false``（仅主理人在人类终端显式置 true）。
② 禁 Production Deploy / Migration / Rollback / Secret / Permission / Data / GO。
③ 未隔离不得真实部署；未双钥匙（Human Authorization Key actor_kind=USER）不得 apply/deploy。
④ fake/synthetic 不得冒充 External；plan/validate 不得冒充 deployed。
⑤ Secret 不得入 Git/log/Audit/API/report；不得 skip/xfail/ignore/continue-on-error 掩盖失败。
"""
