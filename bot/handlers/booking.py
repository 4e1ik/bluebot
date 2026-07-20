from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.db import Database
from bot.keyboards import catalog_kb, my_bookings_kb

router = Router()


def _booking_instruction(config: Config) -> str:
    return (
        f"Товар забронирован на {config.booking_ttl_hours} часов.\n"
        f"Когда закончите выбор товаров — напишите админу "
        f"@{config.admin_username} для согласования."
    )


@router.callback_query(F.data.startswith("book:"))
async def book_item(callback: CallbackQuery, db: Database, config: Config) -> None:
    item_id = int(callback.data.split(":")[1])
    booking_id = await db.create_booking(
        item_id=item_id,
        user_id=callback.from_user.id,
        username=callback.from_user.username,
        ttl_hours=config.booking_ttl_hours,
    )
    if not booking_id:
        await callback.answer("Товар уже забронирован", show_alert=True)
        return

    await callback.answer("Забронировано!")
    await callback.message.answer(_booking_instruction(config))


@router.message(F.text == "Мои брони")
async def my_bookings(message: Message, db: Database, config: Config) -> None:
    bookings = await db.get_user_pending_bookings(message.from_user.id)
    if not bookings:
        await message.answer("У вас нет активных броней.")
        return

    total = sum(b["price"] for b in bookings)
    lines = ["<b>Мои брони:</b>"]
    for i, b in enumerate(bookings, 1):
        lines.append(f"{i}. {b['name']} — {b['price']:.0f}₽")
    lines.append(f"\n<b>Итого: {total:.0f}₽</b>")
    lines.append(f"\nНапишите админу @{config.admin_username} для согласования.")

    await message.answer(
        "\n".join(lines),
        reply_markup=my_bookings_kb(bookings),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "my_bookings")
async def my_bookings_callback(callback: CallbackQuery, db: Database, config: Config) -> None:
    bookings = await db.get_user_pending_bookings(callback.from_user.id)
    if not bookings:
        await callback.message.edit_text("У вас нет активных броней.")
        await callback.answer()
        return

    total = sum(b["price"] for b in bookings)
    lines = ["<b>Мои брони:</b>"]
    for i, b in enumerate(bookings, 1):
        lines.append(f"{i}. {b['name']} — {b['price']:.0f}₽")
    lines.append(f"\n<b>Итого: {total:.0f}₽</b>")
    lines.append(f"\nНапишите админу @{config.admin_username} для согласования.")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=my_bookings_kb(bookings),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_booking:"))
async def cancel_booking_by_id(callback: CallbackQuery, db: Database) -> None:
    booking_id = int(callback.data.split(":")[1])
    ok = await db.cancel_booking(booking_id, callback.from_user.id)
    if not ok:
        await callback.answer("Не удалось отменить", show_alert=True)
        return

    await callback.answer("Бронь снята")
    bookings = await db.get_user_pending_bookings(callback.from_user.id)
    if not bookings:
        await callback.message.edit_text("Бронь снята. Товар снова доступен.\n\nУ вас нет активных броней.")
        return

    total = sum(b["price"] for b in bookings)
    lines = ["Бронь снята. Товар снова доступен.\n", "<b>Мои брони:</b>"]
    for i, b in enumerate(bookings, 1):
        lines.append(f"{i}. {b['name']} — {b['price']:.0f}₽")
    lines.append(f"\n<b>Итого: {total:.0f}₽</b>")
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=my_bookings_kb(bookings),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("cancel:"))
async def cancel_booking_by_item(callback: CallbackQuery, db: Database) -> None:
    item_id = int(callback.data.split(":")[1])
    booking = await db.get_pending_booking_for_item(item_id)
    if not booking or booking["user_id"] != callback.from_user.id:
        await callback.answer("Бронь не найдена", show_alert=True)
        return

    ok = await db.cancel_booking(booking["id"], callback.from_user.id)
    if not ok:
        await callback.answer("Не удалось отменить", show_alert=True)
        return

    await callback.answer("Бронь снята")
    items = await db.get_catalog_items()
    await callback.message.delete()
    await callback.message.answer(
        "Бронь снята. Товар снова доступен.",
        reply_markup=catalog_kb(items),
    )
