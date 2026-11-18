import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bot.chart import render_category_chart
from bot.db import Database
from bot.keyboards import category_manage_kb, main_menu_kb, subcategory_manage_kb
from bot.stats import build_report, format_report

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
MINSK = ZoneInfo("Europe/Minsk")


def _ago(**kwargs) -> datetime:
    return NOW - timedelta(**kwargs)


class MenuTests(unittest.TestCase):
    def test_stats_buttons_are_admin_only(self) -> None:
        admin = main_menu_kb(True).keyboard
        labels = [button.text for row in admin for button in row]
        self.assertIn("Статистика заказов", labels)
        self.assertIn("Статистика товаров", labels)
        user = [button.text for row in main_menu_kb(False).keyboard for button in row]
        self.assertNotIn("Статистика заказов", user)
        self.assertNotIn("Статистика товаров", user)

    def test_delete_buttons_exist(self) -> None:
        category = category_manage_kb(1, [])
        subcategory = subcategory_manage_kb(2, 1)
        category_labels = [
            button.text for row in category.inline_keyboard for button in row
        ]
        subcategory_labels = [
            button.text for row in subcategory.inline_keyboard for button in row
        ]
        self.assertIn("Удалить", category_labels)
        self.assertIn("Удалить", subcategory_labels)


class StatsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        handle.close()
        self.path = handle.name
        self.db = Database(self.path)
        await self.db.connect()

    async def asyncTearDown(self) -> None:
        os.unlink(self.path)

    async def _order(self, category_id: int, price: float, when: datetime, name: str):
        item_id = await self.db.create_item(
            name, price, "photo", category_id=category_id
        )
        booking_id = await self.db.create_booking(item_id, 7, "buyer", 20)
        submitted = await self.db.submit_user_cart(7)
        self.assertEqual(len(submitted), 1)
        self.assertTrue(await self.db.confirm_booking(booking_id, when=when))
        return item_id

    async def test_later_confirmation_stays_in_the_first_order_window(self) -> None:
        fruit = await self.db.create_category("Фрукты")
        first = await self.db.create_item("Первый", 50, "photo", category_id=fruit)
        second = await self.db.create_item("Второй", 70, "photo", category_id=fruit)
        first_booking = await self.db.create_booking(first, 7, "buyer", 20)
        second_booking = await self.db.create_booking(second, 7, "buyer", 20)
        self.assertEqual(len(await self.db.submit_user_cart(7)), 2)
        self.assertTrue(
            await self.db.confirm_booking(first_booking, when=_ago(days=10))
        )
        self.assertTrue(
            await self.db.confirm_booking(second_booking, when=_ago(days=1))
        )
        await self.db.update_item_price(first, 999)

        orders = await build_report(self.db, "orders", now=NOW)
        products = await build_report(self.db, "products", now=NOW)
        self.assertEqual(_window(orders, "Неделя").count, 0)
        self.assertEqual(_window(orders, "2 недели").count, 0)
        self.assertEqual(_window(orders, "Месяц").count, 1)
        self.assertEqual(_window(orders, "Месяц").total, 120)
        self.assertEqual(_window(products, "Неделя").count, 1)
        self.assertEqual(_window(products, "Неделя").total, 70)
        self.assertEqual(_window(products, "2 недели").total, 70)
        self.assertEqual(_window(products, "Месяц").count, 2)
        self.assertEqual(_window(products, "Месяц").total, 120)

    async def test_today_uses_minsk_midnight_and_rejection_is_excluded(self) -> None:
        fruit = await self.db.create_category("Фрукты")
        midnight = datetime(2026, 11, 18, 0, 0, tzinfo=MINSK)
        await self._order(fruit, 10, midnight + timedelta(minutes=1), "Утро")
        await self._order(fruit, 3, midnight - timedelta(minutes=1), "Вечер")
        kept = await self.db.create_item("Оставить", 8, "photo", category_id=fruit)
        dropped = await self.db.create_item("Убрать", 100, "photo", category_id=fruit)
        kept_booking = await self.db.create_booking(kept, 7, "buyer", 20)
        dropped_booking = await self.db.create_booking(dropped, 7, "buyer", 20)
        await self.db.submit_user_cart(7)
        self.assertTrue(await self.db.confirm_booking(kept_booking, when=_ago(days=2)))
        self.assertTrue(await self.db.reject_booking(dropped_booking))

        orders = await build_report(self.db, "orders", now=NOW)
        self.assertEqual(_window(orders, "Сегодня").count, 1)
        self.assertEqual(_window(orders, "Сегодня").total, 10)
        self.assertEqual(_window(orders, "Неделя").count, 3)
        self.assertEqual(_window(orders, "Неделя").total, 21)
        self.assertNotIn("100", format_report(orders))

    async def test_category_sums_match_and_products_use_their_own_time(self) -> None:
        fruit = await self.db.create_category("Фрукты")
        tea = await self.db.create_category("Чай")
        seasonal = await self.db.create_subcategory(fruit, "Сезонные")
        await self._order(fruit, 30, _ago(days=3), "Прямой")
        nested = await self.db.create_item(
            "Внутри", 8, "photo", subcategory_id=seasonal
        )
        nested_booking = await self.db.create_booking(nested, 7, "buyer", 20)
        await self.db.submit_user_cart(7)
        self.assertTrue(
            await self.db.confirm_booking(nested_booking, when=_ago(days=3))
        )
        await self._order(tea, 5, _ago(days=3), "Чайный")
        loose = await self.db.create_item("Свободный", 4, "photo", category_id=fruit)
        async with __import__("aiosqlite").connect(self.path) as raw:
            await raw.execute(
                "UPDATE items SET category_id = NULL, subcategory_id = NULL WHERE id = ?",
                (loose,),
            )
            await raw.commit()
        loose_booking = await self.db.create_booking(loose, 7, "buyer", 20)
        await self.db.submit_user_cart(7)
        self.assertTrue(
            await self.db.confirm_booking(loose_booking, when=_ago(days=3))
        )

        products = await build_report(self.db, "products", now=NOW)
        month = _window(products, "Месяц")
        self.assertEqual(month.count, 4)
        self.assertEqual(month.total, 47)
        self.assertEqual(_bucket(month.categories, "Фрукты").count, 2)
        self.assertEqual(_bucket(month.categories, "Фрукты").total, 38)
        self.assertEqual(_bucket(month.categories, "Чай").total, 5)
        self.assertEqual(_bucket(month.categories, "Без категории").total, 4)
        self.assertEqual(_bucket(month.subcategories, "Фрукты → Сезонные").total, 8)
        self.assertEqual(
            sum(bucket.total for bucket in month.categories), month.total
        )

    async def test_ranking_average_and_outer_windows(self) -> None:
        many = await self.db.create_category("Много")
        rich = await self.db.create_category("Богатая")
        alpha = await self.db.create_category("Альфа")
        await self.db.create_category("Пустая")
        await self._order(many, 10, _ago(days=2), "М1")
        await self._order(many, 10, _ago(days=2), "М2")
        await self._order(many, 2, _ago(days=7), "Ровно")
        await self._order(many, 9, _ago(days=40), "Старше месяца")
        await self._order(many, 1, _ago(days=400), "Давно")
        await self._order(rich, 100, _ago(days=2), "Б1")
        await self._order(alpha, 4, _ago(days=2), "А1")

        orders = await build_report(self.db, "orders", now=NOW)
        by_count = [bucket.name for bucket in orders.categories_by_count]
        by_sum = [bucket.name for bucket in orders.categories_by_sum]
        self.assertEqual(by_count[0], "Много")
        self.assertEqual(by_sum[0], "Богатая")
        self.assertEqual(by_count[-1], "Пустая")
        self.assertLess(by_count.index("Альфа"), by_count.index("Богатая"))
        self.assertEqual(orders.average, 25.2)
        self.assertIn("25.2", format_report(orders))
        self.assertEqual(_window(orders, "Неделя").total, 124)
        self.assertEqual(_window(orders, "Месяц").count, 5)
        self.assertEqual(_window(orders, "Квартал").total, 135)
        self.assertEqual(_window(orders, "Год").total, 135)
        self.assertEqual(_window(orders, "Всё время").total, 136)

    async def test_empty_month_has_no_average(self) -> None:
        fruit = await self.db.create_category("Фрукты")
        await self._order(fruit, 10, _ago(days=40), "Старый")
        orders = await build_report(self.db, "orders", now=NOW)
        self.assertIsNone(orders.average)
        self.assertIn("средней нет", format_report(orders))

    async def test_snapshot_survives_delete(self) -> None:
        fruit = await self.db.create_category("Фрукты")
        item_id = await self._order(fruit, 15, _ago(days=1), "Голден")
        self.assertTrue(await self.db.delete_item(item_id))
        self.assertEqual(await self.db.delete_category(fruit), "ok")
        orders = await build_report(self.db, "orders", now=NOW)
        self.assertEqual(_window(orders, "Всё время").total, 15)
        self.assertEqual(_bucket(orders.categories_by_sum, "Фрукты").total, 15)

    async def test_delete_only_empty_category_and_subcategory(self) -> None:
        fruit = await self.db.create_category("Фрукты")
        tea = await self.db.create_category("Чай")
        seasonal = await self.db.create_subcategory(fruit, "Сезонные")
        item_id = await self.db.create_item(
            "Голден", 12, "photo", subcategory_id=seasonal
        )
        self.assertEqual(await self.db.delete_subcategory(seasonal), "has_items")
        self.assertEqual(await self.db.delete_category(fruit), "has_subcategories")
        self.assertIsNotNone(await self.db.get_subcategory(seasonal))
        hidden = await self.db.create_item("Скрытый", 1, "photo", category_id=tea)
        await self.db.create_booking(hidden, 7, "buyer", 20)
        await self.db.submit_user_cart(7)
        booking = (await self._submitted_ids())[0]
        self.assertTrue(await self.db.confirm_booking(booking, when=NOW))
        self.assertEqual(await self.db.delete_category(tea), "has_items")
        self.assertTrue(await self.db.delete_item(item_id))
        self.assertEqual(await self.db.delete_subcategory(seasonal), "ok")
        self.assertEqual(await self.db.delete_category(fruit), "ok")
        self.assertEqual(await self.db.delete_category(fruit), "missing")
        self.assertEqual(await self.db.delete_subcategory(seasonal), "missing")

    async def _submitted_ids(self) -> list[int]:
        import aiosqlite

        async with aiosqlite.connect(self.path) as raw:
            cursor = await raw.execute(
                "SELECT id FROM bookings WHERE status = 'submitted'"
            )
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    def test_chart_is_png_only_for_positive_sums(self) -> None:
        chart = render_category_chart([("Фрукты", 30), ("Чай", 5), ("Пустая", 0)])
        self.assertIsNotNone(chart)
        self.assertTrue(chart.startswith(b"\x89PNG"))
        self.assertIsNone(render_category_chart([("Пустая", 0)]))
        self.assertIsNone(render_category_chart([]))


def _window(report, label: str):
    return next(window for window in report.windows if window.label == label)


def _bucket(buckets, name: str):
    return next(bucket for bucket in buckets if bucket.name == name)


if __name__ == "__main__":
    unittest.main()
