"""Application configuration loaded from environment."""
from pathlib import Path

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        protected_namespaces=("settings_",),
    )

    azure_ai_project_endpoint: str
    azure_openai_endpoint: str | None = None
    azure_ai_api_key: str | None = None

    model_gpt: str = "gpt-5.6-sol"
    model_claude: str = "claude-fable-5-1"
    model_kimi: str = "Kimi-K2.7-Code"
    model_grok: str = "grok-4.6"

    upload_dir: Path = Path("./data/uploads")
    output_dir: Path = Path("./data/outputs")
    job_store_path: Path = Path("./data/jobs.jsonl")


settings = Settings()
