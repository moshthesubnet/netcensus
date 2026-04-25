"""API validation regression tests.

Found by /qa on 2026-04-25
Report: .gstack/qa-reports/qa-report-netcensus-2026-04-25.md

Each test asserts that endpoints reject bad inputs with HTTP 422 instead of
silently persisting them.
"""
import os
import tempfile
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient


@contextmanager
def _app_with_temp_db():
    """Spin up the FastAPI app with a fresh temp SQLite DB.

    Avoids touching the running production DB and lets each test seed a single
    known device row so PUT endpoints can hit a real MAC.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        os.environ["DB_PATH"] = db_path
        # Disable optional integrations so the lifespan startup stays quick.
        for var in ("OPNSENSE_URL", "OPNSENSE_KEY", "OPNSENSE_SECRET",
                    "PROXMOX_NODES", "DOCKER_HOSTS", "NMAP_SUBNETS", "SNMP_HOSTS"):
            os.environ.pop(var, None)

        # Import after env setup so module-level config picks up the temp DB.
        # Reload to drop any cached state from previous tests.
        import importlib
        import src.database as database
        import src.main as main
        importlib.reload(database)
        importlib.reload(main)

        with TestClient(main.app) as client:
            # Seed one known device row so PUT-by-mac has something to hit.
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                database.upsert_device(
                    mac="aa:bb:cc:dd:ee:01",
                    ip="10.0.0.1",
                    vendor="Test",
                    device_type="bare-metal",
                )
            )
            yield client


# ── ISSUE-001: PUT /type rejects values outside the device-type enum ─────────


def test_put_type_accepts_valid_enum_value():
    """A valid device_type value must be accepted and persist."""
    with _app_with_temp_db() as client:
        r = client.put("/api/devices/aa:bb:cc:dd:ee:01/type",
                       json={"type": "switch"})
        assert r.status_code == 200, r.text
        assert r.json()["custom_type"] == "switch"


def test_put_type_rejects_arbitrary_string():
    """Bug: arbitrary strings used to be accepted and persist as effective_type.

    Regression for ISSUE-001 (high severity, data corruption).
    """
    with _app_with_temp_db() as client:
        r = client.put("/api/devices/aa:bb:cc:dd:ee:01/type",
                       json={"type": "definitely-not-valid"})
        assert r.status_code == 422, (
            f"Expected 422 for invalid device_type, got {r.status_code}: {r.text}"
        )


def test_put_type_rejects_empty_string():
    """Empty string is not a valid enum value either — must be 422 (not 200)."""
    with _app_with_temp_db() as client:
        r = client.put("/api/devices/aa:bb:cc:dd:ee:01/type",
                       json={"type": ""})
        assert r.status_code == 422, r.text


def test_put_type_accepts_null_to_clear():
    """null clears the override — this path must keep working."""
    with _app_with_temp_db() as client:
        r = client.put("/api/devices/aa:bb:cc:dd:ee:01/type",
                       json={"type": None})
        assert r.status_code == 200, r.text
        assert r.json()["custom_type"] is None


# ── ISSUE-002: PUT /syslog-ip rejects malformed IP addresses ─────────────────


def test_put_syslog_ip_accepts_valid_ipv4():
    with _app_with_temp_db() as client:
        r = client.put("/api/devices/aa:bb:cc:dd:ee:01/syslog-ip",
                       json={"syslog_ip": "10.30.30.1"})
        assert r.status_code == 200, r.text


def test_put_syslog_ip_accepts_valid_ipv6():
    with _app_with_temp_db() as client:
        r = client.put("/api/devices/aa:bb:cc:dd:ee:01/syslog-ip",
                       json={"syslog_ip": "fe80::1"})
        assert r.status_code == 200, r.text


def test_put_syslog_ip_rejects_garbage():
    """Bug: 'not-an-ip' used to be persisted silently.

    Regression for ISSUE-002 (high severity, validation gap).
    """
    with _app_with_temp_db() as client:
        r = client.put("/api/devices/aa:bb:cc:dd:ee:01/syslog-ip",
                       json={"syslog_ip": "not-an-ip"})
        assert r.status_code == 422, (
            f"Expected 422 for invalid IP, got {r.status_code}: {r.text}"
        )


def test_put_syslog_ip_accepts_null_to_clear():
    """null/empty clears the override."""
    with _app_with_temp_db() as client:
        r = client.put("/api/devices/aa:bb:cc:dd:ee:01/syslog-ip",
                       json={"syslog_ip": None})
        assert r.status_code == 200, r.text
