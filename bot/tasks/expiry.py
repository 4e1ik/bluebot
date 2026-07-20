import asyncio
import logging

from aiogram import Bot

from bot.config import Config
from bot.db import Database

logger = logging.getLogger(__name__)


async def expiry_loop(
    bot: Bot, db: Database, config: Config, interval_sec: int = 300
) -> None:
    while True:
        try:
            expired = await db.expire_old_bookings()
            for booking in expired:
                try:
                    await bot.send_message(
                        booking["user_id"],
                        f"Бронь на «{booking['item_name']}» снята — "
                        f"админ не подтвердил за {config.booking_ttl_hours} часов.",
                    )
                except Exception:
                    logger.exception(
                        "Failed to notify user %s about expiry", booking["user_id"]
                    )
        except Exception:
            logger.exception("Expiry task error")

        await asyncio.sleep(interval_sec)
