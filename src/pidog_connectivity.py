#!/usr/bin/env python3
"""Minimal PiDog connectivity smoke test.

This script is intended to run directly on a PiDog where the SunFounder
`pidog` and `robot_hat` packages are already installed via the standard
installation path.

Usage:
    python3 src/pidog_connectivity.py
    python3 src/pidog_connectivity.py --init
"""

from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path
from typing import Any

try:
    from .hardware_adapter import PiAdapter, inspect_runtime
except ImportError:  # pragma: no cover - executed when run as a script
    from hardware_adapter import PiAdapter, inspect_runtime

ROOT = Path(__file__).resolve().parents[1]


def build_report() -> dict[str, Any]:
    report: dict[str, Any] = {
        "project_root": str(ROOT),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "machine": platform.machine(),
        "imports": inspect_runtime(),
    }
    return report


def can_instantiate_hardware() -> bool:
    """Best-effort safety gate: only attempt hardware init on Raspberry Pi-like systems."""
    if os.name != "posix":
        return False
    machine = platform.machine().lower()
    if "arm" not in machine and "aarch64" not in machine:
        return False
    return Path("/dev/i2c-1").exists() or Path("/dev/i2c-0").exists()


def get_battery_status(adapter: PiAdapter) -> dict[str, Any]:
    """Return raw voltage and an approximate percentage for the PiDog battery pack."""
    return adapter.get_battery_status()


def display_battery_level(adapter: PiAdapter) -> str:
    """Human-readable battery detail for the PiDog startup check."""
    battery = get_battery_status(adapter)
    if not battery.get("ok", False):
        return f"Battery unavailable: {battery.get('error', 'unknown error')}"
    return f"Battery: {battery['voltage_v']}V ({battery['percent']}%)"


def instantiate_pidog() -> dict[str, Any]:
    if not can_instantiate_hardware():
        return {
            "ok": False,
            "skipped": "Hardware probe skipped; this script is running outside a Pi-like environment.",
        }

    adapter = PiAdapter()
    try:
        adapter.arm()
        bark_result = adapter.speak("single_bark_1", 80)
        battery = get_battery_status(adapter)
        return {
            "ok": True,
            "instance_type": type(adapter).__name__,
            "battery": battery,
            "display": display_battery_level(adapter),
            "bark": {
                "ok": bool(bark_result),
                "sound": "single_bark_1",
            },
        }
    except Exception as exc:  # pragma: no cover - diagnostic only
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test PiDog library connectivity on the robot itself.")
    parser.add_argument(
        "--init",
        action="store_true",
        help="Attempt to instantiate Pidog if running on a Raspberry Pi-like host.",
    )
    args = parser.parse_args()

    report = build_report()
    if args.init:
        report["hardware_init"] = instantiate_pidog()

    print(json.dumps(report, indent=2, sort_keys=True))

    missing_runtime = not report["imports"].get("robot_hat", {}).get("ok", False)
    missing_runtime = missing_runtime or not report["imports"].get("pidog", {}).get("ok", False)
    if missing_runtime and can_instantiate_hardware():
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
