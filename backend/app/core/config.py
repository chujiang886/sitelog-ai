"""Environment-based application configuration."""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 加载 BOIP 根目录 .env（含 LLM_A_* 真实 key 等），确保在任何 Agent 运行时读取
# os.environ 之前注入环境变量。本模块在 app 启动时即被导入，早于请求处理。
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")


#: 已知"测试用"密钥。生产环境若仍使用其中之一，视为配置违规，启动即拒绝。
KNOWN_TEST_SECRETS: frozenset[str] = frozenset(
    {
        "test-jwt-secret-not-for-production",
        "changeme",
        "change-me",
        "secret",
        "test",
        "password",
        "",
    }
)

#: 生产环境禁止启用的身份提供方（任何会自动降级/伪造身份的方案）。
PRODUCTION_FORBIDDEN_IDENTITY_PROVIDERS: frozenset[str] = frozenset(
    {
        "static-dev",
    }
)


class Settings(BaseSettings):
    """Validated BOIP backend settings loaded from environment variables."""

    app_env: str = Field(default="development", validation_alias="APP_ENV")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    database_url: str = Field(default="", validation_alias="DATABASE_URL")
    redis_url: str = Field(default="", validation_alias="REDIS_URL")
    qdrant_url: str = Field(default="", validation_alias="QDRANT_URL")
    minio_endpoint: str = Field(default="", validation_alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="", validation_alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="", validation_alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field(default="", validation_alias="MINIO_BUCKET")
    jwt_secret: str = Field(default="", validation_alias="JWT_SECRET")
    llm_api_key: str = Field(default="", validation_alias="LLM_API_KEY")

    # ---- Phase 3.8.29：生产安全与部署强化 ----
    # 身份提供方选择：jwt（默认，HS256）/ oidc / sso-gateway。
    # 未配置齐全时对应验证器**不注册**，整体 fail-closed，绝不降级。
    identity_provider: str = Field(default="jwt", validation_alias="IDENTITY_PROVIDER")
    # OIDC（RS256 + JWKS）：三点皆需显式配置，否则该方式不启用。
    oidc_issuer: str = Field(default="", validation_alias="OIDC_ISSUER")
    oidc_audience: str = Field(default="", validation_alias="OIDC_AUDIENCE")
    oidc_jwks_url: str = Field(default="", validation_alias="OIDC_JWKS_URL")
    # SSO 网关：必须显式声明"后端不可从网关外直达"才允许启用。
    sso_gateway_trusted: bool = Field(
        default=False, validation_alias="SSO_GATEWAY_TRUSTED"
    )
    # 开发态逃生舱：仅显式开启时允许 static-dev；生产强制 False。
    static_dev_identity_enabled: bool = Field(
        default=False, validation_alias="STATIC_DEV_IDENTITY_ENABLED"
    )

    # ---- Cookie 策略 ----
    auth_cookie_name: str = Field(
        default="boip_access_token", validation_alias="AUTH_COOKIE_NAME"
    )
    # 显式 false 时（含开发缺省）cookie 不带 Secure；生产由 is_production 强制开启。
    cookie_secure: bool = Field(default=False, validation_alias="COOKIE_SECURE")
    cookie_samesite: str = Field(default="lax", validation_alias="COOKIE_SAMESITE")
    cookie_domain: str = Field(default="", validation_alias="COOKIE_DOMAIN")

    # ---- CSRF（双提交令牌）----
    csrf_cookie_name: str = Field(
        default="boip_csrf_token", validation_alias="CSRF_COOKIE_NAME"
    )
    csrf_header_name: str = Field(
        default="X-CSRF-Token", validation_alias="CSRF_HEADER_NAME"
    )
    # 显式开启或生产环境默认开启；开发缺省关闭以兼容既有测试。
    csrf_protection_enabled: bool = Field(
        default=False, validation_alias="CSRF_PROTECTION_ENABLED"
    )

    # ---- Token 生命周期 ----
    token_ttl_minutes: int = Field(
        default=60, validation_alias="TOKEN_TTL_MINUTES"
    )
    refresh_grace_minutes: int = Field(
        default=15, validation_alias="REFRESH_GRACE_MINUTES"
    )

    # ---- CORS（生产必须显式声明，空值即不跨域）----
    cors_origins: str = Field(default="", validation_alias="CORS_ORIGINS")

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # 环境判定（T3：环境隔离）                                              #
    # ------------------------------------------------------------------ #

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_testing(self) -> bool:
        return self.app_env == "testing"

    @property
    def is_development(self) -> bool:
        return not self.is_production and not self.is_testing

    @property
    def effective_cookie_secure(self) -> bool:
        """生产环境强制 Secure；显式关闭只应在非生产生效。"""

        return bool(self.cookie_secure) or self.is_production

    @property
    def effective_csrf_enabled(self) -> bool:
        """生产环境默认开启 CSRF；显式关闭只应在非生产生效。"""

        return bool(self.csrf_protection_enabled) or self.is_production

    @property
    def cors_explicitly_disabled(self) -> bool:
        """运维显式声明"本部署同源、不需要跨域"。

        区分「没配」和「明确不需要」很重要：前者是**遗漏**，生产必须拦；
        后者是**决策**，同源部署（前后端同域名）本就不该开任何跨域来源。
        没有这个出口的话，同源部署会被迫填一个假的 Origin 才能启动，
        反而制造了本不存在的跨域授权。
        """

        return self.cors_origins.strip().lower() in ("none", "disabled")

    @property
    def parsed_cors_origins(self) -> tuple[str, ...]:
        if self.cors_explicitly_disabled:
            return ()
        return tuple(o.strip() for o in self.cors_origins.split(",") if o.strip())

    @property
    def cors_configured(self) -> bool:
        """是否已就跨域策略**表过态**（给了白名单，或明确声明不需要）。"""

        return self.cors_explicitly_disabled or bool(self.parsed_cors_origins)

    @property
    def uses_test_secret(self) -> bool:
        return self.jwt_secret in KNOWN_TEST_SECRETS

    def assert_production_safe(self) -> None:
        """生产启动时的配置红线校验；任何违规即拒绝启动（fail-closed）。

        调用方（main.py）仅在 ``is_production`` 时调用；开发/测试环境为 no-op。
        """

        if not self.is_production:
            return
        problems: list[str] = []
        if self.uses_test_secret:
            problems.append(
                "JWT_SECRET 为已知测试密钥，生产环境严禁使用。"
            )
        if self.identity_provider in PRODUCTION_FORBIDDEN_IDENTITY_PROVIDERS:
            problems.append(
                f"身份提供方 {self.identity_provider!r} 在生产环境被禁止"
                f"（仅 {sorted(PRODUCTION_FORBIDDEN_IDENTITY_PROVIDERS)} 一类逃生舱禁用）。"
            )
        if self.static_dev_identity_enabled:
            problems.append("STATIC_DEV_IDENTITY_ENABLED 在生产环境必须为 False。")
        if not self.effective_cookie_secure:
            problems.append("生产环境 Cookie 必须带 Secure 标记。")
        if not self.cors_configured:
            problems.append(
                "生产环境必须就 CORS_ORIGINS 显式表态："
                "给出来源白名单，或填 'none' 声明同源部署不需要跨域。"
            )
        if "*" in self.parsed_cors_origins:
            problems.append(
                "CORS_ORIGINS 含通配符 '*'：本服务对跨域请求放行凭据 Cookie，"
                "通配来源等于允许任意站点携带用户凭据发起请求，生产严禁。"
            )
        if not self.jwt_secret:
            problems.append("JWT_SECRET 缺失：身份基础设施不可用（fail-closed）。")
        if problems:
            raise RuntimeError(
                "生产配置安全检查未通过，拒绝启动：\n- "
                + "\n- ".join(problems)
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide immutable settings snapshot."""

    return Settings()
