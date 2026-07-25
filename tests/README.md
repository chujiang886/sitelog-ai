# 跨层测试

本目录保存不属于单一前端或后端模块的测试资产：

- `e2e/`：端到端用户流程测试入口
- `evals/`：Agent 与系统级 AI 评测入口

Phase 0 / T01 只建立目录和评测规范占位，不创建虚构业务样例。后端健康接口测试位于 `backend/tests/test_health.py`；前端单元测试由 `frontend/jest.config.js` 管理。

本地统一验证：

```bash
bash scripts/ci/local_ci.sh
```
