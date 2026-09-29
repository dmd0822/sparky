#!/usr/bin/env python3
"""Hardware-in-the-loop checklist runner for Sparky's hardware ports and motion service.

The script imports cleanly off-robot. Real PiDog vendor packages are imported
only inside the step that validates the Pi environment, or through
``sparky_device.hardware.create_ports(profile="pidog")`` when the operator
chooses the real hardware run.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import sys
import time
from typing import Callable, Iterable, TextIO


ROOT = Path(__file__).resolve().parents[1]
DEVICE_SRC = ROOT / "src" / "device"
if DEVICE_SRC.exists():
    sys.path.insert(0, str(DEVICE_SRC))

from sparky_device.hardware import (  # noqa: E402
    HARDWARE_ENV_VAR,
    HardwareError,
    ImuReading,
    PIDOG_PROFILE,
    RgbColor,
    RobotPorts,
    SIMULATOR_PROFILE,
    TouchState,
    create_ports,
)
from sparky_device.services import MotionService  # noqa: E402


StepHook = Callable[[int, RobotPorts | None], None]
Prompt = Callable[[str], str]
ImportFunc = Callable[[str], object]


class Status(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class StepResult:
    number: int
    title: str
    status: Status
    message: str

    @property
    def ok(self) -> bool:
        return self.status is not Status.FAIL


@dataclass(frozen=True)
class RunResult:
    """Result returned by the HIL checklist runner."""

    ok: bool
    message: str
    results: tuple[StepResult, ...]
    robot: RobotPorts | None = None


@dataclass
class RunContext:
    robot: RobotPorts | None = None
    camera_import_ok: bool = True
    camera_import_message: str = "optional camera import not checked"
    motion_service: MotionService | None = None


_STEP_TITLES = {
    1: "Vendor import check",
    2: "Hardware profile check",
    3: "Port motion sit",
    4: "Port head turn",
    5: "Port forward gait and stop",
    6: "Ultrasonic distance",
    7: "Touch pads",
    8: "IMU tilt",
    9: "Bark sound",
    10: "RGB strip",
    11: "Camera capture",
    12: "Clean shutdown",
    13: "MotionService sit",
    14: "MotionService rejects sit-to-trot",
    15: "MotionService stand and forward",
    16: "MotionService rejects conflicting turn",
    17: "MotionService stop idempotency",
}
_ALL_STEPS = tuple(range(1, 18))
_SIMULATED_SENSOR_STEPS = {6, 7, 8}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run Sparky's full hardware-in-the-loop checklist (steps 1-17). "
            "By default this requires a Raspberry Pi with a PiDog attached; "
            "use --simulate to rehearse safely on a laptop."
        )
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Use simulator ports and skip real vendor imports.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help=(
            "Do not pause for operator confirmation before physical moves or "
            "manual sensor actions. Only use this when the dog is supported and "
            "the area is clear."
        ),
    )
    parser.add_argument(
        "--wait-timeout",
        type=float,
        default=10.0,
        help="Seconds to wait for motion to settle before failing (default: 10).",
    )
    parser.add_argument(
        "--steps",
        "--only",
        dest="steps",
        default="1-17",
        help=(
            "Comma-separated step list or ranges to run, for example '11' or "
            "'13-17' (default: 1-17). Cleanup still runs even when step 12 is omitted."
        ),
    )
    return parser


def parse_steps(value: str) -> tuple[int, ...]:
    selected: list[int] = []
    for raw_part in value.split(","):
        part = raw_part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if start > end:
                raise argparse.ArgumentTypeError(f"invalid descending range {part!r}")
            selected.extend(range(start, end + 1))
        else:
            selected.append(int(part))
    if not selected:
        raise argparse.ArgumentTypeError("at least one step must be selected")
    invalid = [step for step in selected if step not in _STEP_TITLES]
    if invalid:
        raise argparse.ArgumentTypeError(
            f"unknown step(s) {invalid}; expected numbers 1 through 17"
        )
    return tuple(dict.fromkeys(selected))


def make_robot(*, simulate: bool) -> RobotPorts:
    """Build the requested port bundle through the existing hardware factory."""

    profile = SIMULATOR_PROFILE if simulate else None
    robot = create_ports(profile=profile)
    if simulate:
        _prime_simulated_inputs(robot)
    return robot


def _prime_simulated_inputs(robot: RobotPorts) -> None:
    sensors = robot.sensors
    feed_distances = getattr(sensors, "feed_distances", None)
    if feed_distances is not None:
        feed_distances([20.0])
    feed_touches = getattr(sensors, "feed_touches", None)
    if feed_touches is not None:
        feed_touches([TouchState.LEFT, TouchState.RIGHT, TouchState.BOTH])
    feed_imu = getattr(sensors, "feed_imu", None)
    if feed_imu is not None:
        feed_imu(
            [
                ImuReading(acceleration=(0.0, 0.0, 1.0), gyro=(0.0, 0.0, 0.0)),
                ImuReading(acceleration=(0.4, 0.0, 0.8), gyro=(0.0, 0.1, 0.0)),
            ]
        )


def _result(number: int, status: Status, message: str) -> StepResult:
    return StepResult(number, _STEP_TITLES[number], status, message)


def _print_step(result: StepResult, out: TextIO) -> None:
    print(
        f"Step {result.number} {result.status.value}: {result.title} - {result.message}",
        file=out,
    )


def _pause(message: str, *, assume_yes: bool, out: TextIO, prompt: Prompt) -> None:
    if assume_yes:
        print(f"{message} (--yes supplied; continuing)", file=out)
        return
    prompt(f"\n{message}\nPress Enter to continue, or Ctrl+C to abort...")


def _check_imports(
    *, simulate: bool, import_func: ImportFunc = __import__
) -> tuple[StepResult, bool, str]:
    if simulate:
        return (
            _result(
                1,
                Status.SKIP,
                "simulator run: pidog, robot_hat, and vilib imports were not attempted",
            ),
            False,
            "simulator run skips optional camera import",
        )
    try:
        import_func("pidog")
        import_func("robot_hat")
    except Exception as error:  # noqa: BLE001 - import-time vendor failures are environment failures.
        return (
            _result(
                1,
                Status.FAIL,
                f"required PiDog import failed ({type(error).__name__}: {error}); fix the Pi environment before continuing",
            ),
            False,
            "required PiDog import failed",
        )
    try:
        import_func("vilib")
    except Exception as error:  # noqa: BLE001 - Picamera2 may raise RuntimeError at import time.
        return (
            _result(
                1,
                Status.PASS,
                f"required imports OK; optional vilib unavailable ({type(error).__name__}: {error}) so step 11 will SKIP",
            ),
            False,
            f"optional vilib import failed: {type(error).__name__}: {error}",
        )
    return (
        _result(1, Status.PASS, "required PiDog imports OK; optional vilib import OK"),
        True,
        "optional vilib import OK",
    )


def _ensure_robot(ctx: RunContext, *, simulate: bool) -> RobotPorts:
    if ctx.robot is None:
        ctx.robot = make_robot(simulate=simulate)
    return ctx.robot


def _ensure_motion_service(ctx: RunContext) -> MotionService:
    robot = ctx.robot
    if robot is None:
        raise HardwareError("robot ports have not been created")
    if ctx.motion_service is None:
        ctx.motion_service = MotionService(robot.motion)
    return ctx.motion_service


def _run_step(
    step: int,
    ctx: RunContext,
    *,
    simulate: bool,
    assume_yes: bool,
    wait_timeout: float,
    out: TextIO,
    prompt: Prompt,
) -> StepResult:
    robot = _ensure_robot(ctx, simulate=simulate)

    if step == 2:
        expected_env = os.environ.get(HARDWARE_ENV_VAR)
        if simulate:
            return _result(2, Status.PASS, f"create_ports() profile is {robot.profile!r}")
        if expected_env != PIDOG_PROFILE:
            return _result(
                2,
                Status.FAIL,
                f"set {HARDWARE_ENV_VAR}=pidog before the hardware run; current value is {expected_env!r}",
            )
        if robot.profile != PIDOG_PROFILE:
            return _result(
                2,
                Status.FAIL,
                f"{HARDWARE_ENV_VAR}=pidog created profile {robot.profile!r}, expected 'pidog'",
            )
        return _result(2, Status.PASS, f"create_ports() profile is {robot.profile!r}")

    if step == 3:
        _pause(
            "Step 3: confirm the dog is supported with legs clear, then sit.",
            assume_yes=assume_yes,
            out=out,
            prompt=prompt,
        )
        robot.motion.do_action("sit", steps=1, speed=50)
        robot.motion.wait_all_done(timeout=wait_timeout)
        return _result(3, Status.PASS, "sit command settled")

    if step == 4:
        _pause(
            "Step 4: watch the head turn right about 30 degrees.",
            assume_yes=assume_yes,
            out=out,
            prompt=prompt,
        )
        robot.motion.move_head(yaw=30, speed=50)
        robot.motion.wait_all_done(timeout=min(wait_timeout, 5.0))
        return _result(4, Status.PASS, "head command settled")

    if step == 5:
        _pause(
            "Step 5: the dog will start a slow forward gait; be ready for stop.",
            assume_yes=assume_yes,
            out=out,
            prompt=prompt,
        )
        robot.motion.do_action("forward", steps=5, speed=30)
        if not simulate:
            time.sleep(0.5)
        robot.motion.stop()
        robot.motion.wait_all_done(timeout=min(wait_timeout, 3.0))
        return _result(5, Status.PASS, "stop requested and motion drained")

    if step == 6:
        _pause(
            "Step 6: place your hand about 20 cm in front of the ultrasonic sensor.",
            assume_yes=assume_yes,
            out=out,
            prompt=prompt,
        )
        distance = robot.sensors.read_distance_cm()
        if distance is None:
            return _result(6, Status.FAIL, "distance_cm is None; ultrasonic echo failed")
        simulated = " (simulated reading)" if simulate else ""
        return _result(6, Status.PASS, f"distance_cm={distance}{simulated}")

    if step == 7:
        expected_reads = (
            ("left pad", TouchState.LEFT),
            ("right pad", TouchState.RIGHT),
            ("both pads", TouchState.BOTH),
        )
        observed: list[str] = []
        for label, expected in expected_reads:
            _pause(
                f"Step 7: touch {label}.",
                assume_yes=assume_yes,
                out=out,
                prompt=prompt,
            )
            actual = robot.sensors.read_touch()
            observed.append(actual.name)
            if actual is not expected:
                return _result(
                    7,
                    Status.FAIL,
                    f"expected {expected.name} for {label}, observed {actual.name}",
                )
        simulated = " (simulated readings)" if simulate else ""
        return _result(7, Status.PASS, f"observed {', '.join(observed)}{simulated}")

    if step == 8:
        _pause(
            "Step 8: hold the dog level for the baseline IMU sample.",
            assume_yes=assume_yes,
            out=out,
            prompt=prompt,
        )
        level = robot.sensors.read_imu()
        _pause(
            "Step 8: tilt the dog gently for the second IMU sample.",
            assume_yes=assume_yes,
            out=out,
            prompt=prompt,
        )
        tilted = robot.sensors.read_imu()
        if tilted.acceleration == level.acceleration:
            return _result(
                8,
                Status.FAIL,
                f"acceleration did not change: level={level.acceleration}, tilted={tilted.acceleration}",
            )
        simulated = " (simulated readings)" if simulate else ""
        return _result(
            8,
            Status.PASS,
            f"level acceleration={level.acceleration}; tilted acceleration={tilted.acceleration}{simulated}",
        )

    if step == 9:
        _pause(
            "Step 9: listen for the bark sound.",
            assume_yes=assume_yes,
            out=out,
            prompt=prompt,
        )
        robot.board.play_sound("single_bark_1", volume=80)
        return _result(9, Status.PASS, "sound command sent")

    if step == 10:
        _pause(
            "Step 10: watch the RGB strip turn blue.",
            assume_yes=assume_yes,
            out=out,
            prompt=prompt,
        )
        # Valid RGB styles are: monochromatic, breath, boom, bark, speak, listen.
        robot.board.set_rgb(
            style="monochromatic",
            color=RgbColor(0, 64, 255),
            brightness=0.5,
            speed=50,
        )
        if not simulate:
            time.sleep(1)
        robot.board.clear_rgb()
        return _result(10, Status.PASS, "RGB set to blue and cleared")

    if step == 11:
        if not simulate and not ctx.camera_import_ok:
            return _result(11, Status.SKIP, ctx.camera_import_message)
        _pause(
            "Step 11: uncover the camera and capture one frame.",
            assume_yes=assume_yes,
            out=out,
            prompt=prompt,
        )
        try:
            if not robot.camera.camera_available():
                return _result(
                    11,
                    Status.SKIP,
                    "camera unavailable: no camera reported by the camera probe",
                )
            robot.camera.start(width=640, height=480)
            frame = robot.camera.capture()
        except HardwareError as error:
            return _result(11, Status.SKIP, f"camera unavailable: {error}")
        return _result(
            11,
            Status.PASS,
            f"frame {frame.width}x{frame.height} {frame.format}, {len(frame.data)} bytes, sequence {frame.sequence}",
        )

    if step == 12:
        return _result(12, Status.PASS, "clean shutdown is reported after safety cleanup")

    motion = _ensure_motion_service(ctx)

    if step == 13:
        _pause(
            "Step 13: confirm the dog is supported with legs clear; the service will sit.",
            assume_yes=assume_yes,
            out=out,
            prompt=prompt,
        )
        motion.sit(speed=50)
        motion.wait_until_idle(timeout=wait_timeout)
        return _result(13, Status.PASS, f"service state settled: {motion.state}")

    if step == 14:
        try:
            motion.trot(steps=1, speed=40)
        except HardwareError as error:
            return _result(14, Status.PASS, f"rejected trot from sit: {error}")
        return _result(14, Status.FAIL, "trot from sitting posture was accepted")

    if step == 15:
        _pause(
            "Step 15a: the service will stand. Clear the area and keep the switch reachable.",
            assume_yes=assume_yes,
            out=out,
            prompt=prompt,
        )
        motion.stand(speed=50)
        motion.wait_until_idle(timeout=wait_timeout)
        _pause(
            "Step 15b: the dog will start a slow forward gait.",
            assume_yes=assume_yes,
            out=out,
            prompt=prompt,
        )
        motion.forward(steps=10, speed=30)
        return _result(15, Status.PASS, f"stood, then issued forward gait: {motion.state}")

    if step == 16:
        try:
            motion.turn_left(steps=1, speed=30)
        except HardwareError as error:
            return _result(16, Status.PASS, f"rejected conflicting turn: {error}")
        return _result(16, Status.FAIL, "conflicting turn was accepted")

    if step == 17:
        _pause(
            "Step 17: stop will pre-empt the gait, then run a second no-op stop.",
            assume_yes=assume_yes,
            out=out,
            prompt=prompt,
        )
        motion.stop()
        motion.stop()
        motion.wait_until_idle(timeout=min(wait_timeout, 3.0))
        return _result(17, Status.PASS, f"stop completed and repeated safely: {motion.state}")

    raise AssertionError(f"unhandled step {step}")


def run_check(
    robot: RobotPorts | None = None,
    *,
    simulate: bool = False,
    assume_yes: bool = False,
    wait_timeout: float = 10.0,
    steps: Iterable[int] = _ALL_STEPS,
    out: TextIO = sys.stdout,
    prompt: Prompt = input,
    after_step: StepHook | None = None,
    import_func: ImportFunc = __import__,
) -> RunResult:
    """Run selected HIL steps and return the PASS/FAIL/SKIP results."""

    selected = tuple(steps)
    ctx = RunContext(robot=robot)
    results: list[StepResult] = []
    print(f"Sparky HIL checklist using profile: {'simulator' if simulate else 'pidog'}", file=out)
    try:
        if 1 in selected:
            step1, ctx.camera_import_ok, ctx.camera_import_message = _check_imports(
                simulate=simulate,
                import_func=import_func,
            )
            results.append(step1)
            _print_step(step1, out)
            if step1.status is Status.FAIL:
                return _finish_results(results, ctx.robot)
        elif simulate:
            ctx.camera_import_ok = False
            ctx.camera_import_message = "simulator run skips optional camera import"

        for step in selected:
            if step in (1, 12):
                continue
            try:
                result = _run_step(
                    step,
                    ctx,
                    simulate=simulate,
                    assume_yes=assume_yes,
                    wait_timeout=wait_timeout,
                    out=out,
                    prompt=prompt,
                )
            except Exception as error:  # noqa: BLE001 - convert step failure into summary.
                result = _result(
                    step,
                    Status.FAIL,
                    f"{type(error).__name__}: {error}",
                )
                results.append(result)
                _print_step(result, out)
                return _finish_results(results, ctx.robot)
            results.append(result)
            _print_step(result, out)
            if result.status is Status.FAIL and step in (2, 3, 4, 5, 9, 10, 13, 15):
                return _finish_results(results, ctx.robot)
            if after_step is not None:
                after_step(step, ctx.robot)
    except KeyboardInterrupt:
        interrupted = StepResult(0, "Interrupted", Status.FAIL, "interrupted by operator")
        results.append(interrupted)
        return RunResult(False, "Sparky HIL checklist interrupted by operator", tuple(results), ctx.robot)
    finally:
        pass
    return _finish_results(results, ctx.robot)


def _finish_results(results: list[StepResult], robot: RobotPorts | None = None) -> RunResult:
    ok = all(result.ok for result in results)
    status = "PASS" if ok else "FAIL"
    return RunResult(ok, f"Sparky HIL checklist {status}", tuple(results), robot)


def safe_shutdown(robot: RobotPorts | None, out: TextIO = sys.stdout) -> StepResult | None:
    """Best-effort safe stop and close, including camera stop and RGB clear."""

    if robot is None:
        return None
    print("Safety cleanup: stopping motion, stopping camera, clearing RGB, and closing ports.", file=out)
    try:
        robot.close()
    except Exception as error:  # noqa: BLE001 - report after cleanup attempt.
        return _result(12, Status.FAIL, f"cleanup reported {type(error).__name__}: {error}")
    return _result(12, Status.PASS, "ports closed; motion stopped, camera stopped, RGB cleared")


def print_summary(results: Iterable[StepResult], out: TextIO = sys.stdout) -> None:
    results = tuple(results)
    print("", file=out)
    print("Summary:", file=out)
    for result in results:
        print(f"  {result.number:>2}. {result.status.value:<4} {result.title}: {result.message}", file=out)
    failures = [result.number for result in results if result.status is Status.FAIL]
    skips = [result.number for result in results if result.status is Status.SKIP]
    if failures:
        print("", file=out)
        print("Triage:", file=out)
        if any(step in failures for step in (1, 2)):
            print("  - Failure in step 1 or 2 is an environment/profile problem on the Pi.", file=out)
        if any(3 <= step <= 10 or step == 12 for step in failures):
            print(
                "  - Failure in steps 3-10 or 12, with simulator tests passing, points at sparky_device/hardware/pidog_adapters.py.",
                file=out,
            )
        if any(13 <= step <= 17 for step in failures):
            print("  - Failure in steps 13-17 points at the MotionService layer or motion adapter interaction.", file=out)
    if 11 in skips:
        print("", file=out)
        print("Camera validation was skipped; this blocks only step 11.", file=out)


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        selected_steps = parse_steps(args.steps)
    except argparse.ArgumentTypeError as error:
        parser.error(str(error))

    robot: RobotPorts | None = None
    run_result = RunResult(False, "Sparky HIL checklist did not complete", ())
    shutdown_result: StepResult | None = None
    exit_code = 1
    try:
        run_result = run_check(
            None,
            simulate=args.simulate,
            assume_yes=args.yes,
            wait_timeout=args.wait_timeout,
            steps=selected_steps,
            out=out,
        )
        robot = run_result.robot
        exit_code = 0 if run_result.ok else 1
    except KeyboardInterrupt:
        interrupt = StepResult(0, "Interrupted", Status.FAIL, "interrupted by operator")
        run_result = RunResult(False, "Sparky HIL checklist interrupted by operator", (interrupt,), robot)
        exit_code = 130
    except Exception as error:  # noqa: BLE001 - CLI reports and exits non-zero.
        failure = StepResult(0, "Unhandled error", Status.FAIL, f"{type(error).__name__}: {error}")
        run_result = RunResult(False, "Sparky HIL checklist FAIL", (failure,), robot)
        exit_code = 1
    finally:
        if robot is not None:
            shutdown_result = safe_shutdown(robot, out=out)

    final_results = list(run_result.results)
    if shutdown_result is not None and 12 in selected_steps:
        final_results = [result for result in final_results if result.number != 12]
        final_results.append(shutdown_result)
        _print_step(shutdown_result, out)
        if shutdown_result.status is Status.FAIL:
            exit_code = 1
    print(run_result.message, file=out)
    print_summary(final_results, out=out)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
