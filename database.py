"""
database.py
SQLite layer: users, daily visit stats and force-join channels/groups.
"""
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional
import logging
from contextlib import contextmanager
from datetime import datetime
from pytz import timezone
import config

logger = logging.getLogger(__name__)
DB_PATH = Path(config.DB_PATH)

TZ = timezone('Asia/Tehran')


@contextmanager
def get_conn():
    """Context manager that yields a sqlite3 connection and commits/closes it."""
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """
    Create tables if missing:
    - users: telegram users (id, username, first_seen, last_seen)
    - visits: per-day visit counters
    - force_channels: channels/groups required to be joined before using the bot
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                first_seen TEXT NOT NULL DEFAULT (datetime('now')),
                last_seen TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
        # migrate older tables that lack the new columns
        cur.execute("PRAGMA table_info(users);")
        cols = {row[1] for row in cur.fetchall()}
        for col in ("first_seen", "last_seen"):
            if col not in cols:
                cur.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT NOT NULL DEFAULT 'unknown';")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS visits (
                day TEXT PRIMARY KEY,           -- YYYY-MM-DD
                count INTEGER NOT NULL DEFAULT 0
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS force_channels (
                chat_id INTEGER PRIMARY KEY,
                title TEXT,
                link TEXT,
                type TEXT NOT NULL DEFAULT 'channel',   -- channel | group
                added_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
    logger.info("Database initialized at %s", DB_PATH)


# ---------------- users ----------------

def add_user(user_id: int, username: Optional[str]) -> None:
    """Insert user if new (counts as a visit for today); else update last_seen/username."""
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE id = ? LIMIT 1", (user_id,))
        exists = cur.fetchone() is not None
        if not exists:
            cur.execute(
                "INSERT INTO users (id, username, first_seen, last_seen) VALUES (?, ?, ?, ?)",
                (user_id, username or "ندارد", today, today),
            )
            cur.execute(
                "INSERT INTO visits (day, count) VALUES (?, 1) "
                "ON CONFLICT(day) DO UPDATE SET count = count + 1",
                (today,),
            )
        else:
            cur.execute(
                "UPDATE users SET username = ?, last_seen = ? WHERE id = ?",
                (username or "ندارد", today, user_id),
            )
    logger.debug("add_user: %s / %s", user_id, username)


def get_all_users() -> List[Dict]:
    """Return list of users as dicts: [{"id":..., "username":...}, ...]"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, username FROM users")
        rows = cur.fetchall()
    return [{"id": row[0], "username": row[1]} for row in rows]


def user_exists(user_id: int) -> bool:
    """Check whether a user exists in the DB."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE id = ? LIMIT 1", (user_id,))
        return cur.fetchone() is not None


def count_users() -> int:
    """Return the total number of registered users."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        return cur.fetchone()[0]


# ---------------- visit stats ----------------

def count_visits_between(day_from: str, day_to: str) -> int:
    """Count visits (new users) whose first_seen day is between day_from and day_to (inclusive)."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(SUM(count), 0) FROM visits WHERE day BETWEEN ? AND ?",
                    (day_from, day_to))
        return cur.fetchone()[0]


def visits_today() -> int:
    """Number of new users today (Tehran time)."""
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    return count_visits_between(today, today)


def visits_this_week() -> int:
    """Number of new users in the last 7 days (Tehran time)."""
    now = datetime.now(TZ)
    today = now.strftime("%Y-%m-%d")
    week_ago = (now - __import__('datetime').timedelta(days=6)).strftime("%Y-%m-%d")
    return count_visits_between(week_ago, today)


def visits_this_month() -> int:
    """Number of new users in the current month (Tehran time)."""
    now = datetime.now(TZ)
    return count_visits_between(now.strftime("%Y-%m-01"), now.strftime("%Y-%m-%d"))


# ---------------- force-join channels ----------------

def add_force_channel(chat_id: int, title: str, link: str, ctype: str) -> bool:
    """Add a channel/group to the force-join list. Returns False if it already exists."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM force_channels WHERE chat_id = ? LIMIT 1", (chat_id,))
        if cur.fetchone() is not None:
            return False
        cur.execute(
            "INSERT INTO force_channels (chat_id, title, link, type) VALUES (?, ?, ?, ?)",
            (chat_id, title or "بدون عنوان", link or "", ctype or "channel"),
        )
    return True


def remove_force_channel(chat_id: int) -> bool:
    """Remove a channel/group from the force-join list. Returns True if it was removed."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM force_channels WHERE chat_id = ?", (chat_id,))
        return cur.rowcount > 0


def get_force_channels() -> List[Dict]:
    """Return all force-join channels/groups as dicts."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT chat_id, title, link, type FROM force_channels")
        rows = cur.fetchall()
    return [{"chat_id": r[0], "title": r[1], "link": r[2], "type": r[3]} for r in rows]


def get_force_channel_by_id(chat_id: int) -> Optional[Dict]:
    """Return one force channel by id, or None."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT chat_id, title, link, type FROM force_channels WHERE chat_id = ?",
                    (chat_id,))
        row = cur.fetchone()
    return {"chat_id": row[0], "title": row[1], "link": row[2], "type": row[3]} if row else None
