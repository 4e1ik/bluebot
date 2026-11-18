from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.catalog_nav import (
    category_screen,
    item_back_callback,
    placement_line,
    root_screen,
    subcategory_screen,
    uncategorized_screen,
)
from bot.db import Database, is_new_item
from bot.keyboards import item_kb

router = Router()


def _item_caption(item, booking_user_id: int | None, current_user_id: int) -> str:
    name = item["name"]
    if is_new_item(item["created_at"]):
        name = f"🆕 {name}"
    lines = [f"<b>{name}</b>", f"Цена: {item['price']:.0f} Br", placement_line(item)]
    if item["status"] == "pending":
        if booking_user_id == current_user_id:
            lines.append("\n🔒 Забронировано вами")
        else:
            lines.append("\n🔒 Забронирован")
    return "\n".join(lines)


async def _show_screen(callback: CallbackQuery, text: str, markup) -> None:
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        text,
        reply_markup=markup,
        protect_content=True,
    )
    await callback.answer()


@router.message(F.text == "Каталог")
async def show_catalog(message: Message, db: Database) -> None:
    text, markup = await root_screen(db)
    await message.answer(text, reply_markup=markup, protect_content=True)


@router.callback_query(F.data == "catalog")
async def catalog_callback(callback: CallbackQuery, db: Database) -> None:
    text, markup = await root_screen(db)
    await _show_screen(callback, text, markup)


@router.callback_query(F.data.startswith("catalog:cat:"))
async def catalog_category(callback: CallbackQuery, db: Database) -> None:
    category_id = int(callback.data.split(":")[2])
    screen = await category_screen(db, category_id)
    if screen is None:
        await callback.answer("Категория не найдена", show_alert=True)
        return
    await _show_screen(callback, *screen)


@router.callback_query(F.data.startswith("catalog:sub:"))
async def catalog_subcategory(callback: CallbackQuery, db: Database) -> None:
    subcategory_id = int(callback.data.split(":")[2])
    screen = await subcategory_screen(db, subcategory_id)
    if screen is None:
        await callback.answer("Подкатегория не найдена", show_alert=True)
        return
    await _show_screen(callback, *screen)


@router.callback_query(F.data == "catalog:none")
async def catalog_uncategorized(callback: CallbackQuery, db: Database) -> None:
    await _show_screen(callback, *(await uncategorized_screen(db)))


@router.callback_query(F.data.startswith("item:"))
async def show_item(
    callback: CallbackQuery, db: Database, is_admin: bool = False
) -> None:
    item_id = int(callback.data.split(":")[1])
    item = await db.get_item(item_id)
    if not item or item["status"] == "hidden":
        await callback.answer("Товар недоступен", show_alert=True)
        return

    booking = None
    if item["status"] == "pending":
        booking = await db.get_pending_booking_for_item(item_id)

    booking_user_id = booking["user_id"] if booking else None
    is_own = (
        booking is not None
        and booking["status"] == "pending"
        and booking_user_id == callback.from_user.id
    )

    await callback.message.delete()
    await callback.message.answer_photo(
        photo=item["photo_file_id"],
        caption=_item_caption(item, booking_user_id, callback.from_user.id),
        reply_markup=item_kb(
            item_id,
            item["status"],
            is_own,
            is_admin,
            item_back_callback(item),
        ),
        parse_mode="HTML",
        protect_content=True,
    )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()
