from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.db import Database
from bot.keyboards import catalog_kb, my_bookings_kb
from bot.notify import notify_admins

router = Router()


def _cart_hint(config: Config) -> str:
    return (
        f"У вас {config.cart_ttl_minutes} минут на корзину.\n"
        "Когда закончите — откройте «Мои брони» и нажмите «Оформить заказ»."
    )


def _format_my_bookings(bookings: list, config: Config, prefix: str = "") -> str:
    total = sum(b["price"] for b in bookings)
    lines = []
    if prefix:
        lines.append(prefix)
    lines.append("<b>Мои брони:</b>")
    for i, b in enumerate(bookings, 1):
        lines.append(f"{i}. {b['name']} — {b['price']:.0f} Br")
    lines.append(f"\n<b>Итого: {total:.0f} Br</b>")
    lines.append(f"\nУ вас {config.cart_ttl_minutes} минут на оформление заказа.")
    return "\n".join(lines)


@router.callback_query(F.data.startswith("book:"))
async def book_item(callback: CallbackQuery, db: Database, config: Config) -> None:
    item_id = int(callback.data.split(":")[1])
    booking_id = await db.create_booking(
        item_id=item_id,
        user_id=callback.from_user.id,
        username=callback.from_user.username,
        ttl_minutes=config.cart_ttl_minutes,
    )
    if not booking_id:
        await callback.answer("Товар уже забронирован", show_alert=True)
        return

    await callback.answer("Забронировано!")
    await callback.message.answer(
        f"Товар забронирован.\n{_cart_hint(config)}",
        protect_content=True,
    )


@router.message(F.text == "Мои брони")
async def my_bookings(message: Message, db: Database, config: Config) -> None:
    bookings = await db.get_user_pending_bookings(message.from_user.id)
    if not bookings:
        await message.answer(
            "У вас нет активных броней.",
            protect_content=True,
        )
        return

    await message.answer(
        _format_my_bookings(bookings, config),
        reply_markup=my_bookings_kb(bookings),
        parse_mode="HTML",
        protect_content=True,
    )


@router.callback_query(F.data == "my_bookings")
async def my_bookings_callback(
    callback: CallbackQuery, db: Database, config: Config
) -> None:
    bookings = await db.get_user_pending_bookings(callback.from_user.id)
    if not bookings:
        await callback.message.edit_text("У вас нет активных броней.")
        await callback.answer()
        return

    await callback.message.edit_text(
        _format_my_bookings(bookings, config),
        reply_markup=my_bookings_kb(bookings),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "cart:submit")
async def submit_cart(
    callback: CallbackQuery, db: Database, config: Config, bot: Bot
) -> None:
    bookings = await db.submit_user_cart(callback.from_user.id)
    if not bookings:
        await callback.answer("Корзина пуста", show_alert=True)
        return

    username = callback.from_user.username or "unknown"
    total = sum(b["price"] for b in bookings)
    lines = [
        f"<b>Новый заказ от @{username}</b>",
        f"user_id: {callback.from_user.id}",
    ]
    for i, b in enumerate(bookings, 1):
        lines.append(f"{i}. {b['name']} — {b['price']:.0f} Br")
    lines.append(f"\n<b>Итого: {total:.0f} Br</b>")

    await notify_admins(bot, db, "\n".join(lines))
    await callback.answer("Заказ оформлен")
    await callback.message.edit_text(
        "Заказ оформлен. Ожидайте, скоро с вами свяжутся."
    )


@router.callback_query(F.data == "cart:clear")
async def clear_cart(callback: CallbackQuery, db: Database) -> None:
    count = await db.clear_user_cart(callback.from_user.id)
    if not count:
        await callback.answer("Корзина пуста", show_alert=True)
        return
    await callback.answer("Корзина очищена")
    await callback.message.edit_text("Корзина очищена. Товары снова доступны.")


@router.callback_query(F.data.startswith("cancel_booking:"))
async def cancel_booking_by_id(
    callback: CallbackQuery, db: Database, config: Config
) -> None:
    booking_id = int(callback.data.split(":")[1])
    ok = await db.cancel_booking(booking_id, callback.from_user.id)
    if not ok:
        await callback.answer("Не удалось отменить", show_alert=True)
        return

    await callback.answer("Бронь снята")
    bookings = await db.get_user_pending_bookings(callback.from_user.id)
    if not bookings:
        await callback.message.edit_text(
            "Бронь снята. Товар снова доступен.\n\nУ вас нет активных броней."
        )
        return

    await callback.message.edit_text(
        _format_my_bookings(
            bookings, config, prefix="Бронь снята. Товар снова доступен.\n"
        ),
        reply_markup=my_bookings_kb(bookings),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("cancel:"))
async def cancel_booking_by_item(callback: CallbackQuery, db: Database) -> None:
    item_id = int(callback.data.split(":")[1])
    booking = await db.get_pending_booking_for_item(item_id)
    if (
        not booking
        or booking["status"] != "pending"
        or booking["user_id"] != callback.from_user.id
    ):
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
        protect_content=True,
    )
