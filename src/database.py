"""
Async SQLite layer (aiosqlite).

Tables
------
devices  — one row per MAC address; upserted on every scan.
syslogs  — append-only syslog messages keyed by source IP.

All timestamps are stored as ISO-8601 UTC strings so they sort lexically.
"""

import os
from datetime import datetime, timezone
from typing import Any

import aiosqlite

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH: str = os.environ.get(
    "DB_PATH",
    os.path.join(_PROJECT_ROOT, "network_monitor.db"),
)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_CREATE_DEVICES = """
CREATE TABLE IF NOT EXISTS devices (
    mac         TEXT PRIMARY KEY,
    ip          TEXT NOT NULL,
    vendor      TEXT NOT NULL DEFAULT 'Unknown',
    device_type TEXT NOT NULL DEFAULT 'bare-metal',
    alias       TEXT,
    last_seen   TEXT NOT NULL
)
"""

_CREATE_SYSLOGS = """
CREATE TABLE IF NOT EXISTS syslogs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    source_ip   TEXT    NOT NULL,
    severity    TEXT    NOT NULL DEFAULT 'info',
    message     TEXT    NOT NULL
)
"""

_IDX_SYSLOGS_IP = """
CREATE INDEX IF NOT EXISTS idx_syslogs_source_ip ON syslogs (source_ip)
"""


async def init_db() -> None:
    """Create tables and indexes if they don't already exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(_CREATE_DEVICES)
        await db.execute(_CREATE_SYSLOGS)
        await db.execute(_IDX_SYSLOGS_IP)
        await db.commit()


# ---------------------------------------------------------------------------
# Devices CRUD
# ---------------------------------------------------------------------------

async def upsert_device(
    mac: str,
    ip: str,
    vendor: str,
    device_type: str,
) -> None:
    """
    Insert or update a device row.
    The alias column is intentionally excluded so manual aliases survive scans.
    """
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO devices (mac, ip, vendor, device_type, last_seen)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(mac) DO UPDATE SET
                ip          = excluded.ip,
                vendor      = excluded.vendor,
                device_type = excluded.device_type,
                last_seen   = excluded.last_seen
            """,
            (mac, ip, vendor, device_type, now),
        )
        await db.commit()


async def set_device_alias(mac: str, alias: str) -> bool:
    """
    Set a human-readable alias for a device.
    Returns False if the MAC doesn't exist.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE devices SET alias = ? WHERE mac = ?", (alias, mac)
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_all_devices() -> list[dict[str, Any]]:
    """Return every device row, most recently seen first."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM devices ORDER BY last_seen DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Syslogs CRUD
# ---------------------------------------------------------------------------

async def insert_syslog(
    source_ip: str,
    message: str,
    severity: str = "info",
    timestamp: str | None = None,
) -> None:
    """Append a syslog entry. Timestamp defaults to now (UTC ISO-8601)."""
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO syslogs (timestamp, source_ip, severity, message)
            VALUES (?, ?, ?, ?)
            """,
            (ts, source_ip, severity, message),
        )
        await db.commit()


async def get_logs_for_ip(
    ip: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return the most recent `limit` syslog rows for a given source IP."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM syslogs
            WHERE source_ip = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (ip, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
