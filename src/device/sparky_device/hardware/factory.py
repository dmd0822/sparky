"""Selects a hardware profile and builds the matching port bundle.

Application code calls :func:`create_ports` and never imports an adapter or a
simulator directly. That is what keeps the vendor libraries out of the import
graph on machines that have no robot attached.

Profiles:

``simulator``
    Always use the recording fakes. This is the CI default.
``pidog``
    Always use the SunFounder libraries; fail loudly if they are missing.
``auto``
    Use the vendor libraries when they import cleanly, otherwise fall back to
    the simulators. Handy on a developer laptop.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Mapping

from .pidog_adapters import PIDOG_PROFILE, build_pidog_ports, vendor_libraries_available
from .ports import DEFAULT_LIMITS, Frame, MotionLimits, RobotPorts
from .simulators import SIMULATOR_PROFILE, SimulatedMicrophone, build_simulated_ports

__all__ = [
    "AUTO_PROFILE",
    "HARDWARE_ENV_VAR",
    "PIDOG_PROFILE",
    "SIMULATOR_PROFILE",
    "VALID_PROFILES",
    "create_ports",
    "resolve_profile",
]

#: Environment variable that selects the profile.
HARDWARE_ENV_VAR = "SPARKY_HARDWARE"

AUTO_PROFILE = "auto"
VALID_PROFILES = (SIMULATOR_PROFILE, PIDOG_PROFILE, AUTO_PROFILE)


def resolve_profile(
    requested: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    """Resolve the effective profile name.

    Precedence is explicit argument, then ``SPARKY_HARDWARE``, then ``auto``.
    An ``auto`` result is narrowed to ``pidog`` or ``simulator`` by probing for
    the vendor packages.
    """

    environ = os.environ if env is None else env
    raw = requested if requested is not None else environ.get(HARDWARE_ENV_VAR, AUTO_PROFILE)
    profile = (raw or AUTO_PROFILE).strip().lower()
    if profile not in VALID_PROFILES:
        raise ValueError(
            f"unknown hardware profile {raw!r}; expected one of "
            f"{', '.join(VALID_PROFILES)}"
        )
    if profile == AUTO_PROFILE:
        return PIDOG_PROFILE if vendor_libraries_available() else SIMULATOR_PROFILE
    return profile


def create_ports(
    profile: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
    limits: MotionLimits = DEFAULT_LIMITS,
    frames: Iterable[Frame] | None = None,
    microphone: SimulatedMicrophone | None = None,
    microphone_fixture_path: str | Path | None = None,
) -> RobotPorts:
    """Build the port bundle for the resolved profile.

    Args:
        profile: ``simulator``, ``pidog``, ``auto``, or ``None`` to read the
            environment.
        env: Environment mapping to read instead of :data:`os.environ`.
        limits: Motion envelope applied by both the simulators and adapters.
        frames: Frames the simulated camera should replay. Ignored on hardware.
        microphone: Simulated microphone to use. Ignored on hardware.
        microphone_fixture_path: WAV fixture for the simulated microphone.
            Ignored on hardware.

    Raises:
        HardwareUnavailableError: ``pidog`` was requested but the vendor
            libraries are missing or the board failed to initialise.
    """

    resolved = resolve_profile(profile, env=env)
    if resolved == PIDOG_PROFILE:
        return build_pidog_ports(limits=limits)
    return build_simulated_ports(
        limits=limits,
        frames=frames,
        microphone=microphone,
        microphone_fixture_path=microphone_fixture_path,
    )
