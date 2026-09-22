from functools import lru_cache
from typing import Self

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ScoutApiV2"
    environment: str = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    redis_url: str | None = None
    redis_connect_timeout_seconds: float = 0.3
    redis_socket_timeout_seconds: float = 0.5
    # PostgreSQL / Supabase (SQLAlchemy + psycopg). Never use Supabase Data API.
    database_url: str | None = None
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout_seconds: int = 30
    database_pool_recycle_seconds: int = 1800
    database_connect_timeout_seconds: int = 10
    database_statement_timeout_ms: int = 30_000
    database_sslmode: str | None = None
    database_application_name: str = "scout-api-v2"
    # --- API security (Supabase Auth). Never expose service_role to clients. ---
    # AUTH_REQUIRED: whether protected routes demand a client Bearer.
    # Alias AUTH_ENABLED kept for backward compatibility (same polarity).
    auth_required: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "auth_required",
            "AUTH_REQUIRED",
            "auth_enabled",
            "AUTH_ENABLED",
        ),
    )
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    # HS256 legacy/test only. Prefer JWKS (ES256/RS256) via supabase_url.
    supabase_jwt_secret: str | None = None
    supabase_jwt_audience: str = "authenticated"
    auth_google_redirect_url: str | None = None
    auth_frontend_success_url: str | None = None
    auth_admin_user_ids: str = ""
    cors_allowed_origins: str = ""
    trusted_proxy_ips: str = ""
    rate_limit_enabled: bool = True
    rate_limit_default_per_minute: int = 120
    rate_limit_auth_per_minute: int = 20
    rate_limit_crawler_per_minute: int = 10
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
    scrape_distributed_lock_enabled: bool = True
    scrape_single_flight_lock_ttl_seconds: int = 180
    scrape_single_flight_wait_seconds: float = 120.0
    scrape_distributed_cooldown_enabled: bool = True
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
    # Keep Camoufox persistent context warm across fetches (ADR 0032).
    camoufox_warm_reuse: bool = True
    camoufox_warm_max_fetches: int = 40
    # Product Match: independent stores may overlap; Camoufox stays lock-serialized.
    match_store_concurrency: int = 3
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
    # --- Product images / Google Drive (ADR 0029). Backend-only secrets. ---
    google_drive_client_id: str | None = None
    google_drive_client_secret: str | None = None
    google_drive_refresh_token: str | None = None
    google_drive_root_folder_id: str | None = None
    image_max_bytes: int = 8_000_000
    image_max_dimension: int = 4096
    image_download_timeout_seconds: float = 30.0
    image_max_redirects: int = 5
    image_max_per_product: int = 20
    image_avif_quality: int = 60
    image_avif_max_concurrency: int = 2
    # Alias conceitual: IMAGE_OPTIMIZATION_CONCURRENCY → image_avif_max_concurrency
    image_optimization_concurrency: int | None = None
    image_media_cache_max_age_seconds: int = 86_400
    image_optimization_enabled: bool = True
    image_optimization_sweep_interval_seconds: int = 2
    image_optimization_batch_size: int = 4
    image_optimization_lease_seconds: int = 300
    # --- Persistent offer monitoring (ADR 0030). Clock lives in PostgreSQL. ---
    offer_refresh_interval_hours: int = 12
    offer_monitor_enabled: bool = True
    offer_monitor_sweep_interval_seconds: int = 30
    offer_monitor_batch_size: int = 10
    offer_monitor_lease_seconds: int = 300
    offer_monitor_retry_base_seconds: int = 300
    offer_monitor_retry_max_seconds: int = 3600
    offer_monitor_jitter_seconds: int = 600
    offer_promotion_grace_seconds: int = 60
    offer_monitor_stale_heartbeat_seconds: int = 300
    # --- Exchange-rate subsystem (ADR 0034). HTTP-only; no API keys. ---
    exchange_rate_enabled: bool = True
    exchange_rate_refresh_interval_seconds: int = 1800
    exchange_rate_sweep_interval_seconds: int = 60
    exchange_rate_http_timeout_seconds: float = 20.0
    exchange_rate_stale_after_seconds: int = 21600
    exchange_rate_outlier_max_change_pct: float = 15.0
    exchange_rate_tourism_max_premium_pct: float = 12.0
    exchange_rate_ptax_agreement_pct: float = 0.5
    # Emergency / test override — never use in production for live rates.
    exchange_rate_manual_usd_brl_tourism_sell: str | None = None

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

    @model_validator(mode="after")
    def reject_insecure_auth_in_production(self) -> Self:
        """Fail closed: never boot production with client auth optional."""
        if self.environment.lower() == "production" and not self.auth_required:
            raise ValueError(
                "AUTH_REQUIRED=false (ou AUTH_ENABLED=false) não é permitido "
                "quando ENVIRONMENT=production. "
                "Defina AUTH_REQUIRED=true ou use um ambiente não-produção."
            )
        if self.image_optimization_concurrency is not None:
            self.image_avif_max_concurrency = max(
                1, int(self.image_optimization_concurrency)
            )
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
