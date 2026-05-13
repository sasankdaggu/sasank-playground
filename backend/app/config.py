from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://wand:wand@localhost:5433/wand_spike"
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 30  # 30 days

    # Google OAuth
    google_client_id: str = ""

    # Email OTP (Resend)
    resend_api_key: str = ""
    otp_from_email: str = "onboarding@resend.dev"

    # Background removal (Remove.bg)
    removebg_api_key: str = ""

    # Image storage (Cloudflare R2)
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "wand-images"
    r2_public_url: str = ""  # e.g. https://pub-xxxx.r2.dev

    cors_origins: list[str] = ["http://localhost:3000"]
    debug: bool = False

    # LLM (Anthropic — ingredient schema detection)
    anthropic_api_key: str = ""

    # Scraper — ScraperAPI (Shopify D2C bulk ingestion)
    scraperapi_key: str = ""

    # Scraper — Smartproxy residential (Indian marketplace scrapers)
    proxy_url: str = ""    # e.g. http://gate.smartproxy.com:10000
    proxy_user: str = ""   # e.g. user-YOURUSER-cc-in
    proxy_pass: str = ""

    scraper_headless: bool = True
    scraper_page_limit: int = 2000  # max products per retailer per run (use 0 for unlimited)


settings = Settings()
