#!/usr/bin/env python3
"""Build the ARTIQ-Zynq device_map config blob from a device_db.py file."""

from __future__ import annotations

import argparse
import importlib.util
import struct
from pathlib import Path
from typing import Any


def load_device_db(path: Path) -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location("device_db_source", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "device_db")


def rtio_device_entries(device_db: dict[str, Any]) -> list[tuple[int, str]]:
    entries_by_channel: dict[int, str] = {}

    for name, descriptor in device_db.items():
        if not isinstance(descriptor, dict) or descriptor.get("type") != "local":
            continue

        arguments = descriptor.get("arguments", {})
        if not isinstance(arguments, dict) or "channel" not in arguments:
            continue

        channel = arguments["channel"]
        if isinstance(channel, str):
            channel = int(channel, 0)
        if not isinstance(channel, int):
            continue

        entries_by_channel.setdefault(channel, name)

    return sorted((channel, name) for channel, name in entries_by_channel.items())


def encode_device_map(entries: list[tuple[int, str]]) -> bytes:
    payload = bytearray()
    payload += struct.pack("<I", len(entries))

    for channel, name in entries:
        encoded_name = name.encode("utf-8")
        payload += struct.pack("<I", channel)
        payload += struct.pack("<I", len(encoded_name))
        payload += encoded_name

    return bytes(payload)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate /config/device_map.bin for ARTIQ-Zynq RTIO error names."
    )
    parser.add_argument(
        "--device-db",
        default="device_db.py",
        type=Path,
        help="device_db.py to read, default: %(default)s",
    )
    parser.add_argument(
        "--output",
        default=Path("device_map.bin"),
        type=Path,
        help="binary output path, default: %(default)s",
    )
    args = parser.parse_args()

    device_db = load_device_db(args.device_db)
    entries = rtio_device_entries(device_db)
    args.output.write_bytes(encode_device_map(entries))

    print(f"wrote {args.output} with {len(entries)} RTIO channel names")


if __name__ == "__main__":
    main()
