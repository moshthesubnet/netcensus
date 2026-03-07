"""
ARP scanner: discovers devices on a subnet, resolves MAC OUI vendor names,
and enriches results with Docker and Proxmox identity data.
Requires root/elevated privileges to send raw ARP packets.
"""

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from scapy.all import ARP, Ether, srp

from src.identifiers import (
    DockerInfo,
    ProxmoxInfo,
    lookup_vendor,
    query_docker,
    query_proxmox,
)

logger = logging.getLogger(__name__)


@dataclass
class Device:
    ip: str
    mac: str
    vendor: str = "Unknown"
    # Enriched identity fields
    type: str = "bare-metal"     # "bare-metal" | "docker-container" | "vm" | "lxc"
    name: str | None = None      # Container/VM name when identified
    hostnames: list[str] = field(default_factory=list)
    docker: dict[str, Any] | None = None
    proxmox: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProxmoxConfig:
    host: str
    user: str
    password: str | None = None
    token_id: str | None = None
    token_secret: str | None = None
    verify_ssl: bool = False


async def arp_scan(
    subnet: str,
    interface: str | None = None,
    timeout: int = 2,
    proxmox: ProxmoxConfig | None = None,
) -> list[Device]:
    """
    Perform an ARP scan then enrich results with Docker and Proxmox data.

    Args:
        subnet:    CIDR notation target (e.g. '192.168.1.0/24').
        interface: Network interface (e.g. 'eth0', 'vmbr0.10').
        timeout:   Seconds to wait for ARP replies.
        proxmox:   Optional Proxmox connection config. Pass None to skip.
    """
    logger.info("Starting ARP scan on %s (iface=%s)", subnet, interface or "default")

    arp_request = ARP(pdst=subnet)
    broadcast = Ether(dst="ff:ff:ff:ff:ff:ff")
    packet = broadcast / arp_request

    kwargs: dict = {"timeout": timeout, "verbose": False}
    if interface:
        kwargs["iface"] = interface

    loop = asyncio.get_event_loop()
    answered, _ = await loop.run_in_executor(None, lambda: srp(packet, **kwargs))

    raw_devices = [Device(ip=recv.psrc, mac=recv.hwsrc) for _, recv in answered]
    logger.info("ARP scan complete — %d device(s) found", len(raw_devices))

    if not raw_devices:
        return raw_devices

    # Fan out: OUI lookup + Docker + Proxmox all run concurrently
    proxmox_coro = (
        query_proxmox(
            proxmox.host,
            proxmox.user,
            password=proxmox.password,
            token_id=proxmox.token_id,
            token_secret=proxmox.token_secret,
            verify_ssl=proxmox.verify_ssl,
        )
        if proxmox
        else asyncio.coroutine(lambda: {})()  # empty awaitable
    )

    vendors, docker_map, proxmox_map = await asyncio.gather(
        asyncio.gather(*[lookup_vendor(d.mac) for d in raw_devices]),
        query_docker(),
        proxmox_coro,
    )

    return enrich_devices(raw_devices, vendors, docker_map, proxmox_map)


def enrich_devices(
    devices: list[Device],
    vendors: list[str],
    docker_map: dict[str, DockerInfo],
    proxmox_map: dict[str, ProxmoxInfo],
) -> list[Device]:
    """
    Merge ARP scan results with Docker and Proxmox identity data.

    Matching priority (first match wins):
      1. Docker — matched by IP address.
      2. Proxmox — matched by MAC address.
      3. bare-metal — fallback.
    """
    for device, vendor in zip(devices, vendors):
        device.vendor = vendor

        docker_info: DockerInfo | None = docker_map.get(device.ip)
        proxmox_info: ProxmoxInfo | None = proxmox_map.get(device.mac.lower())

        if docker_info:
            device.type = "docker-container"
            device.name = docker_info.name
            device.docker = {
                "container_id": docker_info.container_id,
                "image": docker_info.image,
                "status": docker_info.status,
                "networks": docker_info.networks,
            }
        elif proxmox_info:
            device.type = proxmox_info.type          # "vm" or "lxc"
            device.name = proxmox_info.name
            device.proxmox = {
                "vm_id": proxmox_info.vm_id,
                "node": proxmox_info.node,
                "status": proxmox_info.status,
            }

    return devices
