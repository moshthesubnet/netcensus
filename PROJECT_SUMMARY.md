# API-Driven Cross-VLAN Network Monitor

> A unified "God View" of every device on your homelab network — bare metal, VMs, LXCs, and containers — discovered without raw sockets, without layer-2 boundaries, and without blind spots.

---

## The Problem

Standard network scanners rely on layer-2 ARP broadcasts. A process runs on a host, sends ARP requests, and maps replies to IP/MAC pairs. This approach has a fundamental flaw in segmented networks: **ARP does not cross VLAN boundaries**. A scanner running on VLAN 30 is completely blind to devices on VLANs 10, 20, or 99 without a dedicated probe on each segment.

The common workarounds — running a scanner per VLAN, promiscuous-mode capture, or flooding every segment — all require root privileges, raw sockets, or brittle host-level configuration. In a homelab with 5+ VLANs, dozens of VMs, and multiple Docker hosts, none of these scale cleanly.

Additionally, layer-2 scanning alone cannot answer: *Is that IP a VM or a bare-metal host? Which Proxmox node is it on? What containers are sharing that host's network stack?* Resolving those questions requires a different approach entirely.

---

## The Solution

This application bypasses layer-2 limits entirely by querying the authoritative sources that already have complete network visibility:

- **OPNsense** — as the edge router, it maintains the global ARP and NDP tables for every VLAN it routes. Its REST API surfaces all of this over a single authenticated HTTPS call.
- **Proxmox** — the hypervisor knows the MAC address, VM name, node assignment, and live status of every guest before a single packet hits the wire.
- **Docker Engine API** — each daemon reports its running containers with their virtual MAC addresses and bridge IPs.

These three sources are queried concurrently every scan cycle and merged into a single SQLite-backed device registry. The result is a real-time dashboard with full-stack context for every endpoint on the network — no raw sockets, no per-VLAN probes, no root required for the core discovery path.

---

## Key Features

- **Cross-VLAN hardware discovery via OPNsense REST API**
  Pulls the global ARP table (IPv4) and NDP neighbour table (IPv6) from OPNsense, covering every VLAN the router is aware of in a single authenticated API call. DHCP leases are fetched separately to auto-populate device hostnames.

- **Multi-node Proxmox VM and LXC inventory**
  Polls one or more Proxmox hosts concurrently using per-node API token credentials. For running QEMU VMs, the QEMU Guest Agent is queried for a live IP address as a fallback when ARP hasn't yet resolved the guest. LXC containers use the `/interfaces` endpoint for the same purpose. All guests — including stopped ones — are tracked by MAC address with their node, VMID, and power state.

- **Distributed Docker container mapping**
  Queries multiple Docker Engine TCP sockets in parallel, enumerating running containers across all bridge networks. Host-networked containers (which share the daemon host's MAC/IP) are correctly attributed back to the physical host's ARP entry rather than stored as phantom IPs.

- **Automatic device naming via OPNsense DHCP**
  Active DHCP leases from OPNsense's dnsmasq are fetched each cycle and used to set hostnames on newly discovered devices. Manual aliases set through the UI always take precedence and are never overwritten by subsequent scans.

- **Integrated real-time syslog receiver**
  An async UDP server (port 514) runs alongside the FastAPI app, accepting RFC 3164 and RFC 5424 messages. OPNsense `filterlog` CSV payloads are parsed into human-readable firewall rule summaries (`[BLOCK] IN on igb0 | tcp 1.2.3.4:443 → 10.30.0.5:8080`). Logs are stored per source IP and linked to the device that sent them. A secondary syslog IP can be configured per device for appliances that send from a different interface than their management IP.

- **Optional supplemental scanning (nmap + SNMP)**
  Nmap ping sweeps can cover subnets not managed by OPNsense. SNMP ARP-cache walks can pull device tables from managed switches. Both sources are folded into the main ARP map with OPNsense data taking priority on conflict.

- **Disappearance tracking and webhook alerts**
  Each scan cycle increments a `disappearance_count` for any device not seen that cycle. When a device crosses a configurable threshold, a `device_gone` webhook fires. New devices trigger a `device_discovered` event. Webhooks POST a structured JSON payload to any HTTP endpoint (e.g. Home Assistant, Slack, ntfy).

- **Device management UI**
  Devices can be assigned human-readable aliases, custom type overrides, and free-text notes — all of which survive subsequent scans. The full inventory can be exported as CSV or JSON. A `/api/health` endpoint reports the last-success timestamp and result count for each of the seven discovery sources.

---

## Architecture & Tech Stack

### Backend
| Component | Technology |
|---|---|
| API framework | **FastAPI** (Python 3.12), served by **Uvicorn** |
| Async runtime | `asyncio` — all I/O is non-blocking; no threads except for blocking SDK calls (Docker, Proxmox) offloaded via `run_in_executor` |
| Database | **SQLite** via `aiosqlite` — two tables: `devices` (keyed by MAC) and `syslogs` (append-only, 30-day rolling retention) |
| HTTP client | `httpx` — async requests to OPNsense API and outbound webhooks |

### External API Integrations
| Integration | API / Transport | Auth method |
|---|---|---|
| OPNsense ARP/NDP | `GET /api/diagnostics/interface/getArp` / `getNdp` | API key + secret (HTTP Basic Auth) |
| OPNsense DHCP | `GET /api/dnsmasq/leases/search` | API key + secret (HTTP Basic Auth) |
| Proxmox VE | `proxmoxer` REST client | Per-node API tokens (`user@pam!token-name`) |
| Proxmox guest IPs | `qemu/{id}/agent/network-get-interfaces`, `lxc/{id}/interfaces` | Same token, best-effort |
| Docker Engine | Docker SDK over TCP (`tcp://host:2375`) or Unix socket | Unauthenticated TCP (LAN-internal) |
| nmap (optional) | Subprocess ping sweep | None (requires `nmap` binary) |
| SNMP (optional) | ARP-cache MIB walk | Community string |

### Frontend
A single-page dark-mode dashboard built with **vanilla JavaScript** and **Tailwind CSS** (CDN). No build step. Served as a static file by FastAPI.

### Design Shift: From Raw Sockets to Authenticated APIs
The original prototype used `scapy` to send raw ARP broadcasts — a technique that requires `CAP_NET_RAW` or running as root and is inherently limited to a single layer-2 segment. The current architecture eliminates that dependency entirely for the core discovery path. OPNsense already has the complete ARP table; querying its API over HTTPS is both more privileged-friendly and more accurate than any local broadcast scan could be. The Proxmox and Docker integrations follow the same philosophy: instead of inferring device identity from network traffic, the application asks the hypervisor and container runtime directly.

---

## Environment Configuration

All integration endpoints and credentials are supplied via environment variables (`.env` file supported via `python-dotenv`):

```
OPNSENSE_URL          # https://10.0.99.1
OPNSENSE_KEY          # API key (Basic Auth username)
OPNSENSE_SECRET       # API secret (Basic Auth password)

PROXMOX_NODES         # JSON array: [{"host":"…","user":"root@pam","token_id":"…","token_secret":"…"}]

DOCKER_HOSTS          # Comma-separated: tcp://10.30.40.2:2375,tcp://10.30.40.4:2375
NMAP_SUBNETS          # Comma-separated CIDRs: 10.0.10.0/24,10.0.20.0/24
SNMP_HOSTS            # JSON array: [{"host":"…","community":"public","port":161}]

SCAN_INTERVAL_SECONDS # Discovery cycle frequency (default: 300)
SYSLOG_PORT           # UDP port for syslog receiver (default: 514, requires root)
ALERT_WEBHOOK_URL     # HTTP endpoint for device_discovered / device_gone events
ALERT_DISAPPEARANCE_THRESHOLD  # Scans missed before firing device_gone (default: 3)
DB_PATH               # SQLite file path (default: ./network_monitor.db)
```

---

## Phase-by-Phase Development History

### Phase 1 — Initial Prototype (ARP + Basic Identity)
**Commit:** `8205eb7 Initial commit`

The starting point. A bare Python project with:
- `src/scanner.py` — async ARP scan via `scapy.srp()` wrapped in `run_in_executor` to avoid blocking the event loop. Bound to a configurable interface (`SCAN_IFACE`).
- `src/identifiers.py` — MAC OUI vendor lookup using `mac-vendor-lookup` (offline bundled database, async API).
- `scan.py` — CLI entrypoint for ad-hoc scans with `--json` output and subnet/iface flags.
- `Device` dataclass with `ip`, `mac`, `vendor`, `hostnames` fields.
- `requirements.txt` with initial dependencies: `scapy`, `mac-vendor-lookup`, `fastapi`, `aiosqlite`.

**Limitations at this stage:** Single VLAN, root required for ARP, no persistence, no web UI.

---

### Phase 2 — Docker & Proxmox Identity Enrichment
**Commits:** `163d983`, `fdb205a`, `de05b50`, `9207762`, `ad3cca9`, `b8e2c61`

Layered in the two hypervisor/container integrations:

#### Docker Discovery (`src/identifiers.py` — `query_docker`)
- Added `DockerInfo` dataclass: `name`, `container_id`, `image`, `status`, `networks`, `mac`, `network_mode`, `host_ip`, `docker_host`.
- Queries the Docker SDK over TCP sockets (`DOCKER_HOSTS` env var, comma-separated).
- Falls back to local Unix socket (`unix:///var/run/docker.sock`) when no TCP hosts are configured.
- Host-networked containers (`--network host`) are stored under a synthetic `hostnet:<id>` key and later resolved back to the physical host's ARP entry in the merge step — preventing phantom IPs.
- Multiple Docker daemons queried concurrently via `run_in_executor`.

#### Proxmox Discovery (`src/identifiers.py` — `query_proxmox`)
- Added `ProxmoxInfo` dataclass: `name`, `vm_id`, `type` (vm/lxc), `node`, `status`, `ip`.
- `PROXMOX_NODES` env var: JSON array of per-node credential dicts — supports separate API token per physical host.
- Authenticates via `proxmoxer` using API tokens (`user@pam!token-name` + UUID secret) or password fallback.
- Enumerates all QEMU VMs and LXC containers per node.
- MAC extraction: regex patterns `_QEMU_MAC_RE` (covers `virtio`, `e1000`, `e1000e`, `vmxnet3`, `rtl8139`, `ne2k_pci`) and `_LXC_MAC_RE` (`hwaddr=`) parse the Proxmox net config strings.
- QEMU Guest Agent fallback (`agent/network-get-interfaces`): for running VMs, queries the guest agent for a live IPv4 address when ARP hasn't resolved it yet. Filters out loopback and link-local addresses.
- LXC interface fallback (`lxc/{vmid}/interfaces`): queries the `/interfaces` endpoint to get the live IP of running LXC containers, same filtering applied.
- All nodes queried concurrently using `asyncio.gather` + `run_in_executor`.

---

### Phase 3 — SQLite Persistence, FastAPI Endpoints & Background Scan Loop
**Commit:** `c5366b8`

The project became a running service:

#### Database Layer (`src/database.py`)
- `devices` table keyed by MAC address with columns: `mac`, `ip`, `vendor`, `device_type`, `alias`, `first_seen`, `last_seen`, `metadata` (JSON blob).
- `syslogs` table: append-only log storage keyed by `source_ip` with `timestamp`, `severity`, `message`. Index on `source_ip`.
- `upsert_device()`: `INSERT … ON CONFLICT DO UPDATE` — alias column intentionally excluded from update so manual labels survive re-scans. NULL `ip`/`ipv6` never overwrites a real stored address.
- `set_hostname_if_unset()`: only sets alias from DHCP/Proxmox when `alias IS NULL` — manual aliases always win.
- `get_all_devices()`: returns rows ordered by `last_seen DESC`.
- `get_logs_for_ip()`: most recent 50 syslog rows for a given source IP.

#### FastAPI Application (`src/main.py`)
- `GET /api/devices` — list all devices.
- `GET /api/logs/{ip}` — last 50 syslogs for a device IP.
- `PUT /api/devices/{mac}/alias` — set human-readable alias.
- Background scan loop via `asyncio.create_task(_scan_loop())` inside the `lifespan` context manager.
- Concurrent discovery: `asyncio.gather(query_opnsense(), query_proxmox(), query_docker(), ...)`.
- Merge logic: OPNsense ARP → Proxmox cross-reference → Docker upserts (independent).

#### Phase 3.5 — Async Syslog Receiver (`src/syslog_server.py`)
**Commit:** `40f7ee8`
- `SyslogProtocol(asyncio.DatagramProtocol)` — UDP server on port 514.
- Parses **RFC 3164** (`<PRI>Mmm DD HH:MM:SS HOSTNAME TAG: MSG`).
- Parses **RFC 5424** (`<PRI>VERSION TIMESTAMP HOSTNAME APP PROCID MSGID SD MSG`).
- OPNsense `filterlog` CSV parsing: converts raw comma-separated firewall log fields into `[BLOCK] IN on igb0 | tcp src:port → dst:port` human-readable format.
- PRI decoding: extracts severity (0–7) and facility from the priority byte.
- RFC 3164 timestamp parsing handles the year-rollover boundary (Dec→Jan).
- rsyslog relay support: when UDP source is `127.0.0.1`, uses the HOSTNAME field from the message as the real source IP.
- DB writes scheduled as `asyncio.create_task` to never block the receive loop.
- Runs concurrently with FastAPI; transport started in `lifespan`, closed on shutdown.

---

### P1 Audit Fixes — Visibility & Reliability
**Commit:** `c48ce8a Audit fixes: P1 + P2 visibility and reliability improvements`

A targeted reliability pass fixing schema and source issues found in testing:

#### Database Migrations (`src/database.py`)
- `_migrate_devices_ip_nullable()`: rebuilds the `devices` table if `ip` has a `NOT NULL` constraint from older schema versions, converting empty strings to `NULL`. Safe to run repeatedly.
- `_migrate_add_columns()`: idempotently adds new columns to existing databases:
  - `first_seen` — ISO-8601 UTC timestamp of first discovery.
  - `metadata` — JSON blob for Proxmox/Docker structured data.
  - `ipv6` — IPv6 address from NDP table.
  - `custom_type` — user override for device type.
  - `disappearance_count` — incremented each scan the device is absent.
  - `notes` — free-text operator annotation.
  - `scan_count` — total number of times device has been seen.
  - `syslog_ip` — secondary IP for syslog lookup (for multi-interface devices).

#### OPNsense Module (`src/opnsense.py`) — extracted from `main.py`
- `query_opnsense()`: fetches IPv4 ARP table via `GET /api/diagnostics/interface/getArp`. Handles both list response and `{"arp": [...]}` envelope. Filters multicast/broadcast/incomplete entries.
- `query_opnsense_dhcp()`: fetches active DHCP leases via `GET /api/dnsmasq/leases/search`. Accepts both `hwaddr` and `mac` field names (dnsmasq vs ISC/Kea). Excludes entries with IP-shaped or empty hostnames.
- `query_opnsense_ndp()`: fetches IPv6 NDP neighbour table via `GET /api/diagnostics/interface/getNdp`. Skips link-local (`fe80:`) addresses — only globally routable IPv6 addresses are stored.
- All three functions use `httpx.AsyncClient(verify=False)` with `urllib3` InsecureRequestWarning suppressed (expected with OPNsense's self-signed cert).

#### Upsert Improvements
- `disappearance_count` resets to 0 on every successful upsert (`ON CONFLICT DO UPDATE`).
- `scan_count` increments by 1 each time a device is seen.
- NDP-only devices (IPv6 with no ARP entry) are now upserted as their own rows.
- Proxmox-only devices (offline VMs not in ARP) upserted with their last-known IP.

---

### P2 Audit Fixes — Multi-Source Merge & OPNsense Replacement
**Commits:** `5acb0be`, `b8e2c61`, `9207762`, `ad3cca9`

The most significant architectural change: **scapy ARP scanning removed entirely** as the primary discovery source, replaced by the OPNsense global ARP table.

#### OPNsense as Primary ARP Source
- Replaced `scapy.srp()` with `query_opnsense()` API call — no raw sockets, no root required for discovery.
- Covers all VLANs the OPNsense router handles in a single API call.
- The `src/scanner.py` file (scapy-based) retained for optional CLI use but no longer part of the main discovery loop.

#### Multi-Source Merge in `_run_scan_once()` (`src/main.py`)
Seven sources now run concurrently via `asyncio.gather`:
1. `query_opnsense()` → ARP map (MAC → IPv4)
2. `query_opnsense_ndp()` → NDP map (MAC → IPv6)
3. `query_opnsense_dhcp()` → DHCP map (MAC → hostname)
4. `query_proxmox(PROXMOX_NODES)` → Proxmox map (MAC → ProxmoxInfo)
5. `query_docker(DOCKER_HOSTS)` → Docker map (IP → DockerInfo)
6. `query_nmap(NMAP_SUBNETS)` → nmap map (MAC → IPv4) — optional
7. `query_snmp(SNMP_HOSTS)` → SNMP map (MAC → IPv4) — optional

Merge priority order:
- OPNsense ARP takes precedence on IP conflict with nmap/SNMP.
- nmap and SNMP results folded in only for MACs not already in ARP table.
- Proxmox entries: if MAC is in ARP, enriched with VM metadata; if not in ARP (offline guest), upserted with Proxmox-supplied IP from guest agent.
- NDP-only entries (IPv6, no ARP match, no Proxmox match): stored with NULL IPv4.
- Docker entries: upserted independently; host-net containers resolved via reverse ARP map.

#### Per-Node Proxmox Credentials
- `PROXMOX_NODES` is a JSON array — each element is an independent credential set.
- Allows different API tokens per physical Proxmox host.
- All nodes queried concurrently.

---

### P3 — Enriched Discovery & Additional Sources
**Commit:** `d183ca0 Add P3 + P4 features: enriched discovery, device management, and dashboard improvements`

#### nmap Integration (`src/nmap_scanner.py`)
- `query_nmap(subnets)`: runs `nmap -sn -oX -` as an async subprocess against configured CIDRs.
- Parses nmap's XML output to extract `ipv4` + `mac` address pairs.
- Only hosts with MAC addresses (L2-reachable) are returned — remote-ping-only hosts skipped since the device table is keyed by MAC.
- 120-second per-subnet timeout. Graceful fallback if `nmap` binary not found.
- Controlled by `NMAP_SUBNETS` env var (comma-separated CIDRs).

#### SNMP Integration (`src/snmp_scanner.py`)
- `query_snmp(hosts)`: walks `ipNetToMediaPhysAddress` MIB OID `1.3.6.1.2.1.4.22.1.2` via `snmpwalk` subprocess.
- Parses `Hex-STRING:` and `STRING:` output formats; normalises to `aa:bb:cc:dd:ee:ff` form.
- IP extracted from OID suffix (`.ifIndex.a.b.c.d`).
- 15-second per-host timeout. Graceful fallback if `snmpwalk` not found.
- Controlled by `SNMP_HOSTS` env var (JSON array of `{host, community, port}` dicts).

#### New API Endpoints (`src/main.py`)
- `PUT /api/devices/{mac}/notes` — persist/clear free-text operator notes.
- `PUT /api/devices/{mac}/syslog-ip` — set a secondary syslog lookup IP for multi-interface devices (e.g. OPNsense firewall with separate management and LAN IPs).
- `PUT /api/devices/{mac}/type` — override auto-detected device type; pass null to clear.
- `GET /api/devices/export` — download full inventory as CSV or JSON (`?format=csv|json`). CSV serialises `metadata` as a JSON string column.
- `GET /api/logs` — global syslog full-text search across all entries (`?q=term&limit=N`).
- `GET /api/health` — per-source health status: `ok` / `stale` / `unknown`, last-ok timestamp, last result count.

#### Disappearance Tracking & Webhook Alerting
- `update_disappearance_counts(seen_macs)`: increments `disappearance_count` for every device NOT seen in the current scan cycle.
- `ALERT_WEBHOOK_URL`: when set, the scanner POSTs JSON payloads to this URL:
  - `device_discovered` — new MAC seen for the first time.
  - `device_gone` — device's `disappearance_count` reaches `ALERT_DISAPPEARANCE_THRESHOLD` (default: 3 consecutive missed scans).
- Payload includes: `event`, `timestamp`, `device.mac`, `device.ip`, `device.alias`, `device.vendor`, `device.device_type`, `device.last_seen`.
- Webhook delivery is fire-and-forget with a 5-second timeout; failures logged as warnings.

#### Source Health Tracking
- In-memory `_source_health` dict tracking `last_ok` timestamp and `last_count` per source.
- Updated after every scan via `_record_source(name, count)`.
- `/api/health` computes staleness against `SCAN_INTERVAL * 2` threshold.

#### Syslog Purge
- `purge_old_syslogs(days=30)`: deletes syslog entries older than 30 days, called once per scan cycle.

---

### P4 — Dashboard & Device Management UI
**Commit:** `d183ca0` (same as P3)

Major frontend overhaul (`frontend/index.html`):

#### Header / Stats Bar
- Per-type device count chips: Total, Bare-metal, Docker, VM, LXC — all live-updated on each refresh.
- Per-source health indicator dots: OPNsense ARP, DHCP, Proxmox, Docker, NDP, nmap, SNMP — coloured green/amber/red based on `/api/health`.
- Animated pulsing live-dot + "Last updated" timestamp.
- Manual Refresh button with spinning icon during fetch.

#### Device Table
- Columns: checkbox, type-icon, IP, MAC, Vendor, Type badge, Name/Alias, Last Seen, expand arrow.
- Colour-coded type badges: bare-metal (gray), vm (amber), lxc (purple), docker-container (cyan), with icon per type.
- Client-side search/filter input: filters across IP, MAC, vendor, alias in real-time.
- Filter result count shown inline.
- Disappearance count warning indicator on rows where count > 0.
- Rows are clickable to open the slide-in detail panel.

#### Bulk Action Bar
- Checkbox select-all / individual row selection.
- Bulk retype: applies a chosen device type to all selected MACs via sequential `PUT /api/devices/{mac}/type` calls.
- Bulk export: downloads a JSON blob of only the selected devices.
- Selected count label, Clear button.

#### Slide-in Detail Panel
- Slides in from the right with `transform: translateX` CSS transition; overlay backdrop.
- Header: type badge, device name/alias, IPv4, IPv6 (hidden if absent), MAC, vendor, first-seen, disappearance warning.
- **Docker metadata block**: container status, image tag, short container ID, network names, and Docker host (resolved to alias if set) — shown only for docker-container devices.
- **Host-network containers block**: lists all `--network host` containers running on a device; shown on any device type when present (see P5).
- **Proxmox metadata block**: node name, VMID, power status, proxmox type (VM/LXC) — shown only for vm/lxc devices.
- **Alias editor**: inline text input + Save button; calls `PUT /api/devices/{mac}/alias`.
- **Type override**: dropdown of all device types + Save/Clear buttons; calls `PUT /api/devices/{mac}/type`.
- **Notes field**: multi-line textarea + Save button; calls `PUT /api/devices/{mac}/notes`.
- **Syslog IP override**: text input for secondary IP + Save/Clear; calls `PUT /api/devices/{mac}/syslog-ip`.
- **Syslog viewer**: fetches `/api/logs/{syslog_ip_or_primary_ip}`, colour-coded by severity (emergency=red, warning=amber, info=blue, debug=gray). Severity badge + timestamp + message per row.
- Export buttons (CSV / JSON) in the filter bar.

---

### P5 — Host-Network Container Fix & Docker Host Attribution

#### Problem: Host-Network Containers Overwriting Docker Host Identity
Containers running with `--network host` share the daemon host's MAC address and IP — they have no independent network identity. The previous merge logic upserted these containers directly onto the host device record, overwriting its `device_type` with `docker-container` and its `vendor` with `"Docker"`. If multiple host-network containers ran on the same host (e.g. rustdesk alongside logspout), each scan cycle the last container processed would win, clobbering all prior metadata.

#### Fix: Accumulate Host-Network Containers Without Overwriting Host Identity (`src/main.py`, `src/database.py`)
- During the Docker merge loop, host-network containers are no longer immediately upserted. Instead they are collected into `_host_net_containers: dict[str, list[dict]]`, keyed by the resolved host MAC.
- After the main loop, `merge_host_containers(mac, containers)` is called once per host. This function reads the host device's existing `metadata` JSON, injects `host_network_containers` as a list, and writes it back — **without touching `device_type`, `vendor`, or any other column**.
- Result: the Docker host retains its original `bare-metal` type and vendor identity. Its metadata blob now carries a `host_network_containers` array listing every `--network host` container running on it.

#### New Database Function: `merge_host_containers` (`src/database.py`)
- Reads current `metadata` for the device, merges in the `host_network_containers` key, and writes back via a targeted `UPDATE devices SET metadata = ? WHERE mac = ?`.
- Safe to call repeatedly — each scan cycle replaces the full list with the current snapshot.

#### Frontend: Host-Network Containers Panel (`frontend/index.html`)
- New "Host-Network Containers" panel in the slide-in detail view, hidden by default.
- Shown whenever `device.metadata.host_network_containers` is a non-empty array.
- Renders one card per container: name, image, status (colour-coded), short container ID.
- Appears on any device type — a bare-metal Docker host correctly shows its host-networked containers without being relabelled as a `docker-container`.

---

#### Docker Host Attribution (`src/identifiers.py`, `src/main.py`, `frontend/index.html`)
- Added `docker_host: str = ""` field to the `DockerInfo` dataclass.
- In `_fetch_one`, populated for every container — both bridge-networked and host-networked:
  - TCP hosts: IP extracted from the URL (`tcp://10.30.40.2:2375` → `"10.30.40.2"`).
  - Local Unix socket: `"localhost"`.
- `docker_host` is stored in every container's `metadata` JSON blob via `docker_meta`.
- **Frontend**: The Docker Container Details panel now includes a **Host** row. At render time, `allDevices` is searched for a device whose `ip` matches `metadata.docker_host`. If found and aliased, displays `"DockerHost1 (10.30.40.2)"`; if no alias, displays the raw IP. Setting an alias on the Docker host device retroactively improves the label for all containers on that host without any re-scan.

---

#### Logspout Syslog Forwarding (Deployment Note)
To stream container stdout/stderr logs from Docker hosts into the syslog receiver, deploy one Logspout container per Docker host:

```bash
sudo docker run -d --name logspout --restart=always \
  -e SYSLOG_HOSTNAME=$(hostname) \
  -v /var/run/docker.sock:/var/run/docker.sock \
  gliderlabs/logspout syslog+udp://MONITOR_IP:514
```

- Logspout mounts the Docker socket, tails all running container logs, and forwards them as UDP syslog datagrams — no daemon restart or container recreation required.
- Messages arrive from the Docker host's IP, so logs are attributed to the host device row in the dashboard. The container name is embedded in the syslog message body.
- The monitoring app's syslog receiver (`src/syslog_server.py`) already handles these without modification — UDP port 514, RFC 3164 format.

---

## File Structure

```
src/
  main.py           FastAPI app, lifespan, scan loop, all API endpoints
  database.py       SQLite schema, migrations, async CRUD (devices + syslogs)
  opnsense.py       OPNsense ARP, NDP, and DHCP REST API clients
  identifiers.py    Docker (multi-host) and Proxmox (multi-node) discovery
  nmap_scanner.py   Optional nmap subprocess ping sweep
  snmp_scanner.py   Optional SNMP ARP-cache MIB walk
  syslog_server.py  Async UDP syslog receiver (RFC 3164, RFC 5424, filterlog)
  scanner.py        Legacy scapy ARP scanner (CLI use only)

frontend/
  index.html        Single-page dark-mode dashboard (vanilla JS + Tailwind CDN)

scan.py             CLI entrypoint for manual ARP scans
requirements.txt    Python dependencies
```

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serve the dashboard HTML |
| `GET` | `/api/devices` | List all devices (filterable: `device_type`, `search`, `since`; paginated: `limit`, `offset`) |
| `GET` | `/api/devices/export` | Download inventory as CSV or JSON (`?format=csv\|json`) |
| `GET` | `/api/logs/{ip}` | Last 50 syslogs for a device IP |
| `GET` | `/api/logs` | Global syslog search (`?q=term&limit=N`) |
| `PUT` | `/api/devices/{mac}/alias` | Set human-readable alias |
| `PUT` | `/api/devices/{mac}/type` | Override device type (null to clear) |
| `PUT` | `/api/devices/{mac}/notes` | Set/clear operator notes |
| `PUT` | `/api/devices/{mac}/syslog-ip` | Set/clear secondary syslog IP |
| `GET` | `/api/health` | Per-source discovery health status |
