from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS whitelist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    added_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    user_id INTEGER UNIQUE,
    added_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    photo_file_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'available',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
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
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def normalize_username(username: str | None) -> str | None:
    if not username:
        return None
    return username.lstrip("@").lower()


class Database:
    def __init__(self, path: str) -> None:
        self.path = path

    async def connect(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA)
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

    async def create_item(self, name: str, price: float, photo_file_id: str) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "INSERT INTO items (name, price, photo_file_id) VALUES (?, ?, ?)",
                (name, price, photo_file_id),
            )
            await db.commit()
            return cur.lastrowid

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
            cur = await db.execute("SELECT * FROM items WHERE id = ?", (item_id,))
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
            await db.execute(
                "UPDATE bookings SET status = 'submitted' "
                "WHERE user_id = ? AND status = 'pending'",
                (user_id,),
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

    async def confirm_booking(self, booking_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            ok = await self._finish_booking(db, booking_id, "confirmed", "hidden")
            if ok:
                await db.commit()
            return ok

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
