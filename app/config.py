from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration using pydantic-settings."""

    # Database
    database_url: str

    # LLM API
    deepseek_api_key: str = ""
    deepseek_api_base: str = "https://api.deepseek.com/v1"

    # Task processing
    max_concurrent_tasks: int = 3
    max_retries: int = 3
    zombie_task_timeout: int = 300  # 5 minutes in seconds

    # File storage
    upload_dir: str = "./uploads"
    max_file_size: int = 50 * 1024 * 1024  # 50MB

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )


settings = Settings()
