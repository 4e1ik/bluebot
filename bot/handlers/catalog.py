from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.db import Database
from bot.keyboards import catalog_kb, item_kb

router = Router()


def _item_caption(item, booking_user_id: int | None, current_user_id: int) -> str:
    lines = [f"<b>{item['name']}</b>", f"Цена: {item['price']:.0f}₽"]
    if item["status"] == "pending":
        if booking_user_id == current_user_id:
            lines.append("\n🔒 Забронировано вами")
        else:
            lines.append("\n🔒 Забронирован")
    return "\n".join(lines)


@router.message(F.text == "Каталог")
async def show_catalog(message: Message, db: Database) -> None:
    items = await db.get_catalog_items()
    await message.answer(
        "Каталог:",
        reply_markup=catalog_kb(items),
    )


@router.callback_query(F.data == "catalog")
async def catalog_callback(callback: CallbackQuery, db: Database) -> None:
    items = await db.get_catalog_items()
    await callback.message.edit_text("Каталог:", reply_markup=catalog_kb(items))
    await callback.answer()


@router.callback_query(F.data.startswith("item:"))
async def show_item(callback: CallbackQuery, db: Database) -> None:
    item_id = int(callback.data.split(":")[1])
    item = await db.get_item(item_id)
    if not item or item["status"] == "hidden":
        await callback.answer("Товар недоступен", show_alert=True)
        return

    booking = None
    if item["status"] == "pending":
        booking = await db.get_pending_booking_for_item(item_id)

    booking_user_id = booking["user_id"] if booking else None
    is_own = booking_user_id == callback.from_user.id

    await callback.message.delete()
    await callback.message.answer_photo(
        photo=item["photo_file_id"],
        caption=_item_caption(item, booking_user_id, callback.from_user.id),
        reply_markup=item_kb(item_id, item["status"], is_own),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()
