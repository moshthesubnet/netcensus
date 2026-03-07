#!/usr/bin/env python3
"""
CLI entrypoint for the network scanner (Phase 2).
Discovers devices via ARP, then enriches with Docker and Proxmox identity.

Usage:
    sudo python3 scan.py [subnet] [options]

Examples:
    sudo python3 scan.py
    sudo python3 scan.py 192.168.1.0/24 --json
    sudo python3 scan.py 10.0.10.0/24 --iface vmbr0.10 --json
    sudo python3 scan.py --proxmox-host 10.0.0.1 --proxmox-user root@pam --proxmox-password secret
    sudo python3 scan.py --proxmox-host 10.0.0.1 --proxmox-user root@pam \\
                         --proxmox-token-id root@pam!scanner --proxmox-token-secret <uuid>

Proxmox credentials can also be supplied via environment variables:
    PROXMOX_HOST, PROXMOX_USER, PROXMOX_PASSWORD,
    PROXMOX_TOKEN_ID, PROXMOX_TOKEN_SECRET, PROXMOX_VERIFY_SSL
"""

import argparse
import asyncio
import ipaddress
import json
import logging
import os
import socket
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)


def detect_local_subnet() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        parts = ip.split(".")
        return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    except Exception:
        return "192.168.1.0/24"


def parse_args() -> argparse.Namespace:
    detected = detect_local_subnet()
    p = argparse.ArgumentParser(
        description="ARP network scanner with Docker + Proxmox enrichment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Scan options
    p.add_argument("subnet", nargs="?", default=detected,
                   help=f"CIDR subnet to scan (default: {detected})")
    p.add_argument("--iface", default=None,
                   help="Network interface, e.g. eth0, vmbr0.10")
    p.add_argument("--timeout", type=int, default=2,
                   help="ARP reply timeout in seconds (default: 2)")
    p.add_argument("--json", action="store_true",
                   help="Output results as JSON instead of a table")
    p.add_argument("--no-docker", action="store_true",
                   help="Skip Docker socket query")

    # Proxmox options (env vars are fallbacks)
    px = p.add_argument_group("Proxmox (optional)")
    px.add_argument("--proxmox-host",
                    default=os.environ.get("PROXMOX_HOST"),
                    help="Proxmox hostname or IP  [env: PROXMOX_HOST]")
    px.add_argument("--proxmox-user",
                    default=os.environ.get("PROXMOX_USER", "root@pam"),
                    help="API user  [env: PROXMOX_USER]")
    px.add_argument("--proxmox-password",
                    default=os.environ.get("PROXMOX_PASSWORD"),
                    help="Password auth  [env: PROXMOX_PASSWORD]")
    px.add_argument("--proxmox-token-id",
                    default=os.environ.get("PROXMOX_TOKEN_ID"),
                    help="API token id, e.g. root@pam!mytoken  [env: PROXMOX_TOKEN_ID]")
    px.add_argument("--proxmox-token-secret",
                    default=os.environ.get("PROXMOX_TOKEN_SECRET"),
                    help="API token UUID secret  [env: PROXMOX_TOKEN_SECRET]")
    px.add_argument("--proxmox-verify-ssl", action="store_true",
                    default=os.environ.get("PROXMOX_VERIFY_SSL", "").lower() in ("1", "true"),
                    help="Verify TLS certificate (default: off for self-signed)")

    return p.parse_args()


def build_proxmox_config(args: argparse.Namespace):
    """Return a ProxmoxConfig if the host is provided, else None."""
    if not args.proxmox_host:
        return None

    from src.scanner import ProxmoxConfig
    return ProxmoxConfig(
        host=args.proxmox_host,
        user=args.proxmox_user,
        password=args.proxmox_password,
        token_id=args.proxmox_token_id,
        token_secret=args.proxmox_token_secret,
        verify_ssl=args.proxmox_verify_ssl,
    )


# Type-to-display label and colour code (ANSI, table mode only)
_TYPE_LABEL = {
    "bare-metal":        ("Bare-metal",  "\033[0m"),
    "docker-container":  ("Docker",      "\033[36m"),
    "vm":                ("VM",          "\033[33m"),
    "lxc":               ("LXC",         "\033[35m"),
}


def print_table(devices) -> None:
    col_ip     = max(len(d.ip)              for d in devices)
    col_mac    = max(len(d.mac)             for d in devices)
    col_vendor = max(len(d.vendor)          for d in devices)
    col_type   = max(len(d.type)            for d in devices)
    col_name   = max(len(d.name or "")      for d in devices)

    header = (
        f"{'IP':<{col_ip}}  {'MAC':<{col_mac}}  "
        f"{'Vendor':<{col_vendor}}  {'Type':<{col_type}}  {'Name':<{col_name}}"
    )
    print(header)
    print("─" * len(header))

    for d in sorted(devices, key=lambda x: list(map(int, x.ip.split(".")))):
        label, colour = _TYPE_LABEL.get(d.type, (d.type, "\033[0m"))
        reset = "\033[0m"
        print(
            f"{d.ip:<{col_ip}}  {d.mac:<{col_mac}}  "
            f"{d.vendor:<{col_vendor}}  {colour}{label:<{col_type}}{reset}  "
            f"{d.name or '':<{col_name}}"
        )


async def main() -> None:
    args = parse_args()

    try:
        network = ipaddress.ip_network(args.subnet, strict=False)
    except ValueError as exc:
        print(f"Invalid subnet '{args.subnet}': {exc}", file=sys.stderr)
        sys.exit(1)

    if not args.json:
        print(f"\nScanning {network} ...")
        print(f"  Docker   : {'disabled' if args.no_docker else 'enabled'}")
        print(f"  Proxmox  : {args.proxmox_host or 'not configured'}\n")

    from src.scanner import arp_scan

    # Temporarily suppress identifiers logging when --no-docker is set
    if args.no_docker:
        import unittest.mock as mock
        import src.identifiers as ident_mod
        patcher = mock.patch.object(ident_mod, "query_docker", return_value={})
        patcher.start()

    proxmox_cfg = build_proxmox_config(args)

    devices = await arp_scan(
        str(network),
        interface=args.iface,
        timeout=args.timeout,
        proxmox=proxmox_cfg,
    )

    if not devices:
        msg = "No devices found. Try a longer --timeout or check the interface."
        if args.json:
            print(json.dumps({"devices": [], "count": 0, "message": msg}))
        else:
            print(msg)
        return

    if args.json:
        output = {
            "subnet": str(network),
            "count": len(devices),
            "devices": [d.to_dict() for d in sorted(
                devices, key=lambda x: list(map(int, x.ip.split(".")))
            )],
        }
        print(json.dumps(output, indent=2))
    else:
        print_table(devices)
        counts = {}
        for d in devices:
            counts[d.type] = counts.get(d.type, 0) + 1
        summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
        print(f"\n{len(devices)} device(s) found — {summary}")


if __name__ == "__main__":
    asyncio.run(main())
