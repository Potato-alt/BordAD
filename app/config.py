import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    forcead_base_url: str
    forcead_team_token: str
    app_token: str
    our_team_id: int
    poll_interval_seconds: float
    submit_interval_seconds: float
    submit_batch_size: int
    database_path: str


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


def load_settings() -> Settings:
    base_url = os.getenv("FORCEAD_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
    return Settings(
        forcead_base_url=base_url,
        forcead_team_token=os.getenv("FORCEAD_TEAM_TOKEN", ""),
        app_token=os.getenv("APP_TOKEN", "dev-token"),
        our_team_id=_get_int("OUR_TEAM_ID", 1),
        poll_interval_seconds=_get_float("POLL_INTERVAL_SECONDS", 10),
        submit_interval_seconds=_get_float("SUBMIT_INTERVAL_SECONDS", 1),
        submit_batch_size=min(_get_int("SUBMIT_BATCH_SIZE", 100), 100),
        database_path=os.getenv("DATABASE_PATH", "./data/warboard.sqlite3"),
    )
