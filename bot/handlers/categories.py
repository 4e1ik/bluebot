from __future__ import annotations

from html import escape

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.db import Database
from bot.filters import admin_router
from bot.keyboards import (
    categories_menu_kb,
    category_manage_kb,
    main_menu_kb,
    pick_rows,
    subcategory_manage_kb,
    cancel_kb,
)


class CategoryEdit(StatesGroup):
    category_name = State()
    subcategory_name = State()
    rename_category = State()
    rename_subcategory = State()


async def _categories_view(db: Database) -> tuple[str, object]:
    categories = await db.list_categories()
    lines = ["<b>Категории:</b>"]
    if categories:
        lines.extend(f"• {escape(category['name'])}" for category in categories)
    else:
        lines.append("Пока нет.")
    return "\n".join(lines), categories_menu_kb(categories)


async def _category_view(db: Database, category_id: int):
    category = await db.get_category(category_id)
    if category is None:
        return None
    subs = await db.list_subcategories(category_id)
    lines = [f"<b>{escape(category['name'])}</b>"]
    if subs:
        lines.extend(f"• {escape(sub['name'])}" for sub in subs)
    else:
        lines.append("Подкатегорий нет.")
    return "\n".join(lines), category_manage_kb(category_id, subs)


@admin_router.message(F.text == "Категории")
async def categories_menu(message: Message, db: Database, state: FSMContext) -> None:
    await state.clear()
    text, markup = await _categories_view(db)
    await message.answer(text, reply_markup=markup, protect_content=True)


@admin_router.callback_query(F.data == "admin:cats")
async def categories_callback(
    callback: CallbackQuery, db: Database, state: FSMContext
) -> None:
    await state.clear()
    text, markup = await _categories_view(db)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@admin_router.callback_query(F.data == "admin:cat:new")
async def category_new(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CategoryEdit.category_name)
    await callback.answer()
    await callback.message.answer(
        "Введите название категории (или «Отмена»):",
        reply_markup=cancel_kb(),
        protect_content=True,
    )


@admin_router.message(CategoryEdit.category_name, F.text, F.text != "Отмена")
async def category_name_save(
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
    created = await db.create_category(name)
    await state.clear()
    if created is None:
        await message.answer(
            "Не удалось создать категорию.",
            reply_markup=main_menu_kb(is_admin, is_super),
            protect_content=True,
        )
        return
    await message.answer(
        f"Категория «{escape(name)}» создана.",
        reply_markup=main_menu_kb(is_admin, is_super),
        protect_content=True,
    )
    text, markup = await _categories_view(db)
    await message.answer(text, reply_markup=markup, protect_content=True)


@admin_router.callback_query(F.data == "admin:sub:new")
async def subcategory_new(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    categories = await db.list_categories()
    if not categories:
        await callback.answer("Сначала создайте категорию", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(
        "Выберите категорию для подкатегории:",
        reply_markup=pick_rows(categories, "admin:sub:parent", "admin:cats"),
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:sub:parent:"))
async def subcategory_parent(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    category_id = int(callback.data.split(":")[3])
    if await db.get_category(category_id) is None:
        await callback.answer("Категория не найдена", show_alert=True)
        return
    await state.set_state(CategoryEdit.subcategory_name)
    await state.update_data(category_id=category_id)
    await callback.answer()
    await callback.message.answer(
        "Введите название подкатегории (или «Отмена»):",
        reply_markup=cancel_kb(),
        protect_content=True,
    )


@admin_router.message(CategoryEdit.subcategory_name, F.text, F.text != "Отмена")
async def subcategory_name_save(
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
    category_id = data.get("category_id")
    created = await db.create_subcategory(category_id, name)
    await state.clear()
    if created is None:
        await message.answer(
            "Сначала создайте категорию.",
            reply_markup=main_menu_kb(is_admin, is_super),
            protect_content=True,
        )
        return
    await message.answer(
        f"Подкатегория «{escape(name)}» создана.",
        reply_markup=main_menu_kb(is_admin, is_super),
        protect_content=True,
    )
    view = await _category_view(db, category_id)
    if view:
        await message.answer(view[0], reply_markup=view[1], protect_content=True)


@admin_router.callback_query(F.data.startswith("admin:cat:open:"))
async def category_open(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.clear()
    category_id = int(callback.data.split(":")[3])
    view = await _category_view(db, category_id)
    if view is None:
        await callback.answer("Категория не найдена", show_alert=True)
        return
    await callback.message.edit_text(view[0], reply_markup=view[1])
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:cat:rename:"))
async def category_rename_start(callback: CallbackQuery, state: FSMContext) -> None:
    category_id = int(callback.data.split(":")[3])
    await state.set_state(CategoryEdit.rename_category)
    await state.update_data(category_id=category_id)
    await callback.answer()
    await callback.message.answer(
        "Введите новое название категории (или «Отмена»):",
        reply_markup=cancel_kb(),
        protect_content=True,
    )


@admin_router.message(CategoryEdit.rename_category, F.text, F.text != "Отмена")
async def category_rename_save(
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
    category_id = data.get("category_id")
    ok = await db.rename_category(category_id, name)
    await state.clear()
    text = "Название обновлено." if ok else "Категория не найдена."
    await message.answer(
        text,
        reply_markup=main_menu_kb(is_admin, is_super),
        protect_content=True,
    )
    view = await _category_view(db, category_id) if ok else None
    if view:
        await message.answer(view[0], reply_markup=view[1], protect_content=True)


@admin_router.callback_query(F.data.startswith("admin:sub:open:"))
async def subcategory_open(
    callback: CallbackQuery, db: Database, state: FSMContext
) -> None:
    await state.clear()
    subcategory_id = int(callback.data.split(":")[3])
    sub = await db.get_subcategory(subcategory_id)
    if sub is None:
        await callback.answer("Подкатегория не найдена", show_alert=True)
        return
    parent = await db.get_category(sub["category_id"])
    parent_name = parent["name"] if parent else ""
    text = (
        f"<b>{escape(parent_name)} → {escape(sub['name'])}</b>\n"
        "Можно сменить название или категорию."
    )
    await callback.message.edit_text(
        text,
        reply_markup=subcategory_manage_kb(subcategory_id, sub["category_id"]),
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:sub:rename:"))
async def subcategory_rename_start(callback: CallbackQuery, state: FSMContext) -> None:
    subcategory_id = int(callback.data.split(":")[3])
    await state.set_state(CategoryEdit.rename_subcategory)
    await state.update_data(subcategory_id=subcategory_id)
    await callback.answer()
    await callback.message.answer(
        "Введите новое название подкатегории (или «Отмена»):",
        reply_markup=cancel_kb(),
        protect_content=True,
    )


@admin_router.message(CategoryEdit.rename_subcategory, F.text, F.text != "Отмена")
async def subcategory_rename_save(
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
    subcategory_id = data.get("subcategory_id")
    ok = await db.rename_subcategory(subcategory_id, name)
    await state.clear()
    await message.answer(
        "Название обновлено." if ok else "Подкатегория не найдена.",
        reply_markup=main_menu_kb(is_admin, is_super),
        protect_content=True,
    )


@admin_router.callback_query(F.data.startswith("admin:sub:rebind:"))
async def subcategory_rebind_start(callback: CallbackQuery, db: Database) -> None:
    subcategory_id = int(callback.data.split(":")[3])
    sub = await db.get_subcategory(subcategory_id)
    if sub is None:
        await callback.answer("Подкатегория не найдена", show_alert=True)
        return
    categories = await db.list_categories()
    await callback.message.edit_text(
        "Выберите новую категорию:",
        reply_markup=pick_rows(
            categories,
            f"admin:sub:move:{subcategory_id}",
            f"admin:sub:open:{subcategory_id}",
        ),
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin:sub:move:"))
async def subcategory_rebind_save(callback: CallbackQuery, db: Database) -> None:
    _, _, _, subcategory_id, category_id = callback.data.split(":")
    result = await db.rebind_subcategory(int(subcategory_id), int(category_id))
    if result == "same":
        await callback.answer("Уже относится к этой категории", show_alert=True)
        return
    if result != "ok":
        await callback.answer("Не удалось перепривязать", show_alert=True)
        return
    sub = await db.get_subcategory(int(subcategory_id))
    parent = await db.get_category(sub["category_id"]) if sub else None
    parent_name = parent["name"] if parent else ""
    text = (
        f"<b>{escape(parent_name)} → {escape(sub['name'])}</b>\n"
        "Подкатегория перепривязана."
    )
    await callback.message.edit_text(
        text,
        reply_markup=subcategory_manage_kb(int(subcategory_id), sub["category_id"]),
    )
    await callback.answer("Перепривязано")


_DELETE_REASONS = {
    "has_items": "Нельзя удалить: внутри есть товары.",
    "has_subcategories": "Нельзя удалить: внутри есть подкатегории.",
    "has_both": "Нельзя удалить: внутри есть подкатегории и товары.",
}


@admin_router.callback_query(F.data.startswith("admin:cat:delete:"))
async def category_delete(callback: CallbackQuery, db: Database) -> None:
    category_id = int(callback.data.split(":")[3])
    result = await db.delete_category(category_id)
    if result == "missing":
        await callback.answer("Категория не найдена", show_alert=True)
        return
    if result != "ok":
        await callback.answer(_DELETE_REASONS[result], show_alert=True)
        return
    text, markup = await _categories_view(db)
    await callback.message.edit_text(
        f"Категория удалена.\n\n{text}",
        reply_markup=markup,
    )
    await callback.answer("Категория удалена")


@admin_router.callback_query(F.data.startswith("admin:sub:delete:"))
async def subcategory_delete(callback: CallbackQuery, db: Database) -> None:
    subcategory_id = int(callback.data.split(":")[3])
    sub = await db.get_subcategory(subcategory_id)
    parent_id = sub["category_id"] if sub else None
    result = await db.delete_subcategory(subcategory_id)
    if result == "missing":
        await callback.answer("Подкатегория не найдена", show_alert=True)
        return
    if result != "ok":
        await callback.answer(_DELETE_REASONS[result], show_alert=True)
        return
    view = await _category_view(db, parent_id) if parent_id is not None else None
    if view is None:
        text, markup = await _categories_view(db)
        await callback.message.edit_text(
            f"Подкатегория удалена.\n\n{text}",
            reply_markup=markup,
        )
    else:
        await callback.message.edit_text(
            f"Подкатегория удалена.\n\n{view[0]}",
            reply_markup=view[1],
        )
    await callback.answer("Подкатегория удалена")
