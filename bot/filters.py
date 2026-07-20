from __future__ import annotations

from aiogram import Router
from aiogram.filters import Filter
from aiogram.types import TelegramObject, User

from bot.config import Config
from bot.db import Database

admin_router = Router()
super_router = Router()


class IsAdmin(Filter):
    async def __call__(
        self,
        event: TelegramObject,
        is_admin: bool = False,
        event_from_user: User | None = None,
        config: Config | None = None,
        db: Database | None = None,
    ) -> bool:
        if is_admin:
            return True
        if not event_from_user or not config:
            return False
        if event_from_user.id == config.superuser_id:
            return True
        if db is None:
            return False
        return await db.is_admin_user(event_from_user.id, event_from_user.username)


class IsSuper(Filter):
    async def __call__(
        self,
        event: TelegramObject,
        is_super: bool = False,
        event_from_user: User | None = None,
        config: Config | None = None,
    ) -> bool:
        if is_super:
            return True
        if not event_from_user or not config:
            return False
        return event_from_user.id == config.superuser_id


admin_router.message.filter(IsAdmin())
admin_router.callback_query.filter(IsAdmin())
super_router.message.filter(IsSuper())
super_router.callback_query.filter(IsSuper())
