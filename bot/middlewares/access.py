from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from bot.config import Config
from bot.db import Database


class AccessMiddleware(BaseMiddleware):
    def __init__(self, config: Config, db: Database) -> None:
        self.config = config
        self.db = db

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        is_super = user.id == self.config.superuser_id

        if not is_super and user.username:
            await self.db.bind_admin_user_id(user.username, user.id)

        is_admin = is_super or await self.db.is_admin_user(user.id, user.username)
        data["is_super"] = is_super
        data["is_admin"] = is_admin

        if is_admin:
            return await handler(event, data)

        if not user.username:
            if isinstance(event, Message):
                await event.answer(
                    "Для доступа к боту нужен @username в настройках Telegram."
                )
            return None

        if await self.db.is_whitelisted(user.username):
            return await handler(event, data)

        if isinstance(event, Message):
            await event.answer("Нет доступа. Обратитесь к администратору.")
        elif hasattr(event, "answer"):
            await event.answer()
        return None
