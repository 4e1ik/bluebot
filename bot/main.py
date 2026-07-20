import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import load_config
from bot.db import Database
from bot.handlers import admin, booking, catalog, common
from bot.middlewares.access import AccessMiddleware
from bot.tasks.expiry import expiry_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    config = load_config()
    db = Database(config.db_path)
    await db.connect()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp["config"] = config
    dp["db"] = db

    dp.message.middleware(AccessMiddleware(config, db))
    dp.callback_query.middleware(AccessMiddleware(config, db))

    dp.include_router(common.router)
    dp.include_router(catalog.router)
    dp.include_router(booking.router)
    dp.include_router(admin.router)

    asyncio.create_task(expiry_loop(bot, db, config))

    logger.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
