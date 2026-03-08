"""
Optional SNMP-based ARP cache scanner.

Walks the ipNetToMediaPhysAddress MIB (OID 1.3.6.1.2.1.4.22.1.2) on
routers and managed switches to surface IP→MAC mappings that are present
in the device's ARP table but not forwarded to OPNsense — e.g. hosts on
L2-only segments, or entries aged out of OPNsense but still live on a switch.

Configuration
-------------
SNMP_HOSTS  JSON array of host dicts, e.g.:
            [{"host":"10.0.0.1","community":"public"},
             {"host":"10.0.0.2","community":"private","port":161}]
            Leave unset or empty to disable SNMP scanning entirely.

Requirements
------------
  apt install snmp          # provides snmpwalk
"""

import asyncio
import logging
import re

logger = logging.getLogger(__name__)

# ipNetToMediaPhysAddress — router ARP cache entries
_ARP_OID = "1.3.6.1.2.1.4.22.1.2"

# Matches numeric OID suffix ".ifIndex.a.b.c.d" and the hex MAC value
# snmpwalk -OUn output: .1.3.6.1.2.1.4.22.1.2.1.10.0.0.1 = Hex-STRING: AA BB CC DD EE FF
_ROW_RE = re.compile(
    r"\.\d+\.(\d+\.\d+\.\d+\.\d+)\s*=\s*(?:Hex-STRING:|STRING:)\s*([\dA-Fa-f: ]+)"
)


def _normalise_mac(raw: str) -> str:
    """Convert 'AA BB CC DD EE FF' or 'a:b:c:d:e:f' to 'aa:bb:cc:dd:ee:ff'."""
    parts = re.split(r"[:\s]+", raw.strip())
    if len(parts) == 6:
        return ":".join(p.zfill(2).lower() for p in parts)
    return ""


async def query_snmp(hosts: list[dict]) -> dict[str, str]:
    """
    Walk the ARP cache on each SNMP host and return a MAC → IP mapping.

    Each host dict supports:
      host       (str, required)  — IP or hostname of the device to poll
      community  (str, default "public") — SNMPv2c community string
      port       (int, default 161)      — UDP port

    Returns an empty dict if snmpwalk is not installed, hosts is empty, or
    all walks fail.
    """
    if not hosts:
        return {}

    result: dict[str, str] = {}

    for cfg in hosts:
        host      = cfg.get("host", "")
        community = cfg.get("community", "public")
        port      = int(cfg.get("port", 161))

        if not host:
            continue

        try:
            proc = await asyncio.create_subprocess_exec(
                "snmpwalk",
                "-v2c",
                "-c", community,
                "-OUn",          # numeric OIDs, no units suffix
                f"-p{port}",
                host,
                _ARP_OID,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        except FileNotFoundError:
            logger.warning(
                "snmpwalk not found — skipping SNMP scan (install with: apt install snmp)"
            )
            return {}
        except asyncio.TimeoutError:
            logger.warning("SNMP walk of %s timed out after 15s", host)
            continue
        except Exception as exc:
            logger.warning("SNMP walk of %s failed: %s", host, exc)
            continue

        # snmpwalk returns exit 1 when it reaches the end of the MIB subtree
        # (normal termination), so accept both 0 and 1.
        if proc.returncode not in (0, 1):
            logger.warning(
                "snmpwalk exited %d for %s: %s",
                proc.returncode, host, stderr.decode(errors="replace")[:200],
            )
            continue

        found = 0
        for line in stdout.decode(errors="replace").splitlines():
            m = _ROW_RE.search(line)
            if not m:
                continue
            ip  = m.group(1)
            mac = _normalise_mac(m.group(2))
            if mac and ip:
                result[mac] = ip
                found += 1

        logger.info("SNMP %s: %d MAC→IP mapping(s)", host, found)

    logger.info(
        "SNMP total: %d MAC→IP mapping(s) across %d host(s)", len(result), len(hosts)
    )
    return result
