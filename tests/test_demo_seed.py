"""Tests for the demo seeder.

The seed must be deterministic and must produce the counts specified in
the design spec.
"""
import os
import tempfile
import pytest

from src.demo_seed import seed_demo_db


@pytest.mark.asyncio
async def test_seed_is_deterministic():
    """Seeding the same fresh DB twice must produce identical device rows."""
    with tempfile.TemporaryDirectory() as d:
        db1 = os.path.join(d, "a.db")
        db2 = os.path.join(d, "b.db")
        counts1 = await seed_demo_db(db1)
        counts2 = await seed_demo_db(db2)
        assert counts1 == counts2


@pytest.mark.asyncio
async def test_seed_counts_match_spec():
    """The seed produces the narrative required by the spec."""
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "demo.db")
        counts = await seed_demo_db(db)
        # Spec: 6 VLANs, 2 Proxmox nodes, 8 VMs, 4 LXCs,
        #       3 Docker hosts with ~20 containers,
        #       1 firewall + 1 switch + 2 APs, 4 IoT endpoints,
        #       1 intentional device_gone alert.
        assert counts["vlans"] == 6
        assert counts["vms"] == 8
        assert counts["lxcs"] == 4
        assert 18 <= counts["containers"] <= 22
        assert counts["bare_metal"] >= 4  # firewall + switch + 2 APs
        assert counts["iot"] == 4
        assert counts["alerts"] == 1


@pytest.mark.asyncio
async def test_seed_includes_at_least_one_syslog_block_line():
    """Seed must include OPNsense filterlog BLOCK lines so the log panel isn't empty."""
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "demo.db")
        counts = await seed_demo_db(db)
        assert counts["syslog_block_lines"] >= 2
