from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bot.db import is_new_item

BUTTON_LABEL_MAX = 56


def _truncate(text: str, max_len: int = BUTTON_LABEL_MAX) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def main_menu_kb(is_admin: bool, is_super: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="Каталог"), KeyboardButton(text="Мои брони")],
        [KeyboardButton(text="Помощь")],
    ]
    if is_admin:
        rows.append(
            [
                KeyboardButton(text="Добавить товар"),
                KeyboardButton(text="Категории"),
            ]
        )
        rows.append(
            [
                KeyboardButton(text="Ожидают подтверждения"),
                KeyboardButton(text="Пользователи"),
            ]
        )
        rows.append([KeyboardButton(text="Уведомить о новинках")])
    if is_super:
        rows.append([KeyboardButton(text="Админы")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
    )


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


def _item_button(item) -> InlineKeyboardButton:
    status_mark = " 🔒" if item["status"] == "pending" else ""
    new_mark = "🆕 " if is_new_item(item["created_at"]) else ""
    label = _truncate(
        f"{new_mark}{item['name']} — {item['price']:.0f} Br{status_mark}"
    )
    return InlineKeyboardButton(text=label, callback_data=f"item:{item['id']}")


def _new_prefix(record) -> str:
    try:
        is_new = record["is_new"]
    except (KeyError, IndexError, TypeError):
        return ""
    return "🆕 " if is_new else ""


def catalog_root_kb(categories: list, show_uncategorized: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=_truncate(f"{_new_prefix(category)}{category['name']}"),
                callback_data=f"catalog:cat:{category['id']}",
            )
        ]
        for category in categories
    ]
    if show_uncategorized:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Без категории", callback_data="catalog:none"
                )
            ]
        )
    if not rows:
        rows.append([InlineKeyboardButton(text="Каталог пуст", callback_data="noop")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_browse_kb(subcategories: list, items: list) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=_truncate(f"{_new_prefix(sub)}{sub['name']}"),
                callback_data=f"catalog:sub:{sub['id']}",
            )
        ]
        for sub in subcategories
    ]
    rows.extend([_item_button(item)] for item in items)
    rows.append([InlineKeyboardButton(text="← Каталог", callback_data="catalog")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subcategory_browse_kb(
    parent_category_id: int, items: list
) -> InlineKeyboardMarkup:
    rows = [[_item_button(item)] for item in items]
    rows.append(
        [
            InlineKeyboardButton(
                text="← Назад",
                callback_data=f"catalog:cat:{parent_category_id}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def uncategorized_browse_kb(items: list) -> InlineKeyboardMarkup:
    rows = [[_item_button(item)] for item in items]
    rows.append([InlineKeyboardButton(text="← Каталог", callback_data="catalog")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def categories_menu_kb(categories: list) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=_truncate(category["name"]),
                callback_data=f"admin:cat:open:{category['id']}",
            )
        ]
        for category in categories
    ]
    rows.append(
        [
            InlineKeyboardButton(text="➕ Категория", callback_data="admin:cat:new"),
            InlineKeyboardButton(
                text="➕ Подкатегория", callback_data="admin:sub:new"
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_manage_kb(category_id: int, subcategories: list) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="✏️ Название",
                callback_data=f"admin:cat:rename:{category_id}",
            )
        ]
    ]
    rows.extend(
        [
            InlineKeyboardButton(
                text=_truncate(sub["name"]),
                callback_data=f"admin:sub:open:{sub['id']}",
            )
        ]
        for sub in subcategories
    )
    rows.append([InlineKeyboardButton(text="← Категории", callback_data="admin:cats")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subcategory_manage_kb(
    subcategory_id: int, parent_category_id: int
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Название",
                    callback_data=f"admin:sub:rename:{subcategory_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔗 Перепривязать",
                    callback_data=f"admin:sub:rebind:{subcategory_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="← Назад",
                    callback_data=f"admin:cat:open:{parent_category_id}",
                )
            ],
        ]
    )


def pick_rows(records: list, callback_prefix: str, back: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=_truncate(record["name"]),
                callback_data=f"{callback_prefix}:{record['id']}",
            )
        ]
        for record in records
    ]
    rows.append([InlineKeyboardButton(text="← Назад", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def add_place_kind_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="К категории", callback_data="admin:add:kind:cat"
                )
            ],
            [
                InlineKeyboardButton(
                    text="К подкатегории", callback_data="admin:add:kind:sub"
                )
            ],
        ]
    )


def place_kind_kb(item_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="К категории",
                    callback_data=f"admin:place:cat:{item_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="К подкатегории",
                    callback_data=f"admin:place:sub:{item_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="← Назад", callback_data=f"admin:edit:{item_id}"
                )
            ],
        ]
    )


def item_kb(
    item_id: int,
    status: str,
    is_own: bool,
    is_admin: bool = False,
    back_callback: str = "catalog",
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
                    text="✏️ Изменить", callback_data=f"admin:edit:{item_id}"
                ),
                InlineKeyboardButton(
                    text="🗑 Удалить", callback_data=f"admin:delete_item:{item_id}"
                ),
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="← Назад", callback_data=back_callback)]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def edit_item_kb(item_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🖼 Фото", callback_data=f"admin:edit_photo:{item_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📝 Название", callback_data=f"admin:edit_name:{item_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💰 Цена", callback_data=f"admin:edit_price:{item_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📂 Привязка", callback_data=f"admin:edit_place:{item_id}"
                )
            ],
            [InlineKeyboardButton(text="← Назад", callback_data=f"item:{item_id}")],
        ]
    )


def my_bookings_kb(bookings: list) -> InlineKeyboardMarkup:
    rows = []
    for b in bookings:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_truncate(f"❌ {b['name']} — {b['price']:.0f} Br"),
                    callback_data=f"cancel_booking:{b['id']}",
                )
            ]
        )
    if bookings:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Оформить заказ", callback_data="cart:submit"
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗑 Очистить корзину", callback_data="cart:clear"
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="← Каталог", callback_data="catalog")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pending_carts_kb(carts: list) -> InlineKeyboardMarkup:
    rows = []
    for cart in carts:
        username = cart["username"]
        label = _truncate(
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
        name = _truncate(b["name"], 20)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✅ {name}",
                    callback_data=f"admin:confirm:{b['id']}:{user_id}",
                ),
                InlineKeyboardButton(
                    text=f"❌ {name}",
                    callback_data=f"admin:reject:{b['id']}:{user_id}",
                ),
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="← Назад", callback_data="admin:pending")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
