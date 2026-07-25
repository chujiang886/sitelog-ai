# BOIP 部署骨架

Phase 0 / T01 提供 PostgreSQL、Redis、Qdrant、MinIO 和 Backend 五个服务的本地 Docker Compose 骨架。Nginx 和 Frontend Dockerfile 已准备，但未加入本阶段五服务编排，避免声明不存在的运行依赖。

## 准备环境

在项目根目录执行：

```bash
cp .env.example .env
```

填写本地开发需要的数据库、对象存储、认证和服务 URL。所有值必须由部署负责人确认；Phase 0 不使用真实生产密钥。

## 启动

从项目根目录：

```bash
docker-compose up --build
```

也可显式使用部署目录配置：

```bash
docker-compose --env-file .env -f deployment/docker-compose.yml up --build
```

## 停止

```bash
docker-compose down
```

如需删除本地容器数据卷，必须先确认数据不再需要，再执行：

```bash
docker-compose down --volumes
```

## 健康检查

```bash
curl --fail http://localhost:8000/health
```

基础设施连通性可用各服务官方客户端检查；本阶段不伪造应用级依赖就绪状态。

## 端口

- PostgreSQL：5432
- Redis：6379
- Qdrant：6333
- MinIO API：9000
- MinIO Console：9001
- Backend：8000

这些是本地基础设施端口，不是行业工程参数。
