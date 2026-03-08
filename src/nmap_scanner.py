"""
Optional nmap-based host scanner.

Runs `nmap -sn -oX -` against configured subnets to discover hosts that
don't appear in the OPNsense ARP table — typically static-IP bare-metal
devices that haven't generated ARP traffic since OPNsense's last cache
refresh, or hosts on directly-attached subnets not routed through OPNsense.

On local subnets nmap uses ARP (yielding MAC + IP).
On remote subnets it uses ICMP ping (IP only; these are skipped since the
device table is keyed by MAC).

Configuration
-------------
NMAP_SUBNETS  Comma-separated CIDR blocks, e.g. "10.0.10.0/24,10.0.20.0/24"
              Leave unset or empty to disable nmap scanning entirely.

Requirements
------------
  apt install nmap
Elevated privileges (CAP_NET_RAW or root) are required for ARP-mode scans.
"""

import asyncio
import logging
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


async def query_nmap(subnets: list[str]) -> dict[str, str]:
    """
    Scan each subnet with nmap host-discovery and return a MAC → IP mapping.

    Only hosts that nmap can associate with a MAC address (i.e. on a locally
    reachable L2 segment) are included in the result.

    Returns an empty dict if nmap is not installed, subnets is empty, or all
    scans fail.
    """
    if not subnets:
        return {}

    result: dict[str, str] = {}

    for subnet in subnets:
        try:
            proc = await asyncio.create_subprocess_exec(
                "nmap", "-sn", "-oX", "-", "--", subnet,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        except FileNotFoundError:
            logger.warning(
                "nmap not found — skipping subnet scan (install with: apt install nmap)"
            )
            return {}
        except asyncio.TimeoutError:
            logger.warning("nmap scan of %s timed out after 120s", subnet)
            continue
        except Exception as exc:
            logger.warning("nmap scan of %s failed: %s", subnet, exc)
            continue

        if proc.returncode not in (0, 1):
            logger.warning(
                "nmap exited %d for %s: %s",
                proc.returncode, subnet, stderr.decode(errors="replace")[:200],
            )
            continue

        try:
            root = ET.fromstring(stdout.decode(errors="replace"))
        except ET.ParseError as exc:
            logger.warning("nmap XML parse error for %s: %s", subnet, exc)
            continue

        found = 0
        for host in root.findall("host"):
            if host.find("status[@state='up']") is None:
                continue
            ip = mac = ""
            for addr in host.findall("address"):
                if addr.get("addrtype") == "ipv4":
                    ip = addr.get("addr", "")
                elif addr.get("addrtype") == "mac":
                    mac = addr.get("addr", "").lower()
            if ip and mac:
                result[mac] = ip
                found += 1

        logger.info("nmap %s: %d host(s) with MAC address", subnet, found)

    logger.info(
        "nmap total: %d MAC→IP mapping(s) across %d subnet(s)", len(result), len(subnets)
    )
    return result
