#!/usr/bin/env python3
"""Hardware adapter layer for Milestone 1.

The adapter exposes semantic operations rather than raw joint-angle calls so
callers can be swapped between a real PiDog runtime and a workstation-safe
simulator without changing their code.
"""

from __future__ import annotations

import importlib
import importlib.metadata as metadata
from dataclasses import dataclass, field
from typing import Any, Protocol

PINNED_PKG_VERSIONS = {
    "pidog": "1.3.13",
    "robot_hat": "2.3.6",
}


class HardwareAdapter(Protocol):
    def arm(self) -> None:
        """Prepare the underlying runtime for motion and speech use."""

    def set_posture(self, posture: str) -> None:
        """Set a semantic posture such as 'idle', 'happy', or 'rest'."""

    def set_head(self, heading: str) -> None:
        """Set a semantic head state such as 'neutral' or 'searching'."""

    def set_tail(self, intensity: float) -> None:
        """Move the tail with a clamped intensity in the range [-1.0, 1.0]."""

    def play_gesture(self, gesture: str) -> None:
        """Trigger a named gesture or animation."""

    def speak(self, sound: str, volume: int = 80) -> Any:
        """Play a named sound or utterance."""

    def describe(self) -> dict[str, Any]:
        """Return a stable snapshot of adapter state."""


@dataclass
class RuntimeProbe:
    package: str
    ok: bool
    module: str | None = None
    version: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "module": self.module,
            "version": self.version,
            "error": self.error,
        }


class HardwareAdapterBase:
    """Common state and guard behavior shared by both adapters."""

    def __init__(self) -> None:
        self._armed = False
        self._posture = "idle"
        self._head = "neutral"
        self._tail = 0.0
        self._gesture_log: list[str] = []

    def arm(self) -> None:
        self._armed = True

    def set_posture(self, posture: str) -> None:
        self._ensure_armed()
        self._posture = posture

    def set_head(self, heading: str) -> None:
        self._ensure_armed()
        self._head = heading

    def set_tail(self, intensity: float) -> None:
        self._ensure_armed()
        self._tail = max(-1.0, min(1.0, float(intensity)))

    def play_gesture(self, gesture: str) -> None:
        self._ensure_armed()
        self._gesture_log.append(gesture)

    def speak(self, sound: str, volume: int = 80) -> dict[str, Any]:
        self._ensure_armed()
        return {"ok": True, "sound": sound, "volume": max(0, min(100, int(volume)))}

    def describe(self) -> dict[str, Any]:
        return {
            "armed": self._armed,
            "posture": self._posture,
            "head": self._head,
            "tail": round(self._tail, 3),
            "gestures": list(self._gesture_log),
        }

    def _ensure_armed(self) -> None:
        if not self._armed:
            raise RuntimeError("adapter is not armed")


class SimulatorAdapter(HardwareAdapterBase):
    """Deterministic adapter used for workstation tests and simulation."""


class PiAdapter(HardwareAdapterBase):
    """Adapter backed by the real PiDog libraries when available."""

    def __init__(
        self,
        *,
        backend: Any | None = None,
        pinned_versions: dict[str, str] | None = None,
        resolved_versions: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self._backend = backend
        self._pinned_versions = pinned_versions or dict(PINNED_PKG_VERSIONS)
        self._resolved_versions = resolved_versions

    def arm(self) -> None:
        if self._backend is None:
            self._backend = self._import_backend()
        if self._backend is None:
            raise RuntimeError("PiDog libraries are not available in this environment")
        self._validate_versions()
        super().arm()

    def speak(self, sound: str, volume: int = 80) -> Any:
        self._ensure_armed()
        if self._backend is None:
            raise RuntimeError("PiDog backend unavailable")
        if hasattr(self._backend, "speak_block"):
            return self._backend.speak_block(sound, volume)
        return {"ok": True, "sound": sound, "volume": max(0, min(100, int(volume)))}

    def get_battery_status(self) -> dict[str, Any]:
        if self._backend is None:
            raise RuntimeError("PiDog backend unavailable")
        if not hasattr(self._backend, "get_battery_voltage"):
            return {"ok": False, "error": "battery voltage API is unavailable"}
        try:
            voltage = float(self._backend.get_battery_voltage())
        except Exception as exc:  # pragma: no cover - diagnostic only
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        min_voltage = 6.5
        max_voltage = 8.4
        percent = max(0, min(100, round(((voltage - min_voltage) / (max_voltage - min_voltage)) * 100)))
        return {
            "ok": True,
            "voltage_v": round(voltage, 2),
            "percent": percent,
            "state": "low" if percent < 20 else "ok",
        }

    def _validate_versions(self) -> None:
        resolved = self._resolved_versions or self._probe_versions()
        for package_name, expected_version in self._pinned_versions.items():
            actual_version = resolved.get(package_name)
            if actual_version is None:
                raise RuntimeError(f"{package_name} is not installed")
            if actual_version != expected_version:
                raise RuntimeError(f"{package_name} version mismatch: expected {expected_version}, got {actual_version}")

    def _probe_versions(self) -> dict[str, str]:
        versions: dict[str, str] = {}
        for package_name in self._pinned_versions:
            try:
                versions[package_name] = metadata.version(package_name)
            except metadata.PackageNotFoundError:
                continue
        return versions

    def _import_backend(self) -> Any | None:
        try:
            pidog_module = importlib.import_module("pidog")
        except Exception:
            return None
        return pidog_module.Pidog() if hasattr(pidog_module, "Pidog") else pidog_module


def inspect_runtime() -> dict[str, Any]:
    """Probe the runtime for the PiDog and robot_hat packages."""

    result: dict[str, Any] = {}
    for package_name in ("robot_hat", "pidog"):
        try:
            module = importlib.import_module(package_name)
        except Exception as exc:  # pragma: no cover - diagnostic only
            result[package_name] = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
            continue

        try:
            version = metadata.version(package_name)
        except metadata.PackageNotFoundError:
            version = None

        result[package_name] = {
            "ok": True,
            "module": getattr(module, "__file__", None),
            "version": version,
        }

    return result


def build_runtime_probe() -> dict[str, RuntimeProbe]:
    probes: dict[str, RuntimeProbe] = {}
    for package_name in ("robot_hat", "pidog"):
        try:
            module = importlib.import_module(package_name)
        except Exception as exc:  # pragma: no cover - diagnostic only
            probes[package_name] = RuntimeProbe(package=package_name, ok=False, error=f"{type(exc).__name__}: {exc}")
            continue

        try:
            version = metadata.version(package_name)
        except metadata.PackageNotFoundError:
            version = None

        probes[package_name] = RuntimeProbe(
            package=package_name,
            ok=True,
            module=getattr(module, "__file__", None),
            version=version,
        )

    return probes
