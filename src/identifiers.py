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
    mac: str = ""           # MAC address of the container's network interface
    network_mode: str = "bridge"  # "host" for --network host containers
    host_ip: str = ""       # Docker daemon host IP; set only for host-net containers
    docker_host: str = ""   # IP of the Docker host this container was discovered on


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

        # Extract the host IP from TCP URLs for host-network container attribution.
        host_ip = ""
        if base_url.startswith("tcp://"):
            host_ip = base_url.split("://", 1)[1].split(":")[0]

        result: dict[str, DockerInfo] = {}
        try:
            for container in client.containers.list():
                attrs = container.attrs
                networks: dict[str, Any] = attrs.get("NetworkSettings", {}).get("Networks", {})
                net_names = list(networks.keys())
                image_tags = container.image.tags
                image = image_tags[0] if image_tags else container.image.short_id
                network_mode = attrs.get("HostConfig", {}).get("NetworkMode", "bridge")

                # Host-networked containers share the daemon host's IP/MAC.
                # Store them under a synthetic key so they don't collide with
                # bridge containers; main.py resolves them via the ARP table.
                if network_mode == "host":
                    if host_ip:
                        result[f"hostnet:{container.short_id}"] = DockerInfo(
                            name=container.name,
                            container_id=container.short_id,
                            image=image,
                            status=container.status,
                            networks=["host"],
                            network_mode="host",
                            host_ip=host_ip,
                            docker_host=host_ip,
                        )
                    continue

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
                        docker_host=host_ip or "localhost",
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
    type: str           # "vm" or "lxc"
    node: str
    status: str
    ip: str | None = None  # best-effort IP from guest agent / LXC interfaces


def _first_valid_ipv4(addr: str) -> str | None:
    """Return addr if it is a routable IPv4 address, else None."""
    a = addr.strip()
    if not a:
        return None
    # Reject loopback and link-local
    if a.startswith("127.") or a.startswith("169.254."):
        return None
    # Basic sanity: four dot-separated octets
    parts = a.split(".")
    if len(parts) != 4:
        return None
    try:
        if all(0 <= int(p) <= 255 for p in parts):
            return a
    except ValueError:
        pass
    return None


def _ip_from_qemu_agent(data: dict) -> str | None:
    """
    Parse the response of agent/network-get-interfaces.
    Shape: {"result": [{"name": "eth0", "ip-addresses": [{"ip-address-type": "ipv4",
                                                           "ip-address": "10.x.x.x"}]}]}
    Returns the first routable IPv4 found, or None.
    """
    for iface in data.get("result", []):
        for addr in iface.get("ip-addresses", []):
            if addr.get("ip-address-type") == "ipv4":
                ip = _first_valid_ipv4(addr.get("ip-address", ""))
                if ip:
                    return ip
    return None


def _ip_from_lxc_interfaces(data: list) -> str | None:
    """
    Parse the response of lxc/{vmid}/interfaces.
    Shape: [{"name": "eth0", "inet": "10.x.x.x/24"}, ...]
    Returns the first routable IPv4 found, or None.
    """
    for iface in data if isinstance(data, list) else []:
        inet = iface.get("inet", "")
        if inet:
            ip = _first_valid_ipv4(inet.split("/")[0])
            if ip:
                return ip
    return None


def _parse_mac(net_str: str, vm_type: str) -> str | None:
    """Extract a normalised lowercase MAC from a Proxmox net config string."""
    pattern = _QEMU_MAC_RE if vm_type == "vm" else _LXC_MAC_RE
    m = pattern.search(net_str)
    return m.group(1).lower() if m else None


async def query_proxmox(nodes: list[dict]) -> dict[str, ProxmoxInfo]:
    """
    Poll one or more Proxmox hosts for all QEMU VMs and LXC containers.

    Each node is queried concurrently using its own credentials. Results are
    merged into one dict keyed by MAC address (lowercase); later nodes win
    on collision.

    Args:
        nodes: List of per-host config dicts. Supported keys:
               host         (str, required)  — Proxmox IP or hostname
               user         (str, required)  — API user, e.g. 'root@pam'
               token_id     (str)            — full token id 'user@pam!name'
               token_secret (str)            — token UUID secret
               password     (str)            — password (alt to token auth)
               verify_ssl   (bool, default False)
    """
    if not nodes:
        return {}

    try:
        from proxmoxer import ProxmoxAPI  # type: ignore
    except ImportError:
        logger.warning("proxmoxer not installed — skipping Proxmox discovery")
        return {}

    def _fetch_one(node_cfg: dict) -> dict[str, ProxmoxInfo]:
        """Query a single Proxmox host using its own credentials."""
        host         = node_cfg["host"]
        user         = node_cfg["user"]
        token_id     = node_cfg.get("token_id")
        token_secret = node_cfg.get("token_secret")
        password     = node_cfg.get("password")
        verify_ssl   = bool(node_cfg.get("verify_ssl", False))

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
            pve_nodes = proxmox.nodes.get()
        except Exception as exc:
            logger.warning("Proxmox nodes.get() failed (%s): %s", host, exc)
            return {}

        for node_info in pve_nodes:
            node = node_info["node"]

            # --- QEMU VMs ---
            try:
                vms = proxmox.nodes(node).qemu.get()
            except Exception as exc:
                logger.debug("Could not list VMs on %s/%s: %s", host, node, exc)
                vms = []

            for vm in vms:
                vmid   = vm["vmid"]
                status = vm.get("status", "unknown")
                try:
                    config = proxmox.nodes(node).qemu(vmid).config.get()
                except Exception:
                    continue

                # Best-effort IP via QEMU guest agent (fails silently if not installed)
                vm_ip: str | None = None
                if status == "running":
                    try:
                        agent_data = proxmox.nodes(node).qemu(vmid).agent("network-get-interfaces").get()
                        vm_ip = _ip_from_qemu_agent(agent_data)
                    except Exception:
                        pass  # agent absent, not running, or permission denied

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
                            status=status,
                            ip=vm_ip,
                        )

            # --- LXC containers ---
            try:
                lxcs = proxmox.nodes(node).lxc.get()
            except Exception as exc:
                logger.debug("Could not list LXCs on %s/%s: %s", host, node, exc)
                lxcs = []

            for lxc in lxcs:
                vmid   = lxc["vmid"]
                status = lxc.get("status", "unknown")
                try:
                    config = proxmox.nodes(node).lxc(vmid).config.get()
                except Exception:
                    continue

                # Best-effort IP via LXC network interfaces endpoint
                lxc_ip: str | None = None
                if status == "running":
                    try:
                        iface_data = proxmox.nodes(node).lxc(vmid).interfaces.get()
                        lxc_ip = _ip_from_lxc_interfaces(iface_data)
                    except Exception:
                        pass  # container may not expose interfaces endpoint

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
                            status=status,
                            ip=lxc_ip,
                        )

        logger.info(
            "Proxmox %s: found %d MAC(s) across %d node(s)",
            host, len(result), len(pve_nodes),
        )
        return result

    loop = asyncio.get_event_loop()
    partials = await asyncio.gather(
        *[loop.run_in_executor(None, _fetch_one, n) for n in nodes],
        return_exceptions=True,
    )

    merged: dict[str, ProxmoxInfo] = {}
    for node_cfg, partial in zip(nodes, partials):
        if isinstance(partial, Exception):
            logger.warning("Proxmox query error for %s: %s", node_cfg.get("host"), partial)
        else:
            merged.update(partial)  # type: ignore[arg-type]

    logger.info(
        "Proxmox total: %d unique MAC(s) across %d host(s)",
        len(merged), len(nodes),
    )
    return merged
