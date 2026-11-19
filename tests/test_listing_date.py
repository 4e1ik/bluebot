import os
import tempfile
import unittest

import aiosqlite

from bot.config import Config
from bot.db import Database, listing_day
from bot.handlers.catalog import _item_caption
from bot.keyboards import (
    category_browse_kb,
    my_bookings_kb,
    subcategory_browse_kb,
    uncategorized_browse_kb,
)
from bot.middlewares.access import AccessMiddleware


LATE_UTC = "2026-11-18 21:00:00"
MINSK_DAY = "19.11.2026"
OLD_UTC = "2020-11-18 21:00:00"
OLD_DAY = "19.11.2020"


def _item(**overrides):
    item = {
        "id": 7,
        "name": "Яблоко",
        "price": 10,
        "status": "available",
        "created_at": OLD_UTC,
        "category_id": 2,
        "category_name": "Фрукты",
        "subcategory_id": None,
        "subcategory_name": None,
        "parent_category_name": None,
    }
    item.update(overrides)
    return item


class ListingDayTests(unittest.TestCase):
    def test_minsk_day_crosses_utc_midnight(self) -> None:
        self.assertEqual(listing_day(LATE_UTC), MINSK_DAY)
        self.assertEqual(listing_day("2026-11-18 20:59:59"), "18.11.2026")

    def test_unreadable_moment_has_no_invented_day(self) -> None:
        self.assertIsNone(listing_day(None))
        self.assertIsNone(listing_day(""))
        self.assertIsNone(listing_day("not-a-date"))


class ListingCaptionTests(unittest.TestCase):
    def test_admin_card_has_date_line_after_placement(self) -> None:
        caption = _item_caption(_item(), None, 1, show_listing_date=True)
        lines = caption.split("\n")
        self.assertEqual(lines[0], "<b>Яблоко</b>")
        self.assertEqual(lines[1], "Цена: 10 Br")
        self.assertEqual(lines[2], "Категория: Фрукты")
        self.assertEqual(lines[3], OLD_DAY)

    def test_whitelist_card_has_no_date(self) -> None:
        caption = _item_caption(_item(), None, 1, show_listing_date=False)
        self.assertNotIn(OLD_DAY, caption)
        self.assertIn("Цена: 10 Br", caption)
        self.assertIn("Категория: Фрукты", caption)

    def test_new_mark_and_booking_stay(self) -> None:
        fresh = _item(created_at="2099-01-01 00:00:00", status="pending")
        caption = _item_caption(fresh, 5, 5, show_listing_date=True)
        self.assertTrue(caption.startswith("<b>🆕 Яблоко</b>"))
        self.assertIn("01.01.2099", caption)
        self.assertIn("🔒 Забронировано вами", caption)


class ListingButtonTests(unittest.TestCase):
    def test_admin_catalog_buttons_start_with_the_day(self) -> None:
        item = _item(status="pending")
        expected = f"{OLD_DAY} Яблоко — 10 Br 🔒"
        category = category_browse_kb([], [item], show_listing_date=True)
        subcategory = subcategory_browse_kb(2, [item], show_listing_date=True)
        loose = uncategorized_browse_kb([item], show_listing_date=True)
        self.assertEqual(category.inline_keyboard[0][0].text, expected)
        self.assertEqual(subcategory.inline_keyboard[0][0].text, expected)
        self.assertEqual(loose.inline_keyboard[0][0].text, expected)

    def test_date_precedes_new_mark(self) -> None:
        item = _item(created_at="2099-01-01 00:00:00")
        text = category_browse_kb([], [item], show_listing_date=True).inline_keyboard[0][0].text
        self.assertTrue(text.startswith("01.01.2099 🆕 Яблоко"))

    def test_whitelist_button_keeps_the_old_label(self) -> None:
        item = _item()
        button = category_browse_kb([], [item], show_listing_date=False)
        self.assertEqual(button.inline_keyboard[0][0].text, "Яблоко — 10 Br")

    def test_long_label_keeps_the_day_and_cuts_the_tail(self) -> None:
        item = _item(name="Я" * 80)
        text = category_browse_kb([], [item], show_listing_date=True).inline_keyboard[0][0].text
        self.assertTrue(text.startswith(f"{OLD_DAY} "))
        self.assertTrue(text.endswith("…"))
        self.assertLessEqual(len(text), 56)

    def test_cart_button_has_no_listing_date(self) -> None:
        cart = my_bookings_kb([{"id": 3, "name": "Яблоко", "price": 10}])
        self.assertEqual(cart.inline_keyboard[0][0].text, "❌ Яблоко — 10 Br")


class ListingStoredMomentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        handle.close()
        self.path = handle.name
        self.db = Database(self.path)
        await self.db.connect()

    async def asyncTearDown(self) -> None:
        os.unlink(self.path)

    async def test_edits_keep_created_at(self) -> None:
        category_id = await self.db.create_category("Фрукты")
        other_id = await self.db.create_category("Овощи")
        item_id = await self.db.create_item(
            "Яблоко", 10, "photo", category_id=category_id
        )
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE items SET created_at = ? WHERE id = ?",
                (LATE_UTC, item_id),
            )
            await db.commit()
        self.assertTrue(await self.db.update_item_name(item_id, "Груша"))
        self.assertTrue(await self.db.update_item_price(item_id, 15))
        self.assertTrue(await self.db.update_item_photo(item_id, "other"))
        self.assertEqual(
            await self.db.assign_item(item_id, category_id=other_id), "ok"
        )
        item = await self.db.get_item(item_id)
        self.assertEqual(item["created_at"], LATE_UTC)
        self.assertEqual(listing_day(item["created_at"]), MINSK_DAY)


class SuperuserSeesListingDateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        handle.close()
        self.path = handle.name
        self.db = Database(self.path)
        await self.db.connect()

    async def asyncTearDown(self) -> None:
        os.unlink(self.path)

    async def test_superuser_without_admin_row_is_admin(self) -> None:
        config = Config(
            bot_token="token",
            superuser_id=42,
            superuser_username="root",
            db_path=self.path,
            cart_ttl_minutes=20,
        )
        seen: dict = {}

        async def handler(event, data):
            seen.update(data)

        class User:
            id = 42
            username = "root"

        middleware = AccessMiddleware(config, self.db)
        await middleware(handler, object(), {"event_from_user": User()})
        self.assertTrue(seen["is_super"])
        self.assertTrue(seen["is_admin"])
        self.assertEqual(await self.db.list_admins(), [])
        caption = _item_caption(_item(), None, 42, show_listing_date=seen["is_admin"])
        self.assertIn(OLD_DAY, caption)
