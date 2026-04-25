"""OPNsense ARP fetcher regression tests.

Found by /qa on 2026-04-25
Report: .gstack/qa-reports/qa-report-netcensus-2026-04-25.md

The dashboard's VLANs counter reads device.metadata.vlan, which is populated
from the OPNsense ARP entry's intf_description. Before this fix, the fetcher
returned a flat dict[str, str] of MAC → IP and threw away the interface
fields, so the counter was always '–' for real (non-demo) installs.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.opnsense import query_opnsense


# Sampled from a live OPNsense /api/diagnostics/interface/getArp response
# on 2026-04-25 — see the QA report for the capture session.
_LIVE_SAMPLE = [
    {
        "mac": "2c:4c:15:a8:bd:fc",
        "ip": "38.59.218.1",
        "intf": "igc0",
        "intf_description": "WAN",
        "type": "ethernet",
    },
    {
        "mac": "bc:24:11:fb:e1:cb",
        "ip": "10.30.30.10",
        "intf": "vlan01",
        "intf_description": "Lab",
        "type": "vlan",
    },
    {
        "mac": "00:11:22:33:44:55",
        "ip": "10.30.40.5",
        "intf": "vlan02",
        "intf_description": "Servers",
        "type": "vlan",
    },
    # Broadcast — must be filtered out
    {"mac": "ff:ff:ff:ff:ff:ff", "ip": "10.0.0.255", "intf": "vlan01", "intf_description": "Lab"},
]


@pytest.mark.asyncio
async def test_query_opnsense_returns_intf_metadata():
    """Each result entry must include intf and intf_description so the
    discovery loop can tag devices with their network segment.

    Regression for ISSUE-007 (VLANs counter shows '–' instead of segment count).
    """
    mock_response = MagicMock()
    mock_response.json.return_value = _LIVE_SAMPLE
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("src.opnsense.httpx.AsyncClient", return_value=mock_client):
        result = await query_opnsense(
            url="https://10.0.99.1", key="k", secret="s"
        )

    assert "bc:24:11:fb:e1:cb" in result
    entry = result["bc:24:11:fb:e1:cb"]
    assert entry["ip"] == "10.30.30.10"
    assert entry["intf"] == "vlan01"
    assert entry["intf_description"] == "Lab"


@pytest.mark.asyncio
async def test_query_opnsense_filters_broadcast():
    """Broadcast MAC must still be filtered (existing behaviour preserved)."""
    mock_response = MagicMock()
    mock_response.json.return_value = _LIVE_SAMPLE
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("src.opnsense.httpx.AsyncClient", return_value=mock_client):
        result = await query_opnsense(
            url="https://10.0.99.1", key="k", secret="s"
        )

    assert "ff:ff:ff:ff:ff:ff" not in result


@pytest.mark.asyncio
async def test_query_opnsense_distinct_segments_for_vlan_counter():
    """Across the sample, three distinct intf_description values exist
    ('WAN', 'Lab', 'Servers'). The dashboard's VLANs metric counts these
    distinct values via metadata.vlan, so confirm each entry carries one.
    """
    mock_response = MagicMock()
    mock_response.json.return_value = _LIVE_SAMPLE
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("src.opnsense.httpx.AsyncClient", return_value=mock_client):
        result = await query_opnsense(
            url="https://10.0.99.1", key="k", secret="s"
        )

    descriptions = {entry["intf_description"] for entry in result.values()}
    assert descriptions == {"WAN", "Lab", "Servers"}


@pytest.mark.asyncio
async def test_query_opnsense_handles_missing_intf_fields():
    """Older OPNsense versions may omit intf/intf_description — must not crash."""
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"mac": "aa:bb:cc:dd:ee:ff", "ip": "10.0.0.1"}
    ]
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("src.opnsense.httpx.AsyncClient", return_value=mock_client):
        result = await query_opnsense(
            url="https://10.0.99.1", key="k", secret="s"
        )

    entry = result["aa:bb:cc:dd:ee:ff"]
    assert entry["ip"] == "10.0.0.1"
    assert entry["intf"] == ""
    assert entry["intf_description"] == ""
