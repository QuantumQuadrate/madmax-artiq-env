#!/usr/bin/env bash
set -euo pipefail

CORE_IP="192.168.1.129"
PROXY_BIND="127.0.0.1"
PROXY_PORT="1383"

uv run artiq_master &
sleep 0.5

# Start ctlmgr
exec uv run artiq_ctlmgr &
sleep 0.5

# Start moninj proxy in background with auto-restart
exec uv run aqctl_moninj_proxy --bind "$PROXY_BIND" --port-proxy "$PROXY_PORT" "$CORE_IP" || true
sleep 0.5

# Start dashboard in foreground
exec uv run artiq_dashboard
