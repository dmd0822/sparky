"""Hardware abstraction layer for the Sparky device runtime.

Application code depends on the ports in :mod:`sparky_device.hardware.ports`
and obtains an implementation from :func:`create_ports`. The SunFounder
libraries (``pidog``, ``robot_hat``, ``vilib``) are imported lazily inside the
adapters, so importing this package never requires a Raspberry Pi.

    from sparky_device.hardware import create_ports

    with create_ports() as robot:
        robot.motion.do_action("sit")
"""

from __future__ import annotations

from .factory import (
    AUTO_PROFILE,
    HARDWARE_ENV_VAR,
    PIDOG_PROFILE,
    SIMULATOR_PROFILE,
    VALID_PROFILES,
    create_ports,
    resolve_profile,
)
from .pidog_adapters import (
    PidogBoardAdapter,
    PidogMotionAdapter,
    PidogSensorAdapter,
    VilibCameraAdapter,
    build_pidog_ports,
    vendor_libraries_available,
)
from .ports import (
    DEFAULT_LIMITS,
    HEAD_JOINT_COUNT,
    LEG_JOINT_COUNT,
    BoardPort,
    CameraPort,
    Frame,
    HardwareError,
    HardwareUnavailableError,
    ImuReading,
    MotionLimits,
    MotionPort,
    RgbColor,
    RobotPorts,
    SensorPort,
    ServoRange,
    TouchState,
)
from .simulators import (
    MotionCommand,
    RgbCommand,
    SimulatedBoard,
    SimulatedCamera,
    SimulatedMotion,
    SimulatedSensors,
    SoundCommand,
    build_simulated_ports,
    solid_frame,
)

__all__ = [
    "AUTO_PROFILE",
    "DEFAULT_LIMITS",
    "HARDWARE_ENV_VAR",
    "HEAD_JOINT_COUNT",
    "LEG_JOINT_COUNT",
    "PIDOG_PROFILE",
    "SIMULATOR_PROFILE",
    "VALID_PROFILES",
    "BoardPort",
    "CameraPort",
    "Frame",
    "HardwareError",
    "HardwareUnavailableError",
    "ImuReading",
    "MotionCommand",
    "MotionLimits",
    "MotionPort",
    "PidogBoardAdapter",
    "PidogMotionAdapter",
    "PidogSensorAdapter",
    "RgbColor",
    "RgbCommand",
    "RobotPorts",
    "SensorPort",
    "ServoRange",
    "SimulatedBoard",
    "SimulatedCamera",
    "SimulatedMotion",
    "SimulatedSensors",
    "SoundCommand",
    "TouchState",
    "VilibCameraAdapter",
    "build_pidog_ports",
    "build_simulated_ports",
    "create_ports",
    "resolve_profile",
    "solid_frame",
    "vendor_libraries_available",
]
