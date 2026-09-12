from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def sqlite_file_from_url(url: str) -> Path | None:
    if not url.startswith("sqlite"):
        return None
    if url.startswith("sqlite:////"):
        return Path("/" + url[len("sqlite:////") :])
    if url.startswith("sqlite:///"):
        return PROJECT_ROOT / url[len("sqlite:///") :]
    return None


def ensure_sqlite_dir(url: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db_path = sqlite_file_from_url(url)
    if db_path is not None:
        db_path.parent.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "China Dress Trend Radar"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    mock_mode: bool = True

    tikhub_api_key: str = ""
    tikhub_base_url: str = "https://api.tikhub.io"
    tikhub_search_endpoint: str = "/api/v1/douyin/search/fetch_video_search_v2"
    tikhub_search_fallback_endpoint: str = "/api/v1/douyin/search/fetch_general_search_v2"
    tikhub_stats_endpoint: str = "/api/v1/douyin/app/v3/fetch_multi_video_statistics"
    tikhub_use_fallback_search: bool = False

    database_url: str = "sqlite:///./data/radar.db"

    usd_vnd_rate: float = 26000
    cost_per_search_usd: float = 0.01
    cost_per_stats_usd: float = 0.025
    max_requests_per_run: int = 35
    max_requests_per_month: int = 400
    pages_per_keyword: int = 3
    max_detail_videos_per_run: int = 50
    internal_rate_limit_rps: float = 2.0

    search_sort_type: str = "0"
    search_publish_time: str = "7"
    search_content_type: str = "1"

    scheduler_enabled: bool = False
    scheduler_timezone: str = "Asia/Bangkok"
    scheduler_hour: int = 9
    scheduler_minute: int = 0

    log_level: str = "INFO"

    http_timeout_seconds: float = 30.0
    retry_max_attempts: int = 3
    retry_base_delay_seconds: float = 0.5

    apify_token: str = ""
    apify_base_url: str = "https://api.apify.com"
    apify_actor_id: str = "zen-studio/douyin-product-search-scraper"
    apify_monthly_budget_usd: float = 4.50
    apify_estimated_price_per_1000_products: float = 7.99
    apify_run_timeout_seconds: float = 300.0
    apify_poll_interval_seconds: float = 5.0

    product_results_per_keyword: int = 20
    product_max_keywords_per_run: int = 1
    product_crawl_enabled: bool = False
    product_free_preview_mode: bool = True
    product_free_preview_run_limit: int = 10
    product_auto_schedule_enabled: bool = False
    product_mock_mode: bool = True


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    ensure_sqlite_dir(settings.database_url)
    return settings
