import os
import tempfile
import unittest
from pathlib import Path

import aiosqlite

from bot.catalog_nav import (
    item_back_callback,
    placement_line,
    visible_categories,
    visible_subcategories,
)
from bot.keyboards import catalog_root_kb, category_browse_kb
from bot.db import Database


class PlacementTextTests(unittest.TestCase):
    def test_placement_and_back_target(self) -> None:
        direct = {
            "category_id": 2,
            "category_name": "Фрукты",
            "subcategory_id": None,
            "subcategory_name": None,
            "parent_category_name": None,
        }
        nested = {
            "category_id": None,
            "category_name": None,
            "subcategory_id": 5,
            "subcategory_name": "Красные",
            "parent_category_name": "Фрукты",
        }
        loose = {
            "category_id": None,
            "category_name": None,
            "subcategory_id": None,
            "subcategory_name": None,
            "parent_category_name": None,
        }
        self.assertEqual(placement_line(direct), "Категория: Фрукты")
        self.assertEqual(item_back_callback(direct), "catalog:cat:2")
        self.assertEqual(placement_line(nested), "Категория: Фрукты → Красные")
        self.assertEqual(item_back_callback(nested), "catalog:sub:5")
        self.assertEqual(placement_line(loose), "Без категории")
        self.assertEqual(item_back_callback(loose), "catalog:none")

    def test_catalog_hides_empty_and_marks_new(self) -> None:
        categories = [
            {"id": 1, "name": "Пустая"},
            {"id": 2, "name": "С товаром"},
            {"id": 3, "name": "Только пустые подкатегории"},
            {"id": 4, "name": "С новинкой внутри"},
        ]
        subcategories = [
            {"id": 10, "name": "Пустая подкатегория", "category_id": 4},
            {"id": 11, "name": "С новинкой", "category_id": 4},
            {"id": 12, "name": "Без товаров", "category_id": 3},
        ]
        placements = [
            {
                "category_id": 2,
                "subcategory_id": None,
                "parent_category_id": None,
                "created_at": "2020-01-01 00:00:00",
            },
            {
                "category_id": None,
                "subcategory_id": 11,
                "parent_category_id": 4,
                "created_at": "2099-01-01 00:00:00",
            },
        ]
        visible = visible_categories(categories, placements)
        self.assertEqual([row["name"] for row in visible], ["С товаром", "С новинкой внутри"])
        self.assertFalse(visible[0]["is_new"])
        self.assertTrue(visible[1]["is_new"])
        shown_subs = visible_subcategories(subcategories, placements)
        self.assertEqual([row["name"] for row in shown_subs], ["С новинкой"])
        self.assertTrue(shown_subs[0]["is_new"])

        root = catalog_root_kb(visible, False)
        self.assertEqual(root.inline_keyboard[0][0].text, "С товаром")
        self.assertTrue(root.inline_keyboard[1][0].text.startswith("🆕 "))
        browse = category_browse_kb(shown_subs, [])
        self.assertTrue(browse.inline_keyboard[0][0].text.startswith("🆕 "))


class CategoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        handle.close()
        self.path = handle.name
        self.db = Database(self.path)
        await self.db.connect()

    async def asyncTearDown(self) -> None:
        os.unlink(self.path)

    async def test_blank_category_name_is_rejected_and_list_is_sorted(self) -> None:
        self.assertIsNone(await self.db.create_category("   "))
        second = await self.db.create_category("Яблоки")
        first = await self.db.create_category("бананы")
        names = [row["name"] for row in await self.db.list_categories()]
        self.assertEqual(names, ["бананы", "Яблоки"])
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)

    async def test_subcategory_requires_category_and_moves_with_its_items(self) -> None:
        apples = await self.db.create_category("Яблоки")
        pears = await self.db.create_category("Груши")
        self.assertIsNone(await self.db.create_subcategory(999, "Сезонные"))
        seasonal = await self.db.create_subcategory(apples, "Сезонные")
        item_id = await self.db.create_item(
            "Голден", 12, "photo", subcategory_id=seasonal
        )
        self.assertEqual(
            await self.db.rebind_subcategory(seasonal, apples), "same"
        )
        self.assertEqual(await self.db.rebind_subcategory(seasonal, pears), "ok")
        self.assertEqual(
            await self.db.rebind_subcategory(seasonal, 999), "bad_parent"
        )
        item = await self.db.get_item(item_id)
        self.assertEqual(item["subcategory_id"], seasonal)
        self.assertIsNone(item["category_id"])
        self.assertEqual(item["parent_category_name"], "Груши")
        self.assertEqual(item["subcategory_name"], "Сезонные")

    async def test_rename_keeps_parent(self) -> None:
        fruit = await self.db.create_category("Фрукты")
        sub_id = await self.db.create_subcategory(fruit, "Красные")
        self.assertFalse(await self.db.rename_category(fruit, "  "))
        self.assertTrue(await self.db.rename_category(fruit, "Овощи"))
        self.assertTrue(await self.db.rename_subcategory(sub_id, "Зелёные"))
        sub = await self.db.get_subcategory(sub_id)
        self.assertEqual(sub["name"], "Зелёные")
        self.assertEqual(sub["category_id"], fruit)
        self.assertEqual((await self.db.get_category(fruit))["name"], "Овощи")

    async def test_item_has_one_placement_and_keeps_created_at(self) -> None:
        fruit = await self.db.create_category("Фрукты")
        other = await self.db.create_category("Овощи")
        red = await self.db.create_subcategory(fruit, "Красные")
        green = await self.db.create_subcategory(other, "Зелёные")
        self.assertIsNone(
            await self.db.create_item("Без цели", 1, "photo")
        )
        self.assertIsNone(
            await self.db.create_item(
                "Две цели", 1, "photo", category_id=fruit, subcategory_id=red
            )
        )
        item_id = await self.db.create_item(
            "Голден", 10, "photo", category_id=fruit
        )
        created = (await self.db.get_item(item_id))["created_at"]
        self.assertEqual(
            await self.db.assign_item(item_id, category_id=fruit), "same"
        )
        self.assertEqual(await self.db.assign_item(item_id, category_id=other), "ok")
        self.assertEqual(
            await self.db.assign_item(item_id, subcategory_id=green), "ok"
        )
        await self.db.update_item_name(item_id, "Голден 2")
        await self.db.update_item_price(item_id, 15)
        item = await self.db.get_item(item_id)
        self.assertEqual(item["created_at"], created)
        self.assertEqual(item["name"], "Голден 2")
        self.assertEqual(item["price"], 15)
        self.assertIsNone(item["category_id"])
        self.assertEqual(item["subcategory_id"], green)
        self.assertEqual(item["parent_category_name"], "Овощи")

    async def test_old_item_stays_uncategorized(self) -> None:
        legacy = Path(self.path + ".legacy")
        async with aiosqlite.connect(legacy) as raw:
            await raw.execute(
                """
                CREATE TABLE items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    photo_file_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'available',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            await raw.execute(
                "INSERT INTO items (name, price, photo_file_id) VALUES (?, ?, ?)",
                ("Старый", 5, "photo"),
            )
            await raw.commit()
        database = Database(str(legacy))
        await database.connect()
        rows = await database.list_uncategorized_items()
        self.assertEqual([row["name"] for row in rows], ["Старый"])
        item = await database.get_item(rows[0]["id"])
        self.assertIsNone(item["category_id"])
        self.assertIsNone(item["subcategory_id"])
        self.assertEqual(await database.count_visible_uncategorized(), 1)
        os.unlink(legacy)


if __name__ == "__main__":
    unittest.main()
