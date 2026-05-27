#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

DEVICE_DB="$SCRIPT_DIR/device_db.py"
DATASET_DB="$SCRIPT_DIR/dataset_db.pyon"
REPOSITORY="$SCRIPT_DIR/repository"
SERVER="${ARTIQ_SERVER:-127.0.0.1}"
HEADLESS="${HEADLESS:-auto}"

if [[ "${1:-}" == "--no-entangler" ]]; then
  DEVICE_DB="$SCRIPT_DIR/device_db_no_entangler.py"
  shift
elif [[ "${1:-}" == "--with-entangler" ]]; then
  shift
fi

if [[ ! -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
  echo "Missing virtualenv interpreter at $SCRIPT_DIR/.venv/bin/python" >&2
  echo "Run 'uv sync' in $SCRIPT_DIR first." >&2
  exit 1
fi

unset PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONUSERBASE __PYVENV_LAUNCHER__
export PYTHONNOUSERSITE=1
export PATH="$SCRIPT_DIR/.venv/bin:$PATH"

PYTHON="$SCRIPT_DIR/.venv/bin/python"
PIDS=()
SERVICE_PORTS=(3249 3250 3251 1066 1067 1383 1384 1385 1386)

find_old_services() {
  local pids=()
  local port matches pid

  for port in "${SERVICE_PORTS[@]}"; do
    matches="$(ss -ltnp "sport = :$port" 2>/dev/null \
      | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' || true)"
    if [[ -n "$matches" ]]; then
      while IFS= read -r pid; do
        [[ -n "$pid" && "$pid" != "$$" ]] && pids+=("$pid")
      done <<< "$matches"
    fi
  done

  matches="$(pgrep -f "$SCRIPT_DIR/.venv/bin/.*artiq_\\|uv run artiq_" || true)"
  if [[ -n "$matches" ]]; then
    while IFS= read -r pid; do
      [[ -n "$pid" && "$pid" != "$$" ]] && pids+=("$pid")
    done <<< "$matches"
  fi

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
  sleep 1
}

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

stop_old_services

echo "Starting ARTIQ master with:"
echo "  device_db:  $DEVICE_DB"
echo "  dataset_db: $DATASET_DB"
echo "  repository: $REPOSITORY"

"$PYTHON" -I -m artiq.frontend.artiq_master \
  --name atom_photon_parity_6 \
  --device-db "$DEVICE_DB" \
  --dataset-db "$DATASET_DB" \
  --repository "$REPOSITORY" \
  --bind "$SERVER" \
  "$@" &
PIDS+=("$!")
sleep 1

if ! kill -0 "${PIDS[0]}" 2>/dev/null; then
  echo "ARTIQ master failed to start." >&2
  wait "${PIDS[0]}" || true
  exit 1
fi

echo "Starting ARTIQ controller manager..."
"$PYTHON" -I -m artiq_comtools.artiq_ctlmgr --server "$SERVER" &
PIDS+=("$!")
sleep 1

if [[ "$HEADLESS" == "1" || "$HEADLESS" == "true" ]]; then
  echo "HEADLESS=$HEADLESS; master and ctlmgr are running. Press Ctrl-C to stop."
  wait
elif [[ "$HEADLESS" == "auto" && -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  echo "No GUI display detected; master and ctlmgr are running without artiq_dashboard."
  echo "Set HEADLESS=0 to force dashboard launch."
  wait
else
  echo "Starting ARTIQ dashboard..."
  "$PYTHON" -I -m artiq.frontend.artiq_dashboard --server "$SERVER"
fi
