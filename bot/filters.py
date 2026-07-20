from __future__ import annotations

from aiogram import Router
from aiogram.filters import Filter
from aiogram.types import TelegramObject, User

from bot.config import Config

router = Router()
admin_router = Router()


class IsAdmin(Filter):
    async def __call__(
        self,
        event: TelegramObject,
        event_from_user: User | None = None,
        config: Config | None = None,
    ) -> bool:
        if not event_from_user or not config:
            return False
        return event_from_user.id == config.admin_id


admin_router.message.filter(IsAdmin())
admin_router.callback_query.filter(IsAdmin())
