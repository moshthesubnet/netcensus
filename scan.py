#!/usr/bin/env python3
"""
CLI entrypoint for the ARP scanner.
Usage: sudo python3 scan.py [subnet] [--iface IFACE]

Example:
    sudo python3 scan.py 192.168.1.0/24
    sudo python3 scan.py 10.0.10.0/24 --iface vmbr0.10
"""

import argparse
import asyncio
import ipaddress
import logging
import socket
import struct
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)


def detect_local_subnet() -> str:
    """Best-effort guess at the local subnet by inspecting the default route."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        # Assume /24 for the detected IP
        parts = ip.split(".")
        return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    except Exception:
        return "192.168.1.0/24"


def parse_args() -> argparse.Namespace:
    detected = detect_local_subnet()
    parser = argparse.ArgumentParser(description="ARP subnet scanner with OUI vendor lookup")
    parser.add_argument(
        "subnet",
        nargs="?",
        default=detected,
        help=f"CIDR subnet to scan (default: {detected})",
    )
    parser.add_argument("--iface", default=None, help="Network interface (e.g. eth0, vmbr0.10)")
    parser.add_argument("--timeout", type=int, default=2, help="ARP reply timeout in seconds")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    # Validate subnet
    try:
        network = ipaddress.ip_network(args.subnet, strict=False)
    except ValueError as exc:
        print(f"Invalid subnet '{args.subnet}': {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"\nScanning {network} ...")
    if args.iface:
        print(f"Interface : {args.iface}")
    print()

    # Import here so scapy's startup noise only appears after our banner
    from src.scanner import arp_scan

    devices = await arp_scan(str(network), interface=args.iface, timeout=args.timeout)

    if not devices:
        print("No devices found. Check interface/subnet or try a longer --timeout.")
        return

    # Pretty-print results
    col_ip     = max(len(d.ip)     for d in devices)
    col_mac    = max(len(d.mac)    for d in devices)
    col_vendor = max(len(d.vendor) for d in devices)

    header = f"{'IP':<{col_ip}}  {'MAC':<{col_mac}}  {'Vendor':<{col_vendor}}"
    print(header)
    print("-" * len(header))
    for d in sorted(devices, key=lambda x: list(map(int, x.ip.split(".")))):
        print(f"{d.ip:<{col_ip}}  {d.mac:<{col_mac}}  {d.vendor}")

    print(f"\n{len(devices)} device(s) found.")


if __name__ == "__main__":
    asyncio.run(main())
