#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

CLASS=AtomPhotonParity6NoEntangler
DEVICE_DB=device_db_no_entangler.py
SCRIPT=repository/atom_photon_parity_6_no_entangler.py

if [[ "${1:-}" == "--with-entangler" ]]; then
  CLASS=AtomPhotonParity6WithEntanglerCore
  DEVICE_DB=device_db.py
  SCRIPT=repository/atom_photon_parity_6_with_entangler.py
  shift
elif [[ "${1:-}" == "--no-entangler" ]]; then
  shift
fi

PYTHONNOUSERSITE=1 uv run python -I -m artiq.frontend.artiq_run \
  --device-db "$DEVICE_DB" \
  --dataset-db dataset_db.pyon \
  -c "$CLASS" \
  "$SCRIPT" \
  "$@"
