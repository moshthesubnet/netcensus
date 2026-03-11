# Network Monitor

A unified dashboard for every device on your homelab network — bare metal, VMs, LXCs, and containers — discovered without raw sockets, without layer-2 boundaries, and without blind spots.

See [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) for full architecture and feature details.

---

## How it works

Standard ARP scanning can't cross VLAN boundaries. This app bypasses that entirely by querying the sources that already have complete network visibility:

- **OPNsense** — the edge router's global ARP/NDP table covers every VLAN in a single API call
- **Proxmox** — the hypervisor reports every VM and LXC by MAC before a packet hits the wire
- **Docker Engine API** — each daemon reports running containers with their virtual MACs and IPs

These are queried concurrently each scan cycle and merged into a SQLite-backed device registry. An async UDP syslog receiver (port 514) runs alongside the API, parsing OPNsense `filterlog` payloads into human-readable firewall summaries.

---

## Requirements

- Python 3.11+
- OPNsense with API access enabled (core requirement)
- Proxmox API token (optional)
- Docker Engine TCP sockets exposed (optional)
- `nmap` on the host (optional, for supplemental subnet sweeps)
- Root / `NET_ADMIN` capability only if binding to port 514

---

## Setup

```bash
git clone https://github.com/your-username/network-monitor.git
cd network-monitor

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your OPNsense/Proxmox/Docker credentials
```

---

## Running

```bash
# Requires root only if using port 514 for syslog
sudo python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000

# Or use the start script:
sudo ./start.sh
```

Dashboard: `http://<host-ip>:8000`
API docs: `http://<host-ip>:8000/docs`
Syslog: UDP `<host-ip>:514`

---

## Configuration

All configuration is via environment variables. Copy `.env.example` to `.env` and fill in your values.

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPNSENSE_URL` | Yes | — | OPNsense base URL (e.g. `https://192.168.1.1`) |
| `OPNSENSE_KEY` | Yes | — | OPNsense API key |
| `OPNSENSE_SECRET` | Yes | — | OPNsense API secret |
| `PROXMOX_NODES` | No | — | JSON array of Proxmox node credentials |
| `DOCKER_HOSTS` | No | — | Comma-separated Docker TCP socket URLs |
| `SCAN_INTERVAL_SECONDS` | No | `300` | Seconds between scan cycles |
| `SYSLOG_PORT` | No | `514` | UDP port for the syslog receiver |
| `NMAP_SUBNETS` | No | — | CIDRs for supplemental nmap sweeps |
| `SNMP_HOSTS` | No | — | JSON array of SNMP hosts to walk |
| `ALERT_WEBHOOK_URL` | No | — | HTTP endpoint for device alerts |
| `ALERT_DISAPPEARANCE_THRESHOLD` | No | `3` | Missed scans before firing a `device_gone` alert |
| `DB_PATH` | No | `network_monitor.db` | SQLite database path |

---

## Project structure

```
src/
  main.py           # FastAPI app, endpoints, scan lifecycle
  scanner.py        # ARP scan (scapy, optional fallback)
  opnsense.py       # OPNsense ARP/NDP/DHCP API client
  identifiers.py    # MAC OUI lookup, Docker, Proxmox API
  syslog_server.py  # Async UDP syslog receiver + parser
  database.py       # SQLite schema and async CRUD
  nmap_scanner.py   # Optional nmap sweep integration
  snmp_scanner.py   # Optional SNMP ARP-cache walk
frontend/
  index.html        # Single-page dark-mode dashboard
```
