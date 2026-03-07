"""
ARP scanner: discovers devices on a subnet and resolves MAC OUI vendor names.
Requires root/elevated privileges to send raw ARP packets.
"""

import asyncio
import logging
from dataclasses import dataclass, field

from scapy.all import ARP, Ether, srp

from src.identifiers import lookup_vendor

logger = logging.getLogger(__name__)


@dataclass
class Device:
    ip: str
    mac: str
    vendor: str = "Unknown"
    hostnames: list[str] = field(default_factory=list)


async def arp_scan(subnet: str, interface: str | None = None, timeout: int = 2) -> list[Device]:
    """
    Perform an ARP scan on the given subnet (e.g. '192.168.1.0/24').
    Returns a list of Device objects with IP, MAC, and vendor resolved.

    Args:
        subnet:    CIDR notation target (e.g. '192.168.1.0/24').
        interface: Network interface to use (e.g. 'eth0', 'vmbr0.10').
                   If None, scapy picks the default route interface.
        timeout:   Seconds to wait for ARP replies.
    """
    logger.info("Starting ARP scan on %s (iface=%s)", subnet, interface or "default")

    arp_request = ARP(pdst=subnet)
    broadcast = Ether(dst="ff:ff:ff:ff:ff:ff")
    packet = broadcast / arp_request

    kwargs: dict = {"timeout": timeout, "verbose": False}
    if interface:
        kwargs["iface"] = interface

    # srp is blocking — run it in a thread to keep asyncio happy
    loop = asyncio.get_event_loop()
    answered, _ = await loop.run_in_executor(None, lambda: srp(packet, **kwargs))

    # Build device list, then resolve vendors concurrently
    raw_devices = [
        Device(ip=recv.psrc, mac=recv.hwsrc)
        for _, recv in answered
    ]

    # Resolve vendors in parallel
    vendors = await asyncio.gather(*[lookup_vendor(d.mac) for d in raw_devices])
    for device, vendor in zip(raw_devices, vendors):
        device.vendor = vendor

    logger.info("ARP scan complete — %d device(s) found", len(raw_devices))
    return raw_devices
