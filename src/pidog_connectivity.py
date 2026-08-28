#!/usr/bin/env python3
"""Minimal PiDog connectivity smoke test.

This script verifies that the vendored PiDog and robot_hat libraries in
`exlibs/` can be discovered and imported from this repository without changing
those vendor sources.

Usage:
    python src/pidog_connectivity.py
    python src/pidog_connectivity.py --init
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXLIBS = ROOT / "exlibs"


def add_vendor_paths() -> None:
    """Prepend the local vendored libraries to Python's import path."""
    for library_dir in (EXLIBS / "pidog", EXLIBS / "robot-hat"):
        if library_dir.exists():
            path_text = str(library_dir)
            if path_text not in sys.path:
                sys.path.insert(0, path_text)


def build_report() -> dict[str, Any]:
    report: dict[str, Any] = {
        "project_root": str(ROOT),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "machine": platform.machine(),
        "vendor_paths": {
            "pidog": str(EXLIBS / "pidog"),
            "robot_hat": str(EXLIBS / "robot-hat"),
        },
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


def instantiate_pidog() -> dict[str, Any]:
    if not can_instantiate_hardware():
        return {
            "ok": False,
            "skipped": "Hardware probe skipped; script is running outside a Pi-like environment.",
        }

    try:
        from pidog import Pidog

        dog = Pidog()
        return {
            "ok": True,
            "instance_type": type(dog).__name__,
            "module": Pidog.__module__,
        }
    except Exception as exc:  # pragma: no cover - diagnostic only
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test vendored PiDog connectivity.")
    parser.add_argument(
        "--init",
        action="store_true",
        help="Attempt to instantiate Pidog if running on a Raspberry Pi-like host.",
    )
    args = parser.parse_args()

    add_vendor_paths()
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
