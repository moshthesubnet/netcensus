# Network Discovery & Syslog Monitor

## Project Overview
This is a local network monitoring application that actively scans for devices and passively listens for UDP syslogs. It identifies bare-metal hardware, Docker containers, and Proxmox VMs/LXCs, aggregating everything into a unified dashboard.

## Tech Stack
* **Backend:** Python 3, FastAPI, `asyncio`, `scapy` (for ARP), `aiosqlite`
* **Integrations:** Docker Engine API, Proxmox API (`proxmoxer`), UDP port 514 (Syslog)
* **Database:** SQLite (Relational setup: `devices` and `syslogs` tables)
* **Frontend:** Vanilla JavaScript, HTML5, Tailwind CSS (via CDN)

## File Structure
* `src/main.py`: FastAPI application, API endpoints, and lifespan events (syslog server boot).
* `src/scanner.py`: Asynchronous ARP scanning logic.
* `src/syslog_server.py`: UDP Datagram endpoint listening on port 514. Parses OPNsense logs and general device syslogs.
* `src/identifiers.py`: Logic for MAC OUI lookups, Docker socket querying, and Proxmox API polling.
* `src/database.py`: SQLite schema initialization and async CRUD operations.
* `frontend/index.html`: The single-page dark-mode dashboard.

## Strict Operational Rules
1. **Permissions:** Network scanning (`scapy`) and port 514 binding require elevated privileges. Always remind me to run scripts with `sudo` or execute them with elevated permissions during testing.
2. **VLAN & Interface Handling:** Ensure the ARP scanner allows binding to specific network interfaces or VLAN sub-interfaces (e.g., `vmbr0.10`) to accommodate network segmentation and trunking.
3. **Concurrency:** FastAPI and the UDP Syslog server must run concurrently without blocking each other. Strictly use `asyncio` and non-blocking database calls (`aiosqlite`).
4. **API Polling:** When querying the Proxmox API, handle authentication securely and ensure you map virtual MAC addresses back to their respective nodes and VMs/LXCs.
5. **Database Locks:** Ensure safe asynchronous SQLite connections to prevent database lock errors when both the active scanner and the passive syslog server attempt to write data simultaneously.

## Memory Auto-Update
If we discover workarounds for device APIs, Proxmox hypervisor quirks, or specific OPNsense syslog formatting variations during development, document those workflows in `.claude/rules/` so they are not forgotten.
