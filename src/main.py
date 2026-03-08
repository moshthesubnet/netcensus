"""
FastAPI application — Phase 3.5.

Endpoints
---------
GET  /api/devices              List all known devices from the database.
GET  /api/logs/{ip_address}    Last 50 syslog entries for a device IP.
PUT  /api/devices/{mac}/alias  Set a human-readable alias for a device.

Concurrent background services (all managed by the lifespan)
-------------------------------------------------------------
1. ARP scan loop  — runs every SCAN_INTERVAL_SECONDS, upserts devices table.
                    Requires raw-socket privileges (sudo / CAP_NET_RAW).
2. Syslog server  — UDP DatagramProtocol on SYSLOG_PORT (default 514).
                    Parses RFC 3164/5424 + OPNsense filterlog, writes syslogs table.
                    Port 514 requires root / CAP_NET_BIND_SERVICE.

Configuration via environment variables
----------------------------------------
SUBNET                 CIDR to scan            (default: auto-detected /24)
SCAN_IFACE             Network interface       (default: system default)
SCAN_INTERVAL_SECONDS  Seconds between scans   (default: 300)
DB_PATH                SQLite file path        (default: network_monitor.db)
SYSLOG_HOST            Syslog bind address     (default: 0.0.0.0)
SYSLOG_PORT            Syslog UDP port         (default: 514)
PROXMOX_HOSTS          Comma-separated Proxmox IPs  (optional, e.g. 10.0.99.10,10.0.99.11)
PROXMOX_HOST           Single Proxmox IP (fallback if PROXMOX_HOSTS not set)
PROXMOX_USER           Proxmox API user             (default: root@pam)
PROXMOX_PASSWORD       Password auth                (optional)
PROXMOX_TOKEN_ID       Full token id                (optional, e.g. user@pam!token)
PROXMOX_TOKEN_SECRET   Token UUID secret            (optional)
PROXMOX_VERIFY_SSL     Verify TLS cert              (default: false)
"""

import asyncio
import logging
import os
import socket
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.database import get_all_devices, get_logs_for_ip, init_db, set_device_alias, upsert_device
from src.identifiers import query_docker, query_proxmox
from src.scanner import arp_scan
from src.syslog_server import start_syslog_server

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
# Comma-separated Docker host URLs, e.g. "tcp://10.30.40.2:2375,tcp://10.30.40.4:2375,tcp://10.30.40.6:2375"
# Leave unset to use the local unix socket only.
DOCKER_HOSTS: list[str] = [
    h.strip() for h in os.environ.get("DOCKER_HOSTS", "").split(",") if h.strip()
]
# PROXMOX_HOSTS takes a comma-separated list; falls back to singular PROXMOX_HOST
_proxmox_hosts_raw = os.environ.get("PROXMOX_HOSTS") or os.environ.get("PROXMOX_HOST") or ""
PROXMOX_HOSTS: list[str] = [h.strip() for h in _proxmox_hosts_raw.split(",") if h.strip()]
PROXMOX_USER         = os.environ.get("PROXMOX_USER", "root@pam")
PROXMOX_PASSWORD     = os.environ.get("PROXMOX_PASSWORD") or None
PROXMOX_TOKEN_ID     = os.environ.get("PROXMOX_TOKEN_ID") or None
PROXMOX_TOKEN_SECRET = os.environ.get("PROXMOX_TOKEN_SECRET") or None
PROXMOX_VERIFY_SSL   = os.environ.get("PROXMOX_VERIFY_SSL", "").lower() in ("1", "true")
SYSLOG_HOST = os.environ.get("SYSLOG_HOST", "0.0.0.0")
SYSLOG_PORT = int(os.environ.get("SYSLOG_PORT", "514"))


# ---------------------------------------------------------------------------
# Background scan loop
# ---------------------------------------------------------------------------

async def _run_scan_once() -> int:
    """
    Run one full discovery cycle and persist results. Returns total device count.

    Three independent discovery paths run concurrently:
      1. ARP scan    — raw layer-2 discovery on SUBNET/SCAN_IFACE.
      2. Proxmox API — all VMs and LXCs across every PROXMOX_HOSTS entry,
                       upserted directly so cross-VLAN guests are never missed.
      3. Docker API  — all running containers across every DOCKER_HOSTS entry,
                       upserted directly for the same cross-VLAN reason.

    ARP results are enriched post-hoc using the Proxmox and Docker maps so
    that devices visible on the local subnet also get the correct type label.
    """
    # ── Fan out all three sources concurrently ────────────────────────────────
    arp_task = arp_scan(
        SUBNET, interface=SCAN_IFACE, timeout=2,
        proxmox=None, docker_hosts=None,   # enrichment handled here, not inside arp_scan
    )
    proxmox_task = query_proxmox(
        PROXMOX_HOSTS,
        PROXMOX_USER,
        password=PROXMOX_PASSWORD,
        token_id=PROXMOX_TOKEN_ID,
        token_secret=PROXMOX_TOKEN_SECRET,
        verify_ssl=PROXMOX_VERIFY_SSL,
    )
    docker_task = query_docker(DOCKER_HOSTS or None)

    devices, proxmox_map, docker_map = await asyncio.gather(
        arp_task, proxmox_task, docker_task,
    )

    # ── 1. Enrich + persist ARP-discovered devices ────────────────────────────
    arp_upserted = 0
    for d in devices:
        # Apply correct type from Proxmox/Docker maps when MAC/IP matches
        if d.ip in docker_map:
            d.type = "docker-container"
        elif d.mac.lower() in proxmox_map:
            d.type = proxmox_map[d.mac.lower()].type
        await upsert_device(mac=d.mac, ip=d.ip, vendor=d.vendor, device_type=d.type)
        arp_upserted += 1

    # ── 2. Persist ALL Proxmox guests directly (cross-VLAN safe) ─────────────
    proxmox_upserted = 0
    for mac, info in proxmox_map.items():
        await upsert_device(
            mac=mac,
            ip="",               # IP unknown until ARP sees it; preserved if already set
            vendor="Proxmox",
            device_type=info.type,
        )
        proxmox_upserted += 1

    # ── 3. Persist Docker containers directly (cross-VLAN safe) ──────────────
    docker_upserted = 0
    for ip, info in docker_map.items():
        if not info.mac:
            logger.debug("Docker container %s (%s) has no MAC — skipping", info.name, ip)
            continue
        await upsert_device(
            mac=info.mac,
            ip=ip,
            vendor="Docker",
            device_type="docker-container",
        )
        docker_upserted += 1

    logger.info(
        "Scan complete: %d ARP | %d Proxmox | %d Docker  (%d total upserted)",
        arp_upserted, proxmox_upserted, docker_upserted,
        arp_upserted + proxmox_upserted + docker_upserted,
    )
    return arp_upserted + proxmox_upserted + docker_upserted


async def _scan_loop() -> None:
    """Repeatedly scan the network, sleeping SCAN_INTERVAL seconds between runs."""
    docker_display  = ", ".join(DOCKER_HOSTS)  if DOCKER_HOSTS  else "unix socket (local)"
    proxmox_display = ", ".join(PROXMOX_HOSTS) if PROXMOX_HOSTS else "not configured"
    logger.info(
        "Background scanner starting — subnet=%s  interval=%ds  iface=%s",
        SUBNET, SCAN_INTERVAL, SCAN_IFACE or "default",
    )
    logger.info("  Proxmox hosts : %s", proxmox_display)
    logger.info("  Docker  hosts : %s", docker_display)
    while True:
        try:
            await _run_scan_once()
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
    # 1. Database
    await init_db()
    logger.info("Database initialised at %s", os.path.abspath(
        os.environ.get("DB_PATH", "network_monitor.db")
    ))

    # 2. Syslog UDP server
    syslog_transport = None
    try:
        syslog_transport = await start_syslog_server(SYSLOG_HOST, SYSLOG_PORT)
    except PermissionError:
        logger.error(
            "Cannot bind UDP port %d — re-run with sudo or set "
            "SYSLOG_PORT to a value > 1023 for unprivileged testing.",
            SYSLOG_PORT,
        )
    except OSError as exc:
        logger.error("Syslog server failed to start: %s", exc)

    # 3. Background ARP scan loop
    scan_task = asyncio.create_task(_scan_loop())

    try:
        yield
    finally:
        # Shut down in reverse order
        scan_task.cancel()
        try:
            await scan_task
        except asyncio.CancelledError:
            pass
        logger.info("Background scanner stopped")

        if syslog_transport:
            syslog_transport.close()
            logger.info("Syslog UDP server stopped")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Network Monitor API",
    description="ARP-based network scanner with Docker/Proxmox enrichment and syslog receiver",
    version="0.4.0",
    lifespan=lifespan,
)

# Serve the frontend directory (CSS, JS, assets if added later)
_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/static", StaticFiles(directory=_FRONTEND_DIR), name="static")


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


@app.get("/", include_in_schema=False)
async def dashboard() -> FileResponse:
    """Serve the single-page dashboard."""
    index = os.path.join(_FRONTEND_DIR, "index.html")
    return FileResponse(index, media_type="text/html")


@app.get("/api/health", include_in_schema=False)
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})
