import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    superuser_id: int
    superuser_username: str
    mainadmin_username: str
    db_path: str
    booking_ttl_hours: int


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "")
    superuser_id = int(os.getenv("SUPERUSER_ID", "0"))
    superuser_username = os.getenv("SUPERUSER_USERNAME", "").lstrip("@").lower()
    mainadmin_username = os.getenv("MAINADMIN_USERNAME", "").lstrip("@").lower()
    db_path = os.getenv("DB_PATH", "data/blubot.db")
    booking_ttl_hours = int(os.getenv("BOOKING_TTL_HOURS", "12"))

    if not token:
        raise ValueError("BOT_TOKEN is required")
    if not superuser_id:
        raise ValueError("SUPERUSER_ID is required")
    if not superuser_username:
        raise ValueError("SUPERUSER_USERNAME is required")
    if not mainadmin_username:
        raise ValueError("MAINADMIN_USERNAME is required")

    return Config(
        bot_token=token,
        superuser_id=superuser_id,
        superuser_username=superuser_username,
        mainadmin_username=mainadmin_username,
        db_path=db_path,
        booking_ttl_hours=booking_ttl_hours,
    )
