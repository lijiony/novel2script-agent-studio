from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    use_mock_llm: bool = Field(default=True, alias="USE_MOCK_LLM")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    runs_dir: Path = Field(default=Path("runs"), alias="RUNS_DIR")
    max_input_chars: int = Field(default=50000, alias="MAX_INPUT_CHARS")
    run_ttl_hours: int = Field(default=24, alias="RUN_TTL_HOURS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
