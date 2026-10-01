#!/usr/bin/env python3
"""Hardware-in-the-loop runner for Sparky's microphone capture service.

The script imports cleanly off-robot. Real PiDog and ALSA access happens only
through ``sparky_device.hardware.create_ports(profile="pidog")`` when the
operator chooses the real hardware run. ``--ci`` uses the committed WAV fixture
and the simulated microphone so CI can exercise the same service path without a
robot or vendor packages.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import sys
from typing import Iterable, TextIO


ROOT = Path(__file__).resolve().parents[1]
DEVICE_SRC = ROOT / "src" / "device"
if DEVICE_SRC.exists():
    sys.path.insert(0, str(DEVICE_SRC))

from sparky_device.hardware import (  # noqa: E402
    HARDWARE_ENV_VAR,
    PIDOG_PROFILE,
    RobotPorts,
    SIMULATOR_PROFILE,
    create_ports,
)
from sparky_device.services import AudioBuffer, AudioService, AudioStatus  # noqa: E402


AUDIO_FIXTURE = ROOT / "tests" / "fixtures" / "audio" / "tone-16khz.wav"
DEFAULT_CAPTURE_CHUNKS = 3


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
    """Result returned by the audio HIL runner."""

    ok: bool
    message: str
    results: tuple[StepResult, ...]
    robot: RobotPorts | None = None
    service: AudioService | None = None


@dataclass
class RunContext:
    robot: RobotPorts | None = None
    service: AudioService | None = None
    captures_ok: int = 0
    flushed: AudioBuffer | None = None


_STEP_TITLES = {
    1: "Hardware profile check",
    2: "AudioService start",
    3: "Capture chunks",
    4: "Flush buffer",
    5: "AudioService stop",
    6: "Clean shutdown",
}
_ALL_STEPS = tuple(range(1, 7))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run Sparky's microphone capture service hardware-in-the-loop check. "
            "By default this requires a Raspberry Pi with a PiDog microphone path; "
            "use --simulate to rehearse safely on a laptop."
        )
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Use simulator ports and the committed WAV fixture.",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help=(
            "Run the non-hardware CI harness: simulator microphone, committed "
            "WAV fixture, no prompts, and no vendor imports. Equivalent to --simulate."
        ),
    )
    parser.add_argument(
        "--chunks",
        type=int,
        default=DEFAULT_CAPTURE_CHUNKS,
        help=f"Number of chunks to capture before flushing (default: {DEFAULT_CAPTURE_CHUNKS}).",
    )
    parser.add_argument(
        "--source-id",
        default="sparky-pi-microphone",
        help="Source identifier recorded in the flushed audio buffer.",
    )
    return parser


def make_robot(*, simulate: bool) -> RobotPorts:
    """Build the requested port bundle through the existing hardware factory."""

    if simulate:
        return create_ports(
            profile=SIMULATOR_PROFILE,
            microphone_fixture_path=AUDIO_FIXTURE,
        )
    return create_ports()


def _result(number: int, status: Status, message: str) -> StepResult:
    return StepResult(number, _STEP_TITLES[number], status, message)


def _print_step(result: StepResult, out: TextIO) -> None:
    print(
        f"Step {result.number} {result.status.value}: {result.title} - {result.message}",
        file=out,
    )


def _audio_status_text(status: AudioStatus) -> str:
    return status.value


def _buffer_summary(audio: AudioBuffer) -> str:
    return (
        f"status=ok, sample_rate={audio.sample_rate}, channels={audio.channels}, "
        f"sample_width={audio.sample_width}, chunk_count={audio.chunk_count}, "
        f"duration_seconds={audio.duration_seconds:.3f}, bytes={len(audio.audio_bytes)}"
    )


def _ensure_robot(ctx: RunContext, *, simulate: bool) -> RobotPorts:
    if ctx.robot is None:
        ctx.robot = make_robot(simulate=simulate)
    return ctx.robot


def _ensure_service(ctx: RunContext, *, source_id: str) -> AudioService:
    robot = ctx.robot
    if robot is None:
        raise RuntimeError("robot ports have not been created")
    if robot.microphone is None:
        raise RuntimeError("robot ports do not include a microphone")
    if ctx.service is None:
        ctx.service = AudioService(robot.microphone, source_id=source_id)
    return ctx.service


def _run_step(
    step: int,
    ctx: RunContext,
    *,
    simulate: bool,
    chunks: int,
    source_id: str,
) -> StepResult:
    robot = _ensure_robot(ctx, simulate=simulate)

    if step == 1:
        if simulate:
            expected = "simulator WAV fixture"
            if robot.profile != SIMULATOR_PROFILE:
                return _result(1, Status.FAIL, f"create_ports() profile is {robot.profile!r}, expected simulator")
            if not AUDIO_FIXTURE.is_file():
                return _result(1, Status.FAIL, f"audio fixture missing: {AUDIO_FIXTURE}")
            return _result(1, Status.PASS, f"create_ports() profile is {robot.profile!r}; using {expected}")
        expected_env = os.environ.get(HARDWARE_ENV_VAR)
        if expected_env != PIDOG_PROFILE:
            return _result(
                1,
                Status.FAIL,
                f"set {HARDWARE_ENV_VAR}=pidog before the hardware run; current value is {expected_env!r}",
            )
        if robot.profile != PIDOG_PROFILE:
            return _result(
                1,
                Status.FAIL,
                f"{HARDWARE_ENV_VAR}=pidog created profile {robot.profile!r}, expected 'pidog'",
            )
        return _result(1, Status.PASS, f"create_ports() profile is {robot.profile!r}")

    service = _ensure_service(ctx, source_id=source_id)

    if step == 2:
        state = service.start()
        if state.status is not AudioStatus.OK:
            return _result(2, Status.FAIL, f"status={_audio_status_text(state.status)} detail={state.detail}")
        return _result(
            2,
            Status.PASS,
            f"status={_audio_status_text(state.status)}, running={state.running}, chunk_size_bytes={service.chunk_size_bytes}",
        )

    if step == 3:
        ok_count = 0
        for index in range(chunks):
            capture = service.capture_chunk()
            if capture.status is not AudioStatus.OK:
                return _result(
                    3,
                    Status.FAIL,
                    f"capture {index + 1}/{chunks} status={_audio_status_text(capture.status)} detail={capture.detail}",
                )
            if capture.chunk is None:
                return _result(3, Status.FAIL, f"capture {index + 1}/{chunks} returned no chunk")
            ok_count += 1
        ctx.captures_ok = ok_count
        state = service.state
        return _result(
            3,
            Status.PASS,
            f"captured={ok_count}, buffered_chunks={state.buffered_chunks}, buffered_bytes={state.buffered_bytes}",
        )

    if step == 4:
        flush = service.flush()
        if flush.status is not AudioStatus.OK or flush.audio is None:
            return _result(4, Status.FAIL, f"status={_audio_status_text(flush.status)} detail={flush.detail}")
        ctx.flushed = flush.audio
        if flush.audio.chunk_count < ctx.captures_ok:
            return _result(
                4,
                Status.FAIL,
                f"flush chunk_count={flush.audio.chunk_count}, expected at least {ctx.captures_ok}",
            )
        if ctx.captures_ok and not flush.audio.audio_bytes:
            return _result(4, Status.FAIL, "flush returned empty audio after successful captures")
        return _result(4, Status.PASS, _buffer_summary(flush.audio))

    if step == 5:
        state = service.stop()
        if state.status is not AudioStatus.OK:
            return _result(5, Status.FAIL, f"status={_audio_status_text(state.status)} detail={state.detail}")
        return _result(5, Status.PASS, f"status={_audio_status_text(state.status)}, running={state.running}")

    if step == 6:
        return _result(6, Status.PASS, "clean shutdown is reported after cleanup")

    raise AssertionError(f"unhandled step {step}")


def run_check(
    robot: RobotPorts | None = None,
    *,
    simulate: bool = False,
    chunks: int = DEFAULT_CAPTURE_CHUNKS,
    source_id: str = "sparky-pi-microphone",
    steps: Iterable[int] = _ALL_STEPS,
    out: TextIO = sys.stdout,
) -> RunResult:
    """Run selected audio HIL steps and return the PASS/FAIL/SKIP results."""

    if chunks < 1:
        raise ValueError(f"chunks must be at least 1, got {chunks}")
    selected = tuple(steps)
    ctx = RunContext(robot=robot)
    results: list[StepResult] = []
    print(f"Sparky audio HIL using profile: {'simulator' if simulate else 'pidog'}", file=out)
    try:
        for step in selected:
            if step == 6:
                continue
            try:
                result = _run_step(
                    step,
                    ctx,
                    simulate=simulate,
                    chunks=chunks,
                    source_id=source_id,
                )
            except Exception as error:  # noqa: BLE001 - convert step failure into summary.
                result = _result(step, Status.FAIL, f"{type(error).__name__}: {error}")
                results.append(result)
                _print_step(result, out)
                return _finish_results(results, ctx.robot, ctx.service)
            results.append(result)
            _print_step(result, out)
            if result.status is Status.FAIL:
                return _finish_results(results, ctx.robot, ctx.service)
    except KeyboardInterrupt:
        interrupted = StepResult(0, "Interrupted", Status.FAIL, "interrupted by operator")
        results.append(interrupted)
        return RunResult(False, "Sparky audio HIL interrupted by operator", tuple(results), ctx.robot, ctx.service)
    return _finish_results(results, ctx.robot, ctx.service)


def _finish_results(
    results: list[StepResult],
    robot: RobotPorts | None = None,
    service: AudioService | None = None,
) -> RunResult:
    ok = all(result.ok for result in results)
    status = "PASS" if ok else "FAIL"
    return RunResult(ok, f"Sparky audio HIL {status}", tuple(results), robot, service)


def safe_shutdown(
    robot: RobotPorts | None,
    service: AudioService | None = None,
    out: TextIO = sys.stdout,
) -> StepResult | None:
    """Best-effort microphone stop and port close."""

    if robot is None and service is None:
        return None
    print("Safety cleanup: stopping audio capture and closing ports.", file=out)
    errors: list[BaseException] = []
    if service is not None:
        try:
            service.close()
        except Exception as error:  # noqa: BLE001 - report after cleanup attempt.
            errors.append(error)
    if robot is not None:
        try:
            robot.close()
        except Exception as error:  # noqa: BLE001 - report after cleanup attempt.
            errors.append(error)
    if errors:
        return _result(
            6,
            Status.FAIL,
            "cleanup reported " + "; ".join(f"{type(e).__name__}: {e}" for e in errors),
        )
    return _result(6, Status.PASS, "audio capture stopped and ports closed")


def print_summary(results: Iterable[StepResult], out: TextIO = sys.stdout) -> None:
    results = tuple(results)
    print("", file=out)
    print("Summary:", file=out)
    for result in results:
        print(f"  {result.number:>2}. {result.status.value:<4} {result.title}: {result.message}", file=out)
    failures = [result.number for result in results if result.status is Status.FAIL]
    if failures:
        print("", file=out)
        print("Triage:", file=out)
        if 1 in failures:
            print("  - Failure in step 1 is an environment/profile or fixture problem.", file=out)
        if any(step in failures for step in (2, 3, 4, 5)):
            print("  - Failure in steps 2-5 points at the microphone port, ALSA adapter, or AudioService.", file=out)
        if 6 in failures:
            print("  - Cleanup failure means the operator should confirm the microphone process is stopped.", file=out)


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    simulate = args.simulate or args.ci

    robot: RobotPorts | None = None
    service: AudioService | None = None
    run_result = RunResult(False, "Sparky audio HIL did not complete", ())
    shutdown_result: StepResult | None = None
    exit_code = 1
    try:
        run_result = run_check(
            None,
            simulate=simulate,
            chunks=args.chunks,
            source_id=args.source_id,
            out=out,
        )
        robot = run_result.robot
        service = run_result.service
        exit_code = 0 if run_result.ok else 1
    except KeyboardInterrupt:
        interrupt = StepResult(0, "Interrupted", Status.FAIL, "interrupted by operator")
        run_result = RunResult(False, "Sparky audio HIL interrupted by operator", (interrupt,), robot, service)
        exit_code = 130
    except Exception as error:  # noqa: BLE001 - CLI reports and exits non-zero.
        failure = StepResult(0, "Unhandled error", Status.FAIL, f"{type(error).__name__}: {error}")
        run_result = RunResult(False, "Sparky audio HIL FAIL", (failure,), robot, service)
        exit_code = 1
    finally:
        shutdown_result = safe_shutdown(robot, service, out=out)

    final_results = list(run_result.results)
    if shutdown_result is not None:
        final_results = [result for result in final_results if result.number != 6]
        final_results.append(shutdown_result)
        _print_step(shutdown_result, out)
        if shutdown_result.status is Status.FAIL:
            exit_code = 1
    print(run_result.message, file=out)
    print_summary(final_results, out=out)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
