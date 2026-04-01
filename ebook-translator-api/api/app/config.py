from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    app_name: str = "ebook-translator-api"
    environment: str = "dev"

    database_url: str = Field(default="postgresql://postgres:postgres@postgres:5432/ebook")
    redis_url: str = Field(default="redis://redis:6379/0")
    celery_queue_name: str = Field(default="ebook.jobs.default")

    supabase_url: str = Field(default="https://example.supabase.co")
    supabase_jwks_url: str | None = None
    supabase_jwt_issuer: str | None = None
    supabase_jwt_audience: str = "authenticated"
    supabase_admin_role: str = "admin"
    supabase_publishable_key: str | None = None
    next_public_supabase_anon_key: str | None = None

    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_region: str = "auto"
    r2_raw_bucket: str = "ebook-raw"
    r2_result_bucket: str = "ebook-result"

    max_upload_bytes: int = 100 * 1024 * 1024
    daily_jobs_limit_per_user: int = 20
    presigned_put_expires_seconds: int = 900
    presigned_get_expires_seconds: int = 600
    object_ttl_hours: int = 24

    allowed_input_formats_csv: str = "epub,srt,pgn"
    allowed_output_formats_csv: str = "epub,srt,pgn"
    allowed_engines_csv: str = "openai,deepl,google,deepinfra"
    cors_allow_origins_csv: str = "http://localhost:3000"

    @property
    def effective_supabase_jwks_url(self) -> str:
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def effective_supabase_jwt_issuer(self) -> str:
        if self.supabase_jwt_issuer:
            return self.supabase_jwt_issuer
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def effective_supabase_publishable_key(self) -> str | None:
        return self.supabase_publishable_key or self.next_public_supabase_anon_key

    @property
    def r2_endpoint_url(self) -> str:
        return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"

    @property
    def allowed_input_formats(self) -> set[str]:
        return {
            value.strip().lower()
            for value in self.allowed_input_formats_csv.split(",")
            if value.strip()
        }

    @property
    def allowed_output_formats(self) -> set[str]:
        return {
            value.strip().lower()
            for value in self.allowed_output_formats_csv.split(",")
            if value.strip()
        }

    @property
    def allowed_engines(self) -> set[str]:
        return {
            value.strip().lower()
            for value in self.allowed_engines_csv.split(",")
            if value.strip()
        }

    @property
    def cors_allow_origins(self) -> list[str]:
        return [
            value.strip()
            for value in self.cors_allow_origins_csv.split(",")
            if value.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
