import logging

from aiogram import Bot

from bot.db import Database

logger = logging.getLogger(__name__)


async def notify_admins(bot: Bot, db: Database, text: str) -> None:
    for user_id in await db.list_admin_user_ids():
        try:
            await bot.send_message(user_id, text, protect_content=True)
        except Exception:
            logger.exception("Failed to notify admin %s", user_id)


async def notify_users(bot: Bot, user_ids: list[int], text: str) -> int:
    sent = 0
    for user_id in user_ids:
        try:
            await bot.send_message(user_id, text, protect_content=True)
            sent += 1
        except Exception:
            logger.exception("Failed to notify user %s", user_id)
    return sent
