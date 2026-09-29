#!/usr/bin/env python3
"""Hardware-in-the-loop smoke check for Sparky's motion service.

The script imports cleanly off-robot. Real PiDog vendor packages are reached
only through ``sparky_device.hardware.create_ports(profile="pidog")`` when the
operator chooses the real hardware run.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Callable, TextIO


ROOT = Path(__file__).resolve().parents[1]
DEVICE_SRC = ROOT / "src" / "device"
if DEVICE_SRC.exists():
    sys.path.insert(0, str(DEVICE_SRC))

from sparky_device.hardware import (  # noqa: E402
    HardwareError,
    PIDOG_PROFILE,
    SIMULATOR_PROFILE,
    RobotPorts,
    create_ports,
)
from sparky_device.services import MotionService  # noqa: E402


StepHook = Callable[[str, MotionService, RobotPorts], None]


@dataclass(frozen=True)
class RunResult:
    """Result returned by the smoke-check runner."""

    ok: bool
    message: str


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Sparky motion-service HIL smoke check. By default this "
            "requires a real Raspberry Pi with a PiDog attached; use "
            "--simulate to rehearse safely on a laptop."
        )
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Use the SimulatedMotion port instead of the real PiDog adapter.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help=(
            "Do not pause for operator confirmation before physical moves. "
            "Only use this when the dog is already supported and the area is clear."
        ),
    )
    parser.add_argument(
        "--wait-timeout",
        type=float,
        default=10.0,
        help="Seconds to wait for posture moves to settle before failing (default: 10).",
    )
    return parser


def make_robot(*, simulate: bool) -> RobotPorts:
    """Build the requested port bundle through the existing hardware factory."""

    profile = SIMULATOR_PROFILE if simulate else PIDOG_PROFILE
    return create_ports(profile=profile)


def run_check(
    robot: RobotPorts,
    *,
    assume_yes: bool = False,
    wait_timeout: float = 10.0,
    out: TextIO = sys.stdout,
    prompt: Callable[[str], str] = input,
    after_step: StepHook | None = None,
) -> RunResult:
    """Run the motion-service smoke check against an already-created robot."""

    motion = MotionService(robot.motion)

    def write(message: str = "") -> None:
        print(message, file=out)

    def state(label: str) -> None:
        write(f"{label} MotionState: {motion.state}")

    def pause(message: str) -> None:
        if assume_yes:
            write(f"{message} (--yes supplied; continuing)")
            return
        prompt(f"\n{message}\nPress Enter to continue, or Ctrl+C to abort...")

    def checkpoint(name: str) -> None:
        if after_step is not None:
            after_step(name, motion, robot)

    write(f"Motion service HIL smoke check using profile: {robot.profile}")
    state("Initial")

    pause("Step 13: confirm the dog is supported with legs clear; the service will sit.")
    write("Step 13: service sit.")
    motion.sit(speed=50)
    state("Step 13 issued")
    motion.wait_until_idle(timeout=wait_timeout)
    state("Step 13 settled")
    checkpoint("sit")

    write("Step 14: verify locomotion is rejected while posture is sitting.")
    try:
        motion.trot(steps=1, speed=40)
    except HardwareError as error:
        write(f"Step 14 PASS rejected trot from sit: {error}")
    else:
        return RunResult(False, "Step 14 FAIL: trot from sit was accepted")
    state("Step 14")
    checkpoint("reject-from-sit")

    pause("Step 15a: the service will stand. Clear the area and keep the switch reachable.")
    write("Step 15a: service stand.")
    motion.stand(speed=50)
    state("Step 15a issued")
    motion.wait_until_idle(timeout=wait_timeout)
    state("Step 15a settled")
    checkpoint("stand")

    pause("Step 15b: the dog will start a slow forward gait.")
    write("Step 15b: service slow forward gait.")
    motion.forward(steps=5, speed=30)
    state("Step 15b issued")
    checkpoint("forward")

    write("Step 16: verify a conflicting turn is rejected while forward is in flight.")
    try:
        motion.turn_left(steps=1, speed=30)
    except HardwareError as error:
        write(f"Step 16 PASS rejected conflicting turn: {error}")
    else:
        return RunResult(False, "Step 16 FAIL: conflicting turn was accepted")
    state("Step 16")
    checkpoint("reject-conflict")

    pause("Step 17: stop will pre-empt the gait, then run a second no-op stop.")
    write("Step 17: service stop pre-empts and is idempotent.")
    motion.stop()
    state("Step 17 first stop")
    motion.stop()
    state("Step 17 second stop")
    motion.wait_until_idle(timeout=min(wait_timeout, 3.0))
    state("Step 17 settled")
    checkpoint("stop")

    return RunResult(True, "Motion service HIL smoke check PASS")


def safe_shutdown(robot: RobotPorts | None, out: TextIO = sys.stdout) -> None:
    """Best-effort safe stop and close. Let cleanup failures propagate."""

    if robot is None:
        return
    print("Safety cleanup: safe-stopping motion and closing ports.", file=out)
    robot.close()


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    args = build_arg_parser().parse_args(argv)
    robot: RobotPorts | None = None
    result = RunResult(False, "Motion service HIL smoke check did not complete")
    exit_code = 1
    shutdown_error: BaseException | None = None
    try:
        robot = make_robot(simulate=args.simulate)
        result = run_check(
            robot,
            assume_yes=args.yes,
            wait_timeout=args.wait_timeout,
            out=out,
        )
        exit_code = 0 if result.ok else 1
    except KeyboardInterrupt:
        result = RunResult(False, "Motion service HIL smoke check interrupted by operator")
        exit_code = 130
    except Exception as error:  # noqa: BLE001 - CLI reports and exits non-zero.
        result = RunResult(False, f"Motion service HIL smoke check FAIL: {error}")
        exit_code = 1
    finally:
        try:
            safe_shutdown(robot, out=out)
        except BaseException as error:  # noqa: BLE001 - report after cleanup attempt.
            shutdown_error = error
        print(result.message, file=out)
        if shutdown_error is not None:
            print(f"Safety cleanup reported an error: {shutdown_error}", file=out)
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
