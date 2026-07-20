from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def main_menu_kb(is_admin: bool, is_super: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="Каталог"), KeyboardButton(text="Мои брони")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text="Добавить товар")])
        rows.append(
            [
                KeyboardButton(text="Ожидают подтверждения"),
                KeyboardButton(text="Пользователи"),
            ]
        )
    if is_super:
        rows.append([KeyboardButton(text="Админы")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def whitelist_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить", callback_data="admin:user_add"
                ),
                InlineKeyboardButton(
                    text="➖ Удалить", callback_data="admin:user_remove"
                ),
            ]
        ]
    )


def admins_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить", callback_data="super:admin_add"
                ),
                InlineKeyboardButton(
                    text="➖ Удалить", callback_data="super:admin_remove"
                ),
            ]
        ]
    )


def catalog_kb(items: list) -> InlineKeyboardMarkup:
    buttons = []
    for item in items:
        status_mark = ""
        if item["status"] == "pending":
            status_mark = " 🔒"
        label = f"{item['name']} — {item['price']:.0f} Br{status_mark}"
        buttons.append(
            [InlineKeyboardButton(text=label, callback_data=f"item:{item['id']}")]
        )
    if not buttons:
        buttons.append(
            [InlineKeyboardButton(text="Каталог пуст", callback_data="noop")]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def item_kb(
    item_id: int, status: str, is_own: bool, is_admin: bool = False
) -> InlineKeyboardMarkup:
    rows = []
    if status == "available":
        rows.append(
            [InlineKeyboardButton(text="Забронировать", callback_data=f"book:{item_id}")]
        )
    elif status == "pending" and is_own:
        rows.append(
            [InlineKeyboardButton(text="Отменить бронь", callback_data=f"cancel:{item_id}")]
        )
    if is_admin:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗑 Удалить", callback_data=f"admin:delete_item:{item_id}"
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="← Каталог", callback_data="catalog")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_bookings_kb(bookings: list) -> InlineKeyboardMarkup:
    rows = []
    for b in bookings:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"❌ {b['name']} — {b['price']:.0f} Br",
                    callback_data=f"cancel_booking:{b['id']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="← Каталог", callback_data="catalog")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pending_carts_kb(carts: list) -> InlineKeyboardMarkup:
    rows = []
    for cart in carts:
        username = cart["username"]
        label = (
            f"@{username} — {cart['item_count']} шт., "
            f"{cart['total_price']:.0f} Br"
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=label, callback_data=f"admin:cart:{cart['user_id']}"
                )
            ]
        )
    if not rows:
        rows.append(
            [InlineKeyboardButton(text="Нет ожидающих", callback_data="noop")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_cart_kb(user_id: int, bookings: list) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="✅ Подтвердить всё",
                callback_data=f"admin:confirm_all:{user_id}",
            ),
            InlineKeyboardButton(
                text="❌ Отклонить всё",
                callback_data=f"admin:reject_all:{user_id}",
            ),
        ]
    ]
    for b in bookings:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✅ {b['name']}",
                    callback_data=f"admin:confirm:{b['id']}:{user_id}",
                ),
                InlineKeyboardButton(
                    text=f"❌ {b['name']}",
                    callback_data=f"admin:reject:{b['id']}:{user_id}",
                ),
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="← Назад", callback_data="admin:pending")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
