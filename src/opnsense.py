"""
OPNsense ARP table fetcher.

Authenticates against the OPNsense REST API using an API key/secret pair
(HTTP Basic Auth: key = username, secret = password) and retrieves the
global ARP table via GET /api/diagnostics/interface/getArp.

Returns a dict mapping lowercase MAC address → IP address, covering every
VLAN that OPNsense is aware of — giving us full network visibility without
requiring a local Layer-2 ARP broadcast.

Configuration (environment variables)
--------------------------------------
OPNSENSE_URL     Base URL, e.g. https://10.0.99.1
OPNSENSE_KEY     API key   (used as HTTP Basic Auth username)
OPNSENSE_SECRET  API secret (used as HTTP Basic Auth password)
"""

import logging
import os
import re

import httpx
import urllib3

# Suppress the InsecureRequestWarning that fires when verify=False is used.
# OPNsense ships with self-signed certs by default; this is expected.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

_ARP_ENDPOINT = "/api/diagnostics/interface/getArp"


async def query_opnsense(
    url: str | None = None,
    key: str | None = None,
    secret: str | None = None,
) -> dict[str, str]:
    """
    Fetch the global ARP table from OPNsense and return a MAC → IP mapping.

    Args:
        url:    OPNsense base URL (default: OPNSENSE_URL env var).
        key:    API key / Basic Auth username (default: OPNSENSE_KEY env var).
        secret: API secret / Basic Auth password (default: OPNSENSE_SECRET env var).

    Returns:
        Dict mapping lowercase MAC address to IP string.
        Empty dict on any connection or auth failure.
    """
    base_url = (url or os.environ.get("OPNSENSE_URL", "")).rstrip("/")
    api_key  = key    or os.environ.get("OPNSENSE_KEY",    "")
    api_sec  = secret or os.environ.get("OPNSENSE_SECRET", "")

    if not base_url:
        logger.warning("OPNSENSE_URL not set — skipping OPNsense ARP fetch")
        return {}
    if not api_key or not api_sec:
        logger.warning("OPNSENSE_KEY / OPNSENSE_SECRET not set — skipping OPNsense ARP fetch")
        return {}

    endpoint = f"{base_url}{_ARP_ENDPOINT}"

    try:
        async with httpx.AsyncClient(verify=False, timeout=10) as client:
            resp = await client.get(endpoint, auth=(api_key, api_sec))
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "OPNsense API returned HTTP %s for %s", exc.response.status_code, endpoint
        )
        return {}
    except httpx.RequestError as exc:
        logger.warning("OPNsense request failed (%s): %s", endpoint, exc)
        return {}

    try:
        data = resp.json()
    except Exception as exc:
        logger.warning("OPNsense response is not valid JSON: %s", exc)
        return {}

    # The API returns either a list of entry dicts, or {"arp": [...]}
    entries = data if isinstance(data, list) else data.get("arp", [])

    result: dict[str, str] = {}
    for entry in entries:
        mac = str(entry.get("mac", "")).strip().lower()
        ip  = str(entry.get("ip",  "")).strip()

        # Skip incomplete, multicast, or broadcast entries
        if not mac or not ip or len(mac) != 17 or mac in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00"):
            continue

        result[mac] = ip

    logger.info("OPNsense ARP table: %d valid entries from %s", len(result), base_url)
    return result


_DHCP_ENDPOINT = "/api/dnsmasq/leases/search"

# Matches strings that look like an IPv4 address — these are not real hostnames
_IP_PATTERN = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


async def query_opnsense_dhcp(
    url: str | None = None,
    key: str | None = None,
    secret: str | None = None,
) -> dict[str, str]:
    """
    Fetch active DHCP leases from OPNsense and return a MAC → hostname mapping.

    Args:
        url:    OPNsense base URL (default: OPNSENSE_URL env var).
        key:    API key / Basic Auth username (default: OPNSENSE_KEY env var).
        secret: API secret / Basic Auth password (default: OPNSENSE_SECRET env var).

    Returns:
        Dict mapping lowercase MAC address to hostname string.
        Entries with empty or IP-address-shaped hostnames are excluded.
        Empty dict on any connection or auth failure.
    """
    base_url = (url or os.environ.get("OPNSENSE_URL", "")).rstrip("/")
    api_key  = key    or os.environ.get("OPNSENSE_KEY",    "")
    api_sec  = secret or os.environ.get("OPNSENSE_SECRET", "")

    if not base_url or not api_key or not api_sec:
        return {}

    endpoint = f"{base_url}{_DHCP_ENDPOINT}"

    try:
        async with httpx.AsyncClient(verify=False, timeout=10) as client:
            resp = await client.get(endpoint, auth=(api_key, api_sec))
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "OPNsense DHCP API returned HTTP %s for %s", exc.response.status_code, endpoint
        )
        return {}
    except httpx.RequestError as exc:
        logger.warning("OPNsense DHCP request failed (%s): %s", endpoint, exc)
        return {}

    try:
        data = resp.json()
    except Exception as exc:
        logger.warning("OPNsense DHCP response is not valid JSON: %s", exc)
        return {}

    # Response shape: {"rows": [...], "rowCount": N, "total": N}
    # Each row has at minimum: "mac", "hostname"
    rows = data.get("rows", data) if isinstance(data, dict) else data

    result: dict[str, str] = {}
    for row in rows if isinstance(rows, list) else []:
        # Dnsmasq leases use "hwaddr"; ISC/Kea used "mac" — accept both.
        mac      = str(row.get("hwaddr", row.get("mac", ""))).strip().lower()
        hostname = str(row.get("hostname", "")).strip()

        if not mac or len(mac) != 17:
            continue
        if not hostname or _IP_PATTERN.match(hostname):
            continue

        result[mac] = hostname

    logger.info("OPNsense DHCP leases: %d hostname(s) from %s", len(result), base_url)
    return result
