from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.config import Config
from bot.keyboards import main_menu_kb

router = Router()

USER_HELP = (
    "<b>Как пользоваться:</b>\n"
    "1. Откройте «Каталог» — список товаров\n"
    "2. Выберите товар (откроется фото) и нажмите «Забронировать»\n"
    "3. Соберите корзину в «Мои брони» (на это {minutes} минут)\n"
    "4. Нажмите «Оформить заказ» — скоро с вами свяжутся\n"
    "5. Или «Очистить корзину» / отмените товар\n\n"
    "Не успели за {minutes} минут — брони снимутся автоматически."
)


def _user_help(config: Config) -> str:
    return USER_HELP.format(minutes=config.cart_ttl_minutes)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    config: Config,
    is_admin: bool,
    is_super: bool = False,
) -> None:
    text = "Добро пожаловать!"
    if is_super:
        text += "\n\nВы суперпользователь."
    elif is_admin:
        text += "\n\nВы администратор."
    else:
        text += "\n\n" + _user_help(config)

    await message.answer(
        text,
        reply_markup=main_menu_kb(is_admin, is_super),
        protect_content=True,
    )


@router.message(F.text == "Помощь")
async def help_cmd(message: Message, config: Config, is_admin: bool = False) -> None:
    await message.answer(
        _user_help(config),
        protect_content=True,
    )
