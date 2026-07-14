"""Application configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    """Environment-derived settings."""

    app_name: str = "ODINBET"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    data_dir: Path = DATA_DIR
    model_dir: Path = DATA_DIR / "models"
    odds_api_key: str | None = None
    log_level: str = "INFO"

    class Config:
        env_prefix = "ODINBET_"
        env_file = ".env"


settings = Settings()
settings.model_dir.mkdir(parents=True, exist_ok=True)
