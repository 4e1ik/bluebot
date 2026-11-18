from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

from bot.db import Database

MINSK = ZoneInfo("Europe/Minsk")

_MONTH = "Месяц"


@dataclass(frozen=True)
class Bucket:
    name: str
    count: int
    total: float
    sort_name: str
    sort_id: int
    uncategorized: bool = False


@dataclass(frozen=True)
class WindowStats:
    label: str
    count: int
    total: float
    categories: tuple[Bucket, ...]
    subcategories: tuple[Bucket, ...]


@dataclass(frozen=True)
class Report:
    kind: str
    windows: tuple[WindowStats, ...]
    average: float | None
    categories_by_count: tuple[Bucket, ...]
    categories_by_sum: tuple[Bucket, ...]
    subcategories_by_count: tuple[Bucket, ...]
    subcategories_by_sum: tuple[Bucket, ...]


def _stamp(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _window_starts(now: datetime) -> list[tuple[str, str | None, str]]:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(MINSK)
    end = _stamp(local)
    today = local.replace(hour=0, minute=0, second=0, microsecond=0)
    week = today - timedelta(days=today.weekday())
    quarter_month = ((today.month - 1) // 3) * 3 + 1
    bounds = (
        ("Сегодня", today),
        ("Неделя", week),
        ("2 недели", week - timedelta(days=7)),
        (_MONTH, today.replace(day=1)),
        ("Квартал", today.replace(month=quarter_month, day=1)),
        ("Год", today.replace(month=1, day=1)),
        ("Всё время", None),
    )
    return [
        (label, None if start is None else _stamp(start), end)
        for label, start in bounds
    ]


def _inside(stamp: str, start: str | None, end: str) -> bool:
    if stamp > end:
        return False
    return start is None or stamp >= start


def _plural(count: int, one: str, few: str, many: str) -> str:
    number = abs(int(count))
    if number % 10 == 1 and number % 100 != 11:
        return one
    if 2 <= number % 10 <= 4 and not (12 <= number % 100 <= 14):
        return few
    return many


def _money(amount: float) -> str:
    return f"{amount:.0f} Br"


def _groups(lines: list[dict], kind: str) -> list[dict]:
    if kind == "products":
        return [
            {"at": line["line_confirmed_at"], "lines": [line], "id": index}
            for index, line in enumerate(lines)
        ]
    grouped: dict[int, dict] = {}
    for line in lines:
        order = grouped.setdefault(
            line["order_id"],
            {"at": line["order_confirmed_at"], "lines": [], "id": line["order_id"]},
        )
        order["lines"].append(line)
    return list(grouped.values())


def _placement(line: dict) -> tuple[tuple, str, tuple | None, str | None]:
    if line["subcategory_id"] is not None:
        parent = line["parent_category_name"] or ""
        sub_name = line["subcategory_name"] or "Подкатегория"
        label = f"{parent} → {sub_name}" if parent else sub_name
        return (
            ("category", line["parent_category_id"] or 0),
            parent or "Категория",
            ("sub", line["subcategory_id"]),
            label,
        )
    if line["category_id"] is not None:
        return (
            ("category", line["category_id"]),
            line["category_name"] or "Категория",
            None,
            None,
        )
    return ("none", 0), "Без категории", None, None


def _bucket(
    key: tuple,
    name: str,
    count: int,
    total: float,
) -> Bucket:
    return Bucket(
        name=name,
        count=count,
        total=total,
        sort_name=name.casefold(),
        sort_id=key[1] or 0,
        uncategorized=key[0] == "none",
    )


def _by_name(bucket: Bucket) -> tuple:
    return (bucket.uncategorized, bucket.sort_name, bucket.sort_id)


def _by_count(bucket: Bucket) -> tuple:
    return (-bucket.count, bucket.uncategorized, bucket.sort_name, bucket.sort_id)


def _by_sum(bucket: Bucket) -> tuple:
    return (-bucket.total, bucket.uncategorized, bucket.sort_name, bucket.sort_id)


def _names(
    lines: list[dict],
    categories: list,
    subcategories: list,
) -> tuple[dict[tuple, str], dict[tuple, str], bool]:
    category_names = {
        ("category", category["id"]): category["name"] for category in categories
    }
    subcategory_names = {
        ("sub", sub["id"]): f"{sub['parent_name']} → {sub['name']}"
        for sub in subcategories
    }
    has_loose = False
    for line in lines:
        cat_key, cat_name, sub_key, sub_label = _placement(line)
        if cat_key[0] == "none":
            has_loose = True
            category_names.setdefault(cat_key, cat_name)
        else:
            category_names.setdefault(cat_key, cat_name)
        if sub_key is not None and sub_label is not None:
            subcategory_names.setdefault(sub_key, sub_label)
    for category in categories:
        category_names[("category", category["id"])] = category["name"]
    for sub in subcategories:
        subcategory_names[("sub", sub["id"])] = f"{sub['parent_name']} → {sub['name']}"
    return category_names, subcategory_names, has_loose


def _collect(
    orders: list[dict],
    category_names: dict[tuple, str],
    subcategory_names: dict[tuple, str],
    has_loose: bool,
) -> tuple[list[Bucket], list[Bucket], int, float]:
    category_count: dict[tuple, int] = {}
    category_total: dict[tuple, float] = {}
    subcategory_count: dict[tuple, int] = {}
    subcategory_total: dict[tuple, float] = {}
    count = 0
    total = 0.0
    for order in orders:
        count += 1
        seen_categories: set[tuple] = set()
        seen_subcategories: set[tuple] = set()
        for line in order["lines"]:
            price = float(line["price"])
            total += price
            cat_key, _, sub_key, _ = _placement(line)
            category_total[cat_key] = category_total.get(cat_key, 0.0) + price
            if cat_key not in seen_categories:
                category_count[cat_key] = category_count.get(cat_key, 0) + 1
                seen_categories.add(cat_key)
            if sub_key is not None:
                subcategory_total[sub_key] = subcategory_total.get(sub_key, 0.0) + price
                if sub_key not in seen_subcategories:
                    subcategory_count[sub_key] = subcategory_count.get(sub_key, 0) + 1
                    seen_subcategories.add(sub_key)
    category_keys = set(category_names)
    if not has_loose:
        category_keys.discard(("none", 0))
    categories = [
        _bucket(
            key,
            category_names.get(key, "Категория"),
            category_count.get(key, 0),
            category_total.get(key, 0.0),
        )
        for key in category_keys
    ]
    subcategories = [
        _bucket(
            key,
            subcategory_names[key],
            subcategory_count.get(key, 0),
            subcategory_total.get(key, 0.0),
        )
        for key in subcategory_names
    ]
    categories.sort(key=_by_name)
    subcategories.sort(key=_by_name)
    return categories, subcategories, count, total


async def build_report(
    db: Database, kind: str, now: datetime | None = None
) -> Report:
    if kind not in ("orders", "products"):
        raise ValueError(kind)
    moment = now or datetime.now(timezone.utc)
    lines = await db.list_order_lines()
    categories = await db.list_categories()
    subcategories = await db.list_all_subcategories()
    category_names, subcategory_names, has_loose = _names(
        lines, categories, subcategories
    )
    groups = _groups(lines, kind)
    windows: list[WindowStats] = []
    all_categories: list[Bucket] = []
    all_subcategories: list[Bucket] = []
    month_count = 0
    month_total = 0.0
    for label, start, end in _window_starts(moment):
        included = [order for order in groups if _inside(order["at"], start, end)]
        cats, subs, count, total = _collect(
            included, category_names, subcategory_names, has_loose
        )
        windows.append(
            WindowStats(label, count, total, tuple(cats), tuple(subs))
        )
        if label == "Всё время":
            all_categories = cats
            all_subcategories = subs
        if label == _MONTH:
            month_count = count
            month_total = total
    average = None if month_count == 0 else month_total / month_count
    return Report(
        kind=kind,
        windows=tuple(windows),
        average=average,
        categories_by_count=tuple(sorted(all_categories, key=_by_count)),
        categories_by_sum=tuple(sorted(all_categories, key=_by_sum)),
        subcategories_by_count=tuple(sorted(all_subcategories, key=_by_count)),
        subcategories_by_sum=tuple(sorted(all_subcategories, key=_by_sum)),
    )


def _bucket_lines(
    buckets: tuple[Bucket, ...] | list[Bucket],
    nouns: tuple[str, str, str],
    empty: str,
) -> list[str]:
    if not buckets:
        return [empty]
    lines = []
    for bucket in buckets:
        word = _plural(bucket.count, *nouns)
        lines.append(
            f"• {escape(bucket.name)} — {bucket.count} {word}, {_money(bucket.total)}"
        )
    return lines


def format_report(report: Report) -> str:
    nouns = (
        ("заказ", "заказа", "заказов")
        if report.kind == "orders"
        else ("товар", "товара", "товаров")
    )
    title = "Заказы" if report.kind == "orders" else "Товары"
    lines = [f"<b>{title}</b>", ""]
    for window in report.windows:
        word = _plural(window.count, *nouns)
        lines.append(
            f"{window.label}: {window.count} {word}, {_money(window.total)}"
        )
    lines.append("")
    if report.average is None:
        lines.append("Средняя за месяц: средней нет")
    else:
        lines.append(f"Средняя за месяц: {report.average:.1f} Br")
    for window in report.windows:
        lines.extend(
            [
                "",
                f"<b>{escape(window.label)} по категориям</b>",
                *_bucket_lines(window.categories, nouns, "Нет категорий."),
                "",
                f"<b>{escape(window.label)} по подкатегориям</b>",
                *_bucket_lines(window.subcategories, nouns, "Нет подкатегорий."),
            ]
        )
    lines.extend(
        [
            "",
            "<b>Категории за всё время по количеству</b>",
            *_bucket_lines(report.categories_by_count, nouns, "Нет категорий."),
            "",
            "<b>Категории за всё время по сумме</b>",
            *_bucket_lines(report.categories_by_sum, nouns, "Нет категорий."),
            "",
            "<b>Подкатегории за всё время по количеству</b>",
            *_bucket_lines(report.subcategories_by_count, nouns, "Нет подкатегорий."),
            "",
            "<b>Подкатегории за всё время по сумме</b>",
            *_bucket_lines(report.subcategories_by_sum, nouns, "Нет подкатегорий."),
        ]
    )
    return "\n".join(lines)


def split_report(text: str, limit: int = 3500) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.split("\n"):
        extra = len(line) + (1 if current else 0)
        if current and size + extra > limit:
            parts.append("\n".join(current))
            current = [line]
            size = len(line)
        else:
            current.append(line)
            size += extra
    if current:
        parts.append("\n".join(current))
    return parts
