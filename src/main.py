"""
FastAPI application.

Endpoints
---------
GET  /api/devices              List all known devices (filterable, paginated).
GET  /api/logs/{ip_address}    Last 50 syslog entries for a device IP.
PUT  /api/devices/{mac}/alias  Set a human-readable alias for a device.
PUT  /api/devices/{mac}/type   Override the auto-detected device type.
GET  /api/health               Discovery source health status.

Concurrent background services (all managed by the lifespan)
-------------------------------------------------------------
1. Discovery loop — runs every SCAN_INTERVAL_SECONDS. Six sources run
                    concurrently and are merged into the devices table:
                    a. OPNsense ARP  — global ARP table (IPv4, all VLANs).
                    b. OPNsense NDP  — global NDP table (IPv6, all VLANs).
                    c. OPNsense DHCP — active leases → hostnames.
                    d. Proxmox       — VM/LXC inventory via API.
                    e. Docker        — running containers via TCP socket.
                    f. nmap          — optional subnet ping sweep (NMAP_SUBNETS).
                    g. SNMP          — optional ARP-cache walk (SNMP_HOSTS).
2. Syslog server  — UDP DatagramProtocol on SYSLOG_PORT (default 514).

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
NMAP_SUBNETS           Comma-separated CIDRs, e.g. 10.0.10.0/24,10.0.20.0/24
SNMP_HOSTS             JSON array: [{"host":…,"community":…,"port":161}, …]
ALERT_WEBHOOK_URL      HTTP(S) URL to POST alert events to (default: disabled)
ALERT_DISAPPEARANCE_THRESHOLD  Scans missed before firing "device_gone" alert (default: 3)
"""

import asyncio
import csv
import io
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.database import (
    get_all_devices, get_logs_for_ip, init_db, purge_old_syslogs,
    search_syslogs, set_custom_type, set_device_alias, set_device_notes,
    set_hostname_if_unset, update_disappearance_counts, upsert_device,
)
from src.identifiers import query_docker, query_proxmox
from src.nmap_scanner import query_nmap
from src.opnsense import query_opnsense, query_opnsense_dhcp, query_opnsense_ndp
from src.snmp_scanner import query_snmp
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
NMAP_SUBNETS: list[str] = [
    s.strip() for s in os.environ.get("NMAP_SUBNETS", "").split(",") if s.strip()
]


def _parse_snmp_hosts() -> list[dict]:
    raw = os.environ.get("SNMP_HOSTS", "").strip()
    if not raw:
        return []
    try:
        hosts = json.loads(raw)
        if not isinstance(hosts, list):
            raise ValueError("SNMP_HOSTS must be a JSON array")
        return hosts
    except Exception as exc:
        logger.error("Failed to parse SNMP_HOSTS — SNMP discovery disabled: %s", exc)
        return []


SNMP_HOSTS: list[dict] = _parse_snmp_hosts()

ALERT_WEBHOOK_URL           = os.environ.get("ALERT_WEBHOOK_URL", "")
ALERT_DISAPPEARANCE_THRESHOLD = int(os.environ.get("ALERT_DISAPPEARANCE_THRESHOLD", "3"))


# ---------------------------------------------------------------------------
# Source health tracking  (in-memory, reset on restart)
# ---------------------------------------------------------------------------

_source_health: dict[str, dict[str, Any]] = {
    "opnsense_arp":  {"last_ok": None, "last_count": 0},
    "opnsense_dhcp": {"last_ok": None, "last_count": 0},
    "opnsense_ndp":  {"last_ok": None, "last_count": 0},
    "proxmox":       {"last_ok": None, "last_count": 0},
    "docker":        {"last_ok": None, "last_count": 0},
    "nmap":          {"last_ok": None, "last_count": 0},
    "snmp":          {"last_ok": None, "last_count": 0},
}


def _record_source(name: str, count: int) -> None:
    """Update health tracking for a discovery source after each scan."""
    _source_health[name]["last_count"] = count
    if count > 0:
        _source_health[name]["last_ok"] = datetime.now(timezone.utc).isoformat()


async def _fire_webhook(event: str, device: dict) -> None:
    """POST an alert payload to ALERT_WEBHOOK_URL (fire-and-forget)."""
    if not ALERT_WEBHOOK_URL:
        return
    payload = {
        "event":     event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "device": {
            "mac":          device.get("mac"),
            "ip":           device.get("ip"),
            "alias":        device.get("alias"),
            "vendor":       device.get("vendor"),
            "device_type":  device.get("effective_type") or device.get("device_type"),
            "last_seen":    device.get("last_seen"),
        },
    }
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(ALERT_WEBHOOK_URL, json=payload)
        logger.info("Webhook fired: %s for %s", event, device.get("mac"))
    except Exception as exc:
        logger.warning("Webhook delivery failed (%s): %s", event, exc)


# ---------------------------------------------------------------------------
# Background scan loop
# ---------------------------------------------------------------------------

async def _run_scan_once() -> int:
    """
    Run one full discovery cycle and persist results.

    Merge logic
    -----------
    1. OPNsense ARP — global ARP table (MAC → IP) covering all VLANs.
    2. OPNsense NDP — global IPv6 neighbour table (MAC → IPv6).
    3. nmap         — optional ping sweep; adds hosts missing from ARP.
    4. SNMP         — optional ARP-cache walk on routers/switches.
    5. Proxmox      — VM/LXC inventory; cross-referenced with ARP for IPs.
    6. Docker       — running containers; upserted independently.
    7. DHCP         — hostname enrichment via active leases.
    """
    # Snapshot existing MACs before upserts so we can detect new arrivals
    pre_scan_devices = {d["mac"]: d for d in await get_all_devices()}

    arp_map, proxmox_map, docker_map, dhcp_map, ndp_map, nmap_map, snmp_map = (
        await asyncio.gather(
            query_opnsense(),
            query_proxmox(PROXMOX_NODES),
            query_docker(DOCKER_HOSTS or None),
            query_opnsense_dhcp(),
            query_opnsense_ndp(),
            query_nmap(NMAP_SUBNETS),
            query_snmp(SNMP_HOSTS),
        )
    )

    _record_source("opnsense_arp",  len(arp_map))
    _record_source("opnsense_dhcp", len(dhcp_map))
    _record_source("opnsense_ndp",  len(ndp_map))
    _record_source("proxmox",       len(proxmox_map))
    _record_source("docker",        len(docker_map))
    _record_source("nmap",          len(nmap_map))
    _record_source("snmp",          len(snmp_map))

    # Fold nmap/SNMP extra entries into arp_map (ARP table takes priority on conflict)
    for mac, ip in {**snmp_map, **nmap_map}.items():
        if mac not in arp_map:
            arp_map[mac] = ip

    seen_macs: set[str] = set()

    # ── 1. Merge OPNsense ARP table with Proxmox inventory ───────────────────
    opnsense_upserted = 0
    for mac, arp_ip in arp_map.items():
        proxmox_info = proxmox_map.get(mac)
        ipv6 = ndp_map.get(mac)
        if proxmox_info:
            device_type   = proxmox_info.type
            vendor        = "Proxmox"
            proxmox_meta  = {
                "vm_id":        proxmox_info.vm_id,
                "node":         proxmox_info.node,
                "status":       proxmox_info.status,
                "proxmox_type": proxmox_info.type,
            }
        else:
            device_type  = "bare-metal"
            vendor       = "Unknown"
            proxmox_meta = None

        await upsert_device(
            mac=mac, ip=arp_ip, vendor=vendor,
            device_type=device_type, metadata=proxmox_meta, ipv6=ipv6,
        )

        if proxmox_info:
            await set_hostname_if_unset(mac, proxmox_info.name)
        elif mac in dhcp_map:
            await set_hostname_if_unset(mac, dhcp_map[mac])

        seen_macs.add(mac)
        opnsense_upserted += 1

    # ── 2. Upsert Proxmox guests not in ARP (offline / ARP-aged-out) ──────────
    proxmox_only = 0
    for mac, info in proxmox_map.items():
        if mac not in arp_map:
            proxmox_meta = {
                "vm_id":        info.vm_id,
                "node":         info.node,
                "status":       info.status,
                "proxmox_type": info.type,
            }
            await upsert_device(
                mac=mac, ip=info.ip, vendor="Proxmox",
                device_type=info.type, metadata=proxmox_meta, ipv6=ndp_map.get(mac),
            )
            await set_hostname_if_unset(mac, info.name)
            seen_macs.add(mac)
            proxmox_only += 1

    # ── 2b. Upsert IPv6-only devices (NDP hit but no ARP entry) ───────────────
    ndp_only = 0
    for mac, ipv6 in ndp_map.items():
        if mac not in arp_map and mac not in proxmox_map:
            await upsert_device(
                mac=mac, ip=None, vendor="Unknown",
                device_type="bare-metal", ipv6=ipv6,
            )
            if mac in dhcp_map:
                await set_hostname_if_unset(mac, dhcp_map[mac])
            seen_macs.add(mac)
            ndp_only += 1

    # ── 3. Upsert Docker containers (cross-VLAN, independent of ARP) ──────────
    _ip_to_mac = {ip: mac for mac, ip in arp_map.items()}

    docker_upserted = 0
    for key, info in docker_map.items():
        docker_meta = {
            "container_name": info.name,
            "container_id":   info.container_id,
            "image":          info.image,
            "status":         info.status,
            "networks":       info.networks,
            "network_mode":   info.network_mode,
        }

        if info.network_mode == "host":
            host_mac = _ip_to_mac.get(info.host_ip)
            if host_mac:
                await upsert_device(
                    mac=host_mac, ip=info.host_ip, vendor="Docker",
                    device_type="docker-container", metadata=docker_meta,
                )
                await set_hostname_if_unset(host_mac, info.name)
                seen_macs.add(host_mac)
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
            mac=info.mac, ip=key, vendor="Docker",
            device_type="docker-container", metadata=docker_meta,
        )
        await set_hostname_if_unset(info.mac, info.name)
        seen_macs.add(info.mac)
        docker_upserted += 1

    # ── 4. Increment disappearance count for devices absent this cycle ─────────
    await update_disappearance_counts(seen_macs)

    # ── 5. Alerting ────────────────────────────────────────────────────────────
    if ALERT_WEBHOOK_URL:
        post_scan = {d["mac"]: d for d in await get_all_devices()}
        for mac, device in post_scan.items():
            if mac not in pre_scan_devices:
                await _fire_webhook("device_discovered", device)
            elif device.get("disappearance_count", 0) == ALERT_DISAPPEARANCE_THRESHOLD:
                await _fire_webhook("device_gone", device)

    total = opnsense_upserted + proxmox_only + ndp_only + docker_upserted
    logger.info(
        "Scan complete: %d OPNsense | %d Proxmox-only | %d NDP-only | %d Docker  (%d total)",
        opnsense_upserted, proxmox_only, ndp_only, docker_upserted, total,
    )
    return total


async def _scan_loop() -> None:
    """Repeatedly scan the network, sleeping SCAN_INTERVAL seconds between runs."""
    opnsense_display = os.environ.get("OPNSENSE_URL", "not configured")
    proxmox_display  = ", ".join(n["host"] for n in PROXMOX_NODES) if PROXMOX_NODES else "not configured"
    docker_display   = ", ".join(DOCKER_HOSTS) if DOCKER_HOSTS else "unix socket (local)"
    nmap_display     = ", ".join(NMAP_SUBNETS) if NMAP_SUBNETS else "disabled"
    snmp_display     = f"{len(SNMP_HOSTS)} host(s)" if SNMP_HOSTS else "disabled"
    logger.info("Background discovery loop starting — interval=%ds", SCAN_INTERVAL)
    logger.info("  OPNsense : %s", opnsense_display)
    logger.info("  Proxmox  : %s", proxmox_display)
    logger.info("  Docker   : %s", docker_display)
    logger.info("  nmap     : %s", nmap_display)
    logger.info("  SNMP     : %s", snmp_display)
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


class TypeRequest(BaseModel):
    type: str | None = None


class NotesRequest(BaseModel):
    notes: str | None = None


class DeviceResponse(BaseModel):
    mac: str
    ip: str | None
    vendor: str
    device_type: str
    custom_type: str | None = None
    effective_type: str | None = None
    alias: str | None
    notes: str | None = None
    first_seen: str | None
    last_seen: str
    metadata: dict | None = None
    ipv6: str | None = None
    disappearance_count: int = 0
    scan_count: int = 0


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
    device_type: str | None = Query(default=None, description="Filter by effective device type"),
    search: str | None = Query(default=None, description="Search across ip, mac, alias, vendor, ipv6"),
    since: str | None = Query(default=None, description="ISO-8601 timestamp; only devices seen after"),
) -> list[dict[str, Any]]:
    """
    Returns device rows from the database, ordered by most recently seen.
    Supports pagination (limit/offset) and server-side filtering.
    """
    return await get_all_devices(
        limit=limit, offset=offset,
        device_type=device_type, search=search, since=since,
    )


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


@app.put(
    "/api/devices/{mac}/type",
    summary="Override the auto-detected device type",
)
async def update_type(mac: str, body: TypeRequest) -> JSONResponse:
    """
    Set a custom device type (e.g. 'iot', 'firewall', 'hypervisor').
    Pass null or empty string to clear the override and revert to auto-detected type.
    """
    updated = await set_custom_type(mac, body.type)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Device {mac} not found")
    return JSONResponse({"mac": mac, "custom_type": body.type})


@app.put(
    "/api/devices/{mac}/notes",
    summary="Set or clear free-text notes for a device",
)
async def update_notes(mac: str, body: NotesRequest) -> JSONResponse:
    """Persist operator notes for a device. Pass null or empty string to clear."""
    updated = await set_device_notes(mac, body.notes)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Device {mac} not found")
    return JSONResponse({"mac": mac, "notes": body.notes})


@app.get("/api/devices/export", summary="Export device inventory as CSV or JSON")
async def export_devices(
    format: str = Query(default="csv", pattern="^(csv|json)$"),
) -> Any:
    """
    Download the full device inventory.
    Use `?format=json` for JSON, default is CSV.
    Metadata is serialised as a JSON string in the CSV format.
    """
    devices = await get_all_devices()
    if format == "json":
        return JSONResponse(devices)

    output = io.StringIO()
    if devices:
        flat = []
        for d in devices:
            row = dict(d)
            if isinstance(row.get("metadata"), dict):
                row["metadata"] = json.dumps(row["metadata"])
            flat.append(row)
        writer = csv.DictWriter(output, fieldnames=flat[0].keys(), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(flat)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=devices_{ts}.csv"},
    )


@app.get(
    "/api/logs",
    response_model=list[SyslogResponse],
    summary="Global syslog full-text search",
)
async def search_all_logs(
    q: str = Query(..., min_length=1, description="Search term (message or source IP)"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max rows to return"),
) -> list[dict[str, Any]]:
    """Search across all syslog entries by message content or source IP."""
    return await search_syslogs(q, limit=limit)


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
