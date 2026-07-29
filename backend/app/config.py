from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    database_url_direct: str

    cors_origins: str = "http://localhost:5173"

    scan_interval_minutes: int = 15
    scan_retention_days: int = 14

    # Consensus scoring — see app/core/consensus_engine.py for the formula.
    value_normalizer: float = 6.0
    max_value_boost: float = 1.0

    log_level: str = "INFO"

    polymarket_data_api_base: str = "https://data-api.polymarket.com"
    polymarket_gamma_api_base: str = "https://gamma-api.polymarket.com"
    # Widest top-N filter the UI offers (see consensus_engine.TOP_N_OPTIONS) —
    # fetch that deep per leaderboard so every filter cut is served from cache.
    leaderboard_size: int = 100
    # Lower than you'd expect: fetching top-100 leaderboards pulls in ~300+
    # unique traders, and Polymarket's /positions rate limit bites well before
    # 10 concurrent requests once the trader pool is this wide.
    position_fetch_concurrency: int = 5
    market_metadata_ttl_hours: int = 24
    # A trader's resolved-position history changes slowly — only worth
    # refetching /closed-positions this often, not every 15-min scan.
    track_record_ttl_hours: int = 24
    # Positions below this dollar value are dust, not conviction — excluding them
    # keeps the consensus signal meaningful and keeps scan volume manageable.
    min_position_value: float = 100.0
    gamma_batch_size: int = 50

    # Signs the visitor/admin session tokens — set a real random value in .env.
    secret_key: str = "dev-secret-change-me"
    visitor_session_days: int = 30
    admin_session_hours: int = 12
    # Dev default (Lax, insecure) works because the Vite proxy makes frontend
    # and backend look same-origin to the browser. Once they're on different
    # domains (production), cross-origin fetch only carries the auth cookie
    # if it's SameSite=None — which browsers only honor when Secure is also
    # set. Set COOKIE_SAMESITE=none and COOKIE_SECURE=true in production.
    cookie_samesite: str = "lax"
    cookie_secure: bool = False

    # Optional — the chatbot endpoint returns a "not configured" message until this is set.
    anthropic_api_key: str | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
