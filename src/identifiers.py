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


async def query_docker() -> dict[str, DockerInfo]:
    """
    Connect to the local Docker socket and enumerate running containers.

    Returns a dict keyed by container IP address. Containers with multiple
    network interfaces appear once per IP. Skips containers with no IP
    (host-network or stopped).

    Requires read access to /var/run/docker.sock.
    """
    try:
        import docker  # type: ignore
    except ImportError:
        logger.warning("docker SDK not installed — skipping Docker discovery")
        return {}

    def _fetch() -> dict[str, DockerInfo]:
        try:
            client = docker.DockerClient(base_url="unix:///var/run/docker.sock", timeout=5)
        except Exception as exc:
            logger.warning("Cannot connect to Docker socket: %s", exc)
            return {}

        result: dict[str, DockerInfo] = {}
        try:
            for container in client.containers.list():
                attrs = container.attrs
                networks: dict[str, Any] = attrs.get("NetworkSettings", {}).get("Networks", {})
                net_names = list(networks.keys())
                image_tags = container.image.tags
                image = image_tags[0] if image_tags else container.image.short_id

                for net_name, net_cfg in networks.items():
                    ip = net_cfg.get("IPAddress", "")
                    if not ip:
                        continue
                    result[ip] = DockerInfo(
                        name=container.name,
                        container_id=container.short_id,
                        image=image,
                        status=container.status,
                        networks=net_names,
                    )
        finally:
            client.close()

        return result

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _fetch)
        logger.info("Docker: found %d container IP(s)", len(result))
        return result
    except Exception as exc:
        logger.warning("Docker query error: %s", exc)
        return {}


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
    host: str,
    user: str,
    *,
    password: str | None = None,
    token_id: str | None = None,
    token_secret: str | None = None,
    verify_ssl: bool = False,
) -> dict[str, ProxmoxInfo]:
    """
    Poll the Proxmox API for all QEMU VMs and LXC containers across every node.

    Returns a dict keyed by MAC address (lowercase, colon-separated).
    Provide either (password) or (token_id + token_secret) for auth.

    Args:
        host:         Proxmox hostname or IP.
        user:         API user, e.g. 'root@pam' or 'monitor@pve'.
        password:     Password auth (mutually exclusive with token_*).
        token_id:     API token id, e.g. 'root@pam!mytoken'.
        token_secret: API token UUID secret.
        verify_ssl:   Verify TLS certificate (default False for self-signed).
    """
    try:
        from proxmoxer import ProxmoxAPI  # type: ignore
    except ImportError:
        logger.warning("proxmoxer not installed — skipping Proxmox discovery")
        return {}

    def _fetch() -> dict[str, ProxmoxInfo]:
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
                    host,
                    user=user,
                    password=password,
                    verify_ssl=verify_ssl,
                )
        except Exception as exc:
            logger.warning("Proxmox connection failed (%s): %s", host, exc)
            return {}

        result: dict[str, ProxmoxInfo] = {}

        try:
            nodes = proxmox.nodes.get()
        except Exception as exc:
            logger.warning("Proxmox nodes.get() failed: %s", exc)
            return {}

        for node_info in nodes:
            node = node_info["node"]

            # --- QEMU VMs ---
            try:
                vms = proxmox.nodes(node).qemu.get()
            except Exception as exc:
                logger.debug("Could not list VMs on node %s: %s", node, exc)
                vms = []

            for vm in vms:
                vmid = vm["vmid"]
                try:
                    config = proxmox.nodes(node).qemu(vmid).config.get()
                except Exception:
                    continue

                # Iterate net0..net31
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
                logger.debug("Could not list LXCs on node %s: %s", node, exc)
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

        logger.info("Proxmox: found %d MAC(s) across %d node(s)", len(result), len(nodes))
        return result

    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _fetch)
    except Exception as exc:
        logger.warning("Proxmox query error: %s", exc)
        return {}
