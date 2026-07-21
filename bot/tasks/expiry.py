import logging

from aiogram import Bot

from bot.config import Config
from bot.db import Database

logger = logging.getLogger(__name__)


async def expiry_loop(
    bot: Bot, db: Database, config: Config, interval_sec: int = 60
) -> None:
    import asyncio

    while True:
        try:
            expired = await db.expire_old_bookings()
            # group by user to send one message
            by_user: dict[int, list[str]] = {}
            for booking in expired:
                by_user.setdefault(booking["user_id"], []).append(
                    booking["item_name"]
                )
            for user_id, names in by_user.items():
                try:
                    items = ", ".join(f"«{n}»" for n in names)
                    await bot.send_message(
                        user_id,
                        f"Брони сняты ({items}) — не оформили заказ за "
                        f"{config.cart_ttl_minutes} минут.",
                        protect_content=True,
                    )
                except Exception:
                    logger.exception(
                        "Failed to notify user %s about expiry", user_id
                    )
        except Exception:
            logger.exception("Expiry task error")

        await asyncio.sleep(interval_sec)
