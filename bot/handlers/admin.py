import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.db import Database, normalize_username
from bot.filters import admin_router
from bot.keyboards import pending_carts_kb, user_cart_kb

router = Router()
router.include_router(admin_router)


class AddItem(StatesGroup):
    photo = State()
    name = State()
    price = State()


def _format_cart(username: str, bookings: list) -> str:
    total = sum(b["price"] for b in bookings)
    lines = [f"<b>@{username}</b>"]
    for i, b in enumerate(bookings, 1):
        lines.append(f"{i}. {b['name']} — {b['price']:.0f}₽")
    lines.append(f"\n<b>Итого: {total:.0f}₽</b>")
    return "\n".join(lines)


async def _show_cart_message(message: Message, user_id: int, db: Database) -> bool:
    bookings = await db.get_user_cart(user_id)
    if not bookings:
        return False
    username = bookings[0]["username"] or "unknown"
    await message.edit_text(
        _format_cart(username, bookings),
        reply_markup=user_cart_kb(user_id, bookings),
        parse_mode="HTML",
    )
    return True


@admin_router.message(F.text == "Добавить товар")
async def add_item_start(message: Message, state: FSMContext) -> None:
    await state.set_state(AddItem.photo)
    await message.answer("Отправьте фото товара:")


@admin_router.message(AddItem.photo, F.photo)
async def add_item_photo(message: Message, state: FSMContext) -> None:
    photo = message.photo[-1]
    await state.update_data(photo_file_id=photo.file_id)
    await state.set_state(AddItem.name)
    await message.answer("Введите название товара:")


@admin_router.message(AddItem.photo)
async def add_item_photo_invalid(message: Message) -> None:
    await message.answer("Нужно отправить фото.")


@admin_router.message(AddItem.name, F.text)
async def add_item_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name:
        await message.answer("Название не может быть пустым.")
        return
    await state.update_data(name=name)
    await state.set_state(AddItem.price)
    await message.answer("Введите цену (число):")


@admin_router.message(AddItem.price, F.text)
async def add_item_price(message: Message, state: FSMContext, db: Database) -> None:
    text = message.text.strip().replace(",", ".")
    try:
        price = float(text)
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите корректную цену (положительное число).")
        return

    data = await state.get_data()
    item_id = await db.create_item(data["name"], price, data["photo_file_id"])
    await state.clear()
    await message.answer(f"Товар добавлен (id={item_id}).")


@admin_router.message(F.text == "Ожидают подтверждения")
async def pending_list(message: Message, db: Database) -> None:
    carts = await db.get_pending_carts()
    await message.answer(
        "Ожидают подтверждения:",
        reply_markup=pending_carts_kb(carts),
    )


@admin_router.callback_query(F.data == "admin:pending")
async def pending_callback(callback: CallbackQuery, db: Database) -> None:
    carts = await db.get_pending_carts()
    await callback.message.edit_text(
        "Ожидают подтверждения:",
        reply_markup=pending_carts_kb(carts),
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:cart:"))
async def show_cart(callback: CallbackQuery, db: Database) -> None:
    user_id = int(callback.data.split(":")[2])
    bookings = await db.get_user_cart(user_id)
    if not bookings:
        await callback.answer("Корзина пуста", show_alert=True)
        return

    username = bookings[0]["username"] or "unknown"
    await callback.message.edit_text(
        _format_cart(username, bookings),
        reply_markup=user_cart_kb(user_id, bookings),
        parse_mode="HTML",
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:confirm_all:"))
async def confirm_all(callback: CallbackQuery, db: Database) -> None:
    user_id = int(callback.data.split(":")[2])
    count = await db.confirm_user_cart(user_id)
    await callback.answer(f"Подтверждено: {count}")
    carts = await db.get_pending_carts()
    await callback.message.edit_text(
        "Ожидают подтверждения:",
        reply_markup=pending_carts_kb(carts),
    )


@admin_router.callback_query(F.data.startswith("admin:reject_all:"))
async def reject_all(callback: CallbackQuery, db: Database) -> None:
    user_id = int(callback.data.split(":")[2])
    count = await db.reject_user_cart(user_id)
    await callback.answer(f"Отклонено: {count}")
    carts = await db.get_pending_carts()
    await callback.message.edit_text(
        "Ожидают подтверждения:",
        reply_markup=pending_carts_kb(carts),
    )


@admin_router.callback_query(F.data.regexp(r"^admin:confirm:\d+:\d+$"))
async def confirm_one(callback: CallbackQuery, db: Database) -> None:
    _, _, booking_id, user_id = callback.data.split(":")
    ok = await db.confirm_booking(int(booking_id))
    if not ok:
        await callback.answer("Бронь не найдена", show_alert=True)
        return

    await callback.answer("Подтверждено")
    if not await _show_cart_message(callback.message, int(user_id), db):
        carts = await db.get_pending_carts()
        await callback.message.edit_text(
            "Ожидают подтверждения:",
            reply_markup=pending_carts_kb(carts),
        )


@admin_router.callback_query(F.data.regexp(r"^admin:reject:\d+:\d+$"))
async def reject_one(callback: CallbackQuery, db: Database) -> None:
    _, _, booking_id, user_id = callback.data.split(":")
    ok = await db.reject_booking(int(booking_id))
    if not ok:
        await callback.answer("Бронь не найдена", show_alert=True)
        return

    await callback.answer("Отклонено")
    if not await _show_cart_message(callback.message, int(user_id), db):
        carts = await db.get_pending_carts()
        await callback.message.edit_text(
            "Ожидают подтверждения:",
            reply_markup=pending_carts_kb(carts),
        )


@admin_router.message(Command("adduser"))
async def cmd_adduser(message: Message, db: Database) -> None:
    match = re.search(r"@?(\w+)", message.text or "")
    if not match:
        await message.answer("Использование: /adduser @username")
        return
    username = match.group(1)
    if await db.add_to_whitelist(username):
        await message.answer(f"@{normalize_username(username)} добавлен.")
    else:
        await message.answer("Пользователь уже в списке или неверный username.")


@admin_router.message(Command("removeuser"))
async def cmd_removeuser(message: Message, db: Database) -> None:
    match = re.search(r"@?(\w+)", message.text or "")
    if not match:
        await message.answer("Использование: /removeuser @username")
        return
    username = match.group(1)
    if await db.remove_from_whitelist(username):
        await message.answer(f"@{normalize_username(username)} удалён.")
    else:
        await message.answer("Пользователь не найден.")


@admin_router.message(Command("users"))
async def cmd_users(message: Message, db: Database) -> None:
    users = await db.list_whitelist()
    if not users:
        await message.answer("Список пуст. /adduser @username")
        return
    lines = ["<b>Пользователи:</b>"] + [f"@{u}" for u in users]
    await message.answer("\n".join(lines), parse_mode="HTML")
