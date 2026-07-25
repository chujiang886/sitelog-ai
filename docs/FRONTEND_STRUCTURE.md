# 前端结构（Phase 0 / T02）

前端采用 Next.js App Router、TypeScript、Tailwind CSS 与 Zustand。页面保持最小占位实现，不包含业务状态或真实认证。

## 目录树

```text
frontend/
├── src/
│   ├── app/
│   │   ├── api/health/route.ts   # 前端健康检查
│   │   ├── agents/page.tsx       # Agent 注册表占位
│   │   ├── knowledge/page.tsx    # 知识库占位
│   │   ├── login/page.tsx        # 登录占位
│   │   ├── projects/page.tsx     # 项目列表占位
│   │   ├── globals.css
│   │   ├── layout.tsx            # 全局导航与侧边栏
│   │   └── page.tsx              # 项目状态看板占位
│   ├── lib/
│   │   ├── api.ts                # API fetch 封装
│   │   └── store.ts              # UI 占位 store
│   ├── types/contracts.ts        # 跨层 API 信封类型
│   └── __tests__/health.test.tsx
├── .env.local                    # NEXT_PUBLIC_API_BASE_URL
└── tailwind.config.ts            # BOIP 占位主题色
```

## 路由约定

- `/`：项目状态看板。
- `/projects`：项目列表。
- `/knowledge`：知识库规则。
- `/agents`：读取 `/api/agents` 注册表。
- `/login`：登录流程占位。
- `/api/health`：前端自身健康检查。

## API 约定

`src/lib/api.ts` 为所有浏览器请求提供统一 `success/data` 与 `success/error` 信封解析。`401` 只执行 `/login` 占位重定向，认证流程留待后续阶段。

## 主题约定

Tailwind `boip.primary.main/light/dark` 与 `boip.accent` 当前为开发占位色，不代表最终品牌色。最终品牌规范确认后统一替换配置，不在页面中硬编码颜色。
