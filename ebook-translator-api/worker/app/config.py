from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    environment: str = "dev"

    database_url: str = Field(default="postgresql://postgres:postgres@postgres:5432/ebook")
    redis_url: str = Field(default="redis://redis:6379/0")
    celery_queue_name: str = Field(default="ebook.jobs.default")

    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_region: str = "auto"
    r2_raw_bucket: str = "ebook-raw"
    r2_result_bucket: str = "ebook-result"

    plugin_source_path: str = "/app/calibre_plugins/ebook_translator"
    temp_root: str = "/tmp/jobs"

    openai_engine_name: str = "ChatGPT"
    deepl_engine_name: str = "DeepL"
    google_engine_name: str = "Google(Free)New"
    deepinfra_engine_name: str = "DeepSeek"

    openai_api_keys_csv: str = ""
    deepl_api_keys_csv: str = ""
    google_api_keys_csv: str = ""
    deepinfra_api_keys_csv: str = ""

    openai_model: str = "gpt-4o"
    deepinfra_model: str = "deepseek-ai/DeepSeek-V3.2"
    deepinfra_endpoint: str = "https://api.deepinfra.com/v1/openai/chat/completions"

    task_retry_schedule_csv: str = "30,120,300"

    @property
    def r2_endpoint_url(self) -> str:
        return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"

    @property
    def retry_schedule(self) -> list[int]:
        return [int(v.strip()) for v in self.task_retry_schedule_csv.split(",") if v.strip()]


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
