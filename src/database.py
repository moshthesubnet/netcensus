"""
Async SQLite layer (aiosqlite).

Tables
------
devices  — one row per MAC address; upserted on every scan.
syslogs  — append-only syslog messages keyed by source IP.

All timestamps are stored as ISO-8601 UTC strings so they sort lexically.
"""

import json
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
    mac                 TEXT    PRIMARY KEY,
    ip                  TEXT,
    vendor              TEXT    NOT NULL DEFAULT 'Unknown',
    device_type         TEXT    NOT NULL DEFAULT 'bare-metal',
    custom_type         TEXT,
    alias               TEXT,
    notes               TEXT,
    first_seen          TEXT,
    last_seen           TEXT    NOT NULL,
    metadata            TEXT,
    ipv6                TEXT,
    disappearance_count INTEGER NOT NULL DEFAULT 0,
    scan_count          INTEGER NOT NULL DEFAULT 0
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


async def _migrate_add_columns(db: aiosqlite.Connection) -> None:
    """Add columns introduced after the initial schema (safe to run repeatedly)."""
    async with db.execute("PRAGMA table_info(devices)") as cur:
        cols = [row[1] for row in await cur.fetchall()]
    additions = {
        "first_seen":          "ALTER TABLE devices ADD COLUMN first_seen TEXT",
        "metadata":            "ALTER TABLE devices ADD COLUMN metadata TEXT",
        "ipv6":                "ALTER TABLE devices ADD COLUMN ipv6 TEXT",
        "custom_type":         "ALTER TABLE devices ADD COLUMN custom_type TEXT",
        "disappearance_count": "ALTER TABLE devices ADD COLUMN disappearance_count INTEGER NOT NULL DEFAULT 0",
        "notes":               "ALTER TABLE devices ADD COLUMN notes TEXT",
        "scan_count":          "ALTER TABLE devices ADD COLUMN scan_count INTEGER NOT NULL DEFAULT 0",
        "syslog_ip":           "ALTER TABLE devices ADD COLUMN syslog_ip TEXT",
    }
    for col, ddl in additions.items():
        if col not in cols:
            await db.execute(ddl)
            logger.info("Migration complete: added %s column to devices", col)


async def init_db() -> None:
    """Create tables and indexes if they don't already exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _migrate_devices_ip_nullable(db)
        await db.execute(_CREATE_DEVICES)
        await db.execute(_CREATE_SYSLOGS)
        await db.execute(_IDX_SYSLOGS_IP)
        await _migrate_add_columns(db)
        await db.commit()


# ---------------------------------------------------------------------------
# Devices CRUD
# ---------------------------------------------------------------------------

async def upsert_device(
    mac: str,
    ip: str | None,
    vendor: str,
    device_type: str,
    metadata: dict | None = None,
    ipv6: str | None = None,
) -> None:
    """
    Insert or update a device row.
    - alias and custom_type are excluded from updates so manual values survive scans.
    - A NULL ip/ipv6 never overwrites a real address already stored in the DB.
    - metadata is overwritten when provided; NULL leaves existing metadata intact.
    - disappearance_count is reset to 0 whenever a device is seen (ON CONFLICT).
    """
    now = datetime.now(timezone.utc).isoformat()
    meta_json = json.dumps(metadata) if metadata is not None else None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO devices (mac, ip, vendor, device_type, first_seen, last_seen, metadata, ipv6, scan_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(mac) DO UPDATE SET
                ip                  = CASE WHEN excluded.ip       IS NOT NULL THEN excluded.ip       ELSE ip       END,
                vendor              = excluded.vendor,
                device_type         = excluded.device_type,
                last_seen           = excluded.last_seen,
                metadata            = CASE WHEN excluded.metadata IS NOT NULL THEN excluded.metadata ELSE metadata END,
                ipv6                = CASE WHEN excluded.ipv6     IS NOT NULL THEN excluded.ipv6     ELSE ipv6     END,
                disappearance_count = 0,
                scan_count          = scan_count + 1
            """,
            (mac, ip, vendor, device_type, now, now, meta_json, ipv6),
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


async def set_custom_type(mac: str, custom_type: str | None) -> bool:
    """
    Override a device's type with a user-supplied value.
    Pass None or empty string to clear the override (revert to auto-detected type).
    Returns False if the MAC doesn't exist.
    """
    value = custom_type if custom_type else None
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE devices SET custom_type = ? WHERE mac = ?", (value, mac)
        )
        await db.commit()
        return cursor.rowcount > 0


async def update_disappearance_counts(seen_macs: set[str]) -> None:
    """
    Increment disappearance_count for every device NOT present in seen_macs.
    Called once per scan cycle after all upserts are complete.
    (Devices that WERE seen have their count reset to 0 by the upsert itself.)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        if not seen_macs:
            await db.execute(
                "UPDATE devices SET disappearance_count = disappearance_count + 1"
            )
        else:
            placeholders = ",".join("?" * len(seen_macs))
            await db.execute(
                f"UPDATE devices SET disappearance_count = disappearance_count + 1"
                f" WHERE mac NOT IN ({placeholders})",
                list(seen_macs),
            )
        await db.commit()


async def set_device_syslog_ip(mac: str, syslog_ip: str | None) -> bool:
    """
    Set or clear a secondary IP used for syslog lookup.
    Useful when a device sends syslog from a different interface than its primary IP
    (e.g. OPNsense sends from its LAN IP but is stored under its management IP).
    Returns False if the MAC doesn't exist.
    """
    value = syslog_ip.strip() if syslog_ip and syslog_ip.strip() else None
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE devices SET syslog_ip = ? WHERE mac = ?", (value, mac)
        )
        await db.commit()
        return cursor.rowcount > 0


async def set_device_notes(mac: str, notes: str | None) -> bool:
    """
    Set or clear the free-text notes for a device.
    Returns False if the MAC doesn't exist.
    """
    value = notes if notes else None
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE devices SET notes = ? WHERE mac = ?", (value, mac)
        )
        await db.commit()
        return cursor.rowcount > 0


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


async def merge_host_containers(mac: str, containers: list[dict]) -> None:
    """
    Merge host-network container list into a device's metadata without changing
    device_type or vendor.  Called once per scan for each host that runs one or
    more --network=host containers.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT metadata FROM devices WHERE mac = ?", (mac,)) as cur:
            row = await cur.fetchone()
        if row is None:
            return
        existing = json.loads(row[0]) if row[0] else {}
        existing["host_network_containers"] = containers
        await db.execute(
            "UPDATE devices SET metadata = ? WHERE mac = ?",
            (json.dumps(existing), mac),
        )
        await db.commit()


async def get_all_devices(
    limit: int | None = None,
    offset: int = 0,
    device_type: str | None = None,
    search: str | None = None,
    since: str | None = None,
) -> list[dict[str, Any]]:
    """
    Return device rows ordered by most recently seen.

    Filters (all optional):
      device_type  Match against COALESCE(custom_type, device_type).
      search       LIKE match across ip, mac, alias, vendor, ipv6.
      since        ISO-8601 timestamp; only rows with last_seen >= since.
    Paginated via limit/offset (default: all rows).
    """
    conditions: list[str] = []
    params: list[Any] = []

    if device_type:
        conditions.append("COALESCE(custom_type, device_type) = ?")
        params.append(device_type)
    if search:
        term = f"%{search}%"
        conditions.append(
            "(ip LIKE ? OR mac LIKE ? OR alias LIKE ? OR vendor LIKE ? OR ipv6 LIKE ?"
            " OR COALESCE(custom_type, device_type) LIKE ?)"
        )
        params.extend([term, term, term, term, term, term])
    if since:
        conditions.append("last_seen >= ?")
        params.append(since)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM devices {where} ORDER BY last_seen DESC"

    if limit is not None:
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

    result = []
    for r in rows:
        row = dict(r)
        # Deserialise JSON metadata blob
        if row.get("metadata"):
            try:
                row["metadata"] = json.loads(row["metadata"])
            except (json.JSONDecodeError, TypeError):
                row["metadata"] = None
        # Expose the effective type (custom overrides auto-detected)
        row["effective_type"] = row.get("custom_type") or row.get("device_type") or "bare-metal"
        result.append(row)
    return result


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


async def search_syslogs(
    q: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Full-text search across all syslog entries (message and source_ip).
    Returns up to `limit` rows ordered by newest first.
    """
    term = f"%{q}%"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM syslogs
            WHERE message LIKE ? OR source_ip LIKE ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (term, term, limit),
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
