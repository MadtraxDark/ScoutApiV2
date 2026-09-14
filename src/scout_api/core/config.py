from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ScoutApiV2"
    environment: str = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    redis_url: str | None = None
    scraper_user_agent: str = "ScoutApiV2/0.1 (+price-monitoring)"
    scraper_log_level: str = "INFO"
    scraper_default_concurrency: int = 2
    scraper_default_delay: float = 2.0
    autothrottle_enabled: bool = True
    autothrottle_start_delay: float = 2.0
    autothrottle_max_delay: float = 60.0
    autothrottle_target_concurrency: float = 0.5
    scraper_default_ttl: int = 3600
    scraper_retry_times: int = 3
    retry_backoff_base: float = 1.0
    retry_backoff_cap: float = 60.0
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_cooldown: int = 300
    scrape_url_cooldown_seconds: int = 300
    scrape_domain_min_interval_seconds: float = 15.0
    scrape_result_cache_ttl_seconds: int = 300
    mitmproxy_enabled: bool = False
    mitmproxy_url: str | None = None
    rotating_proxies_enabled: bool = False
    rotating_proxy_list_path: str | None = None
    scraper_http_timeout: int = 30
    camoufox_enabled: bool = True
    camoufox_headless: bool = True
    camoufox_humanize: bool = True
    camoufox_timeout_ms: int = 90_000
    camoufox_settle_ms: int = 5_000
    camoufox_max_settle_attempts: int = 12
    camoufox_proxy_url: str | None = None
    camoufox_user_data_dir: str | None = None
    camoufox_disable_coop: bool = True
    camoufox_warmup_origin: bool = True
    # Cost-aware Shopee controls (DataImpulse is billed primarily by GB).
    shopee_warmup_policy: str = "once_per_session"
    shopee_resource_blocking_enabled: bool = True
    # Challenge / CAPTCHA resolution (ADR 0017). Default: offline amazoncaptcha.
    captcha_solver_enabled: bool = True
    captcha_solver_provider: str = "amazoncaptcha"
    captcha_solver_max_attempts: int = 2
    # Auth wall bypass (ADR 0018). Credentials are operator-local — never commit.
    auth_bypass_enabled: bool = True
    auth_bypass_max_attempts: int = 2
    amazon_auth_email: str | None = None
    amazon_auth_password: str | None = None
    shopee_auth_email: str | None = None
    shopee_auth_password: str | None = None

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug(cls, value: object) -> object:
        """Accept the legacy ``DEBUG=release`` value as production mode."""
        if isinstance(value, str) and value.strip().lower() == "release":
            return False
        return value

    @field_validator("shopee_warmup_policy", mode="before")
    @classmethod
    def normalize_shopee_warmup_policy(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"always", "once_per_session", "never"}:
                return normalized
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
