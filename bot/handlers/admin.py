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
from bot.catalog_nav import placement_line, root_screen
from bot.keyboards import (
    add_place_kind_kb,
    admins_kb,
    cancel_kb,
    edit_item_kb,
    main_menu_kb,
    pending_carts_kb,
    pick_rows,
    place_kind_kb,
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
    place = State()


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
async def add_item_start(
    message: Message,
    state: FSMContext,
    db: Database,
    is_admin: bool = False,
    is_super: bool = False,
) -> None:
    if not await db.list_categories():
        await message.answer(
            "Сначала создайте категорию.",
            reply_markup=main_menu_kb(is_admin, is_super),
            protect_content=True,
        )
        return
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
    text, markup = await root_screen(db)
    await callback.message.answer(
        f"Товар удалён.\n\n{text}",
        reply_markup=markup,
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
            caption=(
                f"Что изменить у «{item['name']}»?\n{placement_line(item)}"
            ),
            reply_markup=edit_item_kb(item_id),
        )
    except Exception:
        await callback.message.answer(
            f"Что изменить у «{item['name']}»?\n{placement_line(item)}",
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
async def add_item_price(message: Message, state: FSMContext) -> None:
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

    await state.update_data(price=price)
    await state.set_state(AddItem.place)
    await message.answer(
        "Куда отнести товар?",
        reply_markup=add_place_kind_kb(),
        protect_content=True,
    )


@admin_router.message(AddItem.place, F.text, F.text != "Отмена")
async def add_place_need_button(message: Message) -> None:
    await message.answer(
        "Выберите категорию или подкатегорию кнопкой.",
        protect_content=True,
    )


async def _save_new_item(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    *,
    category_id: int | None = None,
    subcategory_id: int | None = None,
    is_admin: bool = False,
    is_super: bool = False,
) -> None:
    data = await state.get_data()
    item_id = await db.create_item(
        data["name"],
        data["price"],
        data["photo_file_id"],
        category_id=category_id,
        subcategory_id=subcategory_id,
    )
    if item_id is None:
        await callback.answer("Не удалось сохранить товар", show_alert=True)
        return
    await state.clear()
    item = await db.get_item(item_id)
    await callback.message.answer(
        f"Товар добавлен (id={item_id}).\n{placement_line(item)}",
        reply_markup=main_menu_kb(is_admin, is_super),
        protect_content=True,
    )
    await callback.answer("Товар добавлен")


@admin_router.callback_query(AddItem.place, F.data == "admin:add:back")
async def add_place_back(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "Куда отнести товар?", reply_markup=add_place_kind_kb()
    )
    await callback.answer()


@admin_router.callback_query(AddItem.place, F.data == "admin:add:kind:cat")
async def add_choose_category(callback: CallbackQuery, db: Database) -> None:
    categories = await db.list_categories()
    if not categories:
        await callback.answer("Сначала создайте категорию", show_alert=True)
        return
    await callback.message.edit_text(
        "Выберите категорию:",
        reply_markup=pick_rows(categories, "admin:add:setcat", "admin:add:back"),
    )
    await callback.answer()


@admin_router.callback_query(AddItem.place, F.data == "admin:add:kind:sub")
async def add_choose_subcategory_parent(
    callback: CallbackQuery, db: Database
) -> None:
    if await db.count_subcategories() == 0:
        await callback.answer("Подкатегорий пока нет", show_alert=True)
        return
    categories = await db.list_categories()
    await callback.message.edit_text(
        "Выберите категорию, затем подкатегорию:",
        reply_markup=pick_rows(categories, "admin:add:picksub", "admin:add:back"),
    )
    await callback.answer()


@admin_router.callback_query(AddItem.place, F.data.startswith("admin:add:picksub:"))
async def add_choose_subcategory(callback: CallbackQuery, db: Database) -> None:
    category_id = int(callback.data.split(":")[3])
    subs = await db.list_subcategories(category_id)
    if not subs:
        await callback.answer("В этой категории нет подкатегорий", show_alert=True)
        return
    await callback.message.edit_text(
        "Выберите подкатегорию:",
        reply_markup=pick_rows(subs, "admin:add:setsub", "admin:add:kind:sub"),
    )
    await callback.answer()


@admin_router.callback_query(AddItem.place, F.data.startswith("admin:add:setcat:"))
async def add_set_category(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    is_admin: bool = False,
    is_super: bool = False,
) -> None:
    category_id = int(callback.data.split(":")[3])
    await _save_new_item(
        callback,
        state,
        db,
        category_id=category_id,
        is_admin=is_admin,
        is_super=is_super,
    )


@admin_router.callback_query(AddItem.place, F.data.startswith("admin:add:setsub:"))
async def add_set_subcategory(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    is_admin: bool = False,
    is_super: bool = False,
) -> None:
    subcategory_id = int(callback.data.split(":")[3])
    await _save_new_item(
        callback,
        state,
        db,
        subcategory_id=subcategory_id,
        is_admin=is_admin,
        is_super=is_super,
    )


async def _refresh_edit_menu(callback: CallbackQuery, item) -> None:
    caption = f"Что изменить у «{item['name']}»?\n{placement_line(item)}"
    try:
        await callback.message.edit_caption(
            caption=caption,
            reply_markup=edit_item_kb(item["id"]),
        )
    except Exception:
        await callback.message.answer(
            caption,
            reply_markup=edit_item_kb(item["id"]),
            protect_content=True,
        )


@admin_router.callback_query(F.data.startswith("admin:edit_place:"))
async def edit_place_menu(callback: CallbackQuery, db: Database) -> None:
    item_id = int(callback.data.split(":")[2])
    item = await db.get_item(item_id)
    if not item or item["status"] == "hidden":
        await callback.answer("Товар не найден", show_alert=True)
        return
    caption = f"Куда перепривязать «{item['name']}»?\n{placement_line(item)}"
    try:
        await callback.message.edit_caption(
            caption=caption, reply_markup=place_kind_kb(item_id)
        )
    except Exception:
        await callback.message.answer(
            caption, reply_markup=place_kind_kb(item_id), protect_content=True
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:place:cat:"))
async def edit_place_categories(callback: CallbackQuery, db: Database) -> None:
    item_id = int(callback.data.split(":")[3])
    categories = await db.list_categories()
    if not categories:
        await callback.answer("Сначала создайте категорию", show_alert=True)
        return
    await callback.message.edit_caption(
        caption="Выберите категорию:",
        reply_markup=pick_rows(
            categories, f"admin:place:setcat:{item_id}", f"admin:edit_place:{item_id}"
        ),
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:place:sub:"))
async def edit_place_sub_parents(callback: CallbackQuery, db: Database) -> None:
    item_id = int(callback.data.split(":")[3])
    if await db.count_subcategories() == 0:
        await callback.answer("Подкатегорий пока нет", show_alert=True)
        return
    categories = await db.list_categories()
    await callback.message.edit_caption(
        caption="Выберите категорию, затем подкатегорию:",
        reply_markup=pick_rows(
            categories,
            f"admin:place:picksub:{item_id}",
            f"admin:edit_place:{item_id}",
        ),
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:place:picksub:"))
async def edit_place_subs(callback: CallbackQuery, db: Database) -> None:
    _, _, _, item_id, category_id = callback.data.split(":")
    subs = await db.list_subcategories(int(category_id))
    if not subs:
        await callback.answer("В этой категории нет подкатегорий", show_alert=True)
        return
    await callback.message.edit_caption(
        caption="Выберите подкатегорию:",
        reply_markup=pick_rows(
            subs,
            f"admin:place:setsub:{item_id}",
            f"admin:place:sub:{item_id}",
        ),
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:place:setcat:"))
async def edit_place_set_category(callback: CallbackQuery, db: Database) -> None:
    _, _, _, item_id, category_id = callback.data.split(":")
    result = await db.assign_item(int(item_id), category_id=int(category_id))
    if result == "same":
        await callback.answer("Уже относится сюда", show_alert=True)
        return
    if result != "ok":
        await callback.answer("Не удалось перепривязать", show_alert=True)
        return
    item = await db.get_item(int(item_id))
    await _refresh_edit_menu(callback, item)
    await callback.answer("Привязка обновлена")


@admin_router.callback_query(F.data.startswith("admin:place:setsub:"))
async def edit_place_set_subcategory(callback: CallbackQuery, db: Database) -> None:
    _, _, _, item_id, subcategory_id = callback.data.split(":")
    result = await db.assign_item(int(item_id), subcategory_id=int(subcategory_id))
    if result == "same":
        await callback.answer("Уже относится сюда", show_alert=True)
        return
    if result != "ok":
        await callback.answer("Не удалось перепривязать", show_alert=True)
        return
    item = await db.get_item(int(item_id))
    await _refresh_edit_menu(callback, item)
    await callback.answer("Привязка обновлена")


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


import bot.handlers.categories  # noqa: F401, E402  registers category handlers
import bot.handlers.stats  # noqa: F401, E402  registers statistics handlers
