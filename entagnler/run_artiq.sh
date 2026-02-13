#!/usr/bin/env bash
set -euo pipefail

CORE_IP="192.168.1.129"
PROXY_BIND="127.0.0.1"
PROXY_PORT="1383"

pids=()

cleanup() {
  echo "Stopping ARTIQ processes..."
  for pid in "${pids[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Start master
uv run artiq_master &
pids+=($!)
sleep 0.5

# Start ctlmgr
uv run artiq_ctlmgr &
pids+=($!)
sleep 0.5

# Start moninj proxy with auto-restart (so dashboard survives core resets)
uv run aqctl_moninj_proxy --bind "$PROXY_BIND" --port-proxy "$PROXY_PORT" "$CORE_IP" || true
pids+=($!)
sleep 0.5

# Start dashboard in foreground (so script stays attached)
exec uv run artiq_dashboard
