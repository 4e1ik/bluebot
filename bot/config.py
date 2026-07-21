import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    superuser_id: int
    superuser_username: str
    db_path: str
    cart_ttl_minutes: int


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "")
    superuser_id = int(os.getenv("SUPERUSER_ID", "0"))
    superuser_username = os.getenv("SUPERUSER_USERNAME", "").lstrip("@").lower()
    db_path = os.getenv("DB_PATH", "data/blubot.db")
    cart_ttl_minutes = int(os.getenv("CART_TTL_MINUTES", "20"))

    if not token:
        raise ValueError("BOT_TOKEN is required")
    if not superuser_id:
        raise ValueError("SUPERUSER_ID is required")
    if not superuser_username:
        raise ValueError("SUPERUSER_USERNAME is required")

    return Config(
        bot_token=token,
        superuser_id=superuser_id,
        superuser_username=superuser_username,
        db_path=db_path,
        cart_ttl_minutes=cart_ttl_minutes,
    )
