from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS whitelist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    user_id INTEGER UNIQUE,
    added_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    user_id INTEGER UNIQUE,
    added_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS subcategories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (category_id) REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    photo_file_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'available',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    category_id INTEGER,
    subcategory_id INTEGER,
    FOREIGN KEY (category_id) REFERENCES categories(id),
    FOREIGN KEY (subcategory_id) REFERENCES subcategories(id)
);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    username TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL,
    FOREIGN KEY (item_id) REFERENCES items(id)
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT,
    submitted_at TEXT NOT NULL,
    confirmed_at TEXT
);

CREATE TABLE IF NOT EXISTS order_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    item_id INTEGER,
    confirmed_at TEXT NOT NULL,
    price REAL NOT NULL,
    category_id INTEGER,
    category_name TEXT,
    subcategory_id INTEGER,
    subcategory_name TEXT,
    parent_category_id INTEGER,
    parent_category_name TEXT,
    FOREIGN KEY (order_id) REFERENCES orders(id)
);
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def normalize_username(username: str | None) -> str | None:
    if not username:
        return None
    return username.lstrip("@").lower()


NEW_ITEM_DAYS = 7

_ITEM_WITH_PLACEMENT = """
SELECT
    i.id,
    i.name,
    i.price,
    i.photo_file_id,
    i.status,
    i.created_at,
    i.category_id,
    i.subcategory_id,
    c.name AS category_name,
    sc.name AS subcategory_name,
    sc.category_id AS parent_category_id,
    pc.name AS parent_category_name
FROM items i
LEFT JOIN categories c ON c.id = i.category_id
LEFT JOIN subcategories sc ON sc.id = i.subcategory_id
LEFT JOIN categories pc ON pc.id = sc.category_id
"""


def _clean_name(name: str) -> str | None:
    cleaned = name.strip()
    return cleaned or None


def _by_name(rows: list[aiosqlite.Row]) -> list[aiosqlite.Row]:
    return sorted(rows, key=lambda row: (row["name"].casefold(), row["id"]))


def _created_moment(created_at: str | None) -> datetime | None:
    if not created_at:
        return None
    try:
        return datetime.strptime(created_at[:19], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def is_new_item(created_at: str | None, days: int = NEW_ITEM_DAYS) -> bool:
    created = _created_moment(created_at)
    if created is None:
        return False
    return created > _now() - timedelta(days=days)


def listing_day(created_at: str | None) -> str | None:
    created = _created_moment(created_at)
    if created is None:
        return None
    return created.astimezone(ZoneInfo("Europe/Minsk")).strftime("%d.%m.%Y")


class Database:
    def __init__(self, path: str) -> None:
        self.path = path

    async def connect(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA)
            for table in ("whitelist", "admins"):
                cur = await db.execute(f"PRAGMA table_info({table})")
                cols = {row[1] for row in await cur.fetchall()}
                if "user_id" not in cols:
                    await db.execute(
                        f"ALTER TABLE {table} ADD COLUMN user_id INTEGER"
                    )
                    await db.execute(
                        f"CREATE UNIQUE INDEX IF NOT EXISTS "
                        f"idx_{table}_user_id ON {table}(user_id)"
                    )
            cur = await db.execute("PRAGMA table_info(items)")
            item_cols = {row[1] for row in await cur.fetchall()}
            if "category_id" not in item_cols:
                await db.execute("ALTER TABLE items ADD COLUMN category_id INTEGER")
            if "subcategory_id" not in item_cols:
                await db.execute(
                    "ALTER TABLE items ADD COLUMN subcategory_id INTEGER"
                )
            cur = await db.execute("PRAGMA table_info(bookings)")
            booking_cols = {row[1] for row in await cur.fetchall()}
            if "order_id" not in booking_cols:
                await db.execute("ALTER TABLE bookings ADD COLUMN order_id INTEGER")
            await db.commit()

    async def is_whitelisted(self, username: str | None) -> bool:
        norm = normalize_username(username)
        if not norm:
            return False
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT 1 FROM whitelist WHERE username = ?", (norm,)
            )
            return await cur.fetchone() is not None

    async def add_to_whitelist(self, username: str) -> bool:
        norm = normalize_username(username)
        if not norm:
            return False
        async with aiosqlite.connect(self.path) as db:
            try:
                await db.execute(
                    "INSERT INTO whitelist (username) VALUES (?)", (norm,)
                )
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False

    async def remove_from_whitelist(self, username: str) -> bool:
        norm = normalize_username(username)
        if not norm:
            return False
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "DELETE FROM whitelist WHERE username = ?", (norm,)
            )
            await db.commit()
            return cur.rowcount > 0

    async def list_whitelist(self) -> list[str]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT username FROM whitelist ORDER BY username"
            )
            rows = await cur.fetchall()
            return [row[0] for row in rows]

    async def bind_whitelist_user_id(self, username: str | None, user_id: int) -> None:
        norm = normalize_username(username)
        if not norm:
            return
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE whitelist SET user_id = ? WHERE username = ?",
                (user_id, norm),
            )
            await db.commit()

    async def list_notify_user_ids(self) -> list[int]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                """
                SELECT user_id FROM whitelist WHERE user_id IS NOT NULL
                UNION
                SELECT user_id FROM admins WHERE user_id IS NOT NULL
                """
            )
            rows = await cur.fetchall()
            return [row[0] for row in rows]

    async def count_new_items(self, days: int = NEW_ITEM_DAYS) -> int:
        cutoff = _fmt(_now() - timedelta(days=days))
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT COUNT(*) FROM items "
                "WHERE status IN ('available', 'pending') AND created_at > ?",
                (cutoff,),
            )
            row = await cur.fetchone()
            return int(row[0]) if row else 0

    async def is_admin_user(self, user_id: int, username: str | None = None) -> bool:
        norm = normalize_username(username)
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT 1 FROM admins WHERE user_id = ?", (user_id,)
            )
            if await cur.fetchone() is not None:
                return True
            if norm:
                cur = await db.execute(
                    "SELECT 1 FROM admins WHERE username = ?", (norm,)
                )
                return await cur.fetchone() is not None
            return False

    async def bind_admin_user_id(self, username: str | None, user_id: int) -> None:
        norm = normalize_username(username)
        if not norm:
            return
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE admins SET user_id = ? WHERE username = ?",
                (user_id, norm),
            )
            await db.commit()

    async def add_admin(self, username: str) -> bool:
        norm = normalize_username(username)
        if not norm:
            return False
        async with aiosqlite.connect(self.path) as db:
            try:
                await db.execute(
                    "INSERT INTO admins (username) VALUES (?)", (norm,)
                )
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False

    async def remove_admin(self, username: str) -> bool:
        norm = normalize_username(username)
        if not norm:
            return False
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "DELETE FROM admins WHERE username = ?", (norm,)
            )
            await db.commit()
            return cur.rowcount > 0

    async def list_admins(self) -> list[str]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT username FROM admins ORDER BY username"
            )
            rows = await cur.fetchall()
            return [row[0] for row in rows]

    async def create_item(
        self,
        name: str,
        price: float,
        photo_file_id: str,
        *,
        category_id: int | None = None,
        subcategory_id: int | None = None,
    ) -> int | None:
        if (category_id is None) == (subcategory_id is None):
            return None
        async with aiosqlite.connect(self.path) as db:
            if category_id is not None:
                cur = await db.execute(
                    "SELECT 1 FROM categories WHERE id = ?", (category_id,)
                )
                if await cur.fetchone() is None:
                    return None
                cur = await db.execute(
                    "INSERT INTO items (name, price, photo_file_id, category_id) "
                    "VALUES (?, ?, ?, ?)",
                    (name, price, photo_file_id, category_id),
                )
            else:
                cur = await db.execute(
                    "SELECT 1 FROM subcategories WHERE id = ?", (subcategory_id,)
                )
                if await cur.fetchone() is None:
                    return None
                cur = await db.execute(
                    "INSERT INTO items "
                    "(name, price, photo_file_id, subcategory_id) "
                    "VALUES (?, ?, ?, ?)",
                    (name, price, photo_file_id, subcategory_id),
                )
            await db.commit()
            return cur.lastrowid

    async def update_item_photo(self, item_id: int, photo_file_id: str) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "UPDATE items SET photo_file_id = ? WHERE id = ? "
                "AND status != 'hidden'",
                (photo_file_id, item_id),
            )
            await db.commit()
            return cur.rowcount > 0

    async def update_item_name(self, item_id: int, name: str) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "UPDATE items SET name = ? WHERE id = ? AND status != 'hidden'",
                (name, item_id),
            )
            await db.commit()
            return cur.rowcount > 0

    async def update_item_price(self, item_id: int, price: float) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "UPDATE items SET price = ? WHERE id = ? AND status != 'hidden'",
                (price, item_id),
            )
            await db.commit()
            return cur.rowcount > 0

    async def create_category(self, name: str) -> int | None:
        cleaned = _clean_name(name)
        if not cleaned:
            return None
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "INSERT INTO categories (name) VALUES (?)", (cleaned,)
            )
            await db.commit()
            return cur.lastrowid

    async def list_categories(self) -> list[aiosqlite.Row]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM categories")
            return _by_name(await cur.fetchall())

    async def get_category(self, category_id: int) -> aiosqlite.Row | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM categories WHERE id = ?", (category_id,)
            )
            return await cur.fetchone()

    async def rename_category(self, category_id: int, name: str) -> bool:
        cleaned = _clean_name(name)
        if not cleaned:
            return False
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "UPDATE categories SET name = ? WHERE id = ?",
                (cleaned, category_id),
            )
            await db.commit()
            return cur.rowcount > 0

    async def create_subcategory(self, category_id: int, name: str) -> int | None:
        cleaned = _clean_name(name)
        if not cleaned:
            return None
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT 1 FROM categories WHERE id = ?", (category_id,)
            )
            if await cur.fetchone() is None:
                return None
            cur = await db.execute(
                "INSERT INTO subcategories (category_id, name) VALUES (?, ?)",
                (category_id, cleaned),
            )
            await db.commit()
            return cur.lastrowid

    async def list_subcategories(self, category_id: int) -> list[aiosqlite.Row]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM subcategories WHERE category_id = ?",
                (category_id,),
            )
            return _by_name(await cur.fetchall())

    async def get_subcategory(self, subcategory_id: int) -> aiosqlite.Row | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM subcategories WHERE id = ?", (subcategory_id,)
            )
            return await cur.fetchone()

    async def rename_subcategory(self, subcategory_id: int, name: str) -> bool:
        cleaned = _clean_name(name)
        if not cleaned:
            return False
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "UPDATE subcategories SET name = ? WHERE id = ?",
                (cleaned, subcategory_id),
            )
            await db.commit()
            return cur.rowcount > 0

    async def rebind_subcategory(
        self, subcategory_id: int, category_id: int
    ) -> str:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM subcategories WHERE id = ?", (subcategory_id,)
            )
            sub = await cur.fetchone()
            if sub is None:
                return "missing"
            if sub["category_id"] == category_id:
                return "same"
            cur = await db.execute(
                "SELECT 1 FROM categories WHERE id = ?", (category_id,)
            )
            if await cur.fetchone() is None:
                return "bad_parent"
            await db.execute(
                "UPDATE subcategories SET category_id = ? WHERE id = ?",
                (category_id, subcategory_id),
            )
            await db.commit()
            return "ok"

    async def assign_item(
        self,
        item_id: int,
        *,
        category_id: int | None = None,
        subcategory_id: int | None = None,
    ) -> str:
        if (category_id is None) == (subcategory_id is None):
            return "invalid"
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM items WHERE id = ?", (item_id,))
            item = await cur.fetchone()
            if item is None:
                return "missing"
            if item["status"] == "hidden":
                return "hidden"
            if category_id is not None:
                cur = await db.execute(
                    "SELECT 1 FROM categories WHERE id = ?", (category_id,)
                )
                if await cur.fetchone() is None:
                    return "bad_target"
                if item["category_id"] == category_id and item["subcategory_id"] is None:
                    return "same"
                await db.execute(
                    "UPDATE items SET category_id = ?, subcategory_id = NULL "
                    "WHERE id = ?",
                    (category_id, item_id),
                )
            else:
                cur = await db.execute(
                    "SELECT 1 FROM subcategories WHERE id = ?",
                    (subcategory_id,),
                )
                if await cur.fetchone() is None:
                    return "bad_target"
                if (
                    item["subcategory_id"] == subcategory_id
                    and item["category_id"] is None
                ):
                    return "same"
                await db.execute(
                    "UPDATE items SET category_id = NULL, subcategory_id = ? "
                    "WHERE id = ?",
                    (subcategory_id, item_id),
                )
            await db.commit()
            return "ok"

    async def list_direct_items(self, category_id: int) -> list[aiosqlite.Row]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM items WHERE category_id = ? "
                "AND subcategory_id IS NULL "
                "AND status IN ('available', 'pending') "
                "ORDER BY created_at DESC",
                (category_id,),
            )
            return await cur.fetchall()

    async def list_subcategory_items(self, subcategory_id: int) -> list[aiosqlite.Row]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM items WHERE subcategory_id = ? "
                "AND status IN ('available', 'pending') "
                "ORDER BY created_at DESC",
                (subcategory_id,),
            )
            return await cur.fetchall()

    async def list_visible_placements(self) -> list[aiosqlite.Row]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT i.category_id,
                       i.subcategory_id,
                       i.created_at,
                       sc.category_id AS parent_category_id
                FROM items i
                LEFT JOIN subcategories sc ON sc.id = i.subcategory_id
                WHERE i.status IN ('available', 'pending')
                  AND (i.category_id IS NOT NULL OR i.subcategory_id IS NOT NULL)
                """
            )
            return await cur.fetchall()

    async def list_uncategorized_items(self) -> list[aiosqlite.Row]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM items WHERE category_id IS NULL "
                "AND subcategory_id IS NULL "
                "AND status IN ('available', 'pending') "
                "ORDER BY created_at DESC"
            )
            return await cur.fetchall()

    async def count_subcategories(self) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM subcategories")
            row = await cur.fetchone()
            return int(row[0]) if row else 0

    async def count_visible_uncategorized(self) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT COUNT(*) FROM items WHERE category_id IS NULL "
                "AND subcategory_id IS NULL "
                "AND status IN ('available', 'pending')"
            )
            row = await cur.fetchone()
            return int(row[0]) if row else 0

    async def get_catalog_items(self) -> list[aiosqlite.Row]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM items WHERE status IN ('available', 'pending') "
                "ORDER BY created_at DESC"
            )
            return await cur.fetchall()

    async def get_item(self, item_id: int) -> aiosqlite.Row | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"{_ITEM_WITH_PLACEMENT} WHERE i.id = ?", (item_id,)
            )
            return await cur.fetchone()

    async def delete_item(self, item_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT id FROM items WHERE id = ?", (item_id,))
            if await cur.fetchone() is None:
                return False
            await db.execute("DELETE FROM bookings WHERE item_id = ?", (item_id,))
            await db.execute("DELETE FROM items WHERE id = ?", (item_id,))
            await db.commit()
            return True

    async def list_admin_user_ids(self) -> list[int]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT user_id FROM admins WHERE user_id IS NOT NULL"
            )
            rows = await cur.fetchall()
            return [row[0] for row in rows]

    async def get_pending_booking_for_item(self, item_id: int) -> aiosqlite.Row | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM bookings WHERE item_id = ? "
                "AND status IN ('pending', 'submitted')",
                (item_id,),
            )
            return await cur.fetchone()

    async def create_booking(
        self,
        item_id: int,
        user_id: int,
        username: str | None,
        ttl_minutes: int,
    ) -> int | None:
        expires = _now() + timedelta(minutes=ttl_minutes)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT status FROM items WHERE id = ?", (item_id,)
            )
            item = await cur.fetchone()
            if not item or item["status"] != "available":
                return None

            cur = await db.execute(
                "INSERT INTO bookings (item_id, user_id, username, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (item_id, user_id, normalize_username(username), _fmt(expires)),
            )
            booking_id = cur.lastrowid
            await db.execute(
                "UPDATE items SET status = 'pending' WHERE id = ?", (item_id,)
            )
            await db.commit()
            return booking_id

    async def get_user_pending_bookings(self, user_id: int) -> list[aiosqlite.Row]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT b.*, i.name, i.price, i.photo_file_id
                FROM bookings b
                JOIN items i ON i.id = b.item_id
                WHERE b.user_id = ? AND b.status = 'pending'
                ORDER BY b.created_at
                """,
                (user_id,),
            )
            return await cur.fetchall()

    async def submit_user_cart(self, user_id: int) -> list[aiosqlite.Row]:
        bookings = await self.get_user_pending_bookings(user_id)
        if not bookings:
            return []
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "INSERT INTO orders (user_id, username, submitted_at) VALUES (?, ?, ?)",
                (user_id, bookings[0]["username"], _fmt(_now())),
            )
            order_id = cursor.lastrowid
            await db.execute(
                "UPDATE bookings SET status = 'submitted', order_id = ? "
                "WHERE user_id = ? AND status = 'pending'",
                (order_id, user_id),
            )
            await db.commit()
        return bookings

    async def clear_user_cart(self, user_id: int) -> int:
        bookings = await self.get_user_pending_bookings(user_id)
        count = 0
        for b in bookings:
            if await self.cancel_booking(b["id"], user_id):
                count += 1
        return count

    async def cancel_booking(self, booking_id: int, user_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM bookings WHERE id = ? AND status = 'pending'",
                (booking_id,),
            )
            booking = await cur.fetchone()
            if not booking or booking["user_id"] != user_id:
                return False

            await db.execute(
                "UPDATE bookings SET status = 'cancelled' WHERE id = ?",
                (booking_id,),
            )
            await db.execute(
                "UPDATE items SET status = 'available' WHERE id = ?",
                (booking["item_id"],),
            )
            await db.commit()
            return True

    async def get_pending_carts(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT b.user_id,
                       COALESCE(b.username, 'unknown') AS username,
                       COUNT(*) AS item_count,
                       SUM(i.price) AS total_price
                FROM bookings b
                JOIN items i ON i.id = b.item_id
                WHERE b.status = 'submitted'
                GROUP BY b.user_id
                ORDER BY MIN(b.created_at)
                """
            )
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

    async def get_user_cart(self, user_id: int) -> list[aiosqlite.Row]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT b.*, i.name, i.price
                FROM bookings b
                JOIN items i ON i.id = b.item_id
                WHERE b.user_id = ? AND b.status = 'submitted'
                ORDER BY b.created_at
                """,
                (user_id,),
            )
            return await cur.fetchall()

    async def _finish_booking(
        self, db: aiosqlite.Connection, booking_id: int, booking_status: str, item_status: str
    ) -> bool:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM bookings WHERE id = ? AND status = 'submitted'",
            (booking_id,),
        )
        booking = await cur.fetchone()
        if not booking:
            return False

        await db.execute(
            "UPDATE bookings SET status = ? WHERE id = ?",
            (booking_status, booking_id),
        )
        await db.execute(
            "UPDATE items SET status = ? WHERE id = ?",
            (item_status, booking["item_id"]),
        )
        return True

    async def confirm_booking(
        self, booking_id: int, when: datetime | None = None
    ) -> bool:
        moment = when or _now()
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        stamp = _fmt(moment.astimezone(timezone.utc))
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM bookings WHERE id = ? AND status = 'submitted'",
                (booking_id,),
            )
            booking = await cursor.fetchone()
            if not booking:
                return False
            cursor = await db.execute(
                _ITEM_WITH_PLACEMENT + " WHERE i.id = ?",
                (booking["item_id"],),
            )
            item = await cursor.fetchone()
            if item is None:
                return False
            order_id = booking["order_id"]
            if order_id is None:
                cursor = await db.execute(
                    "INSERT INTO orders (user_id, username, submitted_at) "
                    "VALUES (?, ?, ?)",
                    (booking["user_id"], booking["username"], booking["created_at"]),
                )
                order_id = cursor.lastrowid
                await db.execute(
                    "UPDATE bookings SET order_id = ? WHERE id = ?",
                    (order_id, booking_id),
                )
            if item["subcategory_id"] is not None:
                category_id = None
                category_name = None
                subcategory_id = item["subcategory_id"]
                subcategory_name = item["subcategory_name"]
                parent_category_id = item["parent_category_id"]
                parent_category_name = item["parent_category_name"]
            elif item["category_id"] is not None:
                category_id = item["category_id"]
                category_name = item["category_name"]
                subcategory_id = None
                subcategory_name = None
                parent_category_id = None
                parent_category_name = None
            else:
                category_id = None
                category_name = None
                subcategory_id = None
                subcategory_name = None
                parent_category_id = None
                parent_category_name = None
            await db.execute(
                """
                INSERT INTO order_lines (
                    order_id, item_id, confirmed_at, price,
                    category_id, category_name,
                    subcategory_id, subcategory_name,
                    parent_category_id, parent_category_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    item["id"],
                    stamp,
                    item["price"],
                    category_id,
                    category_name,
                    subcategory_id,
                    subcategory_name,
                    parent_category_id,
                    parent_category_name,
                ),
            )
            await db.execute(
                "UPDATE orders SET confirmed_at = ? "
                "WHERE id = ? AND confirmed_at IS NULL",
                (stamp, order_id),
            )
            await db.execute(
                "UPDATE bookings SET status = 'confirmed' WHERE id = ?",
                (booking_id,),
            )
            await db.execute(
                "UPDATE items SET status = 'hidden' WHERE id = ?",
                (item["id"],),
            )
            await db.commit()
            return True

    async def reject_booking(self, booking_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            ok = await self._finish_booking(db, booking_id, "rejected", "available")
            if ok:
                await db.commit()
            return ok

    async def confirm_user_cart(self, user_id: int) -> int:
        bookings = await self.get_user_cart(user_id)
        count = 0
        for b in bookings:
            if await self.confirm_booking(b["id"]):
                count += 1
        return count

    async def reject_user_cart(self, user_id: int) -> int:
        bookings = await self.get_user_cart(user_id)
        count = 0
        for b in bookings:
            if await self.reject_booking(b["id"]):
                count += 1
        return count

    async def expire_old_bookings(self) -> list[aiosqlite.Row]:
        now = _fmt(_now())
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT b.*, i.name AS item_name
                FROM bookings b
                JOIN items i ON i.id = b.item_id
                WHERE b.status = 'pending' AND b.expires_at < ?
                """,
                (now,),
            )
            expired = await cur.fetchall()
            for booking in expired:
                await db.execute(
                    "UPDATE bookings SET status = 'expired' WHERE id = ?",
                    (booking["id"],),
                )
                await db.execute(
                    "UPDATE items SET status = 'available' WHERE id = ?",
                    (booking["item_id"],),
                )
            await db.commit()
            return expired

    async def list_order_lines(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT
                    ol.order_id,
                    ol.confirmed_at AS line_confirmed_at,
                    ol.price,
                    ol.category_id,
                    ol.category_name,
                    ol.subcategory_id,
                    ol.subcategory_name,
                    ol.parent_category_id,
                    ol.parent_category_name,
                    o.confirmed_at AS order_confirmed_at
                FROM order_lines ol
                JOIN orders o ON o.id = ol.order_id
                WHERE o.confirmed_at IS NOT NULL
                """
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def list_all_subcategories(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT sc.id, sc.name, sc.category_id, c.name AS parent_name
                FROM subcategories sc
                JOIN categories c ON c.id = sc.category_id
                """
            )
            rows = list(await cursor.fetchall())
        return [
            dict(row)
            for row in sorted(rows, key=lambda row: (row["name"].casefold(), row["id"]))
        ]

    async def delete_category(self, category_id: int) -> str:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM categories WHERE id = ?", (category_id,)
            )
            if await cursor.fetchone() is None:
                return "missing"
            cursor = await db.execute(
                "SELECT COUNT(*) FROM subcategories WHERE category_id = ?",
                (category_id,),
            )
            subcategories = int((await cursor.fetchone())[0])
            cursor = await db.execute(
                "SELECT COUNT(*) FROM items WHERE category_id = ?",
                (category_id,),
            )
            items = int((await cursor.fetchone())[0])
            if subcategories and items:
                return "has_both"
            if subcategories:
                return "has_subcategories"
            if items:
                return "has_items"
            await db.execute("DELETE FROM categories WHERE id = ?", (category_id,))
            await db.commit()
            return "ok"

    async def delete_subcategory(self, subcategory_id: int) -> str:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM subcategories WHERE id = ?", (subcategory_id,)
            )
            if await cursor.fetchone() is None:
                return "missing"
            cursor = await db.execute(
                "SELECT COUNT(*) FROM items WHERE subcategory_id = ?",
                (subcategory_id,),
            )
            if int((await cursor.fetchone())[0]):
                return "has_items"
            await db.execute(
                "DELETE FROM subcategories WHERE id = ?", (subcategory_id,)
            )
            await db.commit()
            return "ok"
