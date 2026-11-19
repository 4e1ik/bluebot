from __future__ import annotations

from html import escape

from aiogram.types import InlineKeyboardMarkup

from bot.db import Database, is_new_item
from bot.keyboards import (
    catalog_root_kb,
    category_browse_kb,
    subcategory_browse_kb,
    uncategorized_browse_kb,
)


def placement_line(item) -> str:
    if item["subcategory_id"]:
        parent = escape(item["parent_category_name"] or "")
        sub = escape(item["subcategory_name"] or "")
        return f"Категория: {parent} → {sub}"
    if item["category_id"]:
        return f"Категория: {escape(item['category_name'] or '')}"
    return "Без категории"


def item_back_callback(item) -> str:
    if item["subcategory_id"]:
        return f"catalog:sub:{item['subcategory_id']}"
    if item["category_id"]:
        return f"catalog:cat:{item['category_id']}"
    return "catalog:none"


def visible_categories(categories: list, placements: list) -> list[dict]:
    direct_any: set[int] = set()
    direct_new: set[int] = set()
    parent_any: set[int] = set()
    parent_new: set[int] = set()
    for row in placements:
        is_new = is_new_item(row["created_at"])
        if row["subcategory_id"]:
            parent = row["parent_category_id"]
            if parent is None:
                continue
            parent_any.add(parent)
            if is_new:
                parent_new.add(parent)
        elif row["category_id"]:
            category_id = row["category_id"]
            direct_any.add(category_id)
            if is_new:
                direct_new.add(category_id)
    visible = []
    for category in categories:
        category_id = category["id"]
        if category_id not in direct_any and category_id not in parent_any:
            continue
        visible.append(
            {
                "id": category_id,
                "name": category["name"],
                "is_new": category_id in direct_new or category_id in parent_new,
            }
        )
    return visible


def visible_subcategories(subcategories: list, placements: list) -> list[dict]:
    is_new_by_id: dict[int, bool] = {}
    for row in placements:
        subcategory_id = row["subcategory_id"]
        if not subcategory_id:
            continue
        is_new_by_id[subcategory_id] = is_new_by_id.get(
            subcategory_id, False
        ) or is_new_item(row["created_at"])
    return [
        {
            "id": sub["id"],
            "name": sub["name"],
            "is_new": is_new_by_id[sub["id"]],
        }
        for sub in subcategories
        if sub["id"] in is_new_by_id
    ]


async def root_screen(db: Database) -> tuple[str, InlineKeyboardMarkup]:
    categories = visible_categories(
        await db.list_categories(), await db.list_visible_placements()
    )
    loose = await db.count_visible_uncategorized()
    if not categories and loose == 0:
        text = "Каталог пуст."
    else:
        text = "Каталог:"
    return text, catalog_root_kb(categories, loose > 0)


async def category_screen(
    db: Database, category_id: int, show_listing_date: bool = False
) -> tuple[str, InlineKeyboardMarkup] | None:
    category = await db.get_category(category_id)
    if category is None:
        return None
    placements = await db.list_visible_placements()
    subs = visible_subcategories(
        await db.list_subcategories(category_id), placements
    )
    items = await db.list_direct_items(category_id)
    title = f"<b>{escape(category['name'])}</b>"
    if not subs and not items:
        title = f"{title}\nВ этой категории пока пусто."
    return title, category_browse_kb(
        subs, items, show_listing_date=show_listing_date
    )


async def subcategory_screen(
    db: Database, subcategory_id: int, show_listing_date: bool = False
) -> tuple[str, InlineKeyboardMarkup] | None:
    sub = await db.get_subcategory(subcategory_id)
    if sub is None:
        return None
    parent = await db.get_category(sub["category_id"])
    parent_name = parent["name"] if parent else ""
    items = await db.list_subcategory_items(subcategory_id)
    title = f"<b>{escape(parent_name)} → {escape(sub['name'])}</b>"
    if not items:
        title = f"{title}\nВ этой подкатегории пока пусто."
    return title, subcategory_browse_kb(
        sub["category_id"], items, show_listing_date=show_listing_date
    )


async def uncategorized_screen(
    db: Database, show_listing_date: bool = False
) -> tuple[str, InlineKeyboardMarkup]:
    items = await db.list_uncategorized_items()
    text = "<b>Без категории</b>"
    if not items:
        text = f"{text}\nТоваров без категории нет."
    return text, uncategorized_browse_kb(items, show_listing_date=show_listing_date)
