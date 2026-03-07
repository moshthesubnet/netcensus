"""
FastAPI application — Phase 3.

Endpoints
---------
GET  /api/devices            List all known devices from the database.
GET  /api/logs/{ip_address}  Last 50 syslog entries for a device IP.
PUT  /api/devices/{mac}/alias  Set a human-readable alias for a device.

Background task
---------------
Runs an ARP scan every SCAN_INTERVAL_SECONDS (default 300) and upserts
results into the devices table. Requires the process to have raw-socket
privileges (run with sudo or set CAP_NET_RAW).

Configuration via environment variables
----------------------------------------
SUBNET               CIDR to scan          (default: auto-detected /24)
SCAN_IFACE           Network interface     (default: system default)
SCAN_INTERVAL_SECONDS  Seconds between scans (default: 300)
DB_PATH              SQLite file path      (default: network_monitor.db)
PROXMOX_HOST         Proxmox host          (optional)
PROXMOX_USER         Proxmox user          (default: root@pam)
PROXMOX_PASSWORD     Password auth         (optional)
PROXMOX_TOKEN_ID     Token id              (optional)
PROXMOX_TOKEN_SECRET Token secret          (optional)
PROXMOX_VERIFY_SSL   Verify TLS cert       (default: false)
"""

import asyncio
import logging
import os
import socket
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.database import get_all_devices, get_logs_for_ip, init_db, set_device_alias, upsert_device
from src.scanner import ProxmoxConfig, arp_scan

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _detect_subnet() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        parts = ip.split(".")
        return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    except Exception:
        return "192.168.1.0/24"


SUBNET = os.environ.get("SUBNET", _detect_subnet())
SCAN_IFACE = os.environ.get("SCAN_IFACE") or None
SCAN_INTERVAL = int(os.environ.get("SCAN_INTERVAL_SECONDS", "300"))


def _build_proxmox_config() -> ProxmoxConfig | None:
    host = os.environ.get("PROXMOX_HOST")
    if not host:
        return None
    return ProxmoxConfig(
        host=host,
        user=os.environ.get("PROXMOX_USER", "root@pam"),
        password=os.environ.get("PROXMOX_PASSWORD"),
        token_id=os.environ.get("PROXMOX_TOKEN_ID"),
        token_secret=os.environ.get("PROXMOX_TOKEN_SECRET"),
        verify_ssl=os.environ.get("PROXMOX_VERIFY_SSL", "").lower() in ("1", "true"),
    )


# ---------------------------------------------------------------------------
# Background scan loop
# ---------------------------------------------------------------------------

async def _run_scan_once() -> int:
    """Run one full ARP + enrichment cycle and persist results. Returns device count."""
    proxmox_cfg = _build_proxmox_config()
    devices = await arp_scan(
        SUBNET,
        interface=SCAN_IFACE,
        timeout=2,
        proxmox=proxmox_cfg,
    )
    for d in devices:
        await upsert_device(
            mac=d.mac,
            ip=d.ip,
            vendor=d.vendor,
            device_type=d.type,
        )
    return len(devices)


async def _scan_loop() -> None:
    """Repeatedly scan the network, sleeping SCAN_INTERVAL seconds between runs."""
    logger.info(
        "Background scanner starting — subnet=%s  interval=%ds  iface=%s",
        SUBNET, SCAN_INTERVAL, SCAN_IFACE or "default",
    )
    while True:
        try:
            count = await _run_scan_once()
            logger.info("Scan complete: %d device(s) upserted", count)
        except PermissionError:
            logger.error(
                "ARP scan requires raw-socket privileges. "
                "Restart the server with sudo or grant CAP_NET_RAW."
            )
        except Exception as exc:
            logger.exception("Scan failed (will retry in %ds): %s", SCAN_INTERVAL, exc)

        await asyncio.sleep(SCAN_INTERVAL)


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Database initialised at %s", os.path.abspath(
        os.environ.get("DB_PATH", "network_monitor.db")
    ))

    scan_task = asyncio.create_task(_scan_loop())

    try:
        yield
    finally:
        scan_task.cancel()
        try:
            await scan_task
        except asyncio.CancelledError:
            pass
        logger.info("Background scanner stopped")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Network Monitor API",
    description="ARP-based network scanner with Docker and Proxmox enrichment",
    version="0.3.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class AliasRequest(BaseModel):
    alias: str


class DeviceResponse(BaseModel):
    mac: str
    ip: str
    vendor: str
    device_type: str
    alias: str | None
    last_seen: str


class SyslogResponse(BaseModel):
    id: int
    timestamp: str
    source_ip: str
    severity: str
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/api/devices",
    response_model=list[DeviceResponse],
    summary="List all known devices",
)
async def list_devices() -> list[dict[str, Any]]:
    """
    Returns every device row from the database, ordered by most recently seen.
    """
    return await get_all_devices()


@app.get(
    "/api/logs/{ip_address}",
    response_model=list[SyslogResponse],
    summary="Get recent syslog entries for a device",
)
async def get_device_logs(ip_address: str) -> list[dict[str, Any]]:
    """
    Returns the last 50 syslog messages received from **ip_address**,
    ordered newest first.
    """
    logs = await get_logs_for_ip(ip_address, limit=50)
    if not logs:
        raise HTTPException(
            status_code=404,
            detail=f"No syslog entries found for {ip_address}",
        )
    return logs


@app.put(
    "/api/devices/{mac}/alias",
    summary="Set a human-readable alias for a device",
)
async def update_alias(mac: str, body: AliasRequest) -> JSONResponse:
    """
    Attach a custom label to a device (e.g. 'Living Room TV').
    The alias persists across subsequent scans.
    """
    updated = await set_device_alias(mac, body.alias)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Device {mac} not found")
    return JSONResponse({"mac": mac, "alias": body.alias})


@app.get("/api/health", include_in_schema=False)
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})
