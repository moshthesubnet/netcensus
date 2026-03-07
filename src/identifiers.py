"""
Device identification helpers:
  - MAC OUI vendor lookup (offline, bundled database)
  - Docker socket querying (future)
  - Proxmox API polling (future)
"""

import logging
from mac_vendor_lookup import AsyncMacLookup, VendorNotFoundError

logger = logging.getLogger(__name__)

# Module-level instance; the bundled OUI DB is loaded lazily on first use.
_mac_lookup = AsyncMacLookup()


async def lookup_vendor(mac: str) -> str:
    """Return the OUI vendor name for a MAC address, or 'Unknown' if not found."""
    try:
        return await _mac_lookup.lookup(mac)
    except (VendorNotFoundError, KeyError, ValueError):
        return "Unknown"
    except Exception as exc:
        logger.debug("OUI lookup failed for %s: %s", mac, exc)
        return "Unknown"
