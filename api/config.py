from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    supabase_url: str
    supabase_anon_key: str
    supabase_service_key: str
    redis_url: str = "redis://localhost:6379"
    data_root: str = str(Path(__file__).parent.parent)
    cors_origins: list[str] = ["http://localhost:3000", "https://molecopilot.netlify.app"]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
