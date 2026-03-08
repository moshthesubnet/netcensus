"""
Device identification helpers:
  - MAC OUI vendor lookup   (offline bundled database)
  - Docker socket querying  (local /var/run/docker.sock)
  - Proxmox API polling     (QEMU VMs + LXC containers)
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

from mac_vendor_lookup import AsyncMacLookup, VendorNotFoundError

logger = logging.getLogger(__name__)

_mac_lookup = AsyncMacLookup()

# Matches MAC in QEMU net strings:  virtio=AA:BB:CC:DD:EE:FF,...
_QEMU_MAC_RE = re.compile(
    r"(?:virtio|e1000|e1000e|vmxnet3|rtl8139|ne2k_pci)=([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})",
    re.I,
)
# Matches MAC in LXC net strings:  ...,hwaddr=AA:BB:CC:DD:EE:FF,...
_LXC_MAC_RE = re.compile(
    r"hwaddr=([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})",
    re.I,
)


# ---------------------------------------------------------------------------
# OUI vendor lookup
# ---------------------------------------------------------------------------

async def lookup_vendor(mac: str) -> str:
    """Return the OUI vendor name for a MAC address, or 'Unknown' if not found."""
    try:
        return await _mac_lookup.lookup(mac)
    except (VendorNotFoundError, KeyError, ValueError):
        return "Unknown"
    except Exception as exc:
        logger.debug("OUI lookup failed for %s: %s", mac, exc)
        return "Unknown"


# ---------------------------------------------------------------------------
# Docker socket
# ---------------------------------------------------------------------------

@dataclass
class DockerInfo:
    name: str
    container_id: str
    image: str
    status: str
    networks: list[str]
    mac: str = ""          # MAC address of the container's network interface


async def query_docker(hosts: list[str] | None = None) -> dict[str, DockerInfo]:
    """
    Enumerate running containers from one or more Docker hosts.

    Args:
        hosts: List of Docker base URLs to query, e.g.
               ['tcp://10.30.40.2:2375', 'tcp://10.30.40.4:2375', 'tcp://10.30.40.6:2375'].
               If None or empty, falls back to the local socket
               at unix:///var/run/docker.sock.

    Returns a dict keyed by container IP address. Results from all hosts
    are merged; later hosts win on IP collision.
    """
    try:
        import docker  # type: ignore
    except ImportError:
        logger.warning("docker SDK not installed — skipping Docker discovery")
        return {}

    targets: list[str] = hosts if hosts else ["unix:///var/run/docker.sock"]

    def _fetch_one(base_url: str) -> dict[str, DockerInfo]:
        """Query a single Docker host and return its container IP map."""
        try:
            client = docker.DockerClient(base_url=base_url, timeout=5)
        except Exception as exc:
            logger.warning("Cannot connect to Docker host %s: %s", base_url, exc)
            return {}

        result: dict[str, DockerInfo] = {}
        try:
            for container in client.containers.list():
                attrs = container.attrs
                networks: dict[str, Any] = attrs.get("NetworkSettings", {}).get("Networks", {})
                net_names = list(networks.keys())
                image_tags = container.image.tags
                image = image_tags[0] if image_tags else container.image.short_id

                for _net_name, net_cfg in networks.items():
                    ip = net_cfg.get("IPAddress", "")
                    if not ip:
                        continue
                    result[ip] = DockerInfo(
                        name=container.name,
                        container_id=container.short_id,
                        image=image,
                        status=container.status,
                        networks=net_names,
                        mac=net_cfg.get("MacAddress", ""),
                    )
        finally:
            client.close()

        logger.info("Docker %s: found %d container IP(s)", base_url, len(result))
        return result

    loop = asyncio.get_event_loop()
    merged: dict[str, DockerInfo] = {}
    for base_url in targets:
        try:
            partial = await loop.run_in_executor(None, _fetch_one, base_url)
            merged.update(partial)
        except Exception as exc:
            logger.warning("Docker query error for %s: %s", base_url, exc)

    logger.info("Docker total: %d unique container IP(s) across %d host(s)", len(merged), len(targets))
    return merged


# ---------------------------------------------------------------------------
# Proxmox API
# ---------------------------------------------------------------------------

@dataclass
class ProxmoxInfo:
    name: str
    vm_id: int
    type: str          # "vm" or "lxc"
    node: str
    status: str


def _parse_mac(net_str: str, vm_type: str) -> str | None:
    """Extract a normalised lowercase MAC from a Proxmox net config string."""
    pattern = _QEMU_MAC_RE if vm_type == "vm" else _LXC_MAC_RE
    m = pattern.search(net_str)
    return m.group(1).lower() if m else None


async def query_proxmox(
    hosts: list[str],
    user: str,
    *,
    password: str | None = None,
    token_id: str | None = None,
    token_secret: str | None = None,
    verify_ssl: bool = False,
) -> dict[str, ProxmoxInfo]:
    """
    Poll one or more Proxmox hosts for all QEMU VMs and LXC containers.

    All hosts are queried concurrently. Results are merged into one dict
    keyed by MAC address (lowercase). Later hosts win on MAC collision.

    Args:
        hosts:        List of Proxmox hostnames/IPs to query.
        user:         API user, e.g. 'root@pam' or 'monitor@pve'.
        password:     Password auth (mutually exclusive with token_*).
        token_id:     Full API token id, e.g. 'root@pam!mytoken'.
        token_secret: API token UUID secret.
        verify_ssl:   Verify TLS certificate (default False for self-signed).
    """
    if not hosts:
        return {}

    try:
        from proxmoxer import ProxmoxAPI  # type: ignore
    except ImportError:
        logger.warning("proxmoxer not installed — skipping Proxmox discovery")
        return {}

    def _fetch_one(host: str) -> dict[str, ProxmoxInfo]:
        """Query a single Proxmox host and return its MAC → ProxmoxInfo map."""
        try:
            if token_id and token_secret:
                proxmox = ProxmoxAPI(
                    host,
                    user=user,
                    token_name=token_id.split("!", 1)[-1],
                    token_value=token_secret,
                    verify_ssl=verify_ssl,
                )
            else:
                proxmox = ProxmoxAPI(
                    host, user=user, password=password, verify_ssl=verify_ssl,
                )
        except Exception as exc:
            logger.warning("Proxmox connection failed (%s): %s", host, exc)
            return {}

        result: dict[str, ProxmoxInfo] = {}

        try:
            nodes = proxmox.nodes.get()
        except Exception as exc:
            logger.warning("Proxmox nodes.get() failed (%s): %s", host, exc)
            return {}

        for node_info in nodes:
            node = node_info["node"]

            # --- QEMU VMs ---
            try:
                vms = proxmox.nodes(node).qemu.get()
            except Exception as exc:
                logger.debug("Could not list VMs on %s/%s: %s", host, node, exc)
                vms = []

            for vm in vms:
                vmid = vm["vmid"]
                try:
                    config = proxmox.nodes(node).qemu(vmid).config.get()
                except Exception:
                    continue

                for key, val in config.items():
                    if not key.startswith("net"):
                        continue
                    mac = _parse_mac(str(val), "vm")
                    if mac:
                        result[mac] = ProxmoxInfo(
                            name=vm.get("name", f"vm-{vmid}"),
                            vm_id=vmid,
                            type="vm",
                            node=node,
                            status=vm.get("status", "unknown"),
                        )

            # --- LXC containers ---
            try:
                lxcs = proxmox.nodes(node).lxc.get()
            except Exception as exc:
                logger.debug("Could not list LXCs on %s/%s: %s", host, node, exc)
                lxcs = []

            for lxc in lxcs:
                vmid = lxc["vmid"]
                try:
                    config = proxmox.nodes(node).lxc(vmid).config.get()
                except Exception:
                    continue

                for key, val in config.items():
                    if not key.startswith("net"):
                        continue
                    mac = _parse_mac(str(val), "lxc")
                    if mac:
                        result[mac] = ProxmoxInfo(
                            name=lxc.get("name", f"lxc-{vmid}"),
                            vm_id=vmid,
                            type="lxc",
                            node=node,
                            status=lxc.get("status", "unknown"),
                        )

        logger.info("Proxmox %s: found %d MAC(s) across %d node(s)", host, len(result), len(nodes))
        return result

    loop = asyncio.get_event_loop()
    # Fan out across all hosts concurrently
    partials = await asyncio.gather(
        *[loop.run_in_executor(None, _fetch_one, host) for host in hosts],
        return_exceptions=True,
    )

    merged: dict[str, ProxmoxInfo] = {}
    for host, partial in zip(hosts, partials):
        if isinstance(partial, Exception):
            logger.warning("Proxmox query error for %s: %s", host, partial)
        else:
            merged.update(partial)  # type: ignore[arg-type]

    logger.info(
        "Proxmox total: %d unique MAC(s) across %d host(s)",
        len(merged), len(hosts),
    )
    return merged
