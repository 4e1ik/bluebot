from __future__ import annotations

from aiogram import F
from aiogram.types import BufferedInputFile, Message

from bot.chart import render_category_chart
from bot.db import Database
from bot.filters import admin_router
from bot.stats import build_report, format_report, split_report


async def _send_report(message: Message, db: Database, kind: str) -> None:
    report = await build_report(db, kind)
    for part in split_report(format_report(report)):
        await message.answer(part, parse_mode="HTML", protect_content=True)
    chart = render_category_chart(
        [(bucket.name, bucket.total) for bucket in report.categories_by_sum]
    )
    if chart is None:
        return
    await message.answer_photo(
        BufferedInputFile(chart, filename=f"{kind}-categories.png"),
        protect_content=True,
    )


@admin_router.message(F.text == "Статистика заказов")
async def orders_stats(message: Message, db: Database) -> None:
    await _send_report(message, db, "orders")


@admin_router.message(F.text == "Статистика товаров")
async def products_stats(message: Message, db: Database) -> None:
    await _send_report(message, db, "products")
