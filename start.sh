#!/usr/bin/env bash
# Start the Network Monitor (requires root for ARP scanning and syslog port 514)
set -e

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
cd "$WORKDIR"

# Prefer the project venv's python if present; fall back to PATH python3.
PYTHON="${WORKDIR}/venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="python3"

# DEMO=1 shortcut: bypass scanners, seed the DB, run unprivileged on port 8080.
if [ "${DEMO:-}" = "1" ]; then
  export DEMO_MODE=true
  export DB_PATH="${DB_PATH:-/tmp/netcensus-demo.db}"
  export PORT="${PORT:-8080}"
  # No sudo needed — no UDP 514 bind in demo mode.
  exec "$PYTHON" -m uvicorn src.main:app --host 0.0.0.0 --port "${PORT}" --log-level info
fi

HOST_IP=$(hostname -I | awk '{print $1}')
PORT=${PORT:-8000}
SYSLOG_PORT=${SYSLOG_PORT:-514}

echo ""
echo "  Network Monitor"
echo "  ─────────────────────────────────────"
echo "  Dashboard : http://${HOST_IP}:${PORT}"
echo "  API docs  : http://${HOST_IP}:${PORT}/docs"
echo "  Syslog    : UDP ${HOST_IP}:${SYSLOG_PORT}"
echo "  ─────────────────────────────────────"
echo ""

exec "$PYTHON" -m uvicorn src.main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --log-level info
