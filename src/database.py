"""
Async SQLite layer (aiosqlite).

Tables
------
devices  — one row per MAC address; upserted on every scan.
syslogs  — append-only syslog messages keyed by source IP.

All timestamps are stored as ISO-8601 UTC strings so they sort lexically.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

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
    ip          TEXT,
    vendor      TEXT NOT NULL DEFAULT 'Unknown',
    device_type TEXT NOT NULL DEFAULT 'bare-metal',
    alias       TEXT,
    first_seen  TEXT,
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


async def _migrate_devices_ip_nullable(db: aiosqlite.Connection) -> None:
    """
    One-time migration: rebuild the devices table if the ip column still has
    a NOT NULL constraint (schema from versions < P1 fixes).
    Converts any empty-string IPs to NULL in the process.
    """
    async with db.execute("PRAGMA table_info(devices)") as cur:
        cols = await cur.fetchall()
    ip_col = next((c for c in cols if c[1] == "ip"), None)
    if ip_col is None or ip_col[3] == 0:   # notnull flag == 0 → already nullable
        return

    logger.info("Migrating devices table: making ip column nullable …")
    await db.execute("""
        CREATE TABLE devices_v2 (
            mac         TEXT PRIMARY KEY,
            ip          TEXT,
            vendor      TEXT NOT NULL DEFAULT 'Unknown',
            device_type TEXT NOT NULL DEFAULT 'bare-metal',
            alias       TEXT,
            last_seen   TEXT NOT NULL
        )
    """)
    await db.execute("""
        INSERT INTO devices_v2
        SELECT mac, NULLIF(ip, ''), vendor, device_type, alias, last_seen
        FROM devices
    """)
    await db.execute("DROP TABLE devices")
    await db.execute("ALTER TABLE devices_v2 RENAME TO devices")
    logger.info("Migration complete: devices.ip is now nullable")


async def _migrate_add_first_seen(db: aiosqlite.Connection) -> None:
    """Add the first_seen column to existing databases that predate P2 fixes."""
    async with db.execute("PRAGMA table_info(devices)") as cur:
        cols = [row[1] for row in await cur.fetchall()]
    if "first_seen" not in cols:
        await db.execute("ALTER TABLE devices ADD COLUMN first_seen TEXT")
        logger.info("Migration complete: added first_seen column to devices")


async def init_db() -> None:
    """Create tables and indexes if they don't already exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _migrate_devices_ip_nullable(db)
        await db.execute(_CREATE_DEVICES)
        await db.execute(_CREATE_SYSLOGS)
        await db.execute(_IDX_SYSLOGS_IP)
        await _migrate_add_first_seen(db)
        await db.commit()


# ---------------------------------------------------------------------------
# Devices CRUD
# ---------------------------------------------------------------------------

async def upsert_device(
    mac: str,
    ip: str | None,
    vendor: str,
    device_type: str,
) -> None:
    """
    Insert or update a device row.
    - The alias column is intentionally excluded so manual aliases survive scans.
    - A NULL ip never overwrites a real IP already stored in the DB
      (allows Proxmox/Docker sources to upsert type/vendor without clobbering
      an IP that was discovered later by ARP).
    """
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO devices (mac, ip, vendor, device_type, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(mac) DO UPDATE SET
                ip          = CASE WHEN excluded.ip IS NOT NULL THEN excluded.ip ELSE ip END,
                vendor      = excluded.vendor,
                device_type = excluded.device_type,
                last_seen   = excluded.last_seen
            """,
            (mac, ip, vendor, device_type, now, now),
        )
        await db.commit()


async def set_hostname_if_unset(mac: str, hostname: str) -> None:
    """
    Set the alias to hostname only when the device has no alias yet.
    Used for DHCP-derived hostnames so manual aliases are never overwritten.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE devices SET alias = ? WHERE mac = ? AND alias IS NULL",
            (hostname, mac),
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


async def get_all_devices(
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Return device rows ordered by most recently seen.
    Optionally paginated via limit/offset (default: all rows).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if limit is not None:
            query = "SELECT * FROM devices ORDER BY last_seen DESC LIMIT ? OFFSET ?"
            params: tuple = (limit, offset)
        else:
            query = "SELECT * FROM devices ORDER BY last_seen DESC"
            params = ()
        async with db.execute(query, params) as cursor:
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


async def purge_old_syslogs(days: int = 30) -> int:
    """
    Delete syslog entries older than `days` days.
    Called once per scan cycle to enforce a rolling retention window.
    Returns the number of rows deleted.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM syslogs WHERE timestamp < ?", (cutoff,)
        )
        await db.commit()
        deleted = cursor.rowcount
    if deleted:
        logger.info("Syslog retention: purged %d entries older than %d days", deleted, days)
    return deleted
