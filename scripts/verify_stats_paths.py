"""Прогон путей каталога и проверочные заказы для статистики.

Запуск из корня репозитория:
    python scripts/verify_stats_paths.py
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from bot.db import Database
from bot.stats import build_report, format_report

PROBE_CATEGORIES = ("Проверка каталога", "Проверка новое", "Проверка другая")
DEMO_CATEGORIES = ("Яблоки", "Книги", "Чай", "Ткань", "Лампы")
DEMO_SUBS = {"Яблоки": "Сезонные", "Книги": "Детские", "Чай": "Зелёный"}
ORDER_DAYS = (
    0, 1, 3, 6, 10, 14, 21, 30, 45, 60,
    90, 120, 180, 250, 300, 340, 370, 400, 20, 8,
)


async def _drop_probe(db: Database) -> None:
    categories = await db.list_categories()
    probe_ids = [row["id"] for row in categories if row["name"] in PROBE_CATEGORIES]
    if not probe_ids:
        return
    with sqlite3.connect(db.path) as raw:
        for category_id in probe_ids:
            raw.execute(
                "DELETE FROM items WHERE category_id = ? OR subcategory_id IN "
                "(SELECT id FROM subcategories WHERE category_id = ?)",
                (category_id, category_id),
            )
            raw.execute(
                "DELETE FROM subcategories WHERE category_id = ?", (category_id,)
            )
            raw.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        raw.commit()


async def exercise_catalog(db: Database) -> None:
    await _drop_probe(db)
    category_id = await db.create_category("Проверка каталога")
    other_id = await db.create_category("Проверка другая")
    if not await db.rename_category(category_id, "Проверка новое"):
        raise RuntimeError("категория не переименовалась")
    subcategory_id = await db.create_subcategory(category_id, "Проверка под")
    if not await db.rename_subcategory(subcategory_id, "Проверка под 2"):
        raise RuntimeError("подкатегория не переименовалась")
    item_id = await db.create_item(
        "Проверка товар", 11, "photo", category_id=category_id
    )
    if not await db.update_item_name(item_id, "Проверка товар 2"):
        raise RuntimeError("имя товара не изменилось")
    if not await db.update_item_price(item_id, 12):
        raise RuntimeError("цена товара не изменилась")
    if await db.assign_item(item_id, subcategory_id=subcategory_id) != "ok":
        raise RuntimeError("товар не перепривязался")
    if await db.rebind_subcategory(subcategory_id, other_id) != "ok":
        raise RuntimeError("подкатегория не перепривязалась")
    if await db.delete_subcategory(subcategory_id) != "has_items":
        raise RuntimeError("непустая подкатегория удалилась")
    if await db.delete_category(other_id) != "has_subcategories":
        raise RuntimeError("непустая категория удалилась")
    if not await db.delete_item(item_id):
        raise RuntimeError("товар не удалился")
    if await db.delete_subcategory(subcategory_id) != "ok":
        raise RuntimeError("пустая подкатегория не удалилась")
    if await db.delete_category(category_id) != "ok":
        raise RuntimeError("пустая категория не удалилась")
    if await db.delete_category(other_id) != "ok":
        raise RuntimeError("вторая пустая категория не удалилась")


async def seed_demo(db: Database) -> bool:
    names = {row["name"] for row in await db.list_categories()}
    if "Яблоки" in names:
        return False
    category_ids = {}
    for name in DEMO_CATEGORIES:
        category_ids[name] = await db.create_category(name)
    subcategory_ids = {}
    for parent, sub_name in DEMO_SUBS.items():
        subcategory_ids[parent] = await db.create_subcategory(
            category_ids[parent], sub_name
        )
    now = datetime.now(timezone.utc)
    item_ids = []
    for index in range(50):
        category = DEMO_CATEGORIES[index % 5]
        price = 20 + (index % 17) * 15
        if category in subcategory_ids and index % 2 == 0:
            item_id = await db.create_item(
                f"Демо {index + 1:02d}",
                price,
                "demo-photo",
                subcategory_id=subcategory_ids[category],
            )
        else:
            item_id = await db.create_item(
                f"Демо {index + 1:02d}",
                price,
                "demo-photo",
                category_id=category_ids[category],
            )
        item_ids.append(item_id)
    with sqlite3.connect(db.path) as raw:
        for index, item_id in enumerate(item_ids):
            created = (now - timedelta(days=(49 - index) * 7)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            raw.execute(
                "UPDATE items SET created_at = ? WHERE id = ?",
                (created, item_id),
            )
        raw.commit()
    for order_index, offset in enumerate(ORDER_DAYS):
        left = item_ids[order_index * 2]
        right = item_ids[order_index * 2 + 1]
        left_booking = await db.create_booking(left, 880001, "demo", 20)
        right_booking = await db.create_booking(right, 880001, "demo", 20)
        await db.submit_user_cart(880001)
        first_at = now - timedelta(days=offset)
        second_at = first_at + timedelta(days=1) if offset >= 2 else first_at
        if not await db.confirm_booking(left_booking, when=first_at):
            raise RuntimeError("не подтвердилась первая позиция")
        if not await db.confirm_booking(right_booking, when=second_at):
            raise RuntimeError("не подтвердилась вторая позиция")
    return True


def _assert_varied(report, title: str) -> None:
    totals = [window.total for window in report.windows]
    if len(set(totals)) < 2:
        raise RuntimeError(f"{title}: окна не различаются")
    category_totals = [bucket.total for bucket in report.categories_by_sum]
    if len(set(category_totals)) < 2:
        raise RuntimeError(f"{title}: категории не различаются")


async def main() -> None:
    load_dotenv()
    path = os.getenv("DB_PATH", "data/blubot.db")
    db = Database(path)
    await db.connect()
    await exercise_catalog(db)
    created = await seed_demo(db)
    orders = await build_report(db, "orders")
    products = await build_report(db, "products")
    _assert_varied(orders, "заказы")
    _assert_varied(products, "товары")
    print("Пути каталога пройдены.")
    print("Проверочные данные добавлены." if created else "Проверочные данные уже были.")
    print()
    print(format_report(orders))
    print()
    print(format_report(products))


if __name__ == "__main__":
    asyncio.run(main())
