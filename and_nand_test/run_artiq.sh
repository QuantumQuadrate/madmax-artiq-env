#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
artiq_master -r repository -d device_db.py
