"""
FastAPI application.

Endpoints
---------
GET  /api/devices              List all known devices from the database.
GET  /api/logs/{ip_address}    Last 50 syslog entries for a device IP.
PUT  /api/devices/{mac}/alias  Set a human-readable alias for a device.

Concurrent background services (all managed by the lifespan)
-------------------------------------------------------------
1. Discovery loop — runs every SCAN_INTERVAL_SECONDS. Three sources run
                    concurrently and are merged into the devices table:
                    a. OPNsense  — global ARP table via REST API (all VLANs).
                    b. Proxmox   — VM/LXC inventory via API (per-node creds).
                    c. Docker    — running containers via TCP socket.
2. Syslog server  — UDP DatagramProtocol on SYSLOG_PORT (default 514).
                    Parses RFC 3164/5424 + OPNsense filterlog.

Configuration via environment variables
----------------------------------------
SCAN_INTERVAL_SECONDS  Seconds between discovery cycles  (default: 300)
DB_PATH                SQLite file path                  (default: auto)
SYSLOG_HOST            Syslog bind address               (default: 0.0.0.0)
SYSLOG_PORT            Syslog UDP port                   (default: 514)
OPNSENSE_URL           OPNsense base URL, e.g. https://10.0.99.1
OPNSENSE_KEY           OPNsense API key   (Basic Auth username)
OPNSENSE_SECRET        OPNsense API secret (Basic Auth password)
PROXMOX_NODES          JSON array: [{"host":…,"user":…,"token_id":…,"token_secret":…}, …]
DOCKER_HOSTS           Comma-separated TCP URIs, e.g. tcp://10.30.40.2:2375,…
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.database import get_all_devices, get_logs_for_ip, init_db, purge_old_syslogs, set_device_alias, set_hostname_if_unset, upsert_device
from src.identifiers import query_docker, query_proxmox
from src.opnsense import query_opnsense, query_opnsense_dhcp
from src.syslog_server import start_syslog_server

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCAN_INTERVAL = int(os.environ.get("SCAN_INTERVAL_SECONDS", "300"))
# Comma-separated Docker host URLs, e.g. "tcp://10.30.40.2:2375,tcp://10.30.40.4:2375,tcp://10.30.40.6:2375"
# Leave unset to use the local unix socket only.
DOCKER_HOSTS: list[str] = [
    h.strip() for h in os.environ.get("DOCKER_HOSTS", "").split(",") if h.strip()
]
def _parse_proxmox_nodes() -> list[dict]:
    """
    Parse PROXMOX_NODES from the environment.
    Expected value: a JSON array of dicts with keys:
      host, user, token_id, token_secret  (and optionally: password, verify_ssl)
    Returns an empty list and logs a warning on parse failure.
    """
    raw = os.environ.get("PROXMOX_NODES", "").strip()
    if not raw:
        return []
    try:
        nodes = json.loads(raw)
        if not isinstance(nodes, list):
            raise ValueError("PROXMOX_NODES must be a JSON array")
        for n in nodes:
            if "host" not in n or "user" not in n:
                raise ValueError(f"Each node must have 'host' and 'user' keys; got: {n}")
        return nodes
    except Exception as exc:
        logger.error("Failed to parse PROXMOX_NODES — Proxmox discovery disabled: %s", exc)
        return []

PROXMOX_NODES: list[dict] = _parse_proxmox_nodes()
SYSLOG_HOST = os.environ.get("SYSLOG_HOST", "0.0.0.0")
SYSLOG_PORT = int(os.environ.get("SYSLOG_PORT", "514"))


# ---------------------------------------------------------------------------
# Source health tracking  (in-memory, reset on restart)
# ---------------------------------------------------------------------------

_source_health: dict[str, dict[str, Any]] = {
    "opnsense_arp":  {"last_ok": None, "last_count": 0},
    "opnsense_dhcp": {"last_ok": None, "last_count": 0},
    "proxmox":       {"last_ok": None, "last_count": 0},
    "docker":        {"last_ok": None, "last_count": 0},
}


def _record_source(name: str, count: int) -> None:
    """Update health tracking for a discovery source after each scan."""
    _source_health[name]["last_count"] = count
    if count > 0:
        _source_health[name]["last_ok"] = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Background scan loop
# ---------------------------------------------------------------------------

async def _run_scan_once() -> int:
    """
    Run one full discovery cycle and persist results.

    Merge logic
    -----------
    1. OPNsense  — global ARP table (MAC → IP) covering all VLANs.
                   This is the base layer for physical hosts and VMs.
    2. Proxmox   — inventory of all VMs/LXCs (MAC → ProxmoxInfo).
                   Cross-referenced against the OPNsense map to assign IPs;
                   also upserted directly so offline guests still appear.
    3. Docker    — running containers (IP → DockerInfo + MAC).
                   Upserted independently; they may live on a different VLAN.

    All three sources are fetched concurrently.
    """
    arp_map, proxmox_map, docker_map, dhcp_map = await asyncio.gather(
        query_opnsense(),
        query_proxmox(PROXMOX_NODES),
        query_docker(DOCKER_HOSTS or None),
        query_opnsense_dhcp(),
    )

    _record_source("opnsense_arp",  len(arp_map))
    _record_source("opnsense_dhcp", len(dhcp_map))
    _record_source("proxmox",       len(proxmox_map))
    _record_source("docker",        len(docker_map))

    # ── 1. Merge OPNsense ARP table with Proxmox inventory ───────────────────
    # OPNsense supplies the authoritative IP; Proxmox supplies type and name.
    # If a Proxmox guest is in the ARP map, the OPNsense IP takes priority.
    opnsense_upserted = 0
    for mac, arp_ip in arp_map.items():
        proxmox_info = proxmox_map.get(mac)
        if proxmox_info:
            device_type = proxmox_info.type   # "vm" or "lxc"
            vendor      = "Proxmox"
        else:
            device_type = "bare-metal"
            vendor      = "Unknown"
        await upsert_device(mac=mac, ip=arp_ip, vendor=vendor, device_type=device_type)

        # Assign name/hostname as alias if none is set yet (manual aliases win)
        if proxmox_info:
            await set_hostname_if_unset(mac, proxmox_info.name)
        elif mac in dhcp_map:
            await set_hostname_if_unset(mac, dhcp_map[mac])

        opnsense_upserted += 1

    # ── 2. Upsert Proxmox guests not yet seen in OPNsense ARP ─────────────────
    # Covers offline VMs and ARP-aged-out guests.
    # Use the Proxmox guest-agent / LXC interface IP as a fallback when available.
    proxmox_only = 0
    for mac, info in proxmox_map.items():
        if mac not in arp_map:
            await upsert_device(
                mac=mac,
                ip=info.ip,   # None if guest agent/LXC interfaces unavailable
                vendor="Proxmox",
                device_type=info.type,
            )
            await set_hostname_if_unset(mac, info.name)
            proxmox_only += 1

    # ── 3. Upsert Docker containers (cross-VLAN, independent of ARP) ──────────
    # Build a reverse ARP map (IP → MAC) once for host-net container lookups.
    _ip_to_mac = {ip: mac for mac, ip in arp_map.items()}

    docker_upserted = 0
    for key, info in docker_map.items():
        if info.network_mode == "host":
            # Host-networked containers share the daemon host's network stack.
            # Enrich the host's existing device row if it appears in the ARP table.
            host_mac = _ip_to_mac.get(info.host_ip)
            if host_mac:
                await upsert_device(
                    mac=host_mac,
                    ip=info.host_ip,
                    vendor="Docker",
                    device_type="docker-container",
                )
                await set_hostname_if_unset(host_mac, info.name)
                docker_upserted += 1
            else:
                logger.debug(
                    "Docker host-net container %s: host %s not in ARP — skipping",
                    info.name, info.host_ip,
                )
            continue

        if not info.mac:
            logger.debug("Docker container %s (%s) has no MAC — skipping", info.name, key)
            continue
        await upsert_device(
            mac=info.mac,
            ip=key,
            vendor="Docker",
            device_type="docker-container",
        )
        docker_upserted += 1

    total = opnsense_upserted + proxmox_only + docker_upserted
    logger.info(
        "Scan complete: %d OPNsense | %d Proxmox-only | %d Docker  (%d total upserted)",
        opnsense_upserted, proxmox_only, docker_upserted, total,
    )
    return total


async def _scan_loop() -> None:
    """Repeatedly scan the network, sleeping SCAN_INTERVAL seconds between runs."""
    opnsense_display = os.environ.get("OPNSENSE_URL", "not configured")
    proxmox_display  = ", ".join(n["host"] for n in PROXMOX_NODES) if PROXMOX_NODES else "not configured"
    docker_display   = ", ".join(DOCKER_HOSTS) if DOCKER_HOSTS else "unix socket (local)"
    logger.info("Background discovery loop starting — interval=%ds", SCAN_INTERVAL)
    logger.info("  OPNsense : %s", opnsense_display)
    logger.info("  Proxmox  : %s", proxmox_display)
    logger.info("  Docker   : %s", docker_display)
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

        try:
            await purge_old_syslogs()
        except Exception as exc:
            logger.warning("Syslog purge failed: %s", exc)

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
    ip: str | None
    vendor: str
    device_type: str
    alias: str | None
    first_seen: str | None
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
async def list_devices(
    limit: int | None = Query(default=None, ge=1, description="Max rows to return"),
    offset: int = Query(default=0, ge=0, description="Rows to skip (for pagination)"),
) -> list[dict[str, Any]]:
    """
    Returns device rows from the database, ordered by most recently seen.
    Optionally paginated: use `limit` and `offset` query parameters.
    """
    return await get_all_devices(limit=limit, offset=offset)


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


@app.get("/api/health", summary="Discovery source health status")
async def health() -> JSONResponse:
    """
    Returns the operational status of each discovery source.

    A source is **ok** if it returned results within the last two scan intervals.
    **stale** means it hasn't returned data recently (possible config/connectivity issue).
    **unknown** means no scan has completed since startup.
    """
    now = datetime.now(timezone.utc)
    stale_threshold = SCAN_INTERVAL * 2

    sources: dict[str, Any] = {}
    for name, info in _source_health.items():
        last_ok: str | None = info["last_ok"]
        if last_ok is None:
            status = "unknown"
        else:
            age = (now - datetime.fromisoformat(last_ok)).total_seconds()
            status = "ok" if age <= stale_threshold else "stale"
        sources[name] = {
            "status": status,
            "last_ok": last_ok,
            "last_count": info["last_count"],
        }

    any_unknown = any(s["status"] == "unknown" for s in sources.values())
    any_stale   = any(s["status"] == "stale"   for s in sources.values())
    overall = "unknown" if any_unknown else ("degraded" if any_stale else "ok")

    return JSONResponse({"status": overall, "sources": sources})
