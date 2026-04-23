"""
Demo seeder for netcensus.

Populates a fresh SQLite DB with a coherent homelab narrative so anyone
can run the dashboard without real network access.

Call:
    counts = await seed_demo_db("/path/to/demo.db")

Returns a counts dict that the lifespan logger can print and that the
test suite asserts against.
"""
import os
import random
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Narrative data
# ---------------------------------------------------------------------------

_VLANS = [10, 20, 30, 40, 50, 99]  # 6 VLANs

_BARE_METAL = [
    # (alias, ip, mac, vendor, device_type, vlan)
    ("opnsense-gw",  "10.0.10.1",  "00:1a:2b:10:00:01", "Netgate",         "firewall", 10),
    ("usw-core",     "10.0.10.2",  "00:1a:2b:10:00:02", "Ubiquiti",        "switch",   10),
    ("uap-office",   "10.0.10.3",  "00:1a:2b:10:00:03", "Ubiquiti",        "ap",       10),
    ("uap-lab",      "10.0.10.4",  "00:1a:2b:10:00:04", "Ubiquiti",        "ap",       10),
]

_PROXMOX_NODES = [
    ("pve-01", "10.0.20.11", "00:1a:2b:20:00:11", "Supermicro", "hypervisor", 20),
    ("pve-02", "10.0.20.12", "00:1a:2b:20:00:12", "Supermicro", "hypervisor", 20),
]

_VMS = [
    # pve-01 VMs
    ("grafana",      "10.0.20.21", "bc:24:11:20:00:21", "Proxmox",  "vm", 20, "pve-01"),
    ("prometheus",   "10.0.20.22", "bc:24:11:20:00:22", "Proxmox",  "vm", 20, "pve-01"),
    ("postgres-16",  "10.0.20.23", "bc:24:11:20:00:23", "Proxmox",  "vm", 20, "pve-01"),
    ("gitea",        "10.0.20.24", "bc:24:11:20:00:24", "Proxmox",  "vm", 20, "pve-01"),
    # pve-02 VMs
    ("vaultwarden",      "10.0.20.31", "bc:24:11:20:00:31", "Proxmox", "vm", 20, "pve-02"),
    ("home-assistant",   "10.0.20.32", "bc:24:11:20:00:32", "Proxmox", "vm", 20, "pve-02"),
    ("plex",             "10.0.20.33", "bc:24:11:20:00:33", "Proxmox", "vm", 20, "pve-02"),
    ("pihole",           "10.0.20.34", "bc:24:11:20:00:34", "Proxmox", "vm", 20, "pve-02"),
]

_LXCS = [
    # pve-01 LXCs
    ("nginx-proxy",       "10.0.20.41", "bc:24:11:20:01:41", "Proxmox", "lxc", 20, "pve-01"),
    ("cloudflared",       "10.0.20.42", "bc:24:11:20:01:42", "Proxmox", "lxc", 20, "pve-01"),
    # pve-02 LXCs
    ("syslog-ng",         "10.0.20.51", "bc:24:11:20:01:51", "Proxmox", "lxc", 20, "pve-02"),
    ("unifi-controller",  "10.0.20.52", "bc:24:11:20:01:52", "Proxmox", "lxc", 20, "pve-02"),
]

_DOCKER_HOSTS = [
    ("dock-01", "10.0.30.11", "00:1a:2b:30:00:11", "Dell",   "bare-metal", 30),
    ("dock-02", "10.0.30.12", "00:1a:2b:30:00:12", "Dell",   "bare-metal", 30),
    ("dock-03", "10.0.30.13", "00:1a:2b:30:00:13", "HPE",    "bare-metal", 30),
]

_CONTAINERS = [
    # dock-01 (5)
    ("grafana-agent",    "10.0.30.101", "02:42:1e:30:01:01", "Docker", "container", 30, "dock-01"),
    ("loki",             "10.0.30.102", "02:42:1e:30:01:02", "Docker", "container", 30, "dock-01"),
    ("promtail",         "10.0.30.103", "02:42:1e:30:01:03", "Docker", "container", 30, "dock-01"),
    ("cadvisor",         "10.0.30.104", "02:42:1e:30:01:04", "Docker", "container", 30, "dock-01"),
    ("node-exporter",    "10.0.30.105", "02:42:1e:30:01:05", "Docker", "container", 30, "dock-01"),
    # dock-02 (7)
    ("traefik",          "10.0.30.111", "02:42:1e:30:02:01", "Docker", "container", 30, "dock-02"),
    ("postgres-dev",     "10.0.30.112", "02:42:1e:30:02:02", "Docker", "container", 30, "dock-02"),
    ("redis",            "10.0.30.113", "02:42:1e:30:02:03", "Docker", "container", 30, "dock-02"),
    ("minio",            "10.0.30.114", "02:42:1e:30:02:04", "Docker", "container", 30, "dock-02"),
    ("ollama",           "10.0.30.115", "02:42:1e:30:02:05", "Docker", "container", 30, "dock-02"),
    ("opensearch",       "10.0.30.116", "02:42:1e:30:02:06", "Docker", "container", 30, "dock-02"),
    ("n8n",              "10.0.30.117", "02:42:1e:30:02:07", "Docker", "container", 30, "dock-02"),
    # dock-03 (8)
    ("jellyfin",         "10.0.30.121", "02:42:1e:30:03:01", "Docker", "container", 30, "dock-03"),
    ("uptime-kuma",      "10.0.30.122", "02:42:1e:30:03:02", "Docker", "container", 30, "dock-03"),
    ("code-server",      "10.0.30.123", "02:42:1e:30:03:03", "Docker", "container", 30, "dock-03"),
    ("portainer",        "10.0.30.124", "02:42:1e:30:03:04", "Docker", "container", 30, "dock-03"),
    ("authentik-server", "10.0.30.125", "02:42:1e:30:03:05", "Docker", "container", 30, "dock-03"),
    ("authentik-worker", "10.0.30.126", "02:42:1e:30:03:06", "Docker", "container", 30, "dock-03"),
    ("watchtower",       "10.0.30.127", "02:42:1e:30:03:07", "Docker", "container", 30, "dock-03"),
    ("tailscale",        "10.0.30.128", "02:42:1e:30:03:08", "Docker", "container", 30, "dock-03"),
]

_IOT = [
    ("brother-hl-mfp", "10.0.40.11", "00:80:77:40:00:11", "Brother",  "iot", 40),
    ("camera-front",   "10.0.40.12", "9c:8e:cd:40:00:12", "Hikvision","iot", 40),
    ("camera-back",    "10.0.40.13", "9c:8e:cd:40:00:13", "Hikvision","iot", 40),
    ("plug-office",    "10.0.40.14", "68:57:2d:40:00:14", "TP-Link",  "iot", 40),
]

# 1 device_gone alert: a decommissioned VM on VLAN 99
_GONE_DEVICE = (
    "staging-vm-decommissioned",
    "10.0.99.200",
    "bc:24:11:99:00:c8",
    "Proxmox",
    "vm",
    99,
)

# OPNsense filterlog BLOCK syslog lines
_SYSLOG_BLOCKS = [
    (
        "10.0.10.1",
        'filterlog: 5,,,1000000103,vtnet0,match,block,in,4,0x0,,64,12345,0,DF,6,tcp,'
        '1234,10.0.50.55,203.0.113.42,51234,443,0,S',
        "warning",
    ),
    (
        "10.0.10.1",
        'filterlog: 5,,,1000000103,vtnet0,match,block,in,4,0x0,,64,12346,0,DF,17,udp,'
        '1234,10.0.40.12,198.51.100.7,5353,53,20',
        "warning",
    ),
]

# Info syslog lines (not BLOCK)
_SYSLOG_INFO = [
    ("10.0.10.1", "opnsense: DHCP lease 10.0.30.13 assigned to 00:1a:2b:30:00:13", "info"),
    ("10.0.20.11", "proxmox: VM 101 (grafana) started successfully", "info"),
    ("10.0.20.12", "proxmox: CT 201 (syslog-ng) startup complete", "info"),
    ("10.0.30.11", "dockerd: container grafana-agent started (sha256:a1b2c3)", "info"),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def seed_demo_db(db_path: str) -> dict:
    """
    Delete *db_path* if it exists, initialise a fresh schema at that path,
    and populate it with the homelab narrative.

    Returns a counts dict that matches what the tests assert.
    """
    import src.database as _db_module

    # Remove stale DB
    if os.path.exists(db_path):
        os.remove(db_path)

    # Point the database module at the requested path for this seed run.
    _db_module.DB_PATH = db_path

    # Ensure a deterministic sequence for any random values.
    random.seed(20260423)

    now = datetime.now(timezone.utc)

    # --- Schema ---
    await _db_module.init_db()

    # --- Bare-metal (firewall, switch, APs) ---
    for alias, ip, mac, vendor, dtype, vlan in _BARE_METAL:
        meta = {"vlan": vlan}
        await _db_module.upsert_device(mac, ip, vendor, dtype, metadata=meta)
        await _db_module.set_hostname_if_unset(mac, alias)

    # --- Proxmox nodes ---
    for alias, ip, mac, vendor, dtype, vlan in _PROXMOX_NODES:
        meta = {"vlan": vlan, "proxmox_node": alias}
        await _db_module.upsert_device(mac, ip, vendor, dtype, metadata=meta)
        await _db_module.set_hostname_if_unset(mac, alias)

    # --- VMs ---
    for alias, ip, mac, vendor, dtype, vlan, pve_node in _VMS:
        meta = {"vlan": vlan, "proxmox_node": pve_node, "proxmox_type": "vm"}
        await _db_module.upsert_device(mac, ip, vendor, dtype, metadata=meta)
        await _db_module.set_hostname_if_unset(mac, alias)

    # --- LXCs ---
    for alias, ip, mac, vendor, dtype, vlan, pve_node in _LXCS:
        meta = {"vlan": vlan, "proxmox_node": pve_node, "proxmox_type": "lxc"}
        await _db_module.upsert_device(mac, ip, vendor, dtype, metadata=meta)
        await _db_module.set_hostname_if_unset(mac, alias)

    # --- Docker hosts ---
    for alias, ip, mac, vendor, dtype, vlan in _DOCKER_HOSTS:
        meta = {"vlan": vlan, "docker_host": True}
        await _db_module.upsert_device(mac, ip, vendor, dtype, metadata=meta)
        await _db_module.set_hostname_if_unset(mac, alias)

    # --- Containers ---
    for alias, ip, mac, vendor, dtype, vlan, docker_host in _CONTAINERS:
        meta = {"vlan": vlan, "docker_host": docker_host}
        await _db_module.upsert_device(mac, ip, vendor, dtype, metadata=meta)
        await _db_module.set_hostname_if_unset(mac, alias)

    # --- IoT ---
    for alias, ip, mac, vendor, dtype, vlan in _IOT:
        meta = {"vlan": vlan}
        await _db_module.upsert_device(mac, ip, vendor, dtype, metadata=meta)
        await _db_module.set_hostname_if_unset(mac, alias)

    # --- Gone device (disappearance_count > 0 → triggers alert) ---
    alias, ip, mac, vendor, dtype, vlan = _GONE_DEVICE
    meta = {"vlan": vlan, "proxmox_node": "pve-02", "proxmox_type": "vm"}
    await _db_module.upsert_device(mac, ip, vendor, dtype, metadata=meta)
    await _db_module.set_hostname_if_unset(mac, alias)
    # Manually set disappearance_count to 5 so it registers as "gone".
    import aiosqlite
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            "UPDATE devices SET disappearance_count = 5 WHERE mac = ?", (mac,)
        )
        await conn.commit()

    # --- Syslogs ---
    base_ts = now - timedelta(minutes=30)

    # BLOCK lines
    for i, (src_ip, msg, severity) in enumerate(_SYSLOG_BLOCKS):
        ts = (base_ts + timedelta(minutes=i * 5)).isoformat()
        await _db_module.insert_syslog(src_ip, msg, severity=severity, timestamp=ts)

    # Info lines
    for i, (src_ip, msg, severity) in enumerate(_SYSLOG_INFO):
        ts = (base_ts + timedelta(minutes=10 + i * 3)).isoformat()
        await _db_module.insert_syslog(src_ip, msg, severity=severity, timestamp=ts)

    # --- Build counts dict ---
    counts = {
        "vlans":             len(_VLANS),
        "bare_metal":        len(_BARE_METAL) + len(_DOCKER_HOSTS),  # >= 4
        "vms":               len(_VMS),
        "lxcs":              len(_LXCS),
        "containers":        len(_CONTAINERS),
        "iot":               len(_IOT),
        "alerts":            1,   # the gone device
        "syslog_block_lines": len(_SYSLOG_BLOCKS),
    }
    return counts
