#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

CORE_IP="192.168.1.129"
PROXY_BIND="127.0.0.1"
PROXY_PORT="1383"
HEADLESS="${HEADLESS:-auto}"
DEVICE_DB="$SCRIPT_DIR/device_db.py"
DATASET_DB="$SCRIPT_DIR/dataset_db.pyon"
REPOSITORY="$SCRIPT_DIR/repository"
MASTER_NAME="${MASTER_NAME:-entangler}"
MASTER_PORTS=(3250 3251)
PROXY_PORTS=("$PROXY_PORT" 1384)

# Point dynaconf at the local settings.toml instead of the installed package's copy
export SETTINGS_FILE_FOR_DYNACONF="$SCRIPT_DIR/settings.toml"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

# Prefer the local virtualenv directly and isolate it from any surrounding
# nix/host Python environment variables that can leak incompatible packages.
if [[ ! -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
    echo "Missing virtualenv interpreter at $SCRIPT_DIR/.venv/bin/python" >&2
    echo "Run 'uv sync' in $SCRIPT_DIR first." >&2
    exit 1
fi

unset PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONUSERBASE __PYVENV_LAUNCHER__
export PYTHONNOUSERSITE=1

PYTHON="$SCRIPT_DIR/.venv/bin/python"
PIDS=()

OLD_SERVICE_PATTERNS=(
    "uv run artiq_master"
    "uv run artiq_ctlmgr"
    "$SCRIPT_DIR/.venv/bin/artiq_master"
    "$SCRIPT_DIR/.venv/bin/artiq_ctlmgr"
    "$SCRIPT_DIR/.venv/bin/python3 $SCRIPT_DIR/.venv/bin/artiq_master"
    "$SCRIPT_DIR/.venv/bin/python3 $SCRIPT_DIR/.venv/bin/artiq_ctlmgr"
    "$SCRIPT_DIR/.venv/bin/python -I -m artiq.frontend.artiq_master"
    "$SCRIPT_DIR/.venv/bin/python -I -m artiq_comtools.artiq_ctlmgr"
    "$SCRIPT_DIR/.venv/bin/python -I -m artiq.frontend.artiq_dashboard"
    "$SCRIPT_DIR/.venv/bin/python -I -m artiq.frontend.aqctl_moninj_proxy"
)

port_in_use() {
    local port="$1"
    ss -ltn "sport = :$port" | tail -n +2 | grep -q .
}

show_port_owner() {
    local port="$1"
    ss -ltnp "sport = :$port" 2>/dev/null | tail -n +2 || true
}

find_old_services() {
    local pids=()
    local pattern
    local matches
    local port

    for pattern in "${OLD_SERVICE_PATTERNS[@]}"; do
        matches="$(pgrep -f "$pattern" || true)"
        if [[ -n "$matches" ]]; then
            while IFS= read -r pid; do
                [[ -n "$pid" && "$pid" != "$$" ]] && pids+=("$pid")
            done <<< "$matches"
        fi
    done

    for port in "${MASTER_PORTS[@]}" "${PROXY_PORTS[@]}"; do
        matches="$(ss -ltnp "sport = :$port" 2>/dev/null \
            | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' || true)"
        if [[ -n "$matches" ]]; then
            while IFS= read -r pid; do
                [[ -n "$pid" && "$pid" != "$$" ]] && pids+=("$pid")
            done <<< "$matches"
        fi
    done

    if [[ ${#pids[@]} -gt 0 ]]; then
        printf '%s\n' "${pids[@]}" | sort -n -u
    fi
}

stop_old_services() {
    local old_pids=()
    local pid

    while IFS= read -r pid; do
        [[ -n "$pid" ]] && old_pids+=("$pid")
    done < <(find_old_services)

    if [[ ${#old_pids[@]} -eq 0 ]]; then
        return
    fi

    echo "Stopping old ARTIQ services: ${old_pids[*]}"
    kill "${old_pids[@]}" 2>/dev/null || true

    for _ in {1..20}; do
        local still_running=()
        for pid in "${old_pids[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then
                still_running+=("$pid")
            fi
        done
        if [[ ${#still_running[@]} -eq 0 ]]; then
            return
        fi
        sleep 0.1
    done

    echo "Force-stopping old ARTIQ services: ${old_pids[*]}"
    kill -9 "${old_pids[@]}" 2>/dev/null || true
}

stop_old_services

for port in "${MASTER_PORTS[@]}" "${PROXY_PORTS[@]}"; do
    if port_in_use "$port"; then
        echo "Port $port is already in use; an old ARTIQ service is probably still running." >&2
        show_port_owner "$port" >&2
        echo "Stop the old service before rerunning this script." >&2
        exit 1
    fi
done

cleanup() {
    local status=$?
    if [[ ${#PIDS[@]} -gt 0 ]]; then
        echo "Stopping ARTIQ services: ${PIDS[*]}"
        kill "${PIDS[@]}" 2>/dev/null || true
        wait "${PIDS[@]}" 2>/dev/null || true
    fi
    exit "$status"
}
trap cleanup INT TERM EXIT

echo "Starting ARTIQ master with:"
echo "  device_db:  $DEVICE_DB"
echo "  dataset_db: $DATASET_DB"
echo "  repository: $REPOSITORY"

"$PYTHON" -I -m artiq.frontend.artiq_master \
    --name "$MASTER_NAME" \
    --device-db "$DEVICE_DB" \
    --dataset-db "$DATASET_DB" \
    --repository "$REPOSITORY" &
PIDS+=("$!")
sleep 0.5

# Start ctlmgr
"$PYTHON" -I -m artiq_comtools.artiq_ctlmgr &
PIDS+=("$!")
sleep 0.5

# Start moninj proxy in background
"$PYTHON" -I -m artiq.frontend.aqctl_moninj_proxy --bind "$PROXY_BIND" --port-proxy "$PROXY_PORT" "$CORE_IP" &
PIDS+=("$!")
sleep 0.5

if [[ "$HEADLESS" == "1" || "$HEADLESS" == "true" ]]; then
    wait
elif [[ "$HEADLESS" == "auto" && -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    echo "No GUI display detected; leaving services running without artiq_dashboard."
    echo "Set HEADLESS=0 to force the dashboard or HEADLESS=1 to silence this message."
    wait
else
    "$PYTHON" -I -m artiq.frontend.artiq_dashboard
fi
