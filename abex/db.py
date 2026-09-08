"""SQLite storage.

The merit log is the source of truth. members.merit is a running total kept in
step with it so the common reads stay cheap, but every cap check and every
audit question is answered from the log.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    user_id    INTEGER PRIMARY KEY,
    merit      INTEGER NOT NULL DEFAULT 0,
    rank_key   TEXT    NOT NULL DEFAULT 'loyalist',
    oath       INTEGER NOT NULL DEFAULT 0,
    uniform    INTEGER NOT NULL DEFAULT 0,
    first_seen TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS merit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    delta      INTEGER NOT NULL,
    source     TEXT    NOT NULL,
    reason     TEXT,
    officer_id INTEGER,
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_log_user_time   ON merit_log (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_log_user_source ON merit_log (user_id, source, created_at DESC);

CREATE TABLE IF NOT EXISTS awards (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    name       TEXT    NOT NULL,
    note       TEXT,
    granted_by INTEGER,
    created_at TEXT    NOT NULL,
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS appointments (
    user_id       INTEGER NOT NULL,
    key           TEXT    NOT NULL,
    note          TEXT,
    granted_by    INTEGER,
    created_at    TEXT    NOT NULL,
    PRIMARY KEY (user_id, key)
);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


@dataclass
class MemberRecord:
    user_id: int
    merit: int
    rank_key: str
    oath: bool
    uniform: bool
    first_seen: str
    updated_at: str


@dataclass
class LogEntry:
    id: int
    user_id: int
    delta: int
    source: str
    reason: str | None
    officer_id: int | None
    created_at: str


@dataclass
class AwardRecord:
    name: str
    note: str | None
    granted_by: int | None
    created_at: str


@dataclass
class AppointmentRecord:
    key: str
    note: str | None
    granted_by: int | None
    created_at: str


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database.connect() has not been awaited")
        return self._conn

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # members ---------------------------------------------------------------

    async def ensure_member(self, user_id: int) -> MemberRecord:
        now = _iso(utcnow())
        await self.conn.execute(
            "INSERT INTO members (user_id, first_seen, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO NOTHING",
            (user_id, now, now),
        )
        await self.conn.commit()
        member = await self.get_member(user_id)
        assert member is not None
        return member

    async def get_member(self, user_id: int) -> MemberRecord | None:
        async with self.conn.execute(
            "SELECT * FROM members WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return _member(row) if row else None

    async def set_rank(self, user_id: int, rank_key: str) -> None:
        await self.conn.execute(
            "UPDATE members SET rank_key = ?, updated_at = ? WHERE user_id = ?",
            (rank_key, _iso(utcnow()), user_id),
        )
        await self.conn.commit()

    async def set_flag(self, user_id: int, flag: str, value: bool) -> None:
        if flag not in ("oath", "uniform"):
            raise ValueError(f"unknown flag {flag!r}")
        await self.ensure_member(user_id)
        await self.conn.execute(
            f"UPDATE members SET {flag} = ?, updated_at = ? WHERE user_id = ?",
            (int(value), _iso(utcnow()), user_id),
        )
        await self.conn.commit()

    async def leaderboard(self, limit: int = 10) -> list[MemberRecord]:
        async with self.conn.execute(
            "SELECT * FROM members ORDER BY merit DESC, first_seen ASC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
        return [_member(r) for r in rows]

    async def rank_position(self, user_id: int) -> int | None:
        """1 based position on the merit leaderboard."""
        async with self.conn.execute(
            "SELECT COUNT(*) + 1 FROM members WHERE merit > (SELECT merit FROM members WHERE user_id = ?)",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else None

    async def member_count(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM members") as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    # merit -----------------------------------------------------------------

    async def add_merit(
        self,
        user_id: int,
        delta: int,
        source: str,
        reason: str | None = None,
        officer_id: int | None = None,
    ) -> MemberRecord:
        """Append to the log and move the running total. Never drops below zero.

        A revoke larger than the member's balance is clamped before it is
        written, so the log and the running total can never disagree.
        """
        member = await self.ensure_member(user_id)
        delta = max(delta, -member.merit)
        now = _iso(utcnow())
        await self.conn.execute(
            "INSERT INTO merit_log (user_id, delta, source, reason, officer_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, delta, source, reason, officer_id, now),
        )
        await self.conn.execute(
            "UPDATE members SET merit = merit + ?, updated_at = ? WHERE user_id = ?",
            (delta, now, user_id),
        )
        await self.conn.commit()
        member = await self.get_member(user_id)
        assert member is not None
        return member

    async def set_merit(
        self, user_id: int, total: int, officer_id: int | None = None, reason: str | None = None
    ) -> MemberRecord:
        """Force a total, recording the difference as a correction in the log."""
        member = await self.ensure_member(user_id)
        delta = max(0, total) - member.merit
        return await self.add_merit(user_id, delta, "correction", reason, officer_id)

    async def history(self, user_id: int, limit: int = 15) -> list[LogEntry]:
        async with self.conn.execute(
            "SELECT * FROM merit_log WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)
        ) as cur:
            rows = await cur.fetchall()
        return [_log(r) for r in rows]

    # cap checks ------------------------------------------------------------

    async def has_ever_logged(self, user_id: int, source: str) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM merit_log WHERE user_id = ? AND source = ? AND delta > 0 LIMIT 1",
            (user_id, source),
        ) as cur:
            return await cur.fetchone() is not None

    async def logged_today(self, user_id: int, source: str) -> bool:
        """Same UTC calendar day, which is what officers will assume 'today' means."""
        day = utcnow().strftime("%Y-%m-%d")
        async with self.conn.execute(
            "SELECT 1 FROM merit_log WHERE user_id = ? AND source = ? AND delta > 0 "
            "AND substr(created_at, 1, 10) = ? LIMIT 1",
            (user_id, source, day),
        ) as cur:
            return await cur.fetchone() is not None

    async def merit_from_source_since(self, user_id: int, source: str, days: int) -> int:
        """Positive merit credited from one source over a rolling window."""
        since = _iso(utcnow() - timedelta(days=days))
        async with self.conn.execute(
            "SELECT COALESCE(SUM(delta), 0) FROM merit_log "
            "WHERE user_id = ? AND source = ? AND delta > 0 AND created_at >= ?",
            (user_id, source, since),
        ) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    # awards and appointments ----------------------------------------------

    async def add_award(
        self, user_id: int, name: str, note: str | None, granted_by: int | None
    ) -> bool:
        await self.ensure_member(user_id)
        try:
            await self.conn.execute(
                "INSERT INTO awards (user_id, name, note, granted_by, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, name, note, granted_by, _iso(utcnow())),
            )
        except sqlite3.IntegrityError:
            return False
        await self.conn.commit()
        return True

    async def remove_award(self, user_id: int, name: str) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM awards WHERE user_id = ? AND name = ?", (user_id, name)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def awards(self, user_id: int) -> list[AwardRecord]:
        async with self.conn.execute(
            "SELECT name, note, granted_by, created_at FROM awards WHERE user_id = ? ORDER BY created_at",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [AwardRecord(r["name"], r["note"], r["granted_by"], r["created_at"]) for r in rows]

    async def add_appointment(
        self, user_id: int, key: str, note: str | None, granted_by: int | None
    ) -> bool:
        await self.ensure_member(user_id)
        try:
            await self.conn.execute(
                "INSERT INTO appointments (user_id, key, note, granted_by, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, key, note, granted_by, _iso(utcnow())),
            )
        except sqlite3.IntegrityError:
            return False
        await self.conn.commit()
        return True

    async def remove_appointment(self, user_id: int, key: str) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM appointments WHERE user_id = ? AND key = ?", (user_id, key)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def appointments(self, user_id: int) -> list[AppointmentRecord]:
        async with self.conn.execute(
            "SELECT key, note, granted_by, created_at FROM appointments WHERE user_id = ? ORDER BY created_at",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [AppointmentRecord(r["key"], r["note"], r["granted_by"], r["created_at"]) for r in rows]


def _member(row: sqlite3.Row) -> MemberRecord:
    return MemberRecord(
        user_id=row["user_id"],
        merit=row["merit"],
        rank_key=row["rank_key"],
        oath=bool(row["oath"]),
        uniform=bool(row["uniform"]),
        first_seen=row["first_seen"],
        updated_at=row["updated_at"],
    )


def _log(row: sqlite3.Row) -> LogEntry:
    return LogEntry(
        id=row["id"],
        user_id=row["user_id"],
        delta=row["delta"],
        source=row["source"],
        reason=row["reason"],
        officer_id=row["officer_id"],
        created_at=row["created_at"],
    )
