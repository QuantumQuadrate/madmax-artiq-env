#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHONNOUSERSITE=1 uv run python -I -m artiq.frontend.artiq_run \
  --device-db device_db.py \
  --dataset-db dataset_db.pyon \
  -c AtomPhotonParity6Experiment \
  repository/atom_photon_parity_6_experiment.py \
  "$@"
