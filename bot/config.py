import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_id: int
    admin_username: str
    db_path: str
    booking_ttl_hours: int


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "")
    admin_id = int(os.getenv("ADMIN_ID", "0"))
    admin_username = os.getenv("ADMIN_USERNAME", "").lstrip("@").lower()
    db_path = os.getenv("DB_PATH", "data/blubot.db")
    booking_ttl_hours = int(os.getenv("BOOKING_TTL_HOURS", "12"))

    if not token:
        raise ValueError("BOT_TOKEN is required")
    if not admin_id:
        raise ValueError("ADMIN_ID is required")
    if not admin_username:
        raise ValueError("ADMIN_USERNAME is required")

    return Config(
        bot_token=token,
        admin_id=admin_id,
        admin_username=admin_username,
        db_path=db_path,
        booking_ttl_hours=booking_ttl_hours,
    )
