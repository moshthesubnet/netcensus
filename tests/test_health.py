"""Health endpoint regression tests.

Found by /qa on 2026-04-25
Report: .gstack/qa-reports/qa-report-netcensus-2026-04-25.md
"""
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient


@contextmanager
def _app(env: dict[str, str] | None = None):
    """Spin up the app with controlled env so we can verify enabled-source
    detection without touching the host's real OPNsense/Proxmox/etc."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["DB_PATH"] = os.path.join(tmpdir, "test.db")

        import importlib
        import src.database as database
        import src.main as main
        importlib.reload(database)
        importlib.reload(main)

        # main.load_dotenv() re-pulls .env values during reload. Clear them
        # AFTER reload so _source_enabled() (which reads os.environ at request
        # time) sees a clean slate, then layer on the test's overrides.
        for var in ("OPNSENSE_URL", "OPNSENSE_KEY", "OPNSENSE_SECRET",
                    "PROXMOX_NODES", "DOCKER_HOSTS", "NMAP_SUBNETS", "SNMP_HOSTS"):
            os.environ.pop(var, None)
        # The module-level config constants (PROXMOX_NODES list, etc.) were
        # also captured from the dirty env during reload, so reset them on
        # the imported module too.
        main.PROXMOX_NODES = []
        main.DOCKER_HOSTS = []
        main.NMAP_SUBNETS = []
        main.SNMP_HOSTS = []
        for k, v in (env or {}).items():
            os.environ[k] = v
        if "NMAP_SUBNETS" in (env or {}):
            main.NMAP_SUBNETS = [s.strip() for s in env["NMAP_SUBNETS"].split(",") if s.strip()]

        with TestClient(main.app) as client:
            yield client, main


def test_health_overall_ok_when_all_enabled_sources_are_ok():
    """Bug regression for ISSUE-004.

    With nothing configured but Docker, only Docker is enabled. If Docker's
    last_ok is recent, overall must be 'ok' — not 'unknown' just because
    OPNsense/Proxmox/nmap/SNMP were never configured.
    """
    with _app() as (client, main):
        # Mark Docker as recently OK; leave the other (disabled) sources alone.
        main._source_health["docker"]["last_ok"] = datetime.now(timezone.utc).isoformat()
        main._source_health["docker"]["last_count"] = 5

        body = client.get("/api/health").json()
        assert body["status"] == "ok", body
        assert body["sources"]["docker"]["status"] == "ok"
        # Disabled sources must be flagged so monitoring tools can ignore them.
        assert body["sources"]["opnsense_arp"]["status"] == "disabled"
        assert body["sources"]["opnsense_arp"]["enabled"] is False
        assert body["sources"]["proxmox"]["status"] == "disabled"
        assert body["sources"]["nmap"]["status"] == "disabled"


def test_health_overall_unknown_when_enabled_source_never_ran():
    """An enabled source that hasn't reported yet keeps overall as 'unknown'."""
    with _app(env={"NMAP_SUBNETS": "10.0.0.0/24"}) as (client, main):
        # Docker hasn't run either — leave it 'unknown'.
        body = client.get("/api/health").json()
        assert body["status"] == "unknown", body
        assert body["sources"]["nmap"]["status"] == "unknown"
        assert body["sources"]["nmap"]["enabled"] is True


def test_health_includes_enabled_flag_for_every_source():
    """Every source in the response must carry the new 'enabled' key so
    frontends can render disabled sources distinctly from broken ones."""
    with _app() as (client, _main):
        body = client.get("/api/health").json()
        for name, info in body["sources"].items():
            assert "enabled" in info, f"missing enabled flag for {name}"
            assert isinstance(info["enabled"], bool)
