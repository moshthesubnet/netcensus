"""
Async UDP syslog receiver — Phase 3.5.

Supports:
  • RFC 3164  — <PRI>Mmm DD HH:MM:SS HOSTNAME TAG: MESSAGE
  • RFC 5424  — <PRI>1 TIMESTAMP HOSTNAME APP PROCID MSGID SD MESSAGE
  • OPNsense  — filterlog CSV payload inside RFC 3164 wrapper

Parsed fields saved to the 'syslogs' SQLite table via insert_syslog().
Binding port 514 requires CAP_NET_BIND_SERVICE or root.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone

from src.database import insert_syslog

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Severity / priority helpers
# ---------------------------------------------------------------------------

_SEVERITY_NAMES: dict[int, str] = {
    0: "emergency",
    1: "alert",
    2: "critical",
    3: "error",
    4: "warning",
    5: "notice",
    6: "info",
    7: "debug",
}


def _decode_priority(pri_str: str) -> tuple[str, int]:
    """
    Decode a raw syslog PRI string (e.g. '34') into (severity_name, facility).
    PRI = facility * 8 + severity.
    """
    try:
        pri = int(pri_str)
        return _SEVERITY_NAMES.get(pri % 8, "info"), pri // 8
    except ValueError:
        return "info", 1


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_rfc3164_ts(ts: str) -> str:
    """
    Parse 'Mmm DD HH:MM:SS' (no year) and anchor it to UTC.
    If the resulting month is ahead of today, roll back one year
    (handles the Dec→Jan boundary).
    """
    try:
        now = datetime.now(timezone.utc)
        dt = datetime.strptime(f"{now.year} {ts.strip()}", "%Y %b %d %H:%M:%S")
        if dt.month > now.month:
            dt = dt.replace(year=now.year - 1)
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except Exception:
        return _now_utc()


def _parse_iso_ts(ts: str) -> str:
    """Parse an ISO-8601 timestamp (RFC 5424) and convert to UTC."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return _now_utc()


# ---------------------------------------------------------------------------
# Format regexes
# ---------------------------------------------------------------------------

# RFC 3164:  <PRI>Mmm [D]D HH:MM:SS HOSTNAME rest...
_RFC3164_RE = re.compile(
    r"^<(\d{1,3})>"
    r"(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})"
    r"\s+(\S+)"      # HOSTNAME (we log source IP instead, but capture for stripping)
    r"\s+(.*)?$",
    re.DOTALL,
)

# RFC 5424:  <PRI>VERSION TIMESTAMP HOSTNAME APP PROCID MSGID SD [MSG]
_RFC5424_RE = re.compile(
    r"^<(\d{1,3})>(\d+)"        # <PRI>VERSION
    r"\s+(\S+)"                  # TIMESTAMP
    r"\s+(\S+)"                  # HOSTNAME
    r"\s+(\S+)"                  # APP-NAME
    r"\s+(\S+)"                  # PROCID
    r"\s+(\S+)"                  # MSGID
    r"\s+(\S+)"                  # STRUCTURED-DATA
    r"(?:\s+(.*?))?$",           # MESSAGE (optional)
    re.DOTALL,
)

# OPNsense filterlog CSV: a TAG of "filterlog" followed by comma-separated fields
# Example tail: filterlog: 5,,,0,igb0,match,pass,in,4,0x0,,64,...
_FILTERLOG_RE = re.compile(r"filterlog:\s+(.+)$", re.DOTALL)

# Mapping of filterlog action field (index 5) to human labels
_FILTERLOG_ACTIONS = {"pass": "PASS", "block": "BLOCK", "match": "MATCH"}


def _parse_filterlog(raw_csv: str) -> str:
    """
    Convert an OPNsense filterlog CSV payload into a readable message.
    Fields vary by IP version; we extract the most useful ones defensively.

    IPv4 fields (approx): rule,sub,anchor,tracker,iface,reason,action,dir,
                           ipver,tos,ecn,ttl,id,offset,flags,proto,protoname,...
    """
    fields = raw_csv.split(",")
    try:
        iface   = fields[4]  if len(fields) > 4  else "?"
        action  = fields[6]  if len(fields) > 6  else "?"
        direction = fields[7] if len(fields) > 7 else "?"
        proto   = fields[16] if len(fields) > 16 else "?"
        src_ip  = fields[18] if len(fields) > 18 else "?"
        dst_ip  = fields[19] if len(fields) > 19 else "?"
        src_port = fields[20] if len(fields) > 20 else ""
        dst_port = fields[21] if len(fields) > 21 else ""

        action_label = _FILTERLOG_ACTIONS.get(action.lower(), action.upper())
        src = f"{src_ip}:{src_port}" if src_port else src_ip
        dst = f"{dst_ip}:{dst_port}" if dst_port else dst_ip
        return f"[{action_label}] {direction.upper()} on {iface} | {proto} {src} → {dst}"
    except Exception:
        return f"filterlog: {raw_csv}"


# ---------------------------------------------------------------------------
# Top-level parser
# ---------------------------------------------------------------------------

def parse_syslog(raw: bytes, addr: tuple[str, int]) -> dict[str, str]:
    """
    Parse a raw UDP syslog datagram into a normalised dict:
      source_ip, severity, message, timestamp

    Falls back to storing the raw text on parse failure so no message is lost.
    """
    source_ip = addr[0]
    text = raw.decode("utf-8", errors="replace").strip()

    # --- RFC 5424 (has integer version field immediately after PRI) ---
    m = _RFC5424_RE.match(text)
    if m:
        severity, _ = _decode_priority(m.group(1))
        timestamp    = _parse_iso_ts(m.group(3)) if m.group(3) != "-" else _now_utc()
        app          = m.group(5) if m.group(5) != "-" else ""
        body         = (m.group(9) or "").strip()
        message      = f"{app}: {body}" if app and body else (app or body or text)
        return {"source_ip": source_ip, "severity": severity,
                "message": message, "timestamp": timestamp}

    # --- RFC 3164 (most syslog devices, including OPNsense) ---
    m = _RFC3164_RE.match(text)
    if m:
        severity, _ = _decode_priority(m.group(1))
        timestamp    = _parse_rfc3164_ts(m.group(2))
        body         = (m.group(4) or "").strip()

        # OPNsense filterlog — convert CSV to readable summary
        fm = _FILTERLOG_RE.search(body)
        if fm:
            body = _parse_filterlog(fm.group(1).strip())

        return {"source_ip": source_ip, "severity": severity,
                "message": body or text, "timestamp": timestamp}

    # --- Bare message (no PRI header) ---
    return {"source_ip": source_ip, "severity": "info",
            "message": text, "timestamp": _now_utc()}


# ---------------------------------------------------------------------------
# asyncio DatagramProtocol
# ---------------------------------------------------------------------------

class SyslogProtocol(asyncio.DatagramProtocol):
    """
    UDP DatagramProtocol that receives syslog packets, parses them,
    and schedules a non-blocking SQLite write via asyncio.create_task.
    """

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        host, port = transport.get_extra_info("sockname")
        logger.info("Syslog UDP server listening on %s:%d", host, port)

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        parsed = parse_syslog(data, addr)

        # Schedule DB write without blocking the receive loop
        asyncio.create_task(
            insert_syslog(
                source_ip=parsed["source_ip"],
                message=parsed["message"],
                severity=parsed["severity"],
                timestamp=parsed["timestamp"],
            ),
            name=f"syslog-{parsed['source_ip']}",
        )

        logger.debug(
            "[syslog] %s [%s] %s",
            parsed["source_ip"],
            parsed["severity"],
            parsed["message"][:120],
        )

    def error_received(self, exc: Exception) -> None:
        logger.warning("Syslog UDP error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        logger.info("Syslog UDP transport closed")


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

async def start_syslog_server(
    host: str = "0.0.0.0",
    port: int = 514,
) -> asyncio.DatagramTransport:
    """
    Bind and start the UDP syslog server.
    Returns the transport; caller must call transport.close() to stop it.

    Note: binding port 514 requires root or CAP_NET_BIND_SERVICE.
    For testing without root, set SYSLOG_PORT=5140 (or any port > 1023).
    """
    loop = asyncio.get_event_loop()
    transport, _ = await loop.create_datagram_endpoint(
        SyslogProtocol,
        local_addr=(host, port),
        reuse_port=True,
    )
    return transport  # type: ignore[return-value]
