from __future__ import annotations

import re

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.db import Database, normalize_username
from bot.filters import admin_router, super_router
from bot.keyboards import (
    admins_kb,
    cancel_kb,
    catalog_kb,
    edit_item_kb,
    main_menu_kb,
    pending_carts_kb,
    user_cart_kb,
    whitelist_kb,
)
from bot.notify import notify_users

router = Router()
router.include_router(admin_router)
router.include_router(super_router)

USERNAME_RE = re.compile(r"^@?([A-Za-z0-9_]{5,32})$")


class AddItem(StatesGroup):
    photo = State()
    name = State()
    price = State()


class EditItem(StatesGroup):
    photo = State()
    name = State()
    price = State()


class ManageUser(StatesGroup):
    waiting_username = State()


class ManageAdmin(StatesGroup):
    waiting_username = State()


def _parse_username(text: str) -> str | None:
    match = USERNAME_RE.match(text.strip())
    return match.group(1) if match else None


def _format_cart(username: str, bookings: list) -> str:
    total = sum(b["price"] for b in bookings)
    lines = [f"<b>@{username}</b>"]
    for i, b in enumerate(bookings, 1):
        lines.append(f"{i}. {b['name']} — {b['price']:.0f} Br")
    lines.append(f"\n<b>Итого: {total:.0f} Br</b>")
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


async def _users_text(db: Database) -> str:
    users = await db.list_whitelist()
    if not users:
        return "<b>Пользователи:</b>\nСписок пуст."
    lines = ["<b>Пользователи:</b>"] + [f"@{u}" for u in users]
    return "\n".join(lines)


async def _admins_text(db: Database, config: Config) -> str:
    lines = [
        "<b>Админы:</b>",
        f"👑 @{config.superuser_username} (супер)",
    ]
    admins = await db.list_admins()
    extra = [u for u in admins if u != config.superuser_username]
    if extra:
        lines.extend(f"@{u}" for u in extra)
    else:
        lines.append("Дополнительных админов нет.")
    return "\n".join(lines)


@admin_router.message(F.text == "Отмена")
async def cancel_fsm(
    message: Message,
    state: FSMContext,
    is_admin: bool = False,
    is_super: bool = False,
) -> None:
    await state.clear()
    await message.answer(
        "Отменено.",
        reply_markup=main_menu_kb(is_admin, is_super),
        protect_content=True,
    )


@admin_router.message(F.text == "Добавить товар")
async def add_item_start(message: Message, state: FSMContext) -> None:
    await state.set_state(AddItem.photo)
    await message.answer(
        "Отправьте фото товара (или «Отмена»):",
        reply_markup=cancel_kb(),
        protect_content=True,
    )


@admin_router.callback_query(F.data.startswith("admin:delete_item:"))
async def delete_item(callback: CallbackQuery, db: Database) -> None:
    item_id = int(callback.data.split(":")[2])
    ok = await db.delete_item(item_id)
    if not ok:
        await callback.answer("Товар не найден", show_alert=True)
        return

    await callback.answer("Удалено")
    await callback.message.delete()
    items = await db.get_catalog_items()
    await callback.message.answer(
        "Товар удалён.\n\nКаталог:",
        reply_markup=catalog_kb(items),
    )


@admin_router.message(F.text == "Уведомить о новинках")
async def notify_new_items(
    message: Message, db: Database, bot: Bot, config: Config
) -> None:
    count = await db.count_new_items()
    if count == 0:
        await message.answer(
            "Новых товаров (младше 7 дней) нет.",
            protect_content=True,
        )
        return

    user_ids = [
        uid
        for uid in await db.list_notify_user_ids()
        if uid != config.superuser_id
    ]
    if not user_ids:
        await message.answer(
            "Некому отправить: нет пользователей/админов с известным user_id. "
            "Пусть они хотя бы раз нажмут /start.",
            protect_content=True,
        )
        return

    text = (
        "Появились новые позиции в каталоге.\n"
        "Откройте «Каталог», чтобы посмотреть."
    )
    sent = await notify_users(bot, user_ids, text)
    await message.answer(
        f"Уведомление отправлено: {sent} из {len(user_ids)}.",
        protect_content=True,
    )


@admin_router.callback_query(F.data.regexp(r"^admin:edit:\d+$"))
async def edit_item_menu(callback: CallbackQuery, db: Database) -> None:
    item_id = int(callback.data.split(":")[2])
    item = await db.get_item(item_id)
    if not item or item["status"] == "hidden":
        await callback.answer("Товар не найден", show_alert=True)
        return

    await callback.answer()
    try:
        await callback.message.edit_caption(
            caption=f"Что изменить у «{item['name']}»?",
            reply_markup=edit_item_kb(item_id),
        )
    except Exception:
        await callback.message.answer(
            f"Что изменить у «{item['name']}»?",
            reply_markup=edit_item_kb(item_id),
            protect_content=True,
        )


@admin_router.callback_query(F.data.startswith("admin:edit_photo:"))
async def edit_photo_start(callback: CallbackQuery, state: FSMContext) -> None:
    item_id = int(callback.data.split(":")[2])
    await state.set_state(EditItem.photo)
    await state.update_data(edit_item_id=item_id)
    await callback.answer()
    await callback.message.answer(
        "Отправьте новое фото (или «Отмена»):",
        reply_markup=cancel_kb(),
        protect_content=True,
    )


@admin_router.callback_query(F.data.startswith("admin:edit_name:"))
async def edit_name_start(callback: CallbackQuery, state: FSMContext) -> None:
    item_id = int(callback.data.split(":")[2])
    await state.set_state(EditItem.name)
    await state.update_data(edit_item_id=item_id)
    await callback.answer()
    await callback.message.answer(
        "Введите новое название (или «Отмена»):",
        reply_markup=cancel_kb(),
        protect_content=True,
    )


@admin_router.callback_query(F.data.startswith("admin:edit_price:"))
async def edit_price_start(callback: CallbackQuery, state: FSMContext) -> None:
    item_id = int(callback.data.split(":")[2])
    await state.set_state(EditItem.price)
    await state.update_data(edit_item_id=item_id)
    await callback.answer()
    await callback.message.answer(
        "Введите новую цену (или «Отмена»):",
        reply_markup=cancel_kb(),
        protect_content=True,
    )


@admin_router.message(EditItem.photo, F.photo)
async def edit_photo_save(
    message: Message,
    state: FSMContext,
    db: Database,
    is_admin: bool = False,
    is_super: bool = False,
) -> None:
    data = await state.get_data()
    item_id = data.get("edit_item_id")
    await state.clear()
    ok = await db.update_item_photo(item_id, message.photo[-1].file_id)
    text = "Фото обновлено." if ok else "Не удалось обновить фото."
    await message.answer(
        text,
        reply_markup=main_menu_kb(is_admin, is_super),
        protect_content=True,
    )


@admin_router.message(EditItem.photo)
async def edit_photo_invalid(message: Message) -> None:
    await message.answer(
        "Нужно отправить фото или нажмите «Отмена».",
        protect_content=True,
    )


@admin_router.message(EditItem.name, F.text, F.text != "Отмена")
async def edit_name_save(
    message: Message,
    state: FSMContext,
    db: Database,
    is_admin: bool = False,
    is_super: bool = False,
) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("Название не может быть пустым.", protect_content=True)
        return
    data = await state.get_data()
    item_id = data.get("edit_item_id")
    await state.clear()
    ok = await db.update_item_name(item_id, name)
    text = "Название обновлено." if ok else "Не удалось обновить название."
    await message.answer(
        text,
        reply_markup=main_menu_kb(is_admin, is_super),
        protect_content=True,
    )


@admin_router.message(EditItem.price, F.text, F.text != "Отмена")
async def edit_price_save(
    message: Message,
    state: FSMContext,
    db: Database,
    is_admin: bool = False,
    is_super: bool = False,
) -> None:
    raw = (message.text or "").strip().replace(",", ".")
    try:
        price = float(raw)
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "Введите корректную цену (положительное число).",
            protect_content=True,
        )
        return

    data = await state.get_data()
    item_id = data.get("edit_item_id")
    await state.clear()
    ok = await db.update_item_price(item_id, price)
    text = "Цена обновлена." if ok else "Не удалось обновить цену."
    await message.answer(
        text,
        reply_markup=main_menu_kb(is_admin, is_super),
        protect_content=True,
    )


@admin_router.message(AddItem.photo, F.photo)
async def add_item_photo(message: Message, state: FSMContext) -> None:
    photo = message.photo[-1]
    await state.update_data(photo_file_id=photo.file_id)
    await state.set_state(AddItem.name)
    await message.answer(
        "Введите название товара:",
        reply_markup=cancel_kb(),
        protect_content=True,
    )


@admin_router.message(AddItem.photo)
async def add_item_photo_invalid(message: Message) -> None:
    await message.answer(
        "Нужно отправить фото или нажмите «Отмена».",
        protect_content=True,
    )


@admin_router.message(AddItem.name, F.text, F.text != "Отмена")
async def add_item_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name:
        await message.answer("Название не может быть пустым.", protect_content=True)
        return
    await state.update_data(name=name)
    await state.set_state(AddItem.price)
    await message.answer(
        "Введите цену (число):",
        reply_markup=cancel_kb(),
        protect_content=True,
    )


@admin_router.message(AddItem.price, F.text, F.text != "Отмена")
async def add_item_price(
    message: Message,
    state: FSMContext,
    db: Database,
    is_admin: bool = False,
    is_super: bool = False,
) -> None:
    text = message.text.strip().replace(",", ".")
    try:
        price = float(text)
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "Введите корректную цену (положительное число).",
            protect_content=True,
        )
        return

    data = await state.get_data()
    item_id = await db.create_item(data["name"], price, data["photo_file_id"])
    await state.clear()
    await message.answer(
        f"Товар добавлен (id={item_id}).",
        reply_markup=main_menu_kb(is_admin, is_super),
        protect_content=True,
    )

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


@admin_router.message(F.text == "Пользователи")
async def users_menu(message: Message, db: Database, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        await _users_text(db),
        reply_markup=whitelist_kb(),
        parse_mode="HTML",
    )


@admin_router.callback_query(F.data == "admin:user_add")
async def user_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ManageUser.waiting_username)
    await state.update_data(user_action="add")
    await callback.message.answer(
        "Введите @username пользователя для добавления (или «Отмена»):",
        reply_markup=cancel_kb(),
        protect_content=True,
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin:user_remove")
async def user_remove_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ManageUser.waiting_username)
    await state.update_data(user_action="remove")
    await callback.message.answer(
        "Введите @username пользователя для удаления (или «Отмена»):",
        reply_markup=cancel_kb(),
        protect_content=True,
    )
    await callback.answer()


@admin_router.message(ManageUser.waiting_username, F.text, F.text != "Отмена")
async def user_manage_username(
    message: Message,
    state: FSMContext,
    db: Database,
    is_admin: bool = False,
    is_super: bool = False,
) -> None:
    username = _parse_username(message.text or "")
    if not username:
        await message.answer(
            "Неверный формат. Пример: @nickname",
            protect_content=True,
        )
        return

    data = await state.get_data()
    action = data.get("user_action")
    await state.clear()

    if action == "add":
        if await db.add_to_whitelist(username):
            await message.answer(
                f"@{normalize_username(username)} добавлен.",
                reply_markup=main_menu_kb(is_admin, is_super),
                protect_content=True,
            )
        else:
            await message.answer(
                "Пользователь уже в списке.",
                reply_markup=main_menu_kb(is_admin, is_super),
                protect_content=True,
            )
    elif action == "remove":
        if await db.remove_from_whitelist(username):
            await message.answer(
                f"@{normalize_username(username)} удалён.",
                reply_markup=main_menu_kb(is_admin, is_super),
                protect_content=True,
            )
        else:
            await message.answer(
                "Пользователь не найден.",
                reply_markup=main_menu_kb(is_admin, is_super),
                protect_content=True,
            )
    else:
        await message.answer(
            "Действие не выбрано. Откройте «Пользователи» снова.",
            reply_markup=main_menu_kb(is_admin, is_super),
            protect_content=True,
        )
        return

    await message.answer(
        await _users_text(db),
        reply_markup=whitelist_kb(),
        parse_mode="HTML",
        protect_content=True,
    )


@admin_router.message(Command("adduser"))
async def cmd_adduser(message: Message, db: Database) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /adduser @username")
        return
    username = _parse_username(parts[1])
    if not username:
        await message.answer("Неверный формат. Пример: /adduser @nickname")
        return
    if await db.add_to_whitelist(username):
        await message.answer(f"@{normalize_username(username)} добавлен.")
    else:
        await message.answer("Пользователь уже в списке или неверный username.")


@admin_router.message(Command("removeuser"))
async def cmd_removeuser(message: Message, db: Database) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /removeuser @username")
        return
    username = _parse_username(parts[1])
    if not username:
        await message.answer("Неверный формат. Пример: /removeuser @nickname")
        return
    if await db.remove_from_whitelist(username):
        await message.answer(f"@{normalize_username(username)} удалён.")
    else:
        await message.answer("Пользователь не найден.")


@admin_router.message(Command("users"))
async def cmd_users(message: Message, db: Database) -> None:
    await message.answer(
        await _users_text(db),
        reply_markup=whitelist_kb(),
        parse_mode="HTML",
    )


# --- Superuser: manage admins ---


@super_router.message(F.text == "Админы")
async def admins_menu(
    message: Message, db: Database, config: Config, state: FSMContext
) -> None:
    await state.clear()
    await message.answer(
        await _admins_text(db, config),
        reply_markup=admins_kb(),
        parse_mode="HTML",
    )


@super_router.callback_query(F.data == "super:admin_add")
async def admin_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ManageAdmin.waiting_username)
    await state.update_data(admin_action="add")
    await callback.message.answer(
        "Введите @username админа для добавления (или «Отмена»):",
        reply_markup=cancel_kb(),
        protect_content=True,
    )
    await callback.answer()


@super_router.callback_query(F.data == "super:admin_remove")
async def admin_remove_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ManageAdmin.waiting_username)
    await state.update_data(admin_action="remove")
    await callback.message.answer(
        "Введите @username админа для удаления (или «Отмена»):",
        reply_markup=cancel_kb(),
        protect_content=True,
    )
    await callback.answer()


@super_router.message(ManageAdmin.waiting_username, F.text, F.text != "Отмена")
async def admin_manage_username(
    message: Message,
    state: FSMContext,
    db: Database,
    config: Config,
    is_admin: bool = False,
    is_super: bool = False,
) -> None:
    username = _parse_username(message.text or "")
    if not username:
        await message.answer(
            "Неверный формат. Пример: @nickname",
            protect_content=True,
        )
        return

    norm = normalize_username(username)
    if norm == config.superuser_username:
        await state.clear()
        await message.answer(
            "Суперпользователя нельзя добавить или удалить через бота.",
            reply_markup=main_menu_kb(is_admin, is_super),
            protect_content=True,
        )
        await message.answer(
            await _admins_text(db, config),
            reply_markup=admins_kb(),
            parse_mode="HTML",
            protect_content=True,
        )
        return

    data = await state.get_data()
    action = data.get("admin_action")
    await state.clear()

    if action == "add":
        if await db.add_admin(username):
            await message.answer(
                f"@{norm} добавлен как админ.",
                reply_markup=main_menu_kb(is_admin, is_super),
                protect_content=True,
            )
        else:
            await message.answer(
                "Админ уже в списке.",
                reply_markup=main_menu_kb(is_admin, is_super),
                protect_content=True,
            )
    elif action == "remove":
        if await db.remove_admin(username):
            await message.answer(
                f"@{norm} удалён из админов.",
                reply_markup=main_menu_kb(is_admin, is_super),
                protect_content=True,
            )
        else:
            await message.answer(
                "Админ не найден.",
                reply_markup=main_menu_kb(is_admin, is_super),
                protect_content=True,
            )
    else:
        await message.answer(
            "Действие не выбрано. Откройте «Админы» снова.",
            reply_markup=main_menu_kb(is_admin, is_super),
            protect_content=True,
        )
        return

    await message.answer(
        await _admins_text(db, config),
        reply_markup=admins_kb(),
        parse_mode="HTML",
        protect_content=True,
    )
