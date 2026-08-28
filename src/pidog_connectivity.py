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
import importlib
import json
import os
import platform
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def build_report() -> dict[str, Any]:
    report: dict[str, Any] = {
        "project_root": str(ROOT),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "machine": platform.machine(),
        "imports": {},
    }

    for module_name in ("robot_hat", "pidog"):
        try:
            module = importlib.import_module(module_name)
            report["imports"][module_name] = {
                "ok": True,
                "module": getattr(module, "__file__", None),
                "version": getattr(module, "__version__", None),
            }
        except Exception as exc:  # pragma: no cover - diagnostic only
            report["imports"][module_name] = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
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


def get_battery_status(dog: Any) -> dict[str, Any]:
    """Return raw voltage and an approximate percentage for the PiDog battery pack."""
    try:
        voltage = float(dog.get_battery_voltage())
    except Exception as exc:  # pragma: no cover - diagnostic only
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    min_voltage = 6.5
    max_voltage = 8.4
    percent = max(0, min(100, round(((voltage - min_voltage) / (max_voltage - min_voltage)) * 100)))
    return {
        "ok": True,
        "voltage_v": round(voltage, 2),
        "percent": percent,
        "state": "low" if percent < 20 else "ok",
    }


def display_battery_level(dog: Any) -> str:
    """Human-readable battery detail for the PiDog startup check."""
    battery = get_battery_status(dog)
    if not battery.get("ok", False):
        return f"Battery unavailable: {battery.get('error', 'unknown error')}"
    return f"Battery: {battery['voltage_v']}V ({battery['percent']}%)"


def instantiate_pidog() -> dict[str, Any]:
    if not can_instantiate_hardware():
        return {
            "ok": False,
            "skipped": "Hardware probe skipped; this script is running outside a Pi-like environment.",
        }

    try:
        from pidog import Pidog

        dog = Pidog()
        bark_result = dog.speak_block("single_bark_1", 80)
        battery = get_battery_status(dog)
        return {
            "ok": True,
            "instance_type": type(dog).__name__,
            "module": Pidog.__module__,
            "battery": battery,
            "display": display_battery_level(dog),
            "bark": {
                "ok": bark_result is not False,
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

    if not report["imports"].get("robot_hat", {}).get("ok", False):
        return 1
    if not report["imports"].get("pidog", {}).get("ok", False):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
