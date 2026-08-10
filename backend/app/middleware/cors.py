"""CORS 策略（Phase 3.8.29 T3 环境隔离）。

生产环境 CORS 来源**必须显式声明**（``CORS_ORIGINS``，逗号分隔）。空值意味着
"不信任任何跨域来源"——浏览器侧等同于完全禁止跨域，这是 fail-closed 的正确
默认值，而不是"为了方便先放行"。

开发环境沿用 localhost 常见端口，但仍是显式列表，不写 ``*``（``*`` 会与
``allow_credentials`` 冲突，且会暴露到任意站点）。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings

DEVELOPMENT_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8000",
)


def register_cors(app: FastAPI) -> None:
    """按环境注册 CORS。生产读 CORS_ORIGINS；空值即无跨域。"""

    settings = get_settings()
    if settings.is_production:
        # 生产：只接受显式声明的来源；空值 → 不跨域（fail-closed）。
        origins = list(settings.parsed_cors_origins)
    else:
        # 开发/测试：显式 localhost 列表（不写 *）。
        origins = list(DEVELOPMENT_ORIGINS)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
