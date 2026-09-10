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
    mitmproxy_enabled: bool = False
    mitmproxy_url: str | None = None
    rotating_proxies_enabled: bool = False
    rotating_proxy_list_path: str | None = None

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug(cls, value: object) -> object:
        """Accept the legacy ``DEBUG=release`` value as production mode."""
        if isinstance(value, str) and value.strip().lower() == "release":
            return False
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
