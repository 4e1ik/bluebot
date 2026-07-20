from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.config import Config
from bot.keyboards import main_menu_kb

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, is_admin: bool, is_super: bool = False) -> None:
    text = "Добро пожаловать!"
    if is_super:
        text += "\n\nВы суперпользователь."
    elif is_admin:
        text += "\n\nВы администратор."
    await message.answer(text, reply_markup=main_menu_kb(is_admin, is_super))
