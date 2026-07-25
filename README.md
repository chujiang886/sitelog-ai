# BOIP 建筑开口智能设计平台

BOIP（Building Opening Intelligence Platform）定位为面向建筑开口行业的 AI Native 智能设计基础设施。本仓库目前仅提供 Phase 0 工程骨架，不包含行业判断、真实模型调用或生产数据。

## 当前阶段

- **Phase 0 完成 / 进入 Phase 1**
- Phase 0 / T01：项目结构（已完成）
- Phase 0 / T02：前后端骨架（已完成）
- Phase 0 / T03：数据库 + Migration（已完成）
- Phase 0 / T04：Agent 框架（已完成）
- Phase 0 / T05：测试体系 + CI（已完成）
- Phase 0 整体验收：见 [`docs/PHASE0_DONE.md`](docs/PHASE0_DONE.md)
- 实施日志：见 [`docs/PHASE0_LOG.md`](docs/PHASE0_LOG.md)

## 环境要求

- Node.js：22.22.2
- Python：3.11
- Docker 与 Docker Compose

版本与端口属于工程环境配置；行业工程参数必须以 `pending_verification` 标识后方可进入实现。

## 启动方式

### Docker Compose

```bash
cp .env.example .env
# 填写本地开发所需变量后启动
docker-compose up --build
```

### 后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

健康检查：`GET http://localhost:8000/health`。

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端地址：`http://localhost:3000`；健康检查：`GET http://localhost:3000/api/health`。

## 测试与检查

```bash
bash scripts/ci/local_ci.sh
```

该命令执行后端健康检查测试、前端 Jest、业务数字杜撰扫描与硬编码扫描。

## 目录说明

- `frontend/`：Next.js 前端工程
- `backend/`：FastAPI 后端工程
- `agents/`：Agent 基础抽象、注册表与文档契约
- `deployment/`：容器、Nginx 与部署说明
- `docs/`：工程实施记录
- `tests/`：跨层端到端测试与 AI 评测集入口
- `scripts/`：本地 CI 与静态扫描脚本

## 文档索引

- [产品与架构设计文档](../BOIP_AI_Documents/)
- [工程实施文档](docs/)

## 团队角色

- 主理人：项目决策与总协调
- 许清楚：产品经理
- 高见远：系统架构师
- 寇豆码：软件工程师
- 严过关：质量负责人

## 安全声明

不得提交 `.env`、访问令牌、API 密钥、用户数据或企业敏感数据。`.env.example` 仅提供空值模板。
